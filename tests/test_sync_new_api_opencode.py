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


class ProviderPreferenceTest(unittest.TestCase):
    def entry(self, provider, model, **metadata):
        return MODULE.CatalogEntry(f"{provider}/{model}", {
            "id": model, "providerID": provider, **metadata,
        })

    def test_origin_beats_explicit_reseller_for_each_family(self):
        for model, origin in (
            ("gpt-5.4", "openai"), ("deepseek-v4-flash", "deepseek"),
            ("kimi-k2.7", "moonshotai"), ("glm-5.3", "zhipuai"),
            ("qwen3.7-plus", "alibaba"), ("claude-opus-4", "anthropic"),
            ("gemini-3-pro", "google"), ("minimax-m3", "minimax"),
        ):
            with self.subTest(model=model):
                official = self.entry(origin, model)
                reseller = self.entry("opencode", model, status="active",
                    limit={"context": 1000000, "input": 900000, "output": 100000},
                    capabilities={"reasoning": True, "toolcall": True},
                    variants={"low": {}, "high": {}})
                for prefix in ("opencode", "zen", "alibaba"):
                    selected, _ = MODULE.select_entry(f"{prefix}/{model}",
                        [reseller, self.entry("alibaba-cn", model), official], None)
                    self.assertEqual(official, selected)

    def test_alibaba_beats_other_channels_without_origin(self):
        for model in ("deepseek-v4.1-flash", "unknown-1"):
            cloud = self.entry("alibaba-cn", model)
            other = self.entry("hyper", model, limit={"context": 200000})
            selected, _ = MODULE.select_entry(f"hyper/{model}", [other, cloud], None)
            self.assertEqual(cloud, selected)

    def test_precision_and_version_are_not_overridden_by_origin(self):
        exact = self.entry("hyper", "deepseek-v4.1-flash")
        for model in ("deepseek-v4-1-flash", "deepseek-v4", "deepseek-v3"):
            selected, _ = MODULE.select_entry("deepseek-v4.1-flash",
                [self.entry("deepseek", model), exact], None)
            self.assertEqual(exact, selected)

    def test_mapping_can_pin_reseller(self):
        other = self.entry("hyper", "deepseek-v4-flash")
        selected, match = MODULE.select_entry("deepseek-v4-flash",
            [other, self.entry("deepseek", "deepseek-v4-flash")], other.full_id)
        self.assertEqual(other, selected)
        self.assertEqual("mapped", match["status"])

    def test_v41_flash_alias_overrides_exact_match(self):
        official = self.entry("deepseek", "deepseek-flash", limit={"context": 1000000, "output": 384000})
        old_version = self.entry("deepseek", "deepseek-v4-flash")
        reseller = self.entry("hyper", "deepseek-v4.1-flash", status="active")
        for model in ("deepseek-v4.1-flash", "workbuddy/deepseek-v4.1-flash", "Hyper/DeepSeek-V4.1-Flash"):
            with self.subTest(model=model):
                selected, match = MODULE.select_entry(model, [old_version, reseller, official], None)
                self.assertEqual(official, selected)
                self.assertEqual("mapped", match["status"])
                self.assertEqual("official-flash-alias", match["match_rule"])
                generated = MODULE.model_config_from_entry({"id": model}, selected, match, "translate", contexts=(0,))
                self.assertEqual(model, generated[0][0])
                self.assertEqual(official.data["limit"], generated[0][1]["limit"])
        selected, match = MODULE.select_entry("deepseek-v4.1-flash", [official, reseller], reseller.full_id)
        self.assertEqual(reseller, selected)
        self.assertEqual("mapping-file", match["match_rule"])

    def test_v41_flash_alias_missing_origin_and_scope(self):
        reseller = self.entry("hyper", "deepseek-v4.1-flash")
        old_version = self.entry("deepseek", "deepseek-v4-flash")
        selected, match = MODULE.select_entry("deepseek-v4.1-flash", [old_version, reseller], None)
        self.assertEqual(reseller, selected)
        self.assertEqual("matched", match["status"])
        official = self.entry("deepseek", "deepseek-flash")
        for model in ("deepseek-v4.1-pro", "deepseek-v4.2-flash"):
            selected, _ = MODULE.select_entry(model, [official], None)
            self.assertIsNone(selected)

    def test_v41_flash_alias_applies_to_gateway_suffixed_ids(self):
        official = self.entry("deepseek", "deepseek-flash", limit={"context": 1000000, "output": 384000})
        # A reseller that also publishes the literal V4.1 Flash ID must not win
        # merely because the gateway appended a suffix to the official alias.
        reseller = self.entry("nano-gpt", "deepseek-v4.1-flash", limit={"context": 1048576, "output": 384000})
        for model in (
            "deepseek-v4.1-flash-local",
            "workbuddy/deepseek-v4.1-flash-local",
            "WorkBuddy/DeepSeek-V4.1-Flash-local",
        ):
            with self.subTest(model=model):
                selected, match = MODULE.select_entry(model, [reseller, official], None)
                self.assertEqual(official, selected)
                self.assertEqual("mapped", match["status"])
                self.assertEqual("official-flash-alias", match["match_rule"])

    def test_v41_flash_alias_keeps_effort_suffix_orthogonal(self):
        official = self.entry("deepseek", "deepseek-flash", limit={"context": 1000000, "output": 384000})
        for model, effort in (
            ("deepseek-v4.1-flash-high", "high"),
            ("workbuddy/deepseek-v4.1-flash-max", "max"),
        ):
            with self.subTest(model=model):
                selected, match = MODULE.select_entry(model, [official], None)
                self.assertEqual(official, selected)
                self.assertEqual("official-flash-alias", match["match_rule"])
                # The effort level must stay visible; an effort-specific upstream
                # model keeps base limits without nested variants.
                self.assertEqual(effort, match["effort_suffix"])
                _, config, _ = MODULE.model_config_from_entry(
                    {"id": model}, selected, match, "translate", contexts=(0,)
                )[0]
                self.assertNotIn("variants", config)

    def test_v41_flash_alias_does_not_cross_version_or_model(self):
        official = self.entry("deepseek", "deepseek-flash")
        for model in ("deepseek-v4.1-pro", "deepseek-v4.2-flash", "deepseek-v4.1", "deepseek-flash"):
            with self.subTest(model=model):
                selected, match = MODULE.select_entry(model, [official], None)
                self.assertNotEqual("official-flash-alias", match.get("match_rule"))

    def test_api_id_can_select_official(self):
        official = self.entry("deepseek", "deepseek-chat", api={"id": "deepseek-v4"})
        selected, _ = MODULE.select_entry("hyper/deepseek-v4",
            [self.entry("hyper", "deepseek-v4"), official], None)
        self.assertEqual(official, selected)

    def test_fallback_prefers_cloud_but_preserves_specificity(self):
        cloud = self.entry("alibaba", "deepseek-v4")
        reseller = self.entry("hyper", "deepseek-v4")
        selected, match = MODULE.select_entry("hyper/deepseek-v4-flash-local", [reseller, cloud], None)
        self.assertEqual(cloud, selected)
        self.assertEqual("guessed", match["status"])
        specific = self.entry("hyper", "deepseek-v4-flash")
        selected, _ = MODULE.select_entry("deepseek-v4-flash-local", [cloud, specific], None)
        self.assertEqual(specific, selected)

    def test_false_capability_is_as_complete_as_true(self):
        yes = self.entry("hyper", "model", capabilities={"reasoning": True, "toolcall": True})
        no = self.entry("hyper", "model", capabilities={"reasoning": False, "toolcall": False})
        self.assertEqual(MODULE.metadata_completeness(yes), MODULE.metadata_completeness(no))

    def test_v_version_fallback_does_not_cross_version(self):
        selected, match = MODULE.select_entry("deepseek-v4-local",
            [self.entry("deepseek", "deepseek-v3")], None)
        self.assertIsNone(selected)
        self.assertEqual("unmatched", match["status"])


