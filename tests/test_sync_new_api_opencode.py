#!/usr/bin/env python3

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "python" / "sync_new_api_opencode.py"
SPEC = importlib.util.spec_from_file_location("switch_model_sync", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PrefixFallbackTest(unittest.TestCase):
    def setUp(self):
        self.glm52 = MODULE.CatalogEntry(
            "zhipuai/glm-5.2",
            {
                "id": "glm-5.2",
                "providerID": "zhipuai",
                "limit": {"context": 1000000, "output": 131072},
                "capabilities": {"reasoning": True, "toolcall": True},
                "variants": {"high": {"reasoningEffort": "high"}},
            },
        )
        self.glm53 = MODULE.CatalogEntry(
            "zhipuai/glm-5.3",
            {
                "id": "glm-5.3",
                "providerID": "zhipuai",
                "limit": {"context": 512000, "output": 65536},
                "capabilities": {"reasoning": True, "toolcall": True},
                "variants": {"high": {"reasoningEffort": "high"}},
            },
        )
        self.glm53LessComplete = MODULE.CatalogEntry(
            "zai/glm-5.3",
            {"id": "glm-5.3", "providerID": "zai"},
        )
        self.entries = [self.glm52, self.glm53LessComplete, self.glm53]

    def test_exact_match_remains_matched(self):
        entry, match = MODULE.select_entry("GLM-5.2", self.entries, None)

        self.assertEqual(self.glm52, entry)
        self.assertEqual("matched", match["status"])
        self.assertNotEqual("prefix-fallback", match["match_rule"])

    def test_bare_glm_exact_match_ignores_case_and_prefers_official_provider(self):
        official = MODULE.CatalogEntry("zhipuai/glm-5.2", {"id": "glm-5.2", "providerID": "zhipuai"})
        alternate = MODULE.CatalogEntry(
            "zai/glm-5.2",
            {
                "id": "glm-5.2",
                "providerID": "zai",
                "limit": {"context": 1000000, "input": 900000, "output": 131072},
                "capabilities": {"reasoning": True},
                "variants": {"high": {"reasoningEffort": "high"}, "max": {"reasoningEffort": "max"}},
            },
        )

        for model_id in ("GLM-5.2", "glm-5.2", "GlM-5.2"):
            entry, match = MODULE.select_entry(model_id, [alternate, official], None)
            self.assertEqual(official, entry)
            self.assertEqual("matched", match["status"])
            self.assertEqual("model-id-exact", match["match_rule"])

    def test_custom_suffix_uses_most_specific_metadata_rich_prefix(self):
        entry, match = MODULE.select_entry("glm-5.3-flash-local", self.entries, None)

        self.assertEqual(self.glm53, entry)
        self.assertEqual("guessed", match["status"])
        self.assertEqual("prefix-fallback", match["match_rule"])
        self.assertEqual(2, match["prefix_segments"])

        generated = MODULE.model_config_from_entry(
            {"id": "glm-5.3-flash-local"}, entry, match, "translate", contexts=(258000,)
        )
        original_id, original_config, _ = generated[0]
        capped_id, capped_config, capped_report = generated[1]
        self.assertEqual("glm-5.3-flash-local", original_id)
        self.assertEqual({"context": 512000, "output": 65536}, original_config["limit"])
        self.assertTrue(original_config["reasoning"])
        self.assertTrue(original_config["tool_call"])
        self.assertEqual("glm-5.3-flash-local (258k)", capped_id)
        self.assertEqual("glm-5.3-flash-local", capped_config["id"])
        self.assertEqual(258000, capped_config["limit"]["context"])
        self.assertEqual("guessed", capped_report["status"])

    def test_custom_glm_suffix_prefers_official_provider_over_metadata(self):
        official = MODULE.CatalogEntry("zhipuai/glm-5.3-flash", {"id": "glm-5.3-flash", "providerID": "zhipuai"})
        alternate = MODULE.CatalogEntry(
            "nano-gpt/z-ai/glm-5.3-flash",
            {
                "id": "glm-5.3-flash",
                "providerID": "nano-gpt",
                "limit": {"context": 512000, "input": 500000, "output": 65536},
                "capabilities": {"reasoning": True},
                "variants": {"high": {"reasoningEffort": "high"}, "max": {"reasoningEffort": "max"}},
            },
        )

        entry, match = MODULE.select_entry("glm-5.3-flash-local", [alternate, official], None)

        self.assertEqual(official, entry)
        self.assertEqual("guessed", match["status"])
        self.assertEqual("prefix-fallback", match["match_rule"])

    def test_fallback_can_be_disabled(self):
        entry, match = MODULE.select_entry("glm-5.3-flash-local", self.entries, None, prefix_fallback=False)

        self.assertIsNone(entry)
        self.assertEqual("unmatched", match["status"])

    def test_no_prefix_fallback_option_disables_the_feature(self):
        args = MODULE.parse_args([
            "--base-url", "https://new-api.example.com",
            "--models-file", "models.json",
            "--no-prefix-fallback",
        ])

        self.assertFalse(args.prefix_fallback)

    def test_mapping_takes_priority_over_prefix_fallback(self):
        entry, match = MODULE.select_entry("glm-5.3-flash-local", self.entries, "zhipuai/glm-5.2")

        self.assertEqual(self.glm52, entry)
        self.assertEqual("mapped", match["status"])

    def test_fallback_does_not_cross_major_version(self):
        entry, match = MODULE.select_entry("glm-4.9-flash-local", self.entries, None)

        self.assertIsNone(entry)
        self.assertEqual("unmatched", match["status"])

    def test_fallback_requires_a_version_segment(self):
        entry, match = MODULE.select_entry(
            "glm-flash-local",
            [MODULE.CatalogEntry("zhipuai/glm-flash", {"id": "glm-flash", "providerID": "zhipuai"})],
            None,
        )

        self.assertIsNone(entry)
        self.assertEqual("unmatched", match["status"])

    def test_report_counts_guessed_models(self):
        entry, match = MODULE.select_entry("glm-5.3-flash-local", self.entries, None)
        _, _, report = MODULE.model_config_from_entry(
            {"id": "glm-5.3-flash-local"}, entry, match, "translate", contexts=(0,)
        )[0]
        args = MODULE.parse_args([
            "--base-url", "https://new-api.example.com",
            "--models-file", "models.json",
        ])

        generated = MODULE.make_report(args, "fixture", 1, {}, self.entries, [report])

        self.assertEqual(1, generated["summary"]["guessed"])
        self.assertEqual(0, generated["summary"]["unmatched"])


if __name__ == "__main__":
    unittest.main()
