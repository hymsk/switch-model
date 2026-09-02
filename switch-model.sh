#!/bin/bash
# Auto-generated file. Do not edit manually.
# Run bash build.sh to regenerate.
#
# Switch Model - 模型切换脚本
#
# 功能说明：
#   - 从 sk 文件读取 API Key，自动写入 Claude Code / Codex / OpenCode 配置文件
#   - 支持 Claude Code、Codex、OpenCode 三种工具模式
#   - 自动从 API 获取可用模型列表并选择
#   - 自动创建 ~/.config/api-keys/ 目录及保护文件
#
# 支持平台: Linux / macOS / Windows (Git Bash / WSL)
# 运行依赖: Python 3、curl
#
# 使用方法:
#   bash switch-model.sh <claude|codex|opencode> <url> [model] [--sk-filename <name>] [--sk-file <path>]
#
# 示例:
#   bash switch-model.sh claude https://api.example.com
#   bash switch-model.sh codex https://api.example.com --sk-filename work.sk
#   bash switch-model.sh opencode https://api.example.com --preview

set -euo pipefail
umask 077

# ==================== 嵌入的 Python 脚本 ====================
# 以下 Python 代码由 build.sh 从 python/ 目录嵌入


# Python 脚本: claude_update.py
python_claude_update() {
    local python_cmd=$(get_python_cmd)
    "$python_cmd" - "$@" << 'PYEOF'
# -*- coding: utf-8 -*-
"""更新 Claude Code 配置文件"""
import json, os, sys

def main():
    try:
        filepath = os.environ['SWITCH_MODEL_FILE']
        url = os.environ['SWITCH_MODEL_BASE_URL']
        sk = os.environ['SWITCH_MODEL_API_KEY']
        model = os.environ['SWITCH_MODEL_NAME']
        with open(filepath, 'r') as f:
            data = json.load(f)
        data.setdefault('env', {})['ANTHROPIC_BASE_URL'] = url
        data['env']['ANTHROPIC_AUTH_TOKEN'] = sk
        data['model'] = model
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write('\n')
        sys.exit(0)
    except Exception as e:
        sys.stderr.write('Error: ' + str(e) + '\n')
        sys.exit(1)

if __name__ == "__main__":
    main()

PYEOF
}

