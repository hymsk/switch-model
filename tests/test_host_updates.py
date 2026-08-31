import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "python"


class HostUpdateTests(unittest.TestCase):
    def test_codex_config_adds_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text('approval_policy = "on-request"\n', encoding="utf-8")
            completed = subprocess.run(
                (
                    sys.executable,
                    str(PYTHON / "codex_config.py"),
                    "https://api.example.com",
                    "example-model",
                    str(config),
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            content = config.read_text(encoding="utf-8")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn('model_provider = "newapi"', content)
        self.assertIn('model = "example-model"', content)
        self.assertIn('[model_providers.newapi]', content)
        self.assertIn('base_url = "https://api.example.com/v1"', content)
        self.assertIn('approval_policy = "on-request"', content)

    def test_codex_auth_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = Path(directory) / "auth.json"
            environment = dict(os.environ)
            environment.update(
                SWITCH_MODEL_API_KEY="test-key-not-real",
                SWITCH_MODEL_AUTH_PATH=str(auth),
            )
            completed = subprocess.run(
                (sys.executable, str(PYTHON / "codex_auth.py")),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(auth.read_text(encoding="utf-8"))
            mode = auth.stat().st_mode & 0o777

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("test-key-not-real", payload["OPENAI_API_KEY"])
        self.assertEqual(0o600, mode)


if __name__ == "__main__":
    unittest.main()
