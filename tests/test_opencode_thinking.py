"""Opt-in host wire test: SWITCH_MODEL_OPENCODE_BIN=/path/to/opencode.

Uses an isolated HOME and a loopback mock; never contacts a model service.
"""

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import test_sync_new_api_opencode as fixtures

MODULE = fixtures.MODULE


@unittest.skipUnless(os.environ.get("SWITCH_MODEL_OPENCODE_BIN"), "requires opt-in OpenCode binary")
class OpenCodeThinkingWireTest(unittest.TestCase):
    def test_host_sends_thinking_and_selected_effort_and_reads_reasoning(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for delta, finish in (({"role": "assistant", "reasoning_content": "mock reasoning"}, None),
                                      ({"content": "mock answer"}, None), ({}, "stop")):
                    chunk = {"id": "mock", "object": "chat.completion.chunk", "created": 0,
                             "model": body["model"],
                             "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                args = MODULE.parse_args(["--provider", "custom.channel", "--omit-api-key-option"])
                mid = "gateway/deepseek-v4.1-flash"
                fragment, _ = MODULE.build_provider_fragment(
                    args, f"http://127.0.0.1:{server.server_port}/v1", [{"id": mid}],
                    fixtures.DeepSeekThinkingTest().entries(), {})
                fragment["provider"]["custom.channel"]["options"]["apiKey"] = "mock-only"
                fragment["enabled_providers"] = ["custom.channel"]
                fragment["permission"] = "deny"
                config = home / "config.json"
                config.write_text(json.dumps(fragment))
                env = {key: os.environ[key] for key in ("PATH", "LANG") if key in os.environ}
                env.update({"HOME": directory, "XDG_CONFIG_HOME": str(home / "config"),
                            "XDG_CACHE_HOME": str(home / "cache"), "XDG_DATA_HOME": str(home / "data"),
                            "XDG_STATE_HOME": str(home / "state"), "OPENCODE_CONFIG": str(config),
                            "OPENCODE_DISABLE_MODELS_FETCH": "true", "OPENCODE_DISABLE_AUTOUPDATE": "true"})
                for suffix, effort in (("", None), (" (258k)", "max")):
                    previous_count = len(requests)
                    command = [os.environ["SWITCH_MODEL_OPENCODE_BIN"], "run", "--pure", "--thinking", "--format", "json",
                               "--model", f"custom.channel/{mid}{suffix}"]
                    if effort:
                        command += ["--variant", effort]
                    result = subprocess.run(command + ["Reply with mock answer."], cwd=home, env=env,
                                            capture_output=True, text=True, timeout=60)
                    self.assertEqual(0, result.returncode, result.stderr[-2000:])
                    self.assertGreater(len(requests), previous_count,
                                       result.stdout[-2000:] + result.stderr[-2000:])
                    body = requests[-1]
                    self.assertEqual(mid, body["model"])
                    self.assertEqual({"type": "enabled"}, body.get("thinking"))
                    if effort:
                        self.assertEqual(effort, body.get("reasoning_effort"))
                    self.assertIn("mock reasoning", result.stdout)
                    self.assertIn("mock answer", result.stdout)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
