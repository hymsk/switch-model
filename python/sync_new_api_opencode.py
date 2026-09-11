#!/usr/bin/env python3
"""Generate an OpenCode provider config from a New API model list and OpenCode catalog."""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


DEFAULT_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"
DEFAULT_OPENCODE_MODELS_FILE = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "opencode" / "models.json"
# build.sh defines this before embedding the script. Keeping the source default
# empty lets this module still be used directly with --catalog-file.
try:
    EMBEDDED_OPENCODE_MODELS_GZIP
except NameError:
    EMBEDDED_OPENCODE_MODELS_GZIP = ""

# build.sh injects the single source of truth from the VERSION file. The
# fallback keeps direct source execution working without a build step.
try:
    GENERATOR_VERSION
except NameError:
    GENERATOR_VERSION = "unknown"

EFFORT_LEVELS = ("none", "low", "medium", "high", "xhigh", "max")
MIN_COMPLETE_CATALOG_PROVIDERS = 10
MIN_COMPLETE_CATALOG_ENTRIES = 100
MIN_COMPLETE_CATALOG_LIMIT_RATIO = 0.5
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MODEL_BLOCK_RE = re.compile(r"(?m)^([^\s{}]+)\r?\n(?=\{)")
PROVIDER_TYPE_NPM = {
    "openai-compatible": "@ai-sdk/openai-compatible",
    "bailian": "@ai-sdk/alibaba",
    "dashscope": "@ai-sdk/alibaba",
}

# Catalog providerID -> npm package mapping
CATALOG_PROVIDER_NPM = {
    "alibaba": "@ai-sdk/alibaba",
    "alibaba-cn": "@ai-sdk/alibaba",
    "zhipuai": "@ai-sdk/openai-compatible",
    "zai": "@ai-sdk/openai-compatible",
    "deepseek": "@ai-sdk/deepseek",
    "moonshotai": "@ai-sdk/openai-compatible",
    "moonshotai-cn": "@ai-sdk/openai-compatible",
}


class SyncError(RuntimeError):
    """User-facing deterministic failure."""


@dataclass(frozen=True)
class CatalogEntry:
    full_id: str
    data: Dict[str, Any]

    @property
    def model_id(self) -> str:
        return str(self.data.get("id") or self.full_id.rsplit("/", 1)[-1])

    @property
    def provider_id(self) -> str:
        return str(self.data.get("providerID") or self.full_id.split("/", 1)[0])


@dataclass(frozen=True)
class SourceProvider:
    provider_id: str
    name: str
    base_url: str
    models: List[Dict[str, Any]]
    path: Path


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_context_token(value: str) -> int:
    token = str(value).strip()
    if re.fullmatch(r"[0-9]+[kK]", token):
        return int(token[:-1]) * 1000
    if re.fullmatch(r"[0-9]+", token):
        return int(token)
    raise argparse.ArgumentTypeError("must use a token count such as 258000 or 258k")


def parse_contexts(value: str) -> Tuple[int, ...]:
    text = str(value).strip()
    if not text:
        raise argparse.ArgumentTypeError("must contain at least one context value")
    # Reject thousands separators such as 258,000. After comma became the shared
    # value separator this input would otherwise silently parse as two windows.
    if re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+[kK]?", text):
        raise argparse.ArgumentTypeError(
            "does not accept thousands separators; write 258000 instead of 258,000"
        )
    contexts: List[int] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            raise argparse.ArgumentTypeError("must not contain empty context values")
        context = parse_context_token(token)
        if context not in contexts:
            contexts.append(context)
    return tuple(contexts)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Fetch New API models, match them against the current OpenCode built-in catalog, "
            "and generate or replace provider model metadata."
        )
    )
    parser.add_argument("--base-url", default=os.environ.get("NEWAPI_BASE_URL", ""))
    parser.add_argument("--models-url", default="", help="Override the default <base-url>/v1/models URL")
    model_source = parser.add_mutually_exclusive_group()
    model_source.add_argument("--models-file", type=Path, help="Read a saved /v1/models response instead of HTTP")
    model_source.add_argument(
        "--source-config",
        type=Path,
        help="Read provider ID, baseURL, name, and model IDs from an OpenCode JSON/JSONC config",
    )
    parser.add_argument(
        "--source-provider",
        default="",
        help="Provider ID to extract from --source-config; required only when the config has multiple providers",
    )
    parser.add_argument("--api-key-env", default="NEWAPI_API_KEY")
    parser.add_argument(
        "--auth-file",
        type=Path,
        help="Path to auth.json file for API key lookup; does not omit generated options.apiKey",
    )
    parser.add_argument(
        "--auth-key",
        default="newapi",
        help="Key name in auth.json to lookup API key",
    )
    parser.add_argument(
        "--omit-api-key-option",
        action="store_true",
        help="Do not add options.apiKey to generated OpenCode config (HTTP fetch still uses --api-key-env)",
    )
    parser.add_argument(
        "--api-key-file",
        type=str,
        default=str(Path.home() / ".config" / "api-keys" / "default.sk"),
        help="Write {file:<path>} as options.apiKey reference in generated config (default: ~/.config/api-keys/default.sk)",
    )
    parser.add_argument(
        "--provider",
        default="",
        help="Output OpenCode provider ID; defaults to the source provider ID or MyProvider",
    )
    parser.add_argument(
        "--provider-name",
        default="",
        help="Output display name; defaults to the source provider name or New API",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, help="Write generated standalone config preview")
    parser.add_argument("--report", type=Path, help="Write the detailed matching report")
    parser.add_argument("--mapping-file", type=Path, help="JSON object: New API model ID -> OpenCode full model ID")
    parser.add_argument(
        "--no-prefix-fallback",
        dest="prefix_fallback",
        action="store_false",
        help="Disable metadata-preserving fallback from a custom model suffix to a catalog model ID prefix",
    )
    parser.add_argument("--catalog-file", type=Path, help="Read OpenCode verbose output or parsed catalog JSON")
    parser.add_argument(
        "--opencode-models-file",
        type=Path,
        default=DEFAULT_OPENCODE_MODELS_FILE,
        help="Read the local OpenCode model catalog (default: ~/.cache/opencode/models.json)",
    )
    parser.add_argument(
        "--catalog-mode",
        choices=("all", "current"),
        default="all",
        help="Load all built-in providers or only currently visible providers",
    )
    parser.add_argument(
        "--no-catalog-refresh",
        dest="catalog_refresh",
        action="store_false",
        help="Skip refreshing the local OpenCode model catalog before reading it",
    )
    parser.add_argument(
        "--catalog-refresh-timeout",
        type=float,
        default=180.0,
        help="Timeout in seconds for the OpenCode catalog refresh (default: 180)",
    )
    parser.add_argument("--opencode-bin", default="opencode")
    parser.add_argument("--timeout", type=float, default=20.0, help="New API HTTP timeout in seconds")
    parser.add_argument("--command-timeout", type=float, default=180.0)
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification for New API fetch")
    parser.add_argument(
        "--variant-policy",
        choices=("translate", "compatible", "none"),
        default="translate",
    )
    parser.add_argument(
        "--provider-type",
        choices=("openai-compatible", "bailian", "dashscope", "auto-group"),
        default="auto-group",
        help=(
            "Provider type determines npm package and reasoning format. "
            "'bailian'/'dashscope' use @ai-sdk/alibaba and emit enableThinking/thinkingBudget "
            "provider options instead of reasoningEffort variants. "
            "'auto-group' automatically groups models by catalog providerID."
        ),
    )
    parser.add_argument(
        "--new-api-key",
        default="",
        help="Deprecated insecure CLI key; requires --allow-unsafe-cli-key. Use --api-key-env instead.",
    )
    parser.add_argument(
        "--allow-unsafe-cli-key",
        action="store_true",
        help="Explicitly allow the deprecated --new-api-key value to appear in shell history/process arguments.",
    )
    parser.add_argument("--update-auth", action="store_true", help="Overwrite generated provider keys in auth.json with the active key")
    parser.add_argument("--strict", action="store_true", help="Exit 2 if any model is unmatched or ambiguous")
    parser.add_argument("--write", action="store_true", help="Replace all providers in --config after creating a backup")
    parser.add_argument(
        "--context",
        type=parse_contexts,
        default=(258000,),
        metavar="TOKENS[,TOKENS...]",
        help=(
            "Generate a capped submode for each total context-window limit "
            "(examples: 258000, 258k, 258K, or 258000,128000). "
            "Use 0 to disable capped submodes (default: 258000)"
        ),
    )
    return parser.parse_args(argv)