# Python 脚本: codex_auth.py
python_codex_auth() {
    local python_cmd=$(get_python_cmd)
    "$python_cmd" - "$@" << 'PYEOF'
# -*- coding: utf-8 -*-
"""更新 Codex 认证文件"""
import json, os, sys, tempfile

def main():
    try:
        sk = os.environ['SWITCH_MODEL_API_KEY']
        filepath = os.environ['SWITCH_MODEL_AUTH_PATH']

        # 确保目录存在
        directory = os.path.dirname(filepath)
        if not os.path.isdir(directory):
            os.makedirs(directory)

        data = {
            "auth_mode": "apikey",
            "OPENAI_API_KEY": sk
        }
        fd, temporary = tempfile.mkstemp(prefix='.auth.', dir=directory)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
            os.chmod(temporary, 0o600)
            os.replace(temporary, filepath)
            os.chmod(filepath, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        print('Codex auth updated: {0}'.format(filepath))
        sys.exit(0)
    except Exception as e:
        sys.stderr.write('Error: ' + str(e) + '\n')
        sys.exit(1)

if __name__ == "__main__":
    main()

PYEOF
}

# Python 脚本: codex_config.py
python_codex_config() {
    local python_cmd=$(get_python_cmd)
    "$python_cmd" - "$@" << 'PYEOF'
# -*- coding: utf-8 -*-
"""更新 Codex 配置文件"""
import os, sys, tempfile

def write_bytes_atomically(filepath, content):
    """原子写入文件"""
    directory = os.path.dirname(filepath)
    fd, temporary = tempfile.mkstemp(prefix='.config.', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, filepath)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise

def main():
    try:
        url, model, filepath = sys.argv[1], sys.argv[2], sys.argv[3]

        # 确保目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # 如果文件不存在，创建默认配置（使用 LF 换行符）
        if not os.path.exists(filepath):
            default_config = 'model_provider = "newapi"\n'
            default_config += 'model = "{model}"\n'
            default_config += 'model_reasoning_effort = "high"\n'
            default_config += 'disable_response_storage = true\n'
            default_config += 'personality = "pragmatic"\n'
            default_config += '\n'
            default_config += '[model_providers.newapi]\n'
            default_config += 'name = "NewAPI"\n'
            default_config += 'base_url = "{url}/v1"\n'
            default_config += 'wire_api = "responses"\n'
            default_config += 'requires_openai_auth = true\n'
            default_config = default_config.format(model=model, url=url)
            write_bytes_atomically(filepath, default_config.encode('utf-8'))
            print('Created: model={0}, base_url={1}'.format(model, url))
            sys.exit(0)

        # 读取现有配置（统一换行符为 LF）
        with open(filepath, 'rb') as f:
            raw = f.read()
        # 将 CRLF 和 CR 统一为 LF
        content = raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        lines = content.decode('utf-8').split('\n')

        # 更新配置
        new_lines = []
        in_newapi_section = False
        model_provider_updated = False
        model_updated = False
        base_url_updated = False

        for line in lines:
            stripped = line.strip()

            # 更新 model_provider 行
            if stripped.startswith('model_provider = ') and not model_provider_updated:
                new_lines.append('model_provider = "newapi"')
                model_provider_updated = True
                continue

            # 更新 model 行
            if stripped.startswith('model = ') and not model_updated:
                new_lines.append('model = "{0}"'.format(model))
                model_updated = True
                continue

            # 进入 newapi section
            if stripped.startswith('[model_providers.newapi]'):
                in_newapi_section = True
                new_lines.append(line)
                continue

            # 在 newapi section 中更新 base_url
            if in_newapi_section and stripped.startswith('base_url = ') and not base_url_updated:
                new_lines.append('base_url = "{0}/v1"'.format(url))
                base_url_updated = True
                continue

            # 离开 newapi section
            if in_newapi_section and stripped.startswith('[') and not stripped.startswith('[model_providers.newapi]'):
                in_newapi_section = False

            new_lines.append(line)

        if not model_provider_updated:
            new_lines.insert(0, 'model_provider = "newapi"')
        if not model_updated:
            insert_at = 1 if new_lines and new_lines[0].startswith('model_provider = ') else 0
            new_lines.insert(insert_at, 'model = "{0}"'.format(model))
        if not base_url_updated:
            if new_lines and new_lines[-1] != '':
                new_lines.append('')
            if not any(line.strip() == '[model_providers.newapi]' for line in new_lines):
                new_lines.extend([
                    '[model_providers.newapi]',
                    'name = "NewAPI"',
                    'base_url = "{0}/v1"'.format(url),
                    'wire_api = "responses"',
                    'requires_openai_auth = true',
                ])
            else:
                section_index = next(
                    index
                    for index, line in enumerate(new_lines)
                    if line.strip() == '[model_providers.newapi]'
                )
                new_lines.insert(section_index + 1, 'base_url = "{0}/v1"'.format(url))

        # 写回文件，使用 LF 换行符（TOML 标准）
        write_bytes_atomically(filepath, '\n'.join(new_lines).encode('utf-8'))

        print('Updated: model={0}, base_url={1}'.format(model, url))
        sys.exit(0)
    except Exception as e:
        sys.stderr.write('Error: ' + str(e) + '\n')
        sys.exit(1)

if __name__ == "__main__":
    main()

PYEOF
}

# Python 脚本: sync_new_api_opencode.py
python_sync_new_api_opencode() {
    local python_cmd=$(get_python_cmd)
    "$python_cmd" - "$@" << 'PYEOF'
#!/usr/bin/env python3
"""Generate an OpenCode provider config from a New API model list and OpenCode catalog."""

from __future__ import annotations
EMBEDDED_OPENCODE_MODELS_GZIP = 'H4sIAAAAAAAC/22Pyw7CIBBF93xF03WNj7gwrlzowp2/QOnETASGFGqaNP13oS8pyoLHPTf3Dh3LstzU9MYKapufs84LXoKWKyNhEbyElX8toJhlzVWw5bcRZI8pLHIYFQwXjhtbvbZkQPurIGW4wzLOUlSBtFHpd5LNwFYonWmyFLFh/tr9+m/4wSJRoUuCvSxIO2gDOO7CKtaYGmeaQPeHk6cR7FfpghteokSHYH9LauCWNOqnR65uIClxRFJwKScal7D0Np5h71nPPgIqT9PYAQAA'

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

EFFORT_LEVELS = ("none", "low", "medium", "high", "xhigh", "max")
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


def parse_contexts(value: str) -> Tuple[int, ...]:
    raw_values = [item.strip() for item in str(value).split(",")]
    if not raw_values or any(not item or not re.fullmatch(r"[0-9]+", item) for item in raw_values):
        raise argparse.ArgumentTypeError("must be a comma-separated list of non-negative integers")

    contexts: List[int] = []
    seen: Set[int] = set()
    for item in raw_values:
        context = int(item)
        if context not in seen:
            seen.add(context)
            contexts.append(context)
    if 0 in seen and len(seen) > 1:
        raise argparse.ArgumentTypeError("0 cannot be combined with other context values")
    return tuple(contexts)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
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
        help="Output OpenCode provider ID; defaults to the source provider ID or newapi",
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
            "'bailian'/'dashscope' use @ai-sdk/alibaba with enableThinking instead of reasoningEffort. "
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
            "Generate one capped submode for each comma-separated total context-window limit below the model limit. "
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
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SyncError(f"Failed to fetch model list: HTTP {error.code} from {models_url}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise SyncError(f"Failed to fetch or parse model list from {models_url}: {error}") from error
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
    return catalog_entries_from_opencode_models(payload)


def load_embedded_opencode_models_catalog() -> List[CatalogEntry]:
    """Load the catalog snapshot embedded in the generated switch-model script."""
    if not EMBEDDED_OPENCODE_MODELS_GZIP:
        raise SyncError("No embedded OpenCode model catalog is available")
    try:
        compressed = base64.b64decode(EMBEDDED_OPENCODE_MODELS_GZIP, validate=True)
        payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SyncError(f"Failed to load embedded OpenCode model catalog: {error}") from error
    return catalog_entries_from_opencode_models(payload)


def get_opencode_version(args: argparse.Namespace) -> str:
    try:
        return run_command([args.opencode_bin, "--version"], args.command_timeout).strip()
    except SyncError:
        return "unknown"


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


def acquire_catalog(args: argparse.Namespace) -> Tuple[List[CatalogEntry], Dict[str, Any]]:
    if args.catalog_file:
        entries = load_catalog_file(args.catalog_file)
        return entries, {"source": str(args.catalog_file), "opencode_version": "fixture"}

    version = get_opencode_version(args)

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
        return load_current()

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
            return current_entries, {**current_meta, "local_cache_error": str(local_error), "embedded_error": str(embedded_error)}
        else:
            eprint("Warning: OpenCode catalog cache unavailable; using embedded complete snapshot.")
            return entries, {
                "source": "embedded-opencode-models",
                "opencode_version": version,
                "providers": len({entry.provider_id for entry in entries}),
                "local_cache_error": str(local_error),
            }
    else:
        return entries, {
            "source": "opencode-models-cache",
            "opencode_version": version,
            "cache": str(args.opencode_models_file.expanduser()),
            "providers": len({entry.provider_id for entry in entries}),
        }


def normalized_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def strip_provider_prefix(model_id: str) -> str:
    return model_id.split("/", 1)[1] if "/" in model_id else model_id


def split_effort_suffix(model_id: str) -> Tuple[str, Optional[str]]:
    match = re.match(r"^(.+)-(none|low|medium|high|xhigh|max)$", model_id, flags=re.IGNORECASE)
    return (match.group(1), match.group(2).lower()) if match else (model_id, None)


def preferred_providers(model_id: str) -> List[str]:
    lowered = strip_provider_prefix(model_id).lower()
    explicit = model_id.split("/", 1)[0].lower() if "/" in model_id else ""
    if explicit == "zen":
        explicit = "opencode"
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
    result = [explicit] if explicit else []
    for prefixes, providers in rules:
        if lowered.startswith(prefixes):
            result.extend(providers)
    return list(dict.fromkeys(provider for provider in result if provider))


def metadata_completeness(entry: CatalogEntry) -> int:
    limit = entry.data.get("limit", {})
    limit = limit if isinstance(limit, dict) else {}
    capabilities = entry.data.get("capabilities", {})
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    variants = entry.data.get("variants", {})
    score = sum(1 for key in ("context", "input", "output") if isinstance(limit.get(key), int) and limit[key] > 0)
    score += int(bool(capabilities.get("reasoning")))
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
        score, rule = 220, "full-id-exact"
    elif raw == source_id:
        score, rule = 200, "model-id-exact"
    elif raw_without_provider == source_id:
        score, rule = 195, "provider-prefix-stripped"
    elif api_id and raw_without_provider == api_id:
        score, rule = 190, "api-id-exact"
    elif normalized_id(raw_without_provider) == normalized_id(source_id):
        score, rule = 170, "normalized-id"
    elif (
        explicit_provider == "zen"
        and entry.provider_id == "opencode"
        and normalized_id(f"{raw_without_provider}-free") == normalized_id(source_id)
    ):
        score, rule = 180, "zen-free-alias"
    elif effort and normalized_id(base_id) == normalized_id(source_id):
        score, rule = 150, "effort-base"
    if not score:
        return 0, rule, effort
    preferred = preferred_providers(model_id)
    if entry.provider_id in preferred:
        # Provider preference must remain stronger than catalog metadata variance.
        score += 30 - min(20, preferred.index(entry.provider_id) * 10)
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
    preferred = preferred_providers(model_id)
    candidates: List[Tuple[int, int, int, CatalogEntry]] = []
    for entry in entries:
        candidate_segments = model_id_segments(entry.model_id)
        if len(candidate_segments) < 2 or len(candidate_segments) >= len(target_segments):
            continue
        if not candidate_segments[1][0].isdigit():
            continue
        if target_segments[: len(candidate_segments)] != candidate_segments:
            continue
        provider_rank = preferred.index(entry.provider_id) if entry.provider_id in preferred else len(preferred)
        candidates.append((len(candidate_segments), provider_rank, metadata_completeness(entry), entry))
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
        return None, {
            "status": "ambiguous",
            "match_rule": top[1],
            "score": top[0],
            "candidates": [item[3].full_id for item in tied[:10]],
            "warnings": ["multiple catalog models have the same best score; use --mapping-file"],
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


def apply_context_limit(limit: Dict[str, int], context_limit: int) -> Dict[str, int]:
    """Cap the total context window without expanding or inventing other limits."""
    if context_limit <= 0:
        return limit
    result = dict(limit)
    result["context"] = min(result.get("context", context_limit), context_limit)
    for key in ("input", "output"):
        if key in result:
            result[key] = min(result[key], context_limit)
    return result


def context_suffix(context_limit: int) -> str:
    value = f"{context_limit // 1000}k" if context_limit % 1000 == 0 else str(context_limit)
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
    report.update({
        "limit": limit,
        "reasoning": config.get("reasoning"),
        "variants": sorted(config.get("variants", {})),
        "warnings": warnings,
    })

    # Add original version
    results.append((model_id, config, report))

    # Generate one capped version for each configured total window below the model limit.
    original_context = limit.get("context", 0)
    for context_limit in contexts:
        if context_limit <= 0 or original_context <= context_limit:
            continue
        capped_model_id = model_id + context_suffix(context_limit)
        capped_config = copy.deepcopy(config)
        capped_config["name"] = capped_model_id  # 显示名称带后缀
        capped_config["id"] = model_id  # 保持原始模型 ID 用于 API 调用
        capped_config["limit"] = apply_context_limit(limit, context_limit)

        capped_report = copy.deepcopy(report)
        capped_report["model_id"] = capped_model_id
        capped_report["capped_from"] = model_id
        capped_report["limit"] = capped_config["limit"]
        capped_report["warnings"] = warnings + [f"context window capped from {original_context} to {context_limit}"]

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
            results = model_config_from_entry(model, entry, match, args.variant_policy, args.provider_type, contexts)
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
            results = model_config_from_entry(model, entry, match, args.variant_policy, "openai-compatible", contexts)
            for mid, config, report in results:
                group_generated[mid] = config
                reports.append(report)

        provider_options = {"baseURL": base_url}
        if not args.omit_api_key_option and api_key_ref is not None:
            provider_options["apiKey"] = api_key_ref

        provider_name = args.provider_name or f"New API ({group_provider_id})"
        if len(groups) == 1:
            provider_name = args.provider_name or "New API"
            provider_id = args.provider
        else:
            # Use prefix like "newapi-alibaba", "newapi-deepseek"
            base_name = args.provider if args.provider != "newapi" else "newapi"
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

    args.provider = args.provider or "newapi"
    args.provider_name = args.provider_name or "New API"
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
        "generator_version": "0.1.0rc1",
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
        entries, catalog_meta = acquire_catalog(args)
        mappings = load_mapping(args.mapping_file)
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

PYEOF
}

# === 00-config.sh ===
# ==================== 配置区域 ====================
# 所有默认值在此集中配置，便于维护

# Claude Code 配置文件路径
CLAUDE_SETTINGS="$HOME/.claude/settings.json"

# Codex 配置文件路径
CODEX_AUTH="$HOME/.codex/auth.json"
CODEX_CONFIG="$HOME/.codex/config.toml"

# OpenCode 配置文件路径
OPENCODE_CONFIG="$HOME/.config/opencode/opencode.json"

# SK 文件目录
DEFAULT_SK_DIR="$HOME/.config/api-keys"

# SK 文件名（不含路径）
DEFAULT_SK_FILENAME="default.sk"

# API 提供商 URL；公开版本不连接任何预设服务。
DEFAULT_API_URL="${SWITCH_MODEL_BASE_URL:-}"

# Claude 默认模型
DEFAULT_CLAUDE_MODEL="opus"

# Codex 默认模型
DEFAULT_CODEX_MODEL="gpt-5.5"

# OpenCode 默认 provider ID
DEFAULT_OPENCODE_PROVIDER="newapi"

# OpenCode 默认 provider 名称
DEFAULT_OPENCODE_PROVIDER_NAME="New API"

# OpenCode 上下文子模式列表（逗号分隔，0 表示不生成子模式）
# 超过指定值的模型会保留原版本，并为每个适用值生成限制版本
DEFAULT_CONTEXT="258000"

# OpenCode 模型显式映射文件；存在时优先于 catalog 匹配与前缀回退
DEFAULT_OPENCODE_MAPPING_FILE="$HOME/.config/api-keys/model-mapping.json"

# OpenCode 同步报告位置；仅实际写入时覆盖最新报告以便审计
DEFAULT_OPENCODE_REPORT_FILE="${XDG_STATE_HOME:-$HOME/.local/state}/opencode/switch-model-report.json"

# === 01-utils.sh ===
# ==================== 工具函数 ====================

# 颜色定义（仅 TTY 下启用颜色，管道/重定向时无色，避免污染输出）
if [ -t 1 ] && [ -t 2 ]; then
    RED='\033[31m'
    GREEN='\033[32m'
    YELLOW='\033[33m'
    BLUE='\033[34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# 获取可用的 Python 3 命令名
get_python_cmd() {
    if command -v python3 &>/dev/null; then
        echo "python3"
    elif command -v python &>/dev/null && python -c "import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)" 2>/dev/null; then
        echo "python"
    fi
}

# 检查 Python 3 与 json 模块是否可用
check_json_tool() {
    local python_cmd=$(get_python_cmd)
    if [ -z "$python_cmd" ]; then
        echo -e "${RED}错误: 未找到 Python 3${NC}" >&2
        return 1
    fi
    $python_cmd -c "import json; import sys" 2>/dev/null || {
        echo -e "${RED}错误: 无法找到可用的 Python 3 与 json 模块${NC}" >&2
        return 1
    }
    return 0
}

# === 02-sk-manager.sh ===
# ==================== SK 文件管理 ====================

# 运行时变量
TOOL_MODE=""
SK_DIR="$DEFAULT_SK_DIR"
SK_FILENAME="$DEFAULT_SK_FILENAME"
SK_FILE="$SK_DIR/$SK_FILENAME"
CUSTOM_SK=""

# 确保 api-keys 目录下存在保护文件
ensure_api_keys_protection() {
    local dir="$DEFAULT_SK_DIR"
    local protection_content='# 安全说明

> 此目录下 .sk 文件不允许读取

## .sk 文件格式说明

- 文件扩展名：`.sk`
- 文件内容：纯文本，仅包含 API Key 字符串
- 文件权限：建议设置为 `600`（仅所有者可读写）
- 示例：`printf '%s\n' '<api-key>' > ~/.config/api-keys/default.sk`

## 安全警告

此目录下的 `.sk` 文件包含敏感的 API Key 信息，AI 工具不应读取或输出这些文件的内容。'

    # 创建目录（如果不存在）
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        chmod 700 "$dir"
    fi

    # 创建 CLAUDE.md（如果不存在）
    if [ ! -f "$dir/CLAUDE.md" ]; then
        echo "$protection_content" > "$dir/CLAUDE.md"
        chmod 644 "$dir/CLAUDE.md"
    fi

    # 创建 AGENTS.md（如果不存在）
    if [ ! -f "$dir/AGENTS.md" ]; then
        echo "$protection_content" > "$dir/AGENTS.md"
        chmod 644 "$dir/AGENTS.md"
    fi
}

# 从 sk 文件读取 API Key
# 参数: $1 - sk 文件路径（可选，默认使用 SK_FILE）
read_sk_from_file() {
    local file="${1:-$SK_FILE}"
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: SK 文件不存在: $file${NC}" >&2
        exit 1
    fi
    if [ ! -r "$file" ]; then
        echo -e "${RED}Error: SK 文件不可读: $file${NC}" >&2
        exit 1
    fi
    CUSTOM_SK=$(cat "$file" | tr -d '[:space:]')
    if [ -z "$CUSTOM_SK" ]; then
        echo -e "${YELLOW}SK 文件为空: $file${NC}" >&2
        echo -e "${YELLOW}请写入 API Key 后再运行；未执行模型切换。${NC}" >&2
        exit 0
    fi
    if [ "$PREVIEW" != true ]; then
        ensure_api_keys_protection
    fi
}

# === 03-model-fetch.sh ===
# ==================== 模型列表获取 ====================

# 获取模型列表 URL
# 参数: $1 - API 基础 URL
get_models_url() {
    local api_base="${1%/}"
    echo "${api_base}/v1/models"
}

# 从远端读取模型列表
# 参数: $1 - URL, $2 - API Key
fetch_bearer_json() {
    local url="$1"
    local api_key="$2"

    if ! command -v curl >/dev/null 2>&1; then
        echo "错误: 未找到 curl，无法读取模型列表" >&2
        return 1
    fi

    local header_file
    header_file=$(mktemp "${TMPDIR:-/tmp}/switch-model-header.XXXXXX") || return 1
    trap 'rm -f -- "$header_file"' RETURN
    chmod 600 "$header_file" 2>/dev/null || true
    printf 'Authorization: Bearer %s\n' "$api_key" > "$header_file"
    curl --fail --silent --show-error --location \
        --header "@$header_file" "$url" 2>/dev/null
}

# 获取模型列表
# 参数: $1 - API 基础 URL, $2 - API Key
# 返回: 模型 ID 列表 (每行一个)
fetch_models() {
    local api_base="$1"
    local api_key="$2"
    local models_url=$(get_models_url "$api_base")

    # 默认校验证书；HTTPS 校验失败时停止，不降级为不安全连接。
    local response
    response=$(fetch_bearer_json "$models_url" "$api_key") || return 1

    if [ -z "$response" ]; then
        echo "错误: 模型服务返回空响应" >&2
        return 1
    fi

    # 使用 python 解析 JSON 提取模型 ID 列表
    local python_cmd=$(get_python_cmd)
    echo "$response" | $python_cmd -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if 'data' in data:
        for item in data['data']:
            model_id = item.get('id', '')
            if model_id:
                sys.stdout.write(model_id.strip() + '\n')
except Exception:
    pass
" | tr -d '\r'
}

# 从模型列表中选择模型
# 参数: $1 - API 基础 URL, $2 - API Key, $3 - 自动匹配关键字, $4 - 默认模型
# 输出: 通过全局变量 SELECTED_MODEL 返回选中的模型
select_model() {
    local provider_base="$1"
    local sk="$2"
    local auto_model="$3"
    local default_model="$4"
    local model_list=""

    SELECTED_MODEL=""

    echo -e "${BLUE}正在从 API 获取可用模型列表...${NC}"
    if ! model_list=$(fetch_models "$provider_base" "$sk"); then
        echo -e "${RED}Error: 无法从模型服务读取模型列表${NC}" >&2
        return 1
    fi

    if [ -n "$model_list" ]; then
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true

        if [ -n "$auto_model" ]; then
            echo -e "${BLUE}自动匹配模型: ${YELLOW}$auto_model${NC}"
            local matched_models=()
            local m
            for m in "${models[@]}"; do
                if [[ "$m" == *"$auto_model"* ]]; then
                    matched_models+=("$m")
                fi
            done

            if [ ${#matched_models[@]} -gt 0 ]; then
                SELECTED_MODEL="${matched_models[0]}"
                echo -e "${GREEN}已自动选择模型: ${YELLOW}$SELECTED_MODEL${NC}"
            else
                SELECTED_MODEL="${models[0]}"
                echo -e "${YELLOW}未匹配到模型 $auto_model，自动选择第一个: ${YELLOW}$SELECTED_MODEL${NC}"
            fi
        else
            # preview 模式或非交互模式下自动选择第一个
            if [ "$PREVIEW" = true ] || [ ! -t 0 ]; then
                SELECTED_MODEL="${models[0]}"
                echo -e "${GREEN}已自动选择模型: ${YELLOW}$SELECTED_MODEL${NC}"
            else
                echo ""
                echo -e "${BLUE}请选择模型:${NC}"

                local i
                for i in "${!models[@]}"; do
                    printf "  %d) %s\n" $((i+1)) "${models[$i]}"
                done
                echo ""

                local model_choice
                read -p "请输入选项 [1-${#models[@]}]: " model_choice </dev/tty 2>/dev/null || model_choice="1"

                if [[ "$model_choice" =~ ^[0-9]+$ ]] && \
                   [ "$model_choice" -ge 1 ] && \
                   [ "$model_choice" -le ${#models[@]} ]; then
                    SELECTED_MODEL="${models[$((model_choice-1))]}"
                else
                    SELECTED_MODEL="${models[0]}"
                fi

                echo -e "${GREEN}已选择模型: ${YELLOW}$SELECTED_MODEL${NC}"
            fi
        fi
    else
        echo -e "${RED}Error: 模型服务没有返回可用模型${NC}" >&2
        return 1
    fi

    # 去除模型名中的空白字符（\r, \n, 空格等）
    SELECTED_MODEL=$(echo -n "$SELECTED_MODEL" | tr -d '[:space:]')
}

# === 04-claude.sh ===
# ==================== Claude Code 配置 ====================

# 更新 Claude Code 配置文件
# 参数: $1=文件路径, $2=API_URL, $3=sk, $4=model
update_claude_config() {
    local file="$1"
    local url="$2"
    local sk="$3"
    local model="$4"

    # 凭据通过子进程环境传递，避免暴露在进程参数中。
    SWITCH_MODEL_FILE="$file" SWITCH_MODEL_BASE_URL="$url" \
        SWITCH_MODEL_API_KEY="$sk" SWITCH_MODEL_NAME="$model" \
        python_claude_update
}

# 预览 Claude Code 配置
# 参数: $1=API_URL, $2=sk, $3=model, $4=model_list
preview_claude_config() {
    local url="$1"
    local sk="$2"
    local model="$3"
    local model_list="$4"

    echo -e "${BLUE}=== Claude Code 配置预览 ===${NC}"
    echo ""
    echo -e "${YELLOW}配置文件:${NC} $CLAUDE_SETTINGS"
    echo ""

    # 显示可用模型列表
    if [ -n "$model_list" ]; then
        echo -e "${YELLOW}可用模型列表:${NC}"
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
        local i
        for i in "${!models[@]}"; do
            if [ "${models[$i]}" = "$model" ]; then
                echo -e "  $((i+1))) ${GREEN}${models[$i]} (已选择)${NC}"
            else
                echo "  $((i+1))) ${models[$i]}"
            fi
        done
        echo ""
    fi

    echo -e "${YELLOW}已选择模型:${NC} $model"
    echo ""
    echo -e "${YELLOW}将要写入的内容:${NC}"
    echo "{"
    echo '  "env": {'
    echo "    \"ANTHROPIC_BASE_URL\": \"$url\","
    echo '    "ANTHROPIC_AUTH_TOKEN": "<redacted>"'
    echo "  },"
    echo "  \"model\": \"$model\""
    echo "}"
    echo ""
    echo -e "${YELLOW}SK 文件:${NC} $SK_FILE"
    echo -e "${YELLOW}API URL:${NC} $url"
}

# Claude 模式主函数
# 参数: $1=API_URL, $2=auto_model
claude_main() {
    local api_url="$1"
    local auto_model="$2"

    # 读取 sk
    read_sk_from_file
    local sk="$CUSTOM_SK"

    # 删除尾部的 /
    api_url="${api_url%/}"

    # 获取模型列表
    echo -e "${BLUE}正在从 API 获取可用模型列表...${NC}"
    local model_list
    if ! model_list=$(fetch_models "$api_url" "$sk"); then
        echo -e "${RED}Error: 无法从模型服务读取模型列表${NC}" >&2
        return 1
    fi

    # 选择模型
    local model
    if [ -n "$auto_model" ] && [ -n "$model_list" ]; then
        # 自动匹配模型
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
        local matched_models=()
        local m
        for m in "${models[@]}"; do
            if [[ "$m" == *"$auto_model"* ]]; then
                matched_models+=("$m")
            fi
        done
        if [ ${#matched_models[@]} -gt 0 ]; then
            model="${matched_models[0]}"
            echo -e "${GREEN}已自动匹配模型: ${YELLOW}$model${NC}"
        else
            model="${models[0]}"
            echo -e "${YELLOW}未匹配到模型 $auto_model，自动选择第一个: ${YELLOW}$model${NC}"
        fi
    elif [ -n "$model_list" ]; then
        # preview 模式或非交互模式下自动选择第一个
        if [ "$PREVIEW" = true ] || [ ! -t 0 ]; then
            local models=()
            IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
            model="${models[0]}"
            echo -e "${GREEN}已自动选择模型: ${YELLOW}$model${NC}"
        else
            # 交互模式
            select_model "$api_url" "$sk" "$auto_model" "$DEFAULT_CLAUDE_MODEL"
            model="$SELECTED_MODEL"
        fi
    else
        echo -e "${RED}Error: 模型服务没有返回可用模型${NC}" >&2
        return 1
    fi

    # 预览模式
    if [ "$PREVIEW" = true ]; then
        preview_claude_config "$api_url" "$sk" "$model" "$model_list"
        return 0
    fi

    # 检查配置文件
    if [ ! -f "$CLAUDE_SETTINGS" ]; then
        echo -e "${RED}Error: $CLAUDE_SETTINGS not found${NC}"
        exit 1
    fi

    # 备份配置文件
    local backup="${CLAUDE_SETTINGS}.bak.$(date +%Y%m%d%H%M%S)"
    cp "$CLAUDE_SETTINGS" "$backup"
    echo -e "${GREEN}Backup saved to: $backup${NC}"

    # 更新配置文件
    if update_claude_config "$CLAUDE_SETTINGS" "$api_url" "$sk" "$model" > "${CLAUDE_SETTINGS}.tmp" 2>/dev/null; then
        mv "${CLAUDE_SETTINGS}.tmp" "$CLAUDE_SETTINGS"

        echo ""
        echo -e "${GREEN}✓ Claude 切换成功${NC}"
        echo -e "  SK 文件    : ${YELLOW}$SK_FILE${NC}"
        echo -e "  BASE_URL   : ${YELLOW}$api_url${NC}"
        echo -e "  MODEL      : ${YELLOW}$model${NC}"
    else
        echo -e "${RED}Error: failed to update settings, restoring backup...${NC}"
        rm -f "${CLAUDE_SETTINGS}.tmp"
        cp "$backup" "$CLAUDE_SETTINGS"
        exit 1
    fi
}

# === 05-codex.sh ===
# ==================== Codex 配置 ====================

# 更新 Codex 认证文件
# 参数: $1=sk
update_codex_auth() {
    local sk="$1"
    local auth_backup=""

    # 备份（如果文件存在）
    if [ -f "$CODEX_AUTH" ]; then
        auth_backup="${CODEX_AUTH}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$CODEX_AUTH" "$auth_backup"
        echo -e "${GREEN}Codex auth 备份已保存: $auth_backup${NC}"
    else
        echo -e "${YELLOW}Codex auth 文件不存在，将创建新文件${NC}"
    fi

    SWITCH_MODEL_API_KEY="$sk" SWITCH_MODEL_AUTH_PATH="$CODEX_AUTH" \
        python_codex_auth

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Codex auth 更新成功${NC}"
        return 0
    else
        echo -e "${RED}Codex auth 更新失败${NC}"
        [ -f "$auth_backup" ] && cp "$auth_backup" "$CODEX_AUTH"
        return 1
    fi
}

# 更新 Codex 配置文件
# 参数: $1=url, $2=model
update_codex_config() {
    local url="$1"
    local model="$2"
    local config_backup=""

    # 备份（如果文件存在）
    if [ -f "$CODEX_CONFIG" ]; then
        config_backup="${CODEX_CONFIG}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$CODEX_CONFIG" "$config_backup"
        echo -e "${GREEN}Codex config 备份已保存: $config_backup${NC}"
    else
        echo -e "${YELLOW}Codex config 文件不存在，将创建新文件${NC}"
    fi

    python_codex_config "$url" "$model" "$CODEX_CONFIG"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Codex config 更新成功${NC}"
        return 0
    else
        echo -e "${RED}Codex config 更新失败${NC}"
        [ -f "$config_backup" ] && cp "$config_backup" "$CODEX_CONFIG"
        return 1
    fi
}

# 预览 Codex 配置
# 参数: $1=url, $2=sk, $3=model, $4=model_list
preview_codex_config() {
    local url="$1"
    local sk="$2"
    local model="$3"
    local model_list="$4"

    echo -e "${BLUE}=== Codex 配置预览 ===${NC}"
    echo ""
    echo -e "${YELLOW}认证文件:${NC} $CODEX_AUTH"
    echo ""

    # 显示可用模型列表
    if [ -n "$model_list" ]; then
        echo -e "${YELLOW}可用模型列表:${NC}"
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
        local i
        for i in "${!models[@]}"; do
            if [ "${models[$i]}" = "$model" ]; then
                echo -e "  $((i+1))) ${GREEN}${models[$i]} (已选择)${NC}"
            else
                echo "  $((i+1))) ${models[$i]}"
            fi
        done
        echo ""
    fi

    echo -e "${YELLOW}已选择模型:${NC} $model"
    echo ""
    echo -e "${YELLOW}认证文件将要写入:${NC}"
    echo "{"
    echo '  "auth_mode": "apikey",'
    echo '  "OPENAI_API_KEY": "<redacted>"'
    echo "}"
    echo ""
    echo -e "${YELLOW}配置文件:${NC} $CODEX_CONFIG"
    echo -e "${YELLOW}将要写入的内容:${NC}"
    echo 'model_provider = "newapi"'
    echo "model = \"$model\""
    echo 'model_reasoning_effort = "high"'
    echo 'disable_response_storage = true'
    echo 'personality = "pragmatic"'
    echo ""
    echo "[model_providers.newapi]"
    echo 'name = "NewAPI"'
    echo "base_url = \"$url/v1\""
    echo 'wire_api = "responses"'
    echo 'requires_openai_auth = true'
    echo ""
    echo -e "${YELLOW}SK 文件:${NC} $SK_FILE"
    echo -e "${YELLOW}API URL:${NC} $url"
}

# Codex 模式主函数
# 参数: $1=API_URL, $2=auto_model
codex_main() {
    local api_url="$1"
    local auto_model="$2"

    # 读取 sk
    read_sk_from_file
    local sk="$CUSTOM_SK"

    # 删除尾部的 /
    api_url="${api_url%/}"

    # 获取模型列表
    echo -e "${BLUE}正在从 API 获取可用模型列表...${NC}"
    local model_list
    if ! model_list=$(fetch_models "$api_url" "$sk"); then
        echo -e "${RED}Error: 无法从模型服务读取模型列表${NC}" >&2
        return 1
    fi

    # 选择模型
    local model
    if [ -n "$auto_model" ] && [ -n "$model_list" ]; then
        # 自动匹配模型
        local models=()
        IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
        local matched_models=()
        local m
        for m in "${models[@]}"; do
            if [[ "$m" == *"$auto_model"* ]]; then
                matched_models+=("$m")
            fi
        done
        if [ ${#matched_models[@]} -gt 0 ]; then
            model="${matched_models[0]}"
            echo -e "${GREEN}已自动匹配模型: ${YELLOW}$model${NC}"
        else
            model="${models[0]}"
            echo -e "${YELLOW}未匹配到模型 $auto_model，自动选择第一个: ${YELLOW}$model${NC}"
        fi
    elif [ -n "$model_list" ]; then
        # preview 模式或非交互模式下自动选择第一个
        if [ "$PREVIEW" = true ] || [ ! -t 0 ]; then
            local models=()
            IFS=$'\n' read -d '' -ra models <<< "$model_list" || true
            model="${models[0]}"
            echo -e "${GREEN}已自动选择模型: ${YELLOW}$model${NC}"
        else
            # 交互模式
            select_model "$api_url" "$sk" "$auto_model" "$DEFAULT_CODEX_MODEL"
            model="$SELECTED_MODEL"
        fi
    else
        echo -e "${RED}Error: 模型服务没有返回可用模型${NC}" >&2
        return 1
    fi

    # 预览模式
    if [ "$PREVIEW" = true ]; then
        preview_codex_config "$api_url" "$sk" "$model" "$model_list"
        return 0
    fi

    echo -e "${BLUE}更新 Codex 配置...${NC}"
    echo -e "  SK 文件    : ${YELLOW}$SK_FILE${NC}"
    echo -e "  Base URL   : ${YELLOW}${api_url}${NC}"
    echo -e "  Model      : ${YELLOW}${model}${NC}"

    # 更新 auth.json
    if ! update_codex_auth "$sk"; then
        exit 1
    fi

    # 更新 config.toml
    if ! update_codex_config "$api_url" "$model"; then
        exit 1
    fi

    echo ""
    echo -e "${GREEN}✓ Codex 切换成功${NC}"
}

# === 06-opencode.sh ===
# ==================== OpenCode 配置 ====================

run_opencode_sync() {
    if ! declare -F python_sync_new_api_opencode >/dev/null; then
        echo -e "${RED}Error: embedded OpenCode sync helper is unavailable${NC}" >&2
        echo -e "${YELLOW}请运行 bash build.sh 重新生成 switch-model.sh${NC}" >&2
        return 1
    fi

    python_sync_new_api_opencode "$@"
}

# 更新 OpenCode 配置文件（调用 sync_new_api_opencode.py）
# 参数: $1=base_url, $2=provider, $3=provider_name, $4=context
update_opencode_config() {
    local base_url="$1"
    local provider="${2:-$DEFAULT_OPENCODE_PROVIDER}"
    local provider_name="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
    local context="${4-$DEFAULT_CONTEXT}"
    local mapping_file="${OPENCODE_MAPPING_FILE:-$DEFAULT_OPENCODE_MAPPING_FILE}"
    local mapping_file_explicit="${OPENCODE_MAPPING_FILE_EXPLICIT:-false}"
    local prefix_fallback="${OPENCODE_PREFIX_FALLBACK:-true}"
    local report_file="${OPENCODE_REPORT_FILE:-$DEFAULT_OPENCODE_REPORT_FILE}"
    local -a sync_args=()

    if [ -f "$mapping_file" ]; then
        sync_args+=(--mapping-file "$mapping_file")
    elif [ "$mapping_file_explicit" = true ]; then
        echo -e "${RED}Error: 指定的映射文件不存在: $mapping_file${NC}" >&2
        return 1
    fi
    if [ "$prefix_fallback" = false ]; then
        sync_args+=(--no-prefix-fallback)
    fi

    mkdir -p "$(dirname "$report_file")"

    if [ ! -f "$OPENCODE_CONFIG" ]; then
        echo -e "${YELLOW}OpenCode config 文件不存在，将创建新文件${NC}"
        mkdir -p "$(dirname "$OPENCODE_CONFIG")"
    fi

    # 读取 sk 从环境变量传递
    local api_key
    api_key=$(cat "$SK_FILE" | tr -d '[:space:]')

    # 调用内嵌同步器直接生成并写入配置（apiKey 引用由 --api-key-file 生成）
    if NEWAPI_API_KEY="$api_key" \
    NEWAPI_BASE_URL="$base_url" \
        run_opencode_sync \
        --provider "$provider" \
        --provider-name "$provider_name" \
        --catalog-mode all \
        --api-key-file "$SK_FILE" \
        --config "$OPENCODE_CONFIG" \
        --write \
        --context "$context" \
        --report "$report_file" \
        "${sync_args[@]}" \
        2>&1; then
        echo -e "${GREEN}OpenCode config 更新成功${NC}"
        return 0
    else
        echo -e "${RED}OpenCode config 更新失败${NC}"
        return 1
    fi
}

# 预览 OpenCode 配置（调用 sync_new_api_opencode.py 生成预览）
# 参数: $1=base_url, $2=provider, $3=provider_name, $4=context
preview_opencode_config() {
    local base_url="$1"
    local provider="${2:-$DEFAULT_OPENCODE_PROVIDER}"
    local provider_name="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
    local context="${4-$DEFAULT_CONTEXT}"
    local mapping_file="${OPENCODE_MAPPING_FILE:-$DEFAULT_OPENCODE_MAPPING_FILE}"
    local mapping_file_explicit="${OPENCODE_MAPPING_FILE_EXPLICIT:-false}"
    local prefix_fallback="${OPENCODE_PREFIX_FALLBACK:-true}"
    local report_file
    local -a sync_args=()

    if [ -f "$mapping_file" ]; then
        sync_args+=(--mapping-file "$mapping_file")
    elif [ "$mapping_file_explicit" = true ]; then
        echo -e "${RED}Error: 指定的映射文件不存在: $mapping_file${NC}" >&2
        return 1
    fi
    if [ "$prefix_fallback" = false ]; then
        sync_args+=(--no-prefix-fallback)
    fi

    echo -e "${BLUE}=== OpenCode 配置预览 ===${NC}"
    echo ""
    echo -e "${YELLOW}配置文件:${NC} $OPENCODE_CONFIG"
    echo ""

    # 读取 sk 从环境变量传递
    local api_key
    api_key=$(cat "$SK_FILE" | tr -d '[:space:]')

    # 预览只使用临时文件，不写持久报告。
    local preview_file
    preview_file=$(mktemp "${TMPDIR:-/tmp}/switch-model-preview.XXXXXX.json") || return 1
    report_file=$(mktemp "${TMPDIR:-/tmp}/switch-model-report.XXXXXX.json") || {
        rm -f "$preview_file"
        return 1
    }

    # 调用内嵌同步器生成预览（apiKey 引用由 --api-key-file 生成）
    local exit_code
    if NEWAPI_API_KEY="$api_key" \
    NEWAPI_BASE_URL="$base_url" \
        run_opencode_sync \
        --provider "$provider" \
        --provider-name "$provider_name" \
        --catalog-mode all \
        --api-key-file "$SK_FILE" \
        --output "$preview_file" \
        --report "$report_file" \
        --context "$context" \
        "${sync_args[@]}" \
        2>&1; then
        exit_code=0
    else
        exit_code=$?
    fi

    if [ $exit_code -eq 0 ] && [ -f "$preview_file" ]; then
        echo -e "${YELLOW}将要写入的内容:${NC}"
        cat "$preview_file"
        echo ""

        # 显示匹配报告摘要
        if [ -f "$report_file" ]; then
            local summary
            local python_cmd
            python_cmd=$(get_python_cmd)
            summary=$("$python_cmd" - "$report_file" 2>/dev/null <<'PYEOF'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    report = json.load(file)
summary = report.get("summary", {})
print(
    f"matched: {summary.get('matched', 0)}, "
    f"mapped: {summary.get('mapped', 0)}, "
    f"guessed: {summary.get('guessed', 0)}, "
    f"ambiguous: {summary.get('ambiguous', 0)}, "
    f"unmatched: {summary.get('unmatched', 0)}"
)
PYEOF
)
            echo -e "${YELLOW}匹配结果:${NC} $summary"
        fi
    else
        echo -e "${RED}生成预览失败${NC}"
    fi

    # 清理临时文件
    rm -f "$preview_file" "$report_file"

    return $exit_code
}

# OpenCode 模式主函数
# 参数: $1=API_URL, $2=provider, $3=provider_name, $4=context
opencode_main() {
    local api_url="$1"
    local provider="${2:-$DEFAULT_OPENCODE_PROVIDER}"
    local provider_name="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
    local context="${4-$DEFAULT_CONTEXT}"

    # 在创建或更新 OpenCode 配置前先校验 SK，避免空 SK 产生配置改动
    read_sk_from_file

    # 删除尾部的 /
    api_url="${api_url%/}"

    # 预览模式
    if [ "$PREVIEW" = true ]; then
        preview_opencode_config "$api_url" "$provider" "$provider_name" "$context"
        return $?
    fi

    if [ "${OPENCODE_REPLACE_PROVIDERS:-false}" != true ]; then
        echo -e "${RED}Error: OpenCode 写入会替换配置中的整个 provider 对象。确认后添加 --replace-providers。${NC}" >&2
        return 1
    fi

    echo -e "${BLUE}更新 OpenCode 配置...${NC}"
    echo -e "  SK 文件    : ${YELLOW}$SK_FILE${NC}"
    echo -e "  Base URL   : ${YELLOW}${api_url}${NC}"
    echo -e "  Provider   : ${YELLOW}${provider}${NC}"
    echo -e "  Config     : ${YELLOW}${OPENCODE_CONFIG}${NC}"

    # 显示上下文子模式配置
    if [ "$context" != "0" ]; then
        echo -e "  Context子模式: ${YELLOW}${context}${NC}"
    fi

    # 更新配置
    if update_opencode_config "$api_url" "$provider" "$provider_name" "$context"; then
        echo ""
        echo -e "${GREEN}✓ OpenCode 切换成功${NC}"
    else
        exit 1
    fi
}

# === 07-main.sh ===
# ==================== 使用帮助 ====================

usage() {
    local exit_code="${1:-1}"
    echo "Usage: $0 <claude|codex|opencode> <url> [model] [--sk-filename <name>] [--sk-file <path>] [--preview]"
    echo ""
    echo "Arguments:"
    echo "  <claude|codex|opencode> 工具模式（必需，作为第一个参数）"
    echo "  url                     OpenAI-compatible 模型服务 URL；也可设置 SWITCH_MODEL_BASE_URL"
    echo "  model                   模型名，自动 grep 选择"
    echo "                          - Claude 默认: $DEFAULT_CLAUDE_MODEL"
    echo "                          - Codex 默认: $DEFAULT_CODEX_MODEL"
    echo "                          - OpenCode: 不需要指定"
    echo ""
    echo "Options:"
    echo "  --sk-filename <name>    指定 SK 文件名（默认: $DEFAULT_SK_FILENAME）"
    echo "  --sk-file <path>        指定 SK 文件完整路径（优先级高于 --sk-filename）"
    echo "  --preview               预览模式，只输出配置文件位置与内容，不实际写入"
    echo ""
    echo "OpenCode Options:"
    echo "  --context <tokens[,tokens...]>  为超过指定值的模型生成上下文子模式（默认: $DEFAULT_CONTEXT；0 表示禁用）"
    echo "  --mapping-file <path>            显式模型 ID 到 OpenCode catalog ID 的 JSON 映射（默认: $DEFAULT_OPENCODE_MAPPING_FILE）"
    echo "  --no-prefix-fallback             关闭仅在精确匹配失败后启用的安全前缀元数据回退"
    echo "  --replace-providers              确认写入时替换 OpenCode 配置中的整个 provider 对象"
    echo "  Catalog 运行时顺序: 本地 cache -> 内嵌完整 snapshot -> 实时查询"
    echo "  实时查询命令: opencode models --verbose --pure"
    echo "  构建时使用受审计的 OPENCODE_MODELS_FILE；不会隐式刷新本机 cache"
    echo ""
    echo "Examples:"
    echo "  # Claude 模式"
    echo "  $0 claude https://api.example.com $DEFAULT_CLAUDE_MODEL"
    echo "  $0 claude https://api.example.com --sk-filename work.sk"
    echo ""
    echo "  # Codex 模式"
    echo "  $0 codex https://api.example.com"
    echo "  $0 codex https://api.example.com --sk-filename work.sk"
    echo ""
    echo "  # OpenCode 模式"
    echo "  $0 opencode https://api.example.com --preview"
    echo "  $0 opencode https://api.example.com --replace-providers"
    echo "  $0 opencode https://api.example.com --context 128000 --replace-providers"
    echo "  $0 opencode https://api.example.com --mapping-file ~/.config/api-keys/model-mapping.json --replace-providers"
    echo "  $0 opencode https://api.example.com --no-prefix-fallback --replace-providers"
    echo ""
    echo "  # 预览模式"
    echo "  $0 claude https://api.example.com --preview"
    echo "  $0 codex https://api.example.com --preview"
    echo "  $0 opencode https://api.example.com --preview"
    exit "$exit_code"
}

validate_context_argument() {
    local value="$1"
    if ! [[ "$value" =~ ^[[:space:]]*[0-9]+[[:space:]]*(,[[:space:]]*[0-9]+[[:space:]]*)*$ ]]; then
        echo -e "${RED}Error: --context must be a comma-separated list of non-negative integers${NC}" >&2
        return 1
    fi

    local compact="${value//[[:space:]]/}"
    local item
    local has_zero=false
    local has_positive=false
    local -a values=()
    IFS=',' read -ra values <<< "$compact"
    for item in "${values[@]}"; do
        if [[ "$item" =~ ^0+$ ]]; then
            has_zero=true
        else
            has_positive=true
        fi
    done
    if [ "$has_zero" = true ] && [ "$has_positive" = true ]; then
        echo -e "${RED}Error: --context value 0 cannot be combined with other context values${NC}" >&2
        return 1
    fi
}

# ==================== 主逻辑 ====================

# 预览模式标志
PREVIEW=false
OPENCODE_MAPPING_FILE="$DEFAULT_OPENCODE_MAPPING_FILE"
OPENCODE_MAPPING_FILE_EXPLICIT=false
OPENCODE_PREFIX_FALLBACK=true
OPENCODE_REPLACE_PROVIDERS=false

# 检查是否有参数
if [ "$#" -eq 0 ]; then
    echo -e "${RED}Error: 需要指定工具模式 <claude|codex|opencode>${NC}" >&2
    usage
fi

# 第一个参数必须是工具模式或 -h/--help
case "$1" in
    -h|--help)
        usage 0
        ;;
    claude|codex|opencode)
        TOOL_MODE="$1"
        shift
        ;;
    *)
        echo -e "${RED}Error: 第一个参数必须是 'claude'、'codex' 或 'opencode'${NC}" >&2
        usage
        ;;
esac

# 解析剩余选项：扫描所有参数，识别 --* 选项，其余作为位置参数保留
POSITIONAL=()
CONTEXT=$DEFAULT_CONTEXT
while [ "$#" -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage 0
            ;;
        --sk-filename)
            if [ -z "${2:-}" ]; then
                echo -e "${RED}Error: --sk-filename requires argument <name>${NC}"
                usage
            fi
            SK_FILENAME="$2"
            SK_FILE="$SK_DIR/$SK_FILENAME"
            shift 2
            ;;
        --sk-file)
            if [ -z "${2:-}" ]; then
                echo -e "${RED}Error: --sk-file requires argument <path>${NC}"
                usage
            fi
            SK_FILE="$2"
            shift 2
            ;;
        --context)
            if [ -z "${2:-}" ] || [[ "$2" == --* ]]; then
                echo -e "${RED}Error: --context requires argument <tokens[,tokens...]>${NC}"
                usage
            fi
            if ! validate_context_argument "$2"; then
                usage
            fi
            CONTEXT="$2"
            shift 2
            ;;
        --mapping-file)
            if [ -z "${2:-}" ] || [[ "$2" == --* ]]; then
                echo -e "${RED}Error: --mapping-file requires argument <path>${NC}"
                usage
            fi
            OPENCODE_MAPPING_FILE="$2"
            OPENCODE_MAPPING_FILE_EXPLICIT=true
            shift 2
            ;;
        --no-prefix-fallback)
            OPENCODE_PREFIX_FALLBACK=false
            shift
            ;;
        --replace-providers)
            OPENCODE_REPLACE_PROVIDERS=true
            shift
            ;;
        --preview)
            PREVIEW=true
            shift
            ;;
        --*)
            echo -e "${RED}Error: 未知选项 $1${NC}" >&2
            usage
            ;;
        *)
            POSITIONAL+=("$1")
            shift
            ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [ -z "${1:-$DEFAULT_API_URL}" ]; then
    echo -e "${RED}Error: 必须提供模型服务 URL，或设置 SWITCH_MODEL_BASE_URL${NC}" >&2
    usage
fi

# 检查 JSON 处理工具
if ! check_json_tool; then
    exit 1
fi

# 根据工具模式执行
case "$TOOL_MODE" in
    claude)
        URL="${1:-$DEFAULT_API_URL}"
        AUTO_MODEL="${2:-}"
        claude_main "$URL" "$AUTO_MODEL"
        ;;
    codex)
        URL="${1:-$DEFAULT_API_URL}"
        AUTO_MODEL="${2:-}"
        codex_main "$URL" "$AUTO_MODEL"
        ;;
    opencode)
        URL="${1:-$DEFAULT_API_URL}"
        PROVIDER="${2:-$DEFAULT_OPENCODE_PROVIDER}"
        PROVIDER_NAME="${3:-$DEFAULT_OPENCODE_PROVIDER_NAME}"
        opencode_main "$URL" "$PROVIDER" "$PROVIDER_NAME" "$CONTEXT"
        ;;
esac

# === End of auto-generated file ===
