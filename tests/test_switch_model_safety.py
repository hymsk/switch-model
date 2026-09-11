import importlib.util
from argparse import Namespace
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
GENERATED_SCRIPT = ROOT / "switch-model.sh"
OPENCODE_SYNC = ROOT / "python" / "sync_new_api_opencode.py"


def load_opencode_sync_module():
    spec = importlib.util.spec_from_file_location("switch_model_opencode_sync", OPENCODE_SYNC)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {OPENCODE_SYNC}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


OPENCODE_SYNC_MODULE = load_opencode_sync_module()


class SwitchModelSafetyTests(unittest.TestCase):
    def test_generated_bundle_uses_default_url_file_without_personal_defaults(self):
        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('DEFAULT_URL_FILENAME="default.url"', generated)
        self.assertIn('DEFAULT_URL_FILE="$DEFAULT_SK_DIR/$DEFAULT_URL_FILENAME"', generated)
        self.assertIn('DEFAULT_API_URL="${SWITCH_MODEL_BASE_URL:-}"', generated)
        self.assertIn('DEFAULT_OPENCODE_PROVIDER="newapi"', generated)
        self.assertNotIn("${sk:0:10}", generated)
        self.assertIn('"<redacted>"', generated)

    def test_default_build_is_anchored_to_git_head_not_dirty_bundle(self):
        build = (ROOT / "build.sh").read_text(encoding="utf-8")
        self.assertIn("git -C \"$SCRIPT_DIR\" show HEAD:switch-model.sh", build)
        self.assertNotIn("grep -q '^# OpenCode catalog SHA256:", build)

    def test_generated_shell_has_no_provider_replacement_gate(self):
        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("--replace-providers", generated)
        self.assertNotIn("OPENCODE_REPLACE_PROVIDERS", generated)

    def test_generated_shell_writes_api_key_protection_files_without_expanding_example(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, _ = generated.partition("# === 03-model-fetch.sh ===")
        self.assertTrue(marker, "generated script must retain the model-fetch boundary")

        with tempfile.TemporaryDirectory() as directory:
            protection_directory = Path(directory) / "api-keys"
            harness = Path(directory) / "write-api-key-protection.sh"
            harness.write_text(
                prefix
                + '\nDEFAULT_SK_DIR="$TEST_PROTECTION_DIR"\n'
                + "ensure_api_keys_protection\n",
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment["TEST_PROTECTION_DIR"] = str(protection_directory)
            completed = subprocess.run(
                (bash, str(harness)),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            agents_content = (protection_directory / "AGENTS.md").read_text(encoding="utf-8")
            claude_content = (protection_directory / "CLAUDE.md").read_text(encoding="utf-8")

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        expected_example = "`printf '%s\\n' '<api-key>' > ~/.config/api-keys/default.sk`"
        self.assertIn(expected_example, agents_content)
        self.assertEqual(agents_content, claude_content)

    def test_generated_opencode_helper_forwards_arguments(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, _ = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory) / "invoke-opencode-helper.sh"
            harness.write_text(
                prefix + "\npython_sync_new_api_opencode --help\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                (bash, str(harness)),
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(
            0,
            completed.returncode,
            completed.stdout + completed.stderr,
        )
        self.assertIn("--context TOKENS", completed.stdout)
        self.assertNotIn("--context-threshold", completed.stdout)
        self.assertNotIn("--context-limit", completed.stdout)

    def test_generated_preview_uses_python_fallback_when_python3_is_unavailable(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, _ = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            key_file = temporary / "test.sk"
            key_file.write_text("test-key-not-real\n", encoding="utf-8")
            harness = temporary / "preview-with-python-fallback.sh"
            harness.write_text(
                prefix
                + r'''
python3() {
    return 127
}

python() {
    "$REAL_PYTHON" "$@"
}

command() {
    if [ "${1:-}" = "-v" ] && [ "${2:-}" = "python3" ]; then
        return 1
    fi
    if [ "${1:-}" = "-v" ] && [ "${2:-}" = "python" ]; then
        printf '%s\n' python
        return 0
    fi
    builtin command "$@"
}

run_opencode_sync() {
    local output_file=""
    local report_file_path=""
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --output)
                output_file="$2"
                shift 2
                ;;
            --report)
                report_file_path="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    printf '%s\n' '{"provider": {}}' > "$output_file"
    printf '%s\n' '{"summary": {"matched": 1, "mapped": 2, "guessed": 3, "ambiguous": 4, "unmatched": 5}}' > "$report_file_path"
}

SK_FILE="$TEST_KEY_FILE"
OPENCODE_CONFIG="$TEST_CONFIG_FILE"
preview_opencode_config "https://api.example.com" "newapi" "NewAPI" "0"
''',
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment.update(
                REAL_PYTHON=sys.executable,
                TEST_KEY_FILE=str(key_file),
                TEST_CONFIG_FILE=str(temporary / "opencode.json"),
            )
            completed = subprocess.run(
                (bash, str(harness)),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("matched: 1, mapped: 2, guessed: 3, ambiguous: 4, unmatched: 5", completed.stdout)

    def test_generated_shell_normalizes_and_forwards_context(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, main = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory) / "invoke-switch-model.sh"
            harness.write_text(
                prefix
                + '\nopencode_main() { printf "context=%s\\n" "$4"; }\n'
                + marker
                + main,
                encoding="utf-8",
            )
            completed = subprocess.run(
                (
                    bash,
                    str(harness),
                    "opencode",
                    "https://api.example.com",
                    "--context",
                    "258K",
                ),
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("context=258000", completed.stdout)

    def test_generated_shell_uses_default_url_file(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, main = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            default_url_file = Path(directory) / "default.url"
            default_url_file.write_text("https://default.example.com\n", encoding="utf-8")
            harness = Path(directory) / "invoke-switch-model.sh"
            harness.write_text(
                prefix
                + '\nDEFAULT_URL_FILE="$TEST_DEFAULT_URL_FILE"\n'
                + '\nopencode_main() { printf "url=%s\\n" "$1"; }\n'
                + marker
                + main,
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment["TEST_DEFAULT_URL_FILE"] = str(default_url_file)
            completed = subprocess.run(
                (bash, str(harness), "opencode"),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("url=https://default.example.com", completed.stdout)

    def test_generated_shell_prioritizes_command_line_and_environment_urls(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, main = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            default_url_file = Path(directory) / "default.url"
            default_url_file.write_text("https://default.example.com\n", encoding="utf-8")
            harness = Path(directory) / "invoke-switch-model.sh"
            harness.write_text(
                prefix
                + '\nDEFAULT_URL_FILE="$TEST_DEFAULT_URL_FILE"\n'
                + '\nopencode_main() { printf "url=%s\\n" "$1"; }\n'
                + marker
                + main,
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment.update(
                SWITCH_MODEL_BASE_URL="https://environment.example.com",
                TEST_DEFAULT_URL_FILE=str(default_url_file),
            )
            from_environment = subprocess.run(
                (bash, str(harness), "opencode"),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            from_command_line = subprocess.run(
                (bash, str(harness), "opencode", "https://command.example.com"),
                cwd=str(ROOT),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(0, from_environment.returncode, from_environment.stdout + from_environment.stderr)
        self.assertIn("url=https://environment.example.com", from_environment.stdout)
        self.assertEqual(0, from_command_line.returncode, from_command_line.stdout + from_command_line.stderr)
        self.assertIn("url=https://command.example.com", from_command_line.stdout)

    def test_generated_shell_accepts_context_equals_form(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, main = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory) / "invoke-switch-model.sh"
            harness.write_text(
                prefix
                + '\nopencode_main() { printf "context=%s\\n" "$4"; }\n'
                + marker
                + main,
                encoding="utf-8",
            )
            completed = subprocess.run(
                (bash, str(harness), "opencode", "https://api.example.com", "--context=200k"),
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("context=200000", completed.stdout)

    def test_generated_shell_rejects_invalid_context_values(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        prefix, marker, main = generated.partition("# === 07-main.sh ===")
        self.assertTrue(marker, "generated script must retain the main-module boundary")

        with tempfile.TemporaryDirectory() as directory:
            harness = Path(directory) / "invoke-switch-model.sh"
            harness.write_text(
                prefix
                + '\nopencode_main() { printf "opencode-main-called\\n"; }\n'
                + marker
                + main,
                encoding="utf-8",
            )
            for value in ("1,,2", "128k,258k", "258,000", "-1", "128x", "200kk"):
                completed = subprocess.run(
                    (bash, str(harness), "opencode", "--context", value),
                    cwd=str(ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertNotEqual(0, completed.returncode)
                self.assertNotIn("opencode-main-called", completed.stdout)

    def test_removed_threshold_and_limit_options_are_rejected(self):
        bash = shutil.which("bash") or shutil.which("bash.exe")
        if bash is None:
            self.skipTest("bash is not available")

        for option in ("--context-threshold", "--context-limit"):
            completed = subprocess.run(
                (
                    bash,
                    str(GENERATED_SCRIPT),
                    "opencode",
                    "https://api.example.com",
                    option,
                    "128000",
                    "--preview",
                ),
                cwd=str(ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn(f"未知选项 {option}", completed.stdout + completed.stderr)

            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    OPENCODE_SYNC_MODULE.parse_args([option, "128000"])

    def test_missing_cache_rejects_incomplete_embedded_catalog_and_uses_runtime(self):
        args = Namespace(
            catalog_file=None,
            catalog_mode="all",
            opencode_models_file=Path("/missing/models.json"),
            api_key_env="NEWAPI_API_KEY",
            opencode_bin="opencode",
            command_timeout=20,
            catalog_refresh=False,
        )
        embedded_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/example-model",
                {"id": "example-model", "providerID": "openai", "limit": {"context": 1000000}},
            )
        ]
        runtime_output = "openai/runtime-model\n{\"id\":\"runtime-model\",\"providerID\":\"openai\",\"limit\":{\"context\":200000}}\n"

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", side_effect=OPENCODE_SYNC_MODULE.SyncError("missing")), \
             patch.object(OPENCODE_SYNC_MODULE, "catalog_entries_from_opencode_models", return_value=embedded_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "EMBEDDED_OPENCODE_MODELS_GZIP", "placeholder"), \
             patch.object(OPENCODE_SYNC_MODULE, "base64") as base64_module, \
             patch.object(OPENCODE_SYNC_MODULE, "gzip") as gzip_module, \
             patch.object(OPENCODE_SYNC_MODULE, "run_command", return_value=runtime_output) as run_command:
            base64_module.b64decode.return_value = b"compressed"
            gzip_module.decompress.return_value = b"{}"
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args)

        self.assertEqual(["openai/runtime-model"], [entry.full_id for entry in entries])
        self.assertEqual("opencode-current", metadata["source"])
        self.assertIn("incomplete", metadata["embedded_error"])
        run_command.assert_called_once()

    def test_complete_embedded_catalog_remains_preferred_to_runtime(self):
        args = Namespace(
            catalog_file=None,
            catalog_mode="all",
            opencode_models_file=Path("/missing/models.json"),
            api_key_env="NEWAPI_API_KEY",
            opencode_bin="opencode",
            command_timeout=20,
            catalog_refresh=False,
        )
        embedded_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                f"provider-{index % 10}/model-{index}",
                {
                    "id": f"model-{index}",
                    "providerID": f"provider-{index % 10}",
                    "limit": {"context": 200000},
                },
            )
            for index in range(100)
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", side_effect=OPENCODE_SYNC_MODULE.SyncError("missing")), \
             patch.object(OPENCODE_SYNC_MODULE, "load_embedded_opencode_models_catalog", return_value=embedded_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command") as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args)

        self.assertEqual(embedded_entries, entries)
        self.assertEqual("embedded-opencode-models", metadata["source"])
        run_command.assert_not_called()

    def test_zero_embedded_matches_prefers_runtime_when_runtime_matches(self):
        args = Namespace(
            catalog_file=None,
            catalog_mode="all",
            opencode_models_file=Path("/missing/models.json"),
            api_key_env="NEWAPI_API_KEY",
            opencode_bin="opencode",
            command_timeout=20,
            prefix_fallback=True,
            catalog_refresh=False,
        )
        embedded_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                f"provider-{index % 10}/unrelated-{index}",
                {
                    "id": f"unrelated-{index}",
                    "providerID": f"provider-{index % 10}",
                    "limit": {"context": 200000},
                },
            )
            for index in range(100)
        ]
        runtime_output = "openai/requested-model\n{\"id\":\"requested-model\",\"providerID\":\"openai\",\"limit\":{\"context\":400000}}\n"

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", side_effect=OPENCODE_SYNC_MODULE.SyncError("missing")), \
             patch.object(OPENCODE_SYNC_MODULE, "load_embedded_opencode_models_catalog", return_value=embedded_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command", return_value=runtime_output) as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        self.assertEqual(["openai/requested-model"], [entry.full_id for entry in entries])
        self.assertEqual("opencode-current", metadata["source"])
        self.assertEqual(1, metadata["requested_model_matches"])
        run_command.assert_called_once()

    def test_zero_cache_matches_prefers_runtime_when_runtime_matches(self):
        args = Namespace(
            catalog_file=None,
            catalog_mode="all",
            opencode_models_file=Path("/models.json"),
            api_key_env="NEWAPI_API_KEY",
            opencode_bin="opencode",
            command_timeout=20,
            prefix_fallback=True,
            catalog_refresh=False,
        )
        cache_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/unrelated-model",
                {"id": "unrelated-model", "providerID": "openai", "limit": {"context": 200000}},
            )
        ]
        runtime_output = "openai/requested-model\n{\"id\":\"requested-model\",\"providerID\":\"openai\",\"limit\":{\"context\":400000}}\n"

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", return_value=cache_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "load_embedded_opencode_models_catalog", side_effect=OPENCODE_SYNC_MODULE.SyncError("missing")), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command", return_value=runtime_output) as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        self.assertEqual(["openai/requested-model"], [entry.full_id for entry in entries])
        self.assertEqual("opencode-current", metadata["source"])
        self.assertEqual(1, metadata["requested_model_matches"])
        run_command.assert_called_once()

    def test_zero_cache_matches_prefers_matching_embedded_before_runtime(self):
        args = Namespace(
            catalog_file=None,
            catalog_mode="all",
            opencode_models_file=Path("/models.json"),
            api_key_env="NEWAPI_API_KEY",
            opencode_bin="opencode",
            command_timeout=20,
            prefix_fallback=True,
            catalog_refresh=False,
        )
        cache_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/unrelated-model",
                {"id": "unrelated-model", "providerID": "openai", "limit": {"context": 200000}},
            )
        ]
        embedded_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/requested-model",
                {"id": "requested-model", "providerID": "openai", "limit": {"context": 400000}},
            )
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", return_value=cache_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "load_embedded_opencode_models_catalog", return_value=embedded_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command") as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        self.assertEqual(embedded_entries, entries)
        self.assertEqual("embedded-opencode-models", metadata["source"])
        self.assertEqual(1, metadata["requested_model_matches"])
        run_command.assert_not_called()

    def test_catalog_refresh_is_enabled_by_default_and_records_metadata(self):
        args = OPENCODE_SYNC_MODULE.parse_args([])
        self.assertTrue(args.catalog_refresh)

        cache_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/requested-model",
                {"id": "requested-model", "providerID": "openai", "limit": {"context": 400000}},
            )
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", return_value=cache_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command", return_value="") as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        self.assertEqual("opencode-models-cache", metadata["source"])
        self.assertEqual("opencode-models-refresh", metadata["catalog_refresh"])
        run_command.assert_called_once()
        self.assertEqual(
            ["opencode", "models", "--refresh", "--pure"],
            run_command.call_args[0][0],
        )

    def test_no_catalog_refresh_skips_the_refresh_call(self):
        args = OPENCODE_SYNC_MODULE.parse_args(["--no-catalog-refresh"])
        self.assertFalse(args.catalog_refresh)

        cache_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/requested-model",
                {"id": "requested-model", "providerID": "openai", "limit": {"context": 400000}},
            )
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", return_value=cache_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command", return_value="") as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        run_command.assert_not_called()
        self.assertNotIn("catalog_refresh", metadata)

    def test_catalog_refresh_failure_falls_back_to_existing_cache(self):
        args = OPENCODE_SYNC_MODULE.parse_args([])
        cache_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/requested-model",
                {"id": "requested-model", "providerID": "openai", "limit": {"context": 400000}},
            )
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", return_value=cache_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command", side_effect=OPENCODE_SYNC_MODULE.SyncError("offline")):
            with redirect_stderr(StringIO()) as stderr:
                entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        self.assertEqual(["openai/requested-model"], [entry.full_id for entry in entries])
        self.assertEqual("opencode-models-cache", metadata["source"])
        self.assertNotIn("catalog_refresh", metadata)
        self.assertIn("refresh failed", stderr.getvalue())

    def test_catalog_refresh_is_skipped_for_fixture_catalogs(self):
        args = OPENCODE_SYNC_MODULE.parse_args(["--catalog-file", "tests/fixtures/fixture.json"])

        fixture_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/requested-model",
                {"id": "requested-model", "providerID": "openai", "limit": {"context": 400000}},
            )
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "load_catalog_file", return_value=fixture_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command") as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args, ["requested-model"])

        run_command.assert_not_called()
        self.assertEqual("fixture", metadata["opencode_version"])

    def test_context_argument_accepts_plain_and_k_formats(self):
        for value in ("258000", "258k", "258K"):
            args = OPENCODE_SYNC_MODULE.parse_args(["--context", value])
            self.assertEqual((258000,), args.context)

    def test_context_argument_accepts_equals_form_and_rejects_abbreviation(self):
        args = OPENCODE_SYNC_MODULE.parse_args(["--context=200k"])
        self.assertEqual((200000,), args.context)
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                OPENCODE_SYNC_MODULE.parse_args(["--conte", "200k"])

    def test_context_argument_rejects_commas_and_invalid_values(self):
        for value in ("", "1,,2", "128k,258k", "258,000", "-1", "128x", "200kk", "1,000,000"):
            with self.assertRaises(OPENCODE_SYNC_MODULE.argparse.ArgumentTypeError):
                OPENCODE_SYNC_MODULE.parse_contexts(value)

    def test_context_generates_limited_version(self):
        entry = OPENCODE_SYNC_MODULE.CatalogEntry(
            full_id="openai/example-model",
            data={
                "id": "example-model",
                "providerID": "openai",
                "limit": {"context": 1000000, "input": 900000, "output": 32000},
                "capabilities": {},
            },
        )
        match = {"status": "matched", "match_rule": "exact", "score": 100, "candidates": []}

        results = OPENCODE_SYNC_MODULE.model_config_from_entry(
            {"id": "example-model"},
            entry,
            match,
            "none",
            contexts=(258000,),
        )

        self.assertEqual(
            ["example-model", "example-model (258k)"],
            [model_id for model_id, _, _ in results],
        )
        self.assertEqual(
            {"context": 258000, "input": 258000, "output": 32000},
            results[1][1]["limit"],
        )

    def test_context_zero_disables_limited_versions(self):
        entry = OPENCODE_SYNC_MODULE.CatalogEntry(
            full_id="openai/example-model",
            data={"limit": {"context": 1000000, "input": 900000, "output": 32000}},
        )
        match = {"status": "matched", "match_rule": "exact", "score": 100, "candidates": []}

        results = OPENCODE_SYNC_MODULE.model_config_from_entry(
            {"id": "example-model"},
            entry,
            match,
            "none",
            contexts=(0,),
        )

        self.assertEqual(["example-model"], [model_id for model_id, _, _ in results])

    def test_context_only_limit_does_not_invent_input_limit(self):
        entry = OPENCODE_SYNC_MODULE.CatalogEntry(
            full_id="openai/example-model",
            data={"limit": {"context": 200000, "output": 32000}},
        )
        match = {"status": "matched", "match_rule": "exact", "score": 100, "candidates": []}

        results = OPENCODE_SYNC_MODULE.model_config_from_entry(
            {"id": "example-model"},
            entry,
            match,
            "none",
            contexts=(190000,),
        )

        self.assertEqual(["example-model", "example-model (190k)"], [model_id for model_id, _, _ in results])
        self.assertEqual({"context": 190000, "output": 32000}, results[1][1]["limit"])

    def test_context_uses_total_window_even_when_input_is_smaller(self):
        entry = OPENCODE_SYNC_MODULE.CatalogEntry(
            full_id="openai/example-model",
            data={"limit": {"context": 400000, "input": 200000, "output": 128000}},
        )
        match = {"status": "matched", "match_rule": "exact", "score": 100, "candidates": []}

        results = OPENCODE_SYNC_MODULE.model_config_from_entry(
            {"id": "example-model"},
            entry,
            match,
            "none",
            contexts=(258000,),
        )

        self.assertEqual(["example-model", "example-model (258k)"], [model_id for model_id, _, _ in results])

    def test_context_cap_never_expands_original_limits(self):
        entry = OPENCODE_SYNC_MODULE.CatalogEntry(
            full_id="openai/example-model",
            data={"limit": {"context": 400000, "input": 272000, "output": 272000}},
        )
        match = {"status": "matched", "match_rule": "exact", "score": 100, "candidates": []}

        results = OPENCODE_SYNC_MODULE.model_config_from_entry(
            {"id": "example-model"},
            entry,
            match,
            "none",
            contexts=(258000,),
        )

        self.assertEqual(
            {"context": 258000, "input": 258000, "output": 258000},
            results[1][1]["limit"],
        )

    def test_context_above_original_does_not_create_duplicate_version(self):
        entry = OPENCODE_SYNC_MODULE.CatalogEntry(
            full_id="openai/example-model",
            data={"limit": {"context": 512000, "input": 400000, "output": 64000}},
        )
        match = {"status": "matched", "match_rule": "exact", "score": 100, "candidates": []}

        results = OPENCODE_SYNC_MODULE.model_config_from_entry(
            {"id": "example-model"},
            entry,
            match,
            "none",
            contexts=(1000000,),
        )

        self.assertEqual(["example-model"], [model_id for model_id, _, _ in results])

    def test_report_summary_does_not_count_limited_version_as_model(self):
        args = Namespace(
            api_key_env="NEWAPI_API_KEY",
            provider="newapi",
            variant_policy="none",
            context=(128000,),
        )
        model_reports = [
            {"model_id": "example-model", "status": "matched", "source_model": "openai/example-model"},
            {
                "model_id": "example-model (128k)",
                "status": "matched",
                "source_model": "openai/example-model",
                "capped_from": "example-model",
            },
        ]

        report = OPENCODE_SYNC_MODULE.make_report(
            args,
            "fixture",
            1,
            {"source": "fixture", "opencode_version": "fixture"},
            [],
            model_reports,
        )

        self.assertEqual(1, report["summary"]["matched"])
        self.assertEqual({"openai": 1}, report["provider_groups"])
        self.assertEqual([128000], report["contexts"])
        self.assertNotIn("context_threshold", report)
        self.assertNotIn("context_limit", report)

if __name__ == "__main__":
    unittest.main()
