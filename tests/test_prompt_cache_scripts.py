import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "audit-prompt-caching" / "scripts"


def run_script(script_name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), *map(str, args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class PromptCacheScriptsTest(unittest.TestCase):
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

    def test_skill_package_has_report_template_and_actionable_sections(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        self.assertIn("When to use", skill)
        self.assertIn("When not to use", skill)
        self.assertIn("Applicability Gate", skill)
        self.assertIn("file:line | severity | provider/engine | issue", skill)
        self.assertTrue(
            (ROOT / "audit-prompt-caching" / "references" / "report-template.md").exists()
        )


if __name__ == "__main__":
    unittest.main()
