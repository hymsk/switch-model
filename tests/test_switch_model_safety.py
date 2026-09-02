import importlib.util
from argparse import Namespace
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
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
    def test_generated_bundle_never_contains_personal_defaults_or_key_prefix_preview(self):
        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('DEFAULT_API_URL="${SWITCH_MODEL_BASE_URL:-}"', generated)
        self.assertIn('DEFAULT_OPENCODE_PROVIDER="newapi"', generated)
        self.assertNotIn("${sk:0:10}", generated)
        self.assertIn('"<redacted>"', generated)

    def test_generated_shell_requires_explicit_provider_replacement_for_opencode_write(self):
        generated = GENERATED_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--replace-providers", generated)
        self.assertIn("OPENCODE_REPLACE_PROVIDERS=false", generated)

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
        self.assertIn("--context TOKENS[,TOKENS...]", completed.stdout)
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

    def test_generated_shell_forwards_context_list(self):
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
                    "128000,258000",
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
        self.assertIn("context=128000,258000", completed.stdout)

    def test_generated_shell_rejects_invalid_context_before_opencode_main(self):
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
            for value in ("1,,2", "-1", "0,128000"):
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

    def test_context_argument_accepts_multiple_deduplicated_values(self):
        args = OPENCODE_SYNC_MODULE.parse_args(["--context", "128000, 258000,128000"])
        self.assertEqual((128000, 258000), args.context)

    def test_missing_cache_prefers_embedded_catalog_over_current_runtime_models(self):
        args = Namespace(
            catalog_file=None,
            catalog_mode="all",
            opencode_models_file=Path("/missing/models.json"),
            api_key_env="NEWAPI_API_KEY",
            opencode_bin="opencode",
            command_timeout=20,
        )
        embedded_entries = [
            OPENCODE_SYNC_MODULE.CatalogEntry(
                "openai/example-model",
                {"id": "example-model", "providerID": "openai", "limit": {"context": 1000000}},
            )
        ]

        with patch.object(OPENCODE_SYNC_MODULE, "get_opencode_version", return_value="test"), \
             patch.object(OPENCODE_SYNC_MODULE, "load_opencode_models_catalog", side_effect=OPENCODE_SYNC_MODULE.SyncError("missing")), \
             patch.object(OPENCODE_SYNC_MODULE, "load_embedded_opencode_models_catalog", return_value=embedded_entries), \
             patch.object(OPENCODE_SYNC_MODULE, "run_command") as run_command:
            entries, metadata = OPENCODE_SYNC_MODULE.acquire_catalog(args)

        self.assertEqual(embedded_entries, entries)
        self.assertEqual("embedded-opencode-models", metadata["source"])
        run_command.assert_not_called()

    def test_context_argument_rejects_zero_mixed_with_submodes(self):
        with self.assertRaises(OPENCODE_SYNC_MODULE.argparse.ArgumentTypeError):
            OPENCODE_SYNC_MODULE.parse_contexts("0,128000")

    def test_context_list_generates_multiple_submodes(self):
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
            contexts=(128000, 258000),
        )

        self.assertEqual(
            ["example-model", "example-model (128k)", "example-model (258k)"],
            [model_id for model_id, _, _ in results],
        )
        self.assertEqual(
            {"context": 128000, "input": 128000, "output": 32000},
            results[1][1]["limit"],
        )
        self.assertEqual(
            {"context": 258000, "input": 258000, "output": 32000},
            results[2][1]["limit"],
        )

    def test_context_zero_disables_submodes(self):
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

    def test_context_submode_never_expands_original_limits(self):
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

    def test_report_summary_does_not_count_context_submodes_as_models(self):
        args = Namespace(
            api_key_env="NEWAPI_API_KEY",
            provider="newapi",
            variant_policy="none",
            context=(128000, 258000),
        )
        model_reports = [
            {"model_id": "example-model", "status": "matched", "source_model": "openai/example-model"},
            {
                "model_id": "example-model (128k)",
                "status": "matched",
                "source_model": "openai/example-model",
                "capped_from": "example-model",
            },
            {
                "model_id": "example-model (258k)",
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
        self.assertEqual([128000, 258000], report["contexts"])

if __name__ == "__main__":
    unittest.main()
