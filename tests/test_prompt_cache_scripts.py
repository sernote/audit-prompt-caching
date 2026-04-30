import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "audit-prompt-caching" / "scripts"
FIXTURES = ROOT / "fixtures"


def run_script(script_name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class PromptCacheScriptsTest(unittest.TestCase):
    def test_fixture_pack_is_valid(self):
        expected_paths = [
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            FIXTURES / "anthropic" / "cache_control_usage.jsonl",
            FIXTURES / "bedrock" / "checkpoint_usage.jsonl",
            FIXTURES / "openrouter" / "routing_usage.jsonl",
            FIXTURES / "vllm" / "apc_deployment.json",
            FIXTURES / "expected" / "usage_summary_openai.json",
            FIXTURES / "expected" / "report_openai.md",
        ]
        for path in expected_paths:
            self.assertTrue(path.exists(), f"missing fixture: {path}")

        openai_records = load_jsonl(FIXTURES / "openai" / "repeated_prefix_usage.jsonl")
        self.assertEqual(len(openai_records), 3)
        self.assertEqual(openai_records[0]["provider"], "openai")
        self.assertIn(
            "cached_tokens",
            openai_records[1]["usage"]["input_tokens_details"],
        )

        anthropic_records = load_jsonl(
            FIXTURES / "anthropic" / "cache_control_usage.jsonl"
        )
        self.assertEqual(anthropic_records[0]["provider"], "anthropic")
        self.assertIn("cache_creation_input_tokens", anthropic_records[0]["usage"])
        self.assertIn("cache_read_input_tokens", anthropic_records[1]["usage"])

        bedrock_records = load_jsonl(FIXTURES / "bedrock" / "checkpoint_usage.jsonl")
        self.assertEqual(bedrock_records[0]["provider"], "bedrock")
        self.assertIn("CacheWriteInputTokens", bedrock_records[0]["metrics"])
        self.assertIn("CacheReadInputTokens", bedrock_records[1]["metrics"])

        openrouter_records = load_jsonl(FIXTURES / "openrouter" / "routing_usage.jsonl")
        self.assertEqual(openrouter_records[0]["provider"], "openrouter")
        self.assertIn("cache_write_tokens", openrouter_records[0]["usage"])
        self.assertIn("route", openrouter_records[0])

        vllm_fixture = json.loads((FIXTURES / "vllm" / "apc_deployment.json").read_text())
        self.assertEqual(vllm_fixture["engine"], "vllm")
        self.assertTrue(vllm_fixture["prefix_caching_enabled"])

        expected_summary = json.loads(
            (FIXTURES / "expected" / "usage_summary_openai.json").read_text()
        )
        actual_summary = json.loads(
            run_script(
                "analyze_usage_logs.py",
                FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            ).stdout
        )
        self.assertEqual(actual_summary, expected_summary)
        self.assertIn(
            "# Prompt Cache Audit",
            (FIXTURES / "expected" / "report_openai.md").read_text(),
        )

    def test_prefix_stability_check_reports_first_json_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.json"
            second = tmp_path / "second.json"
            first.write_text(
                json.dumps(
                    {
                        "system": "Stable instructions",
                        "tools": [{"name": "lookup"}, {"name": "write"}],
                        "input": "Question A",
                    }
                )
            )
            second.write_text(
                json.dumps(
                    {
                        "system": "Stable instructions",
                        "tools": [{"name": "write"}, {"name": "lookup"}],
                        "input": "Question B",
                    }
                )
            )

            result = run_script("prefix_stability_check.py", first, second)

            self.assertEqual(result.returncode, 1)
            self.assertIn("stable_prefix_bytes", result.stdout)
            self.assertIn("first_difference", result.stdout)
            self.assertIn("tools", result.stdout)

    def test_prefix_stability_check_preserves_raw_json_key_order_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.json"
            second = tmp_path / "second.json"
            first.write_text('{"schema":{"type":"object","properties":{"a":{"type":"string"}}}}')
            second.write_text('{"schema":{"properties":{"a":{"type":"string"}},"type":"object"}}')

            result = run_script("prefix_stability_check.py", first, second)

            self.assertEqual(result.returncode, 1)
            output = json.loads(result.stdout.split("\n\n", 1)[0])
            self.assertFalse(output["stable"])
            self.assertIn("byte_offset", output["first_difference"])

    def test_prefix_stability_check_can_canonicalize_json_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = tmp_path / "first.json"
            second = tmp_path / "second.json"
            first.write_text('{"schema":{"type":"object","properties":{"a":{"type":"string"}}}}')
            second.write_text('{"schema":{"properties":{"a":{"type":"string"}},"type":"object"}}')

            result = run_script(
                "prefix_stability_check.py",
                "--canonical-json",
                first,
                second,
            )

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertTrue(output["stable"])

    def test_analyze_usage_logs_summarizes_openai_and_anthropic_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "usage.jsonl"
            records = [
                {
                    "usage": {
                        "input_tokens": 2000,
                        "input_tokens_details": {"cached_tokens": 1500},
                        "output_tokens": 250,
                    }
                },
                {
                    "usage": {
                        "input_tokens": 500,
                        "cache_read_input_tokens": 300,
                        "cache_creation_input_tokens": 100,
                        "output_tokens": 50,
                    }
                },
            ]
            log_path.write_text("\n".join(json.dumps(record) for record in records))

            result = run_script("analyze_usage_logs.py", log_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["records"], 2)
            self.assertEqual(output["input_tokens"], 2500)
            self.assertEqual(output["total_input_tokens"], 2900)
            self.assertEqual(output["cached_tokens"], 1500)
            self.assertEqual(output["cache_read_input_tokens"], 300)
            self.assertEqual(output["cache_creation_input_tokens"], 100)
            self.assertEqual(output["cache_hit_ratio"], 0.6207)

    def test_analyze_usage_logs_can_emit_normalized_jsonl_events(self):
        result = run_script(
            "analyze_usage_logs.py",
            "--jsonl-normalized",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        events = [
            json.loads(line)
            for line in result.stdout.splitlines()
            if line.strip()
        ]
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["provider"], "openai")
        self.assertEqual(events[0]["model"], "gpt-5.4")
        self.assertEqual(events[0]["route"], "responses-api")
        self.assertEqual(events[0]["input_tokens"], 5200)
        self.assertEqual(events[0]["cache_read_input_tokens"], 0)
        self.assertEqual(events[0]["cache_creation_input_tokens"], 0)
        self.assertEqual(events[1]["cache_benefit_tokens"], 4600)
        self.assertEqual(events[1]["total_input_tokens"], 5200)
        self.assertEqual(events[2]["output_tokens"], 405)

    def test_analyze_usage_logs_uses_full_anthropic_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "anthropic.jsonl"
            record = {
                "usage": {
                    "input_tokens": 500,
                    "cache_read_input_tokens": 300,
                    "cache_creation_input_tokens": 200,
                    "output_tokens": 50,
                }
            }
            log_path.write_text(json.dumps(record))

            result = run_script("analyze_usage_logs.py", log_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["input_tokens"], 500)
            self.assertEqual(output["total_input_tokens"], 1000)
            self.assertEqual(output["cache_hit_ratio"], 0.3)

    def test_analyze_usage_logs_reads_csv_usage_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "usage.csv"
            with log_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["input_tokens", "cached_tokens", "output_tokens"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "input_tokens": "1000",
                        "cached_tokens": "600",
                        "output_tokens": "100",
                    }
                )
                writer.writerow(
                    {
                        "input_tokens": "1000",
                        "cached_tokens": "800",
                        "output_tokens": "100",
                    }
                )

            result = run_script("analyze_usage_logs.py", log_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["records"], 2)
            self.assertEqual(output["input_tokens"], 2000)
            self.assertEqual(output["cached_tokens"], 1400)
            self.assertEqual(output["cache_hit_ratio"], 0.7)

    def test_analyze_usage_logs_does_not_double_count_bedrock_cache_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            log_path = tmp_path / "bedrock.jsonl"
            record = {
                "metrics": {
                    "InputTokens": 1000,
                    "CacheReadInputTokens": 400,
                    "CacheWriteInputTokens": 200,
                    "OutputTokens": 100,
                }
            }
            log_path.write_text(json.dumps(record))

            result = run_script("analyze_usage_logs.py", log_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["cached_tokens"], 0)
            self.assertEqual(output["cache_read_input_tokens"], 400)
            self.assertEqual(output["total_input_tokens"], 1600)
            self.assertEqual(output["cache_hit_ratio"], 0.25)

    def test_estimate_cache_roi_outputs_cost_delta_json(self):
        result = run_script(
            "estimate_cache_roi.py",
            "--static-tokens",
            "9000",
            "--dynamic-tokens",
            "300",
            "--output-tokens",
            "2000",
            "--requests",
            "100",
            "--hit-rate",
            "0.8",
            "--input-price-per-mtok",
            "2.0",
            "--cached-input-price-per-mtok",
            "0.2",
            "--output-price-per-mtok",
            "8.0",
        )

        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["requests"], 100)
        self.assertEqual(output["input_baseline_cost"], 1.86)
        self.assertEqual(output["input_with_cache_cost"], 0.564)
        self.assertEqual(output["output_cost"], 1.6)
        self.assertEqual(output["total_baseline_cost"], 3.46)
        self.assertEqual(output["total_with_cache_cost"], 2.164)
        self.assertEqual(output["input_savings"], 1.296)
        self.assertEqual(output["total_savings_pct"], 37.46)

    def test_render_audit_report_outputs_markdown_from_usage_fixture(self):
        result = run_script(
            "render_audit_report.py",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            "--provider",
            "openai",
            "--engine",
            "Responses API",
            "--finding",
            "fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | cold request has zero cached tokens | first request pays full prefill | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# Prompt Cache Audit", result.stdout)
        self.assertIn("## Executive Summary", result.stdout)
        self.assertIn("## Findings", result.stdout)
        self.assertIn("## Expected Impact", result.stdout)
        self.assertIn("Cache hit ratio: 0.5962", result.stdout)
        self.assertIn("Measurement change: unknown", result.stdout)
        self.assertIn("Prompt behavior change: unknown", result.stdout)
        self.assertIn("Provider/routing change: unknown", result.stdout)
        self.assertIn("Confidence: low", result.stdout)
        self.assertIn("Do first: analyze usage logs and validate prefix stability", result.stdout)
        self.assertIn(
            "Do not do yet: make provider/routing changes without telemetry",
            result.stdout,
        )
        self.assertIn("cold request has zero cached tokens", result.stdout)

    def test_render_audit_report_outputs_json_from_usage_fixture(self):
        result = run_script(
            "render_audit_report.py",
            "--json",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            "--provider",
            "openai",
            "--engine",
            "Responses API",
            "--finding",
            "AP-1 | low | openai | fixture finding | impact | fix | validation",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["provider"], "openai")
        self.assertEqual(output["engine"], "Responses API")
        self.assertEqual(output["measurement_change"], "unknown")
        self.assertEqual(output["prompt_behavior_change"], "unknown")
        self.assertEqual(output["provider_routing_change"], "unknown")
        self.assertEqual(output["confidence"], "low")
        self.assertEqual(
            output["do_first"],
            "analyze usage logs and validate prefix stability",
        )
        self.assertEqual(
            output["do_not_do_yet"],
            "make provider/routing changes without telemetry",
        )
        self.assertEqual(output["usage"]["cache_hit_ratio"], 0.5962)
        self.assertEqual(output["findings"][0]["severity"], "low")

    def test_render_audit_report_preserves_extended_finding_contract(self):
        finding = " | ".join(
            [
                "app/services/llm/client.py:124",
                "medium",
                "openrouter",
                "dynamic opening message fragments route locality",
                "code shows session_id in the first user message",
                "confirmed from code",
                "medium",
                "matters when the operation has repeated long prefixes",
                "can split sticky-route cache families",
                "add observability without changing prompt behavior",
                "test a stable operation anchor on one hot path",
                "compare routed provider/model, cached_tokens, and cache_write_tokens",
                "do not add cache_control or pin providers yet",
            ]
        )
        result = run_script(
            "render_audit_report.py",
            "--json",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            "--provider",
            "openrouter",
            "--engine",
            "Chat Completions",
            "--finding",
            finding,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        parsed = output["findings"][0]
        self.assertEqual(parsed["source"], "app/services/llm/client.py:124")
        self.assertEqual(parsed["evidence"], "code shows session_id in the first user message")
        self.assertEqual(parsed["evidence_type"], "confirmed from code")
        self.assertEqual(parsed["confidence"], "medium")
        self.assertEqual(
            parsed["impact_condition"],
            "matters when the operation has repeated long prefixes",
        )
        self.assertEqual(
            parsed["safe_first_action"],
            "add observability without changing prompt behavior",
        )
        self.assertEqual(
            parsed["do_not_do_yet"],
            "do not add cache_control or pin providers yet",
        )

    def test_rendered_openai_report_matches_expected_fixture(self):
        finding = "fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | cold request has zero cached tokens | first request pays full prefill | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase"
        result = run_script(
            "render_audit_report.py",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            "--provider",
            "openai",
            "--engine",
            "Responses API",
            "--finding",
            finding,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        expected = (FIXTURES / "expected" / "report_openai.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_extract_llm_calls_finds_provider_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "src" / "llm.py"
            source.parent.mkdir()
            source.write_text(
                "\n".join(
                    [
                        "from openai import OpenAI",
                        "client = OpenAI()",
                        "def call(messages):",
                        "    return client.responses.create(model='gpt-5.4', input=messages)",
                    ]
                )
            )
            ignored = tmp_path / ".git" / "ignored.py"
            ignored.parent.mkdir()
            ignored.write_text("client.responses.create(model='gpt-5.4', input='x')")

            result = run_script("extract_llm_calls.py", tmp_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["files_scanned"], 1)
            self.assertEqual(output["matches"], 2)
            self.assertEqual(output["providers"]["openai"], 2)
            self.assertEqual(output["findings"][0]["path"], "src/llm.py")

    def test_extract_llm_calls_detects_openai_prompt_cache_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = tmp_path / "llm-config.json"
            config.write_text('{"prompt_cache_retention": "24h"}')

            result = run_script("extract_llm_calls.py", tmp_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["files_scanned"], 1)
            self.assertEqual(output["providers"]["openai"], 1)
            self.assertEqual(output["findings"][0]["path"], "llm-config.json")

    def test_extract_llm_calls_scans_dockerfile_for_vllm_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "Dockerfile").write_text(
                "\n".join(
                    [
                        'CMD ["vllm", "serve", "model"]',
                        "ARG VLLM_ARGS=--enable-prefix-caching",
                    ]
                )
            )

            result = run_script("extract_llm_calls.py", tmp_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertEqual(output["files_scanned"], 1)
            self.assertEqual(output["providers"]["vllm"], 2)
            self.assertEqual(output["findings"][0]["path"], "Dockerfile")

    def test_extract_llm_calls_matches_sglang_dash_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            compose = tmp_path / "compose.yaml"
            compose.write_text("command: sglang.launch_server\nargs: --disable-radix-cache\n")

            result = run_script("extract_llm_calls.py", tmp_path)

            self.assertEqual(result.returncode, 0)
            output = json.loads(result.stdout)
            self.assertGreaterEqual(output["providers"]["sglang"], 2)

    def test_validate_skill_package_checks_required_files_and_references(self):
        result = run_script("validate_skill_package.py", ROOT / "audit-prompt-caching")

        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertIn("SKILL.md", output["checks"])
        self.assertIn("evals", output["checks"])
        self.assertEqual(output["errors"], [])

    def test_validate_skill_package_reports_missing_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            skill_dir = tmp_path / "bad-skill"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: bad-skill",
                        "description: Use when testing bad references",
                        "---",
                        "",
                        "Load `references/missing.md`.",
                    ]
                )
            )

            result = run_script("validate_skill_package.py", skill_dir)

            self.assertEqual(result.returncode, 1)
            output = json.loads(result.stdout)
            self.assertEqual(output["status"], "error")
            self.assertEqual(output["checks"]["references"], "error")
            self.assertTrue(
                any("references/missing.md" in error for error in output["errors"])
            )

    def test_validate_skill_package_marks_eval_and_script_checks_as_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            skill_dir = tmp_path / "bad-skill"
            (skill_dir / "evals").mkdir(parents=True)
            (skill_dir / "scripts").mkdir()
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: bad-skill",
                        "description: Use when testing bad package",
                        "---",
                    ]
                )
            )
            (skill_dir / "evals" / "broken.json").write_text("{")
            (skill_dir / "scripts" / "broken.py").write_text("def nope(:\n")

            result = run_script("validate_skill_package.py", skill_dir)

            self.assertEqual(result.returncode, 1)
            output = json.loads(result.stdout)
            self.assertEqual(output["checks"]["evals"], "error")
            self.assertEqual(output["checks"]["scripts"], "error")

    def test_run_trigger_eval_summarizes_coverage(self):
        result = run_script("run_trigger_eval.py", ROOT / "audit-prompt-caching")

        self.assertEqual(result.returncode, 0)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertGreater(output["positive_cases"], 0)
        self.assertGreater(output["negative_cases"], 0)
        self.assertEqual(output["errors"], [])

    def test_rules_reference_is_machine_readable(self):
        path = ROOT / "audit-prompt-caching" / "references" / "rules.json"

        self.assertTrue(path.exists(), "missing machine-readable rules.json")
        data = json.loads(path.read_text())
        rules = {rule["id"]: rule for rule in data["rules"]}
        for rule_id in ("AP-1", "AP-2", "AP-7"):
            self.assertIn(rule_id, rules)
        for rule in data["rules"]:
            for key in (
                "id",
                "category",
                "default_severity",
                "summary",
                "validation",
            ):
                self.assertIn(key, rule)
            self.assertIn(
                rule["default_severity"],
                ("critical", "high", "medium", "low"),
            )

    def test_layout_linter_flags_bad_prompt_layout(self):
        result = run_script(
            "layout_linter.py",
            FIXTURES / "layout" / "bad_openai_request.json",
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "findings")
        rule_ids = {finding["rule_id"] for finding in output["findings"]}
        self.assertIn("AP-1", rule_ids)
        self.assertIn("AP-2", rule_ids)

    def test_layout_linter_passes_good_prompt_layout(self):
        result = run_script(
            "layout_linter.py",
            FIXTURES / "layout" / "good_openai_request.json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["findings"], [])
        self.assertIn("AP-1", output["clean_checks"])
        self.assertIn("AP-2", output["clean_checks"])

    def test_productization_files_cover_ci_and_governance(self):
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        license_path = ROOT / "LICENSE"
        contributing_path = ROOT / "CONTRIBUTING.md"

        self.assertTrue(ci_path.exists(), "missing GitHub Actions CI workflow")
        self.assertTrue(license_path.exists(), "missing repository license")
        self.assertTrue(contributing_path.exists(), "missing contribution guide")

        ci = ci_path.read_text()
        for expected in (
            "python3 -m unittest tests/test_prompt_cache_scripts.py",
            "validate_skill_package.py audit-prompt-caching",
            "run_trigger_eval.py audit-prompt-caching",
            "compile(path.read_text()",
            "fetch-depth: 0",
            "git diff --check \"${BASE_SHA}...HEAD\"",
            "git diff-tree --check --no-commit-id --root -r HEAD",
            "find . \\( -name __pycache__ -o -name '*.pyc' \\) -print",
        ):
            self.assertIn(expected, ci)
        self.assertNotIn("rm -rf", ci)

    def test_install_script_installs_full_skill_from_local_source(self):
        installer = ROOT / "install.sh"

        with tempfile.TemporaryDirectory() as tmp:
            install_parent = Path(tmp) / "skills"

            result = subprocess.run(
                [
                    "bash",
                    str(installer),
                    "--source-dir",
                    str(ROOT),
                    "--dir",
                    str(install_parent),
                    "--force",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            installed = install_parent / "audit-prompt-caching"
            for required in [
                "SKILL.md",
                "references/openai.md",
                "scripts/analyze_usage_logs.py",
                "evals/evals.json",
            ]:
                self.assertTrue(
                    (installed / required).exists(),
                    f"missing installed path: {required}",
                )
            self.assertIn(str(installed), result.stdout)

    def test_install_script_refuses_existing_target_without_force(self):
        installer = ROOT / "install.sh"

        with tempfile.TemporaryDirectory() as tmp:
            install_parent = Path(tmp) / "skills"
            existing = install_parent / "audit-prompt-caching"
            existing.mkdir(parents=True)
            marker = existing / "user-file.txt"
            marker.write_text("keep me")

            result = subprocess.run(
                [
                    "bash",
                    str(installer),
                    "--source-dir",
                    str(ROOT),
                    "--dir",
                    str(install_parent),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), "keep me")
            self.assertIn("--force", result.stderr)

    def test_install_script_exposes_simple_install_contract(self):
        installer = ROOT / "install.sh"
        readme = (ROOT / "README.md").read_text()

        self.assertTrue(installer.exists(), "missing install.sh")
        syntax = subprocess.run(
            ["bash", "-n", str(installer)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

        install_text = installer.read_text()
        for expected in [
            "--agent codex",
            "--agent claude",
            "--agent both",
            "--dir",
            "--source-dir",
            "--force",
            "~/.codex/skills/audit-prompt-caching",
        ]:
            self.assertIn(expected, install_text)

        self.assertIn(
            "npx skills add https://github.com/sernote/audit-prompt-caching --skill audit-prompt-caching",
            readme,
        )
        self.assertNotIn("Manual Install", readme)
        self.assertNotIn("raw.githubusercontent.com/sernote/audit-prompt-caching/main/install.sh", readme)

    def test_readme_demo_uses_successful_linter_command(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn("fixtures/layout/good_openai_request.json", readme)
        self.assertNotIn(
            "python3 audit-prompt-caching/scripts/layout_linter.py \\\n"
            "  fixtures/layout/bad_openai_request.json",
            readme,
        )

    def test_readme_front_door_has_adoption_assets(self):
        readme = (ROOT / "README.md").read_text()

        for required in [
            "[![CI]",
            "LLM Cache Audit Skill",
            "Why This Exists",
            "Quick Start",
            "Audit Hero Shot",
            "LLM CACHE AUDIT",
            "Fixture Signal",
            "Cache Flow",
            "Positioning",
            "59.62%",
            "$34.60 -> $23.10",
            "git clone --depth 1",
        ]:
            self.assertIn(required, readme)
        self.assertNotIn("Prompt Cache Doctor", readme)

    def test_readme_examples_cover_non_obvious_audit_scenarios(self):
        readme = (ROOT / "README.md").read_text()

        for required in [
            "OpenAI-compatible wrapper ambiguity",
            "Claude automatic caching writes every request",
            "Bedrock Converse cross-region cachePoint",
            "MCP tool registry drift",
            "vLLM/SGLang multi-replica KV",
            "High cached tokens, low savings",
        ]:
            self.assertIn(required, readme)

    def test_skill_description_has_stronger_trigger_surface(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "Use whenever the user mentions",
            "LLM cost or speed regressed",
            "repeated long prompts",
            "speeding up agents",
        ]:
            self.assertIn(required, skill)

    def test_skill_triggers_on_llm_request_shape_changes(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "LLM request shape",
            "prompt text",
            "message order",
            "request builders",
            "provider API surface",
            "model/router settings",
            "context compaction",
            "repeated long prompts, TTFT, cached-token telemetry, or LLM cost",
            "ordinary short prompt edits",
        ]:
            self.assertIn(required, skill)

    def test_skill_defines_explicit_review_default(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "Explicit Review Default",
            'asks only "review"',
            "cache-focused review",
            "Do not perform a general code review",
        ]:
            self.assertIn(required, skill)

    def test_trigger_eval_covers_request_shape_change_cases(self):
        trigger_eval = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "trigger_eval.json").read_text()
        )
        queries = "\n".join(item["query"] for item in trigger_eval)

        for required in [
            "PR only changes the system prompt wording",
            "moved the shared policy document after the user question",
            "changes tool registry order and response_format serialization",
            "switched from direct Anthropic to OpenRouter",
            "scaled vLLM pods and did not touch prompts",
            "LLM cost increased after an agent refactor",
            "Rewrite this short greeting prompt",
        ]:
            self.assertIn(required, queries)

    def test_evals_cover_explicit_review_request(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        trigger_eval = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "trigger_eval.json").read_text()
        )
        prompts = "\n".join(item["prompt"] for item in evals["evals"])
        expected = "\n".join(item["expected_output"] for item in evals["evals"])
        trigger_queries = "\n".join(item["query"] for item in trigger_eval)

        self.assertIn("Use $audit-prompt-caching. Сделай ревью.", prompts)
        self.assertIn("cache-focused review", expected)
        self.assertIn("not a general code review", expected)
        self.assertIn("Use $audit-prompt-caching. Сделай ревью.", trigger_queries)

    def test_skill_package_has_report_template_and_actionable_sections(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        self.assertIn("When to use", skill)
        self.assertIn("When not to use", skill)
        self.assertIn("Applicability Gate", skill)
        self.assertIn("extract_llm_calls.py", skill)
        self.assertIn("validate_skill_package.py", skill)
        self.assertIn("run_trigger_eval.py", skill)
        self.assertIn("file:line | severity | provider/engine | issue", skill)
        self.assertTrue(
            (ROOT / "audit-prompt-caching" / "references" / "report-template.md").exists()
        )

    def test_skill_has_agent_first_contracts_and_playbooks(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "Agent-First Output Contracts",
            "Quick triage",
            "Code audit findings",
            "Provider migration risk",
            "Agent loop audit",
            "Not worth caching",
            "Audit Playbooks",
            "OpenAI cached_tokens=0",
            "Claude/Bedrock/OpenRouter writes without reads",
            "Dynamic tools in long agent loops",
            "High hit rate but no savings",
            "OpenAI-compatible wrapper ambiguity",
            "Agent-First Quality Bar",
        ]:
            self.assertIn(required, skill)

    def test_report_template_covers_agent_first_outputs(self):
        template = (
            ROOT / "audit-prompt-caching" / "references" / "report-template.md"
        ).read_text()

        for required in [
            "Output Contract Selector",
            "Measurement change",
            "Prompt behavior change",
            "Provider/routing change",
            "Evidence Needed Next",
            "evidence_type",
            "do_not_do_yet",
            "Agent Loop Audit",
            "Not Worth Caching",
        ]:
            self.assertIn(required, template)

    def test_agent_first_evals_cover_project_change_and_wrapper_decisions(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        combined_prompts = "\n".join(item["prompt"] for item in evals["evals"])
        combined_expected = "\n".join(item["expected_output"] for item in evals["evals"])

        for required in [
            "new OpenAI prompt caching docs",
            "Do we need to change the project",
            "OpenAI-compatible",
            "prompt_cache_key",
            "MCP tool registry",
            "not worth changing the cache setup",
        ]:
            self.assertIn(required, combined_prompts + "\n" + combined_expected)

    def test_anthropic_reference_covers_current_prompt_cache_semantics(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "anthropic.md"
        ).read_text()

        for required in [
            "Automatic caching",
            "top-level",
            "Explicit cache breakpoints",
            "20-block lookback",
            "dynamic suffix",
            'ttl": "1h"',
            "longer TTL",
            "thinking blocks",
            "workspace-level isolation",
        ]:
            self.assertIn(required, reference)

    def test_openai_reference_covers_current_prompt_cache_semantics(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "openai.md"
        ).read_text()

        for required in [
            "prefix hash",
            "prompt_cache_key",
            "15 requests per minute",
            "prompt_cache_retention",
            "in_memory",
            '"24h"',
            "gpt-5.5",
            "Zero Data Retention",
            "Regional Inference",
            "TPM rate limits",
            "GPU-local storage",
        ]:
            self.assertIn(required, reference)


if __name__ == "__main__":
    unittest.main()