def normalize_provider_base_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1/models"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
            break
    if not url:
        raise SyncError("--base-url is required (or set NEWAPI_BASE_URL)")
    return url if url.endswith("/v1") else f"{url}/v1"


def resolve_models_url(args: argparse.Namespace, base_url: str) -> str:
    return args.models_url.rstrip("/") if args.models_url else f"{base_url}/models"


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SyncError(f"File not found: {path}") from error
    except json.JSONDecodeError as error:
        raise SyncError(f"Invalid JSON in {path}: {error}") from error
    except OSError as error:
        raise SyncError(f"Failed to read {path}: {error}") from error


def normalize_model_items(payload: Any) -> List[Dict[str, Any]]:
    items = payload if isinstance(payload, list) else payload.get("data", []) if isinstance(payload, dict) else []
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in items:
        model = {"id": item} if isinstance(item, str) else item
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        result.append({**model, "id": model_id})
    if not result:
        raise SyncError("New API model list is empty or has no valid model IDs")
    return result


def get_api_key_from_auth_file(args: argparse.Namespace) -> str:
    """Read API key from auth.json file."""
    if not args.auth_file:
        return ""
    auth_path = args.auth_file.expanduser().resolve()
    try:
        auth_data = load_json_file(auth_path)
    except SyncError:
        return ""
    if not isinstance(auth_data, dict):
        return ""
    provider_data = auth_data.get(args.auth_key, {})
    if isinstance(provider_data, dict):
        return str(provider_data.get("key", ""))
    return ""


def validate_api_key_options(args: argparse.Namespace) -> None:
    """Reject command-line secrets before any preview or write path can run."""
    if args.new_api_key:
        if not args.allow_unsafe_cli_key:
            raise SyncError(
                "--new-api-key is disabled by default because command-line secrets leak to shell history and process lists; "
                "set --api-key-env <ENV_NAME> instead"
            )


def resolve_api_key(args: argparse.Namespace) -> str:
    """Resolve credentials without ever including their value in diagnostics."""
    validate_api_key_options(args)
    if args.new_api_key:
        return args.new_api_key
    return get_api_key_from_auth_file(args) or os.environ.get(args.api_key_env, "")