class DeepSeekThinkingTest(unittest.TestCase):
    def entries(self, reasoning=True, toggle=True, provider="deepseek"):
        return MODULE.catalog_entries_from_opencode_models({provider: {"models": {
            "deepseek-flash": {
                "reasoning": reasoning,
                "reasoning_options": ([{"type": "toggle"}] if toggle else []) + [
                    {"type": "effort", "values": ["low", "high", "max"]}],
                "interleaved": {"field": "reasoning_content"},
                "limit": {"context": 1000000, "output": 384000},
            }
        }}})

    def test_alias_enables_thinking_with_stable_ids_and_compatible_transport(self):
        for mode in ("auto-group", "openai-compatible"):
            for policy in ("translate", "compatible", "none"):
                with self.subTest(mode=mode, policy=policy):
                    args = MODULE.parse_args(["--provider", "custom.channel", "--provider-type", mode,
                                              "--variant-policy", policy])
                    mid = "gateway/deepseek-v4.1-flash"
                    fragment, reports = MODULE.build_provider_fragment(
                        args, "https://example.invalid/v1", [{"id": mid}], self.entries(), {})
                    provider = fragment["provider"]["custom.channel"]
                    self.assertEqual("@ai-sdk/openai-compatible", provider["npm"])
                    self.assertEqual(2, len(provider["models"]))
                    for key, config in provider["models"].items():
                        self.assertEqual(mid, config.get("id", key))
                        self.assertTrue(config["reasoning"])
                        self.assertEqual({"thinking": {"type": "enabled"}}, config["options"])
                        self.assertEqual({"field": "reasoning_content"}, config["interleaved"])
                        self.assertEqual([] if policy == "none" else ["high", "low", "max"],
                                         sorted(config.get("variants", {})))
                    self.assertEqual(["thinking"], reports[0]["provider_options"])

    def test_only_explicit_deepseek_toggle_is_enabled(self):
        for reasoning, toggle, provider_type, provider in (
            (False, True, "openai-compatible", "deepseek"),
            (True, False, "openai-compatible", "deepseek"),
            (True, True, "bailian", "deepseek"),
            (True, True, "openai-compatible", "openai"),
        ):
            with self.subTest(reasoning=reasoning, toggle=toggle,
                              provider_type=provider_type, provider=provider):
                entry = self.entries(reasoning, toggle, provider)[0]
                config = MODULE.model_config_from_entry(
                    {"id": "deepseek-flash"}, entry, {}, "translate", provider_type, (0,))[0][1]
                self.assertNotIn("thinking", config.get("options", {}))


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
        self.assertNotIn("input", capped_config["limit"])
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

    def test_equivalent_provider_duplicates_are_selected_deterministically(self):
        metadata = {
            "id": "mimo-v2.5",
            "limit": {"context": 262144, "output": 32768},
            "capabilities": {"reasoning": True, "toolcall": True},
            "variants": {"high": {"reasoningEffort": "high"}},
        }
        entries = [
            MODULE.CatalogEntry(
                f"xiaomi-token-plan-{region}/mimo-v2.5",
                {**metadata, "providerID": f"xiaomi-token-plan-{region}"},
            )
            for region in ("ams", "cn", "sgp")
        ]

        entry, match = MODULE.select_entry("Mimo/mimo-v2.5", entries, None)

        self.assertIsNotNone(entry)
        self.assertEqual("matched", match["status"])
        self.assertEqual("provider-prefix-stripped-equivalent-metadata", match["match_rule"])
        self.assertEqual("xiaomi-token-plan-ams/mimo-v2.5", entry.full_id)

    def test_differing_tie_metadata_inherits_the_first_candidate(self):
        entries = [
            MODULE.CatalogEntry(
                f"{provider}/deepseek-v4.1-flash",
                {
                    "id": "deepseek-v4.1-flash",
                    "providerID": provider,
                    "limit": {"context": context, "output": output},
                },
            )
            for provider, context, output in (
                ("hyper", 1048576, 26214),
                ("llmgateway", 1050000, 384000),
                ("opencode-go", 1000000, 384000),
                ("requesty", 1048576, 393216),
            )
        ]

        entry, match = MODULE.select_entry("workbuddy/deepseek-v4.1-flash", entries, None)

        self.assertIsNotNone(entry)
        self.assertEqual("hyper/deepseek-v4.1-flash", entry.full_id)
        self.assertEqual("ambiguous", match["status"])
        self.assertEqual("provider-prefix-stripped-first-candidate", match["match_rule"])
        self.assertEqual("hyper/deepseek-v4.1-flash", match["selected"])
        self.assertIn("use --mapping-file", " ".join(match["warnings"]))

    def test_differing_tie_still_reports_a_usable_limit(self):
        entries = [
            MODULE.CatalogEntry(
                f"{provider}/deepseek-v4.1-flash",
                {
                    "id": "deepseek-v4.1-flash",
                    "providerID": provider,
                    "limit": {"context": context, "output": output},
                },
            )
            for provider, context, output in (
                ("hyper", 1048576, 26214),
                ("requesty", 1048576, 393216),
            )
        ]

        entry, match = MODULE.select_entry("workbuddy/deepseek-v4.1-flash", entries, None)
        results = MODULE.model_config_from_entry(
            {"id": "workbuddy/deepseek-v4.1-flash"}, entry, match, "translate", contexts=(0,)
        )

        self.assertEqual(1, len(results))
        _, config, report = results[0]
        self.assertEqual({"context": 1048576, "output": 26214}, config["limit"])
        self.assertEqual("ambiguous", report["status"])

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