def fetch_new_api_models(args: argparse.Namespace, models_url: str) -> List[Dict[str, Any]]:
    if args.models_file:
        return normalize_model_items(load_json_file(args.models_file))

    api_key = resolve_api_key(args)
    if not api_key:
        raise SyncError(f"No API key found (auth file or environment variable {args.api_key_env})")

    request = urllib.request.Request(
        models_url,
        headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    context = ssl._create_unverified_context() if args.insecure else None
    try:
        with urllib.request.urlopen(request, timeout=args.timeout, context=context) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise SyncError(f"Failed to fetch model list: HTTP {error.code} from {models_url}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SyncError(f"Failed to fetch model list from {models_url}: {error}") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise SyncError(
            f"Model list response from {models_url} is not valid UTF-8: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise SyncError(f"Failed to parse model list from {models_url}: {error}") from error
    return normalize_model_items(payload)


def run_command(command: List[str], timeout: float, env: Optional[Dict[str, str]] = None) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError as error:
        raise SyncError(f"Command not found: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise SyncError(f"Command timed out after {timeout}s: {' '.join(command)}") from error
    if completed.returncode != 0:
        detail = ANSI_RE.sub("", completed.stderr or completed.stdout).strip().splitlines()
        raise SyncError(f"Command failed ({completed.returncode}): {' '.join(command)}: {detail[-1] if detail else 'no output'}")
    return ANSI_RE.sub("", completed.stdout)


def decode_first_json(text: str, source: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise SyncError(f"No JSON object found in {source}")


def parse_verbose_catalog(text: str) -> List[CatalogEntry]:
    clean = ANSI_RE.sub("", text)
    decoder = json.JSONDecoder()
    entries: List[CatalogEntry] = []
    for match in MODEL_BLOCK_RE.finditer(clean):
        full_id = match.group(1).strip()
        try:
            data, _ = decoder.raw_decode(clean[match.end() :])
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(CatalogEntry(full_id=full_id, data=data))
    if not entries:
        raise SyncError("Could not parse any model blocks from OpenCode verbose output")
    return entries


def catalog_entries_from_json(payload: Any) -> List[CatalogEntry]:
    raw_entries = payload.get("entries", []) if isinstance(payload, dict) else payload
    entries: List[CatalogEntry] = []
    for item in raw_entries if isinstance(raw_entries, list) else []:
        if not isinstance(item, dict):
            continue
        full_id = str(item.get("full_id") or item.get("fullID") or "").strip()
        data = item.get("data") if isinstance(item.get("data"), dict) else item
        if not full_id:
            provider = str(data.get("providerID") or "").strip()
            model_id = str(data.get("id") or "").strip()
            full_id = f"{provider}/{model_id}" if provider and model_id else ""
        if full_id:
            entries.append(CatalogEntry(full_id=full_id, data=data))
    if not entries:
        raise SyncError("Catalog JSON contains no usable entries")
    return entries


def load_catalog_file(path: Path) -> List[CatalogEntry]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise SyncError(f"Catalog file not found: {path}") from error
    try:
        return catalog_entries_from_json(json.loads(text))
    except json.JSONDecodeError:
        return parse_verbose_catalog(text)


def catalog_entries_from_opencode_models(payload: Any) -> List[CatalogEntry]:
    """Normalize OpenCode's local models.json cache to the catalog entry format."""
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, dict):
        providers = payload
    if not isinstance(providers, dict):
        raise SyncError("OpenCode models cache must be a provider object")

    entries: List[CatalogEntry] = []
    for provider_id, provider in providers.items():
        if not isinstance(provider, dict) or not str(provider_id).strip():
            continue
        models = provider.get("models")
        if not isinstance(models, dict):
            continue
        for configured_id, raw_model in models.items():
            if not isinstance(raw_model, dict):
                continue
            model_id = str(raw_model.get("id") or configured_id).strip()
            if not model_id:
                continue

            data = dict(raw_model)
            limit = data.get("limit")
            data["limit"] = dict(limit) if isinstance(limit, dict) else {}
            api = data.get("api")
            data["api"] = dict(api) if isinstance(api, dict) else {}
            capabilities = data.get("capabilities")
            capabilities = dict(capabilities) if isinstance(capabilities, dict) else {}
            for source, target in (
                ("reasoning", "reasoning"),
                ("temperature", "temperature"),
                ("attachment", "attachment"),
                ("tool_call", "toolcall"),
            ):
                if isinstance(data.get(source), bool):
                    capabilities[target] = data[source]
            if isinstance(data.get("interleaved"), dict):
                capabilities["interleaved"] = data["interleaved"]

            variants = data.get("variants")
            variants = dict(variants) if isinstance(variants, dict) else {}
            reasoning_options = data.get("reasoning_options")
            reasoning_options = reasoning_options if isinstance(reasoning_options, list) else []
            data["reasoning_options"] = reasoning_options
            for option in reasoning_options:
                if not isinstance(option, dict) or option.get("type") != "effort":
                    continue
                values = option.get("values", [])
                if not isinstance(values, list):
                    continue
                for effort in values:
                    effort = str(effort).lower()
                    if effort in EFFORT_LEVELS:
                        variants.setdefault(effort, {"reasoningEffort": effort})

            data["id"] = model_id
            data["providerID"] = str(provider_id)
            data["capabilities"] = capabilities
            data["variants"] = variants
            entries.append(CatalogEntry(full_id=f"{provider_id}/{model_id}", data=data))

    if not entries:
        raise SyncError("OpenCode models cache contains no usable entries")
    return entries


def load_opencode_models_catalog(path: Path) -> List[CatalogEntry]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SyncError(f"OpenCode models cache not found: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"Failed to read OpenCode models cache {path}: {error}") from error
    entries = catalog_entries_from_opencode_models(payload)
    # A truncated or partial cache would silently degrade matching while still
    # satisfying a "matched at least one model" check. Rejecting it here routes
    # the caller into the existing embedded/runtime fallback chain.
    validate_complete_catalog(entries, f"local OpenCode models cache {path}")
    return entries


def load_embedded_opencode_models_catalog() -> List[CatalogEntry]:
    """Load the catalog snapshot embedded in the generated switch-model script."""
    if not EMBEDDED_OPENCODE_MODELS_GZIP:
        raise SyncError("No embedded OpenCode model catalog is available")
    try:
        compressed = base64.b64decode(EMBEDDED_OPENCODE_MODELS_GZIP, validate=True)
        payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SyncError(f"Failed to load embedded OpenCode model catalog: {error}") from error
    entries = catalog_entries_from_opencode_models(payload)
    validate_complete_catalog(entries, "embedded OpenCode model catalog")
    return entries


def validate_complete_catalog(entries: List[CatalogEntry], label: str) -> None:
    """Reject fixtures and partial provider catalogs used as complete snapshots."""
    provider_count = len({entry.provider_id for entry in entries})
    limit_count = 0
    for entry in entries:
        limit = entry.data.get("limit")
        if isinstance(limit, dict) and any(
            isinstance(limit.get(key), int) and limit[key] > 0
            for key in ("context", "input", "output")
        ):
            limit_count += 1
    minimum_limits = int(len(entries) * MIN_COMPLETE_CATALOG_LIMIT_RATIO)
    if provider_count < MIN_COMPLETE_CATALOG_PROVIDERS or len(entries) < MIN_COMPLETE_CATALOG_ENTRIES:
        raise SyncError(
            f"{label} is incomplete: {provider_count} providers, {len(entries)} models"
        )
    if limit_count < minimum_limits:
        raise SyncError(
            f"{label} lacks model limits: {limit_count}/{len(entries)} models include usable limits"
        )


def get_opencode_version(args: argparse.Namespace) -> str:
    try:
        return run_command([args.opencode_bin, "--version"], args.command_timeout).strip()
    except SyncError:
        return "unknown"


def refresh_opencode_catalog(args: argparse.Namespace) -> Optional[str]:
    """Refresh the local OpenCode catalog cache before it is read.

    A stale cache silently degrades matching: newly published models resolve to
    ``unmatched`` and ambiguous families stay unresolved. Refreshing first keeps
    matching aligned with the currently published catalog. Failure is reported as
    a warning so an offline run can still fall back to the existing cache.
    """
    if not getattr(args, "catalog_refresh", True):
        return None
    env = os.environ.copy()
    env.pop(args.api_key_env, None)
    env.update({"NO_COLOR": "1", "TERM": "dumb"})
    timeout = getattr(args, "catalog_refresh_timeout", 180.0)
    try:
        run_command(
            [args.opencode_bin, "models", "--refresh", "--pure"],
            timeout,
            env=env,
        )
    except SyncError as error:
        eprint(f"Warning: OpenCode catalog refresh failed; using the existing cache: {error}")
        return None
    return "opencode-models-refresh"


def write_json(path: Path, payload: Any) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise SyncError(f"Failed to write {path}: {error}") from error


def atomic_write_private_json(path: Path, payload: Any) -> None:
    """Atomically write an auth file with owner-only permissions."""
    path = path.expanduser().resolve()
    temporary: Optional[Path] = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise SyncError(f"Failed to securely write auth file {path}: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def catalog_match_count(
    model_ids: Iterable[str],
    entries: List[CatalogEntry],
    mappings: Optional[Dict[str, str]] = None,
    prefix_fallback: bool = True,
) -> int:
    mappings = mappings or {}
    return sum(
        1
        for model_id in model_ids
        if select_entry(model_id, entries, mappings.get(model_id), prefix_fallback)[0] is not None
    )


def acquire_catalog(
    args: argparse.Namespace,
    expected_model_ids: Optional[Iterable[str]] = None,
    mappings: Optional[Dict[str, str]] = None,
) -> Tuple[List[CatalogEntry], Dict[str, Any]]:
    if args.catalog_file:
        entries = load_catalog_file(args.catalog_file)
        return entries, {"source": str(args.catalog_file), "opencode_version": "fixture"}

    version = get_opencode_version(args)
    prefix_fallback = getattr(args, "prefix_fallback", True)

    refresh_marker = refresh_opencode_catalog(args)

    def with_refresh(meta: Dict[str, Any]) -> Dict[str, Any]:
        if refresh_marker:
            meta["catalog_refresh"] = refresh_marker
        return meta

    def load_current() -> Tuple[List[CatalogEntry], Dict[str, Any]]:
        env = os.environ.copy()
        env.pop(args.api_key_env, None)
        env.update({"NO_COLOR": "1", "TERM": "dumb"})
        output = run_command(
            [args.opencode_bin, "models", "--verbose", "--pure"],
            args.command_timeout,
            env=env,
        )
        entries = parse_verbose_catalog(output)
        return entries, {"source": "opencode-current", "opencode_version": version}

    if args.catalog_mode == "current":
        current_entries, current_meta = load_current()
        return current_entries, with_refresh(current_meta)

    try:
        entries = load_opencode_models_catalog(args.opencode_models_file)
    except SyncError as local_error:
        try:
            # Before this script creates the provider config, `opencode models` only
            # exposes the currently configured providers. Use the complete build-time
            # snapshot first so a first run can still match limits and capabilities.
            entries = load_embedded_opencode_models_catalog()
        except SyncError as embedded_error:
            try:
                current_entries, current_meta = load_current()
            except SyncError as current_error:
                raise SyncError(
                    "No OpenCode model catalog is available. "
                    f"Local cache: {local_error}; "
                    f"embedded snapshot: {embedded_error}; "
                    f"runtime query: {current_error}. "
                    "Run `opencode models --refresh --verbose --pure` and retry, "
                    "or provide --catalog-file."
                ) from current_error
            eprint("Warning: OpenCode catalog cache and embedded snapshot are unavailable; using current runtime catalog.")
            return current_entries, with_refresh({**current_meta, "local_cache_error": str(local_error), "embedded_error": str(embedded_error)})
        else:
            expected_ids = list(expected_model_ids or [])
            if expected_ids and catalog_match_count(expected_ids, entries, mappings, prefix_fallback) == 0:
                try:
                    current_entries, current_meta = load_current()
                except SyncError as current_error:
                    eprint(
                        "Warning: embedded catalog matched none of the requested models and runtime catalog was unavailable; "
                        "continuing with the complete embedded snapshot."
                    )
                    return entries, with_refresh({
                        "source": "embedded-opencode-models",
                        "opencode_version": version,
                        "providers": len({entry.provider_id for entry in entries}),
                        "local_cache_error": str(local_error),
                        "runtime_error": str(current_error),
                        "requested_model_matches": 0,
                    })
                current_matches = catalog_match_count(expected_ids, current_entries, mappings, prefix_fallback)
                if current_matches > 0:
                    eprint(
                        "Warning: embedded catalog matched none of the requested models; using the current runtime catalog instead."
                    )
                    return current_entries, with_refresh({
                        **current_meta,
                        "local_cache_error": str(local_error),
                        "embedded_model_matches": 0,
                        "requested_model_matches": current_matches,
                    })
            eprint("Warning: OpenCode catalog cache unavailable; using embedded complete snapshot.")
            return entries, with_refresh({
                "source": "embedded-opencode-models",
                "opencode_version": version,
                "providers": len({entry.provider_id for entry in entries}),
                "local_cache_error": str(local_error),
                "requested_model_matches": catalog_match_count(expected_ids, entries, mappings, prefix_fallback) if expected_ids else None,
            })
    else:
        expected_ids = list(expected_model_ids or [])
        cache_matches = catalog_match_count(expected_ids, entries, mappings, prefix_fallback) if expected_ids else None
        if expected_ids and cache_matches == 0:
            embedded_entries: Optional[List[CatalogEntry]] = None
            embedded_error: Optional[SyncError] = None
            try:
                embedded_entries = load_embedded_opencode_models_catalog()
            except SyncError as error:
                embedded_error = error
            if embedded_entries is not None:
                embedded_matches = catalog_match_count(expected_ids, embedded_entries, mappings, prefix_fallback)
                if embedded_matches > 0:
                    eprint(
                        "Warning: local OpenCode catalog matched none of the requested models; using the embedded complete snapshot instead."
                    )
                    return embedded_entries, with_refresh({
                        "source": "embedded-opencode-models",
                        "opencode_version": version,
                        "cache": str(args.opencode_models_file.expanduser()),
                        "cache_model_matches": 0,
                        "requested_model_matches": embedded_matches,
                        "providers": len({entry.provider_id for entry in embedded_entries}),
                    })
            try:
                current_entries, current_meta = load_current()
            except SyncError as current_error:
                return entries, with_refresh({
                    "source": "opencode-models-cache",
                    "opencode_version": version,
                    "cache": str(args.opencode_models_file.expanduser()),
                    "providers": len({entry.provider_id for entry in entries}),
                    "requested_model_matches": 0,
                    "embedded_error": str(embedded_error) if embedded_error else None,
                    "runtime_error": str(current_error),
                })
            current_matches = catalog_match_count(expected_ids, current_entries, mappings, prefix_fallback)
            if current_matches > 0:
                eprint(
                    "Warning: local OpenCode catalog matched none of the requested models; using the current runtime catalog instead."
                )
                return current_entries, with_refresh({
                    **current_meta,
                    "cache": str(args.opencode_models_file.expanduser()),
                    "cache_model_matches": 0,
                    "requested_model_matches": current_matches,
                })
        return entries, with_refresh({
            "source": "opencode-models-cache",
            "opencode_version": version,
            "cache": str(args.opencode_models_file.expanduser()),
            "providers": len({entry.provider_id for entry in entries}),
            "requested_model_matches": cache_matches,
        })


def normalized_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def strip_provider_prefix(model_id: str) -> str:
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def split_effort_suffix(model_id: str) -> Tuple[str, Optional[str]]:
    match = re.match(r"^(.+)-(none|low|medium|high|xhigh|max)$", model_id, flags=re.IGNORECASE)
    return (match.group(1), match.group(2).lower()) if match else (model_id, None)


def preferred_providers(model_id: str) -> List[str]:
    lowered = strip_provider_prefix(model_id).lower()
    rules = (
        (("gpt-", "chatgpt-", "o1", "o3", "o4", "codex"), ["openai"]),
        (("claude-",), ["anthropic"]),
        (("gemini-", "gemma-"), ["google"]),
        (("glm-", "glm5", "glm4"), ["zhipuai", "zai"]),
        (("deepseek-",), ["deepseek"]),
        (("qwen",), ["alibaba", "alibaba-cn"]),
        (("kimi-",), ["moonshotai", "moonshotai-cn"]),
        (("minimax-",), ["minimax", "minimax-cn"]),
        (("mistral-", "codestral-", "devstral-", "voxtral-"), ["mistral"]),
        (("grok-",), ["xai"]),
        (("command-",), ["cohere"]),
        (("mimo-",), ["xiaomi"]),
        (("step-",), ["stepfun", "stepfun-ai"]),
        (("longcat-",), ["longcat"]),
    )
    # A gateway prefix is not an instruction to trust that reseller's metadata.
    result: List[str] = []
    for prefixes, providers in rules:
        if lowered.startswith(prefixes):
            result.extend(providers)
    result.extend(["alibaba", "alibaba-cn"])
    return list(dict.fromkeys(result))


def provider_preference(model_id: str, entry: CatalogEntry) -> int:
    preferred = preferred_providers(model_id)
    provider = entry.provider_id.lower()
    if provider not in preferred:
        return 0
    # Keep regional defaults stable, with cloud fallback below every origin.
    origins = [item for item in preferred if item not in ("alibaba", "alibaba-cn")]
    if provider in origins:
        return 60 - origins.index(provider) * 10
    return 30 if provider == "alibaba" else 20


def metadata_completeness(entry: CatalogEntry) -> int:
    limit = entry.data.get("limit", {})
    limit = limit if isinstance(limit, dict) else {}
    capabilities = entry.data.get("capabilities", {})
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    variants = entry.data.get("variants", {})
    score = sum(1 for key in ("context", "input", "output") if isinstance(limit.get(key), int) and limit[key] > 0)
    # Explicit false is useful metadata too; reasoning is not a quality score.
    score += sum(isinstance(capabilities.get(key), bool) for key in ("reasoning", "toolcall"))
    score += min(2, len(variants) if isinstance(variants, dict) else 0)
    return score


def score_entry(model_id: str, entry: CatalogEntry) -> Tuple[int, str, Optional[str]]:
    raw = model_id.lower()
    full_id = entry.full_id.lower()
    source_id = entry.model_id.lower()
    api = entry.data.get("api", {})
    api_id = str(api.get("id") or "").lower() if isinstance(api, dict) else ""
    raw_without_provider = strip_provider_prefix(raw)
    explicit_provider = raw.split("/", 1)[0] if "/" in raw else ""
    base_id, effort = split_effort_suffix(raw_without_provider)
    score = 0
    rule = "none"
    if raw == full_id:
        score, rule = 400, "full-id-exact"
    elif raw == source_id:
        score, rule = 400, "model-id-exact"
    elif raw_without_provider == source_id:
        score, rule = 400, "provider-prefix-stripped"
    elif api_id and raw_without_provider == api_id:
        score, rule = 400, "api-id-exact"
    elif normalized_id(raw_without_provider) == normalized_id(source_id):
        score, rule = 300, "normalized-id"
    elif (
        explicit_provider == "zen"
        and entry.provider_id == "opencode"
        and normalized_id(f"{raw_without_provider}-free") == normalized_id(source_id)
    ):
        score, rule = 200, "zen-free-alias"
    elif effort and normalized_id(base_id) == normalized_id(source_id):
        score, rule = 100, "effort-base"
    if not score:
        return 0, rule, effort
    # Identity tiers (100) > source preference (60) > completeness (7) + active (1).
    score += provider_preference(model_id, entry)
    score += metadata_completeness(entry)
    if entry.data.get("status") == "active":
        score += 1
    return score, rule, effort


def find_nested_effort(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ("reasoningEffort", "effort") and str(child).lower() in EFFORT_LEVELS:
                return str(child).lower()
            found = find_nested_effort(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_nested_effort(child)
            if found:
                return found
    return None


ALIBABA_PROVIDER_TYPES = ("bailian", "dashscope")


def alibaba_reasoning_options(entry: CatalogEntry) -> Tuple[Dict[str, Any], List[str]]:
    """Translate Alibaba reasoning_options into @ai-sdk/alibaba provider options.

    Alibaba models describe thinking as a toggle and/or a token budget rather
    than as discrete effort levels, so `reasoningEffort` does not apply. The
    @ai-sdk/alibaba provider accepts `enableThinking` (boolean) and
    `thinkingBudget` (positive integer) instead.
    """
    options = entry.data.get("reasoning_options")
    options = options if isinstance(options, list) else []
    result: Dict[str, Any] = {}
    warnings: List[str] = []
    seen: Set[str] = set()
    for option in options:
        if not isinstance(option, dict):
            continue
        kind = option.get("type")
        if kind in seen:
            continue
        if kind == "toggle":
            seen.add(kind)
            result["enableThinking"] = True
        elif kind == "budget_tokens":
            seen.add(kind)
            budget = option.get("max")
            if isinstance(budget, int) and budget > 0:
                result["thinkingBudget"] = budget
            else:
                result["enableThinking"] = True
                warnings.append(
                    "Alibaba budget_tokens option has no numeric max; "
                    "using enableThinking instead of thinkingBudget"
                )
    if result and not result.get("enableThinking") and "thinkingBudget" in result:
        # A budget alone only takes effect together with thinking enabled.
        result["enableThinking"] = True
    return result, warnings


def convert_variants(entry: CatalogEntry, policy: str, provider_type: str = "openai-compatible") -> Tuple[Dict[str, Any], List[str]]:
    if policy == "none":
        return {}, []
    raw_variants = entry.data.get("variants", {})
    capabilities = entry.data.get("capabilities", {})
    reasoning = bool(capabilities.get("reasoning")) if isinstance(capabilities, dict) else False
    result: Dict[str, Any] = {}
    warnings: List[str] = []
    for name, config in raw_variants.items() if isinstance(raw_variants, dict) else []:
        if not isinstance(config, dict):
            continue
        direct = config.get("reasoningEffort")
        if provider_type in ALIBABA_PROVIDER_TYPES:
            # Alibaba uses enableThinking/thinkingBudget, not effort levels.
            warnings.append(
                f"variant {name} was skipped: @ai-sdk/alibaba does not accept reasoningEffort; "
                "use enableThinking/thinkingBudget provider options"
            )
            continue
        if str(direct).lower() in EFFORT_LEVELS:
            result[name] = {"reasoningEffort": str(direct).lower()}
            continue
        if policy == "compatible":
            warnings.append(f"variant {name} uses provider-private options and was skipped")
            continue
        translated = find_nested_effort(config)
        if not translated and reasoning and name.lower() in EFFORT_LEVELS:
            translated = name.lower()
        if translated:
            result[name] = {"reasoningEffort": translated}
            warnings.append(f"variant {name} was translated to reasoningEffort={translated}")
        else:
            warnings.append(f"variant {name} could not be translated and was skipped")
    return result, warnings


def load_mapping(path: Optional[Path]) -> Dict[str, str]:
    if not path:
        return {}
    payload = load_json_file(path)
    if not isinstance(payload, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in payload.items()):
        raise SyncError("Mapping file must be a JSON object of string model IDs to string OpenCode model IDs")
    return payload


def model_id_segments(value: str) -> List[str]:
    """Split a provider-free model ID into comparable non-empty hyphen segments."""
    return [segment for segment in strip_provider_prefix(value).lower().split("-") if segment]


def prefix_fallback_entries(model_id: str, entries: List[CatalogEntry]) -> List[Tuple[int, int, int, CatalogEntry]]:
    """Find catalog IDs that safely preserve a custom model's family and version prefix."""
    target_segments = model_id_segments(model_id)
    candidates: List[Tuple[int, int, int, CatalogEntry]] = []
    for entry in entries:
        candidate_segments = model_id_segments(entry.model_id)
        if len(candidate_segments) < 2 or len(candidate_segments) >= len(target_segments):
            continue
        if not re.match(r"v?\d", candidate_segments[1]):
            continue
        if target_segments[: len(candidate_segments)] != candidate_segments:
            continue
        provider_rank = -provider_preference(model_id, entry)
        quality = metadata_completeness(entry) + int(entry.data.get("status") == "active")
        candidates.append((len(candidate_segments), provider_rank, quality, entry))
    return candidates


def select_entry(
    model_id: str,
    entries: List[CatalogEntry],
    explicit_mapping: Optional[str],
    prefix_fallback: bool = True,
) -> Tuple[Optional[CatalogEntry], Dict[str, Any]]:
    if explicit_mapping:
        if "/" in explicit_mapping:
            matches = [entry for entry in entries if entry.full_id.lower() == explicit_mapping.lower()]
        else:
            matches = [entry for entry in entries if entry.model_id.lower() == explicit_mapping.lower()]
        if len(matches) == 1:
            return matches[0], {"status": "mapped", "match_rule": "mapping-file", "score": 1000, "candidates": []}
        return None, {
            "status": "unmatched" if not matches else "ambiguous",
            "match_rule": "mapping-file",
            "score": 0,
            "candidates": [entry.full_id for entry in matches[:10]],
            "warnings": [f"mapping target not unique or missing: {explicit_mapping}"],
        }

    # The official V4.1 Flash catalog ID omits the version; user mappings win.
    if strip_provider_prefix(model_id).lower() == "deepseek-v4.1-flash":
        official = next(
            (entry for entry in entries if entry.full_id.lower() == "deepseek/deepseek-flash"),
            None,
        )
        if official is not None:
            return official, {
                "status": "mapped",
                "match_rule": "official-flash-alias",
                "score": 1000,
                "selected": official.full_id,
                "candidates": [],
                "warnings": ["deepseek-v4.1-flash inherits official deepseek-flash metadata; upstream model ID is unchanged"],
            }

    scored: List[Tuple[int, str, Optional[str], CatalogEntry]] = []
    for entry in entries:
        score, rule, effort = score_entry(model_id, entry)
        if score:
            scored.append((score, rule, effort, entry))
    scored.sort(key=lambda item: (-item[0], item[3].full_id))
    if not scored:
        if prefix_fallback:
            fallback = prefix_fallback_entries(model_id, entries)
            if fallback:
                fallback.sort(key=lambda item: (-item[0], item[1], -item[2], item[3].full_id))
                top = fallback[0]
                return top[3], {
                    "status": "guessed",
                    "match_rule": "prefix-fallback",
                    "score": top[0],
                    "prefix_segments": top[0],
                    "candidates": [item[3].full_id for item in fallback[1:4]],
                }
        return None, {"status": "unmatched", "match_rule": "none", "score": 0, "candidates": []}
    top = scored[0]
    tied = [item for item in scored if item[0] == top[0]]
    if len(tied) > 1:
        # Regional/token-plan providers commonly expose identical model metadata.
        # When every tied entry has the same model ID and semantic metadata,
        # selecting the stable first entry is safe and avoids needless ambiguity.
        fingerprints = {
            json.dumps(
                {
                    "id": item[3].model_id.lower(),
                    "limit": positive_limit(item[3].data.get("limit")),
                    "capabilities": item[3].data.get("capabilities", {}),
                    "variants": item[3].data.get("variants", {}),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            for item in tied
        }
        if len(fingerprints) == 1:
            return top[3], {
                "status": "matched",
                "match_rule": f"{top[1]}-equivalent-metadata",
                "score": top[0],
                "effort_suffix": top[2],
                "candidates": [item[3].full_id for item in tied[1:4]],
                "warnings": ["equivalent metadata was available from multiple catalog providers; selected deterministically"],
            }
        # Ties carry genuinely different metadata. Limits differ across resellers,
        # so no candidate is authoritative; inherit the stable first candidate
        # instead of dropping limits entirely. The report keeps the competing
        # candidates and an ambiguity warning so `--strict` and manual review can
        # still spot the fallback.
        return top[3], {
            "status": "ambiguous",
            "match_rule": f"{top[1]}-first-candidate",
            "score": top[0],
            "effort_suffix": top[2],
            "candidates": [item[3].full_id for item in tied[:10]],
            "selected": top[3].full_id,
            "warnings": [
                "multiple catalog models have the same best score; "
                f"selected the first candidate {top[3].full_id}; use --mapping-file to pin a specific source"
            ],
        }
    return top[3], {
        "status": "matched",
        "match_rule": top[1],
        "score": top[0],
        "effort_suffix": top[2],
        "candidates": [item[3].full_id for item in scored[1:4]],
    }


def positive_limit(data: Any) -> Dict[str, int]:
    """Extract positive context, input, and output limits from catalog data."""
    if not isinstance(data, dict):
        return {}
    result = {}
    for key in ("context", "input", "output"):
        value = data.get(key)
        if isinstance(value, int) and value > 0:
            result[key] = int(value)
    return result


def apply_context_cap(limit: Dict[str, int], context: int) -> Dict[str, int]:
    """Cap the total context window without expanding any catalog limit."""
    if context <= 0:
        return dict(limit)
    result = dict(limit)
    result["context"] = min(result.get("context", context), context)
    if "input" in result:
        result["input"] = min(result["input"], result["context"])
    if "output" in result:
        result["output"] = min(result["output"], result["context"])
    return result


def context_suffix(context: int) -> str:
    value = f"{context // 1000}k" if context % 1000 == 0 else str(context)
    return f" ({value})"


def model_config_from_entry(
    new_model: Dict[str, Any],
    entry: Optional[CatalogEntry],
    match: Dict[str, Any],
    variant_policy: str,
    provider_type: str = "openai-compatible",
    contexts: Tuple[int, ...] = (258000,),
) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Generate the original model plus each applicable capped context submode."""
    model_id = str(new_model["id"])
    name = model_id
    config: Dict[str, Any] = {"name": name}
    report = {"model_id": model_id, **match, "source_model": entry.full_id if entry else None}
    warnings = list(match.get("warnings", []))
    results: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []

    if not entry:
        report["warnings"] = warnings
        results.append((model_id, config, report))
        return results

    limit = positive_limit(entry.data.get("limit"))
    if limit:
        config["limit"] = limit
    capabilities = entry.data.get("capabilities", {})
    if isinstance(capabilities, dict):
        for source, target in (
            ("reasoning", "reasoning"),
            ("temperature", "temperature"),
            ("attachment", "attachment"),
            ("toolcall", "tool_call"),
        ):
            if isinstance(capabilities.get(source), bool):
                config[target] = capabilities[source]
        # Copy interleaved field if present (used for reasoning_content parsing)
        interleaved = capabilities.get("interleaved")
        if isinstance(interleaved, dict) and "field" in interleaved:
            config["interleaved"] = interleaved
    variants, variant_warnings = convert_variants(entry, variant_policy, provider_type)
    if variants and not match.get("effort_suffix"):
        config["variants"] = variants
    elif variants and match.get("effort_suffix"):
        warnings.append("effort-specific upstream model keeps base limits but does not expose nested variants")
    warnings.extend(variant_warnings)
    if provider_type in ALIBABA_PROVIDER_TYPES:
        alibaba_options, alibaba_warnings = alibaba_reasoning_options(entry)
        if alibaba_options:
            config["options"] = {**config.get("options", {}), **alibaba_options}
        warnings.extend(alibaba_warnings)
    report.update({
        "limit": limit,
        "reasoning": config.get("reasoning"),
        "variants": sorted(config.get("variants", {})),
        "provider_options": sorted(config.get("options", {})),
        "warnings": warnings,
    })

    # Add original version
    results.append((model_id, config, report))

    original_context = limit.get("context", 0)
    for context in contexts:
        if context <= 0 or original_context <= context:
            continue
        capped_model_id = model_id + context_suffix(context)
        capped_config = copy.deepcopy(config)
        capped_config["name"] = capped_model_id  # 显示名称带后缀
        capped_config["id"] = model_id  # 保持原始模型 ID 用于 API 调用
        capped_config["limit"] = apply_context_cap(limit, context)

        capped_report = copy.deepcopy(report)
        capped_report["model_id"] = capped_model_id
        capped_report["capped_from"] = model_id
        capped_report["limit"] = capped_config["limit"]
        capped_report["warnings"] = warnings + [f"context window capped from {original_context} to {context}"]

        results.append((capped_model_id, capped_config, capped_report))

    return results


def get_npm_for_catalog_provider(provider_id: str, fallback: str = "@ai-sdk/openai-compatible") -> str:
    """Get npm package for a catalog providerID."""
    return CATALOG_PROVIDER_NPM.get(provider_id, fallback)


def infer_provider_from_model_name(model_id: str) -> str:
    """Infer catalog providerID from model name when no catalog match found."""
    # Strip provider prefix (e.g., "SiliconFlow/DeepSeek-V3.2" -> "deepseek-v3.2")
    model_name = strip_provider_prefix(model_id).lower()
    explicit_provider = model_id.split("/", 1)[0].lower() if "/" in model_id else ""

    rules = [
        (("qwen",), "alibaba"),
        (("deepseek-",), "deepseek"),
        (("glm-", "glm5", "glm4"), "zhipuai"),
        (("kimi-",), "moonshotai"),
        (("minimax-",), "minimax"),
        (("mistral-", "codestral-", "devstral-"), "mistral"),
        (("grok-",), "xai"),
        (("claude-",), "anthropic"),
        (("gemini-", "gemma-"), "google"),
        (("gpt-", "chatgpt-", "o1", "o3", "o4"), "openai"),
        (("mimo-",), "xiaomi"),
    ]
    for prefixes, provider in rules:
        if model_name.startswith(prefixes):
            return provider

    # Handle zen/ prefix -> opencode provider (only if no specific model type matched)
    if explicit_provider == "zen":
        return "opencode"

    return "openai-compatible"


def group_models_by_provider(
    models: List[Dict[str, Any]],
    entries: List[CatalogEntry],
    mappings: Dict[str, str],
    prefix_fallback: bool = True,
) -> Dict[str, List[Tuple[Dict[str, Any], Optional[CatalogEntry], Dict[str, Any]]]]:
    """Group models by their matched catalog providerID."""
    groups: Dict[str, List[Tuple[Dict[str, Any], Optional[CatalogEntry], Dict[str, Any]]]] = {}
    for model in models:
        model_id = str(model["id"])
        entry, match = select_entry(model_id, entries, mappings.get(model_id), prefix_fallback)
        # Matched models use the catalog providerID so the npm package matches what
        # OpenCode declares for that model. Only unmatched models fall back to a
        # name-based guess so they still land in a sensible group.
        provider_id = entry.provider_id if entry else infer_provider_from_model_name(model_id)
        groups.setdefault(provider_id, []).append((model, entry, match))
    return groups


def get_api_key_reference(args: argparse.Namespace) -> Optional[str]:
    """Return the explicit config credential reference unless --omit-api-key-option is used."""
    if args.api_key_file:
        return "{file:" + args.api_key_file + "}"
    return f"{{env:{args.api_key_env}}}"


def build_provider_fragment(
    args: argparse.Namespace,
    base_url: str,
    models: List[Dict[str, Any]],
    entries: List[CatalogEntry],
    mappings: Dict[str, str],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    generated: Dict[str, Any] = {}
    reports: List[Dict[str, Any]] = []
    api_key_ref = get_api_key_reference(args)

    contexts = args.context

    if args.provider_type != "auto-group":
        # Single-provider mode: openai-compatible / bailian / dashscope all produce one
        # provider keyed by args.provider. Only --provider-type auto-group splits models
        # into multiple providers by their matched catalog providerID.
        for model in models:
            model_id = str(model["id"])
            entry, match = select_entry(model_id, entries, mappings.get(model_id), args.prefix_fallback)
            results = model_config_from_entry(
                model,
                entry,
                match,
                args.variant_policy,
                args.provider_type,
                contexts,
            )
            for mid, config, report in results:
                generated[mid] = config
                reports.append(report)
        provider_options = {"baseURL": base_url}
        if not args.omit_api_key_option and api_key_ref is not None:
            provider_options["apiKey"] = api_key_ref
        npm_package = PROVIDER_TYPE_NPM.get(args.provider_type, "@ai-sdk/openai-compatible")
        fragment = {
            "$schema": "https://opencode.ai/config.json",
            "provider": {
                args.provider: {
                    "name": args.provider_name,
                    "npm": npm_package,
                    "options": provider_options,
                    "models": generated,
                }
            },
        }
        return fragment, reports

    # Auto-group mode: group by catalog providerID
    groups = group_models_by_provider(models, entries, mappings, args.prefix_fallback)

    providers: Dict[str, Any] = {}
    for group_provider_id, group_models in groups.items():
        npm_package = get_npm_for_catalog_provider(group_provider_id)
        group_generated: Dict[str, Any] = {}
        for model, entry, match in group_models:
            model_id = str(model["id"])
            results = model_config_from_entry(
                model,
                entry,
                match,
                args.variant_policy,
                "openai-compatible",
                contexts,
            )
            for mid, config, report in results:
                group_generated[mid] = config
                reports.append(report)

        provider_options = {"baseURL": base_url}
        if not args.omit_api_key_option and api_key_ref is not None:
            provider_options["apiKey"] = api_key_ref

        provider_name = args.provider_name or f"MyProvider ({group_provider_id})"
        if len(groups) == 1:
            provider_name = args.provider_name or "MyProvider"
            provider_id = args.provider
        else:
            # Use prefix like "MyProvider-alibaba", "MyProvider-deepseek"
            base_name = args.provider if args.provider != "MyProvider" else "MyProvider"
            provider_id = f"{base_name}-{group_provider_id}"

        providers[provider_id] = {
            "name": provider_name,
            "npm": npm_package,
            "options": provider_options,
            "models": group_generated,
        }

    fragment = {
        "$schema": "https://opencode.ai/config.json",
        "provider": providers,
    }
    return fragment, reports


def strip_jsonc(text: str) -> str:
    output: List[str] = []
    in_string = False
    escaped = False
    line_comment = False
    block_comment = False
    index = 0
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
                output.append(char)
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            output.append(char)
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = True
            index += 1
        else:
            output.append(char)
        index += 1
    stripped = "".join(output)
    result: List[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(stripped):
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            result.append(char)
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(stripped) and stripped[lookahead].isspace():
                lookahead += 1
            if lookahead < len(stripped) and stripped[lookahead] in "}]":
                continue
        result.append(char)
    return "".join(result)


def read_existing_config(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    try:
        payload = json.loads(strip_jsonc(text))
    except json.JSONDecodeError as error:
        raise SyncError(f"Failed to parse existing JSON/JSONC config {path}: {error}") from error
    if not isinstance(payload, dict):
        raise SyncError(f"Existing config must be a JSON object: {path}")
    return payload


def load_source_provider(path: Path, requested_provider: str = "") -> SourceProvider:
    source_path = path.expanduser().resolve()
    if not source_path.is_file():
        raise SyncError(f"Source config not found: {source_path}")
    payload = read_existing_config(source_path)
    providers = payload.get("provider")
    if not isinstance(providers, dict) or not providers:
        raise SyncError(f"Source config has no provider object: {source_path}")

    candidates = sorted(provider_id for provider_id, value in providers.items() if isinstance(value, dict))
    if requested_provider:
        provider_id = requested_provider
        if provider_id not in candidates:
            available = ", ".join(candidates) or "none"
            raise SyncError(f"Provider {provider_id!r} not found in source config; available: {available}")
    elif len(candidates) == 1:
        provider_id = candidates[0]
    elif len(candidates) > 1:
        available = ", ".join(candidates)
        raise SyncError(f"Source config has multiple providers ({available}); select one with --source-provider")
    else:
        raise SyncError(f"Source config has no valid provider entries: {source_path}")

    provider = providers[provider_id]
    options = provider.get("options") if isinstance(provider.get("options"), dict) else {}
    models = provider.get("models")
    if not isinstance(models, dict) or not models:
        raise SyncError(f"Source provider {provider_id!r} has no models object")
    model_items = normalize_model_items([
        {
            "id": str(model_id),
            "name": str(model_config.get("name") or model_id) if isinstance(model_config, dict) else str(model_id),
        }
        for model_id, model_config in models.items()
    ])
    return SourceProvider(
        provider_id=provider_id,
        name=str(provider.get("name") or provider_id),
        base_url=str(options.get("baseURL") or ""),
        models=model_items,
        path=source_path,
    )


def resolve_model_source(args: argparse.Namespace) -> Tuple[str, str, List[Dict[str, Any]]]:
    if args.source_provider and not args.source_config:
        raise SyncError("--source-provider requires --source-config")
    if args.source_config:
        source = load_source_provider(args.source_config, args.source_provider)
        args.provider = args.provider or source.provider_id
        args.provider_name = args.provider_name or source.name
        base_url = normalize_provider_base_url(args.base_url or source.base_url)
        return base_url, f"source-config:{source.path}", source.models

    args.provider = args.provider or "MyProvider"
    args.provider_name = args.provider_name or "MyProvider"
    base_url = normalize_provider_base_url(args.base_url)
    models_url = resolve_models_url(args, base_url)
    return base_url, models_url, fetch_new_api_models(args, models_url)


def replace_provider_config(existing: Dict[str, Any], fragment: Dict[str, Any]) -> Dict[str, Any]:
    fragment_providers = fragment.get("provider")
    if not isinstance(fragment_providers, dict):
        raise SyncError("Generated configuration has no provider object")
    result = copy.deepcopy(existing)
    result.setdefault("$schema", "https://opencode.ai/config.json")
    result["provider"] = copy.deepcopy(fragment_providers)
    return result


def atomic_write_config(path: Path, payload: Dict[str, Any]) -> Optional[Path]:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    backup: Optional[Path] = None
    original_mode = None
    if path.exists():
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = path.with_name(f"{path.name}.bak-{timestamp}")
        shutil.copy2(path, backup)
        original_mode = path.stat().st_mode
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    if original_mode is not None:
        os.chmod(temporary, original_mode)
    os.replace(temporary, path)
    return backup


def make_report(
    args: argparse.Namespace,
    model_source: str,
    model_count: int,
    catalog_meta: Dict[str, Any],
    entries: List[CatalogEntry],
    model_reports: List[Dict[str, Any]],
) -> Dict[str, Any]:
    source_reports = [item for item in model_reports if "capped_from" not in item]
    counts = {
        status: sum(1 for item in source_reports if item["status"] == status)
        for status in ("matched", "mapped", "guessed", "ambiguous", "unmatched")
    }
    provider_groups: Dict[str, int] = {}
    for report in source_reports:
        source = report.get("source_model", "")
        if source and "/" in source:
            pid = source.split("/", 1)[0]
            provider_groups[pid] = provider_groups.get(pid, 0) + 1
    return {
        "generator": "switch-model",
        "generator_version": GENERATOR_VERSION,
        "generated_at": utc_now(),
        "new_api": {"model_source": model_source, "model_count": model_count, "api_key_env": args.api_key_env},
        "catalog": {**catalog_meta, "entry_count": len(entries)},
        "provider": args.provider,
        "provider_groups": provider_groups,
        "variant_policy": args.variant_policy,
        "contexts": list(args.context),
        "summary": counts,
        "models": model_reports,
    }


def update_auth_file(auth_path: Path, provider_ids: List[str], api_key: str) -> None:
    """Overwrite generated provider keys in auth.json with the active key."""
    auth_path = auth_path.expanduser().resolve()
    if auth_path.exists():
        auth_data = load_json_file(auth_path)
        if not isinstance(auth_data, dict):
            raise SyncError(f"Auth file must be a JSON object: {auth_path}")
    else:
        auth_data = {}
    for pid in sorted(set(provider_ids)):
        entry = auth_data.get(pid)
        if isinstance(entry, dict):
            entry["key"] = api_key
        else:
            auth_data[pid] = {"type": "api", "key": api_key}
    atomic_write_private_json(auth_path, auth_data)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        validate_api_key_options(args)
        if args.insecure:
            eprint("Warning: --insecure disables TLS verification; use it only for a deliberately trusted local test endpoint.")
        if args.new_api_key:
            eprint("Warning: --new-api-key is deprecated; migrate to --api-key-env before the next release.")
        base_url, model_source, models = resolve_model_source(args)
        mappings = load_mapping(args.mapping_file)
        entries, catalog_meta = acquire_catalog(
            args,
            (str(model["id"]) for model in models),
            mappings,
        )
        fragment, model_reports = build_provider_fragment(args, base_url, models, entries, mappings)
        report = make_report(args, model_source, len(models), catalog_meta, entries, model_reports)
        if args.output:
            write_json(args.output, fragment)
        if args.report:
            write_json(args.report, report)
        backup = None
        if args.write:
            existing = read_existing_config(args.config.expanduser())
            updated_config = replace_provider_config(existing, fragment)
            backup = atomic_write_config(args.config, updated_config)
        if not args.output and not args.write:
            print(json.dumps(fragment, ensure_ascii=False, indent=2))
        summary = report["summary"]
        eprint(
            "New API models: {total}; matched: {matched}; mapped: {mapped}; guessed: {guessed}; ambiguous: {ambiguous}; unmatched: {unmatched}".format(
                total=len(models), **summary
            )
        )
        eprint(f"Catalog: {catalog_meta.get('source')} ({len(entries)} entries), OpenCode {catalog_meta.get('opencode_version')}")
        provider_groups = report.get("provider_groups", {})
        if provider_groups:
            groups_str = ", ".join(f"{pid}: {count}" for pid, count in sorted(provider_groups.items()))
            eprint(f"Provider groups: {groups_str}")
        if args.output:
            eprint(f"Preview: {args.output.expanduser().resolve()}")
        if args.report:
            eprint(f"Report: {args.report.expanduser().resolve()}")
        if args.write:
            eprint(f"Config updated: {args.config.expanduser().resolve()}")
            if backup:
                eprint(f"Backup: {backup}")
        if args.update_auth:
            active_key = resolve_api_key(args)
            if not active_key:
                eprint("Warning: --update-auth skipped, no API key available")
            else:
                auth_path = args.auth_file or (Path.home() / ".local" / "share" / "opencode" / "auth.json")
                provider_ids = sorted(fragment.get("provider", {}).keys())
                update_auth_file(auth_path, provider_ids, active_key)
                eprint(f"Auth updated: {auth_path.expanduser().resolve()} ({len(provider_ids)} providers)")
        incomplete = summary["ambiguous"] + summary["unmatched"]
        return 2 if args.strict and incomplete else 0
    except SyncError as error:
        eprint(f"Error: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
