import csv
import importlib.util
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


def load_script_module(script_name):
    """Import a script for module-level assertions without writing bytecode."""
    path = SCRIPTS / script_name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


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
        self.assertEqual(events[0]["schema_version"], 1)
        self.assertEqual(
            events[0]["source_fields"],
            {
                "input_tokens": "usage.input_tokens",
                "cached_tokens": "usage.input_tokens_details.cached_tokens",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": None,
                "output_tokens": "usage.output_tokens",
            },
        )
        self.assertEqual(events[0]["denominator_status"], "valid")

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

    def test_analyze_usage_logs_reads_bedrock_converse_lower_camel_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "bedrock-converse.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "bedrock",
                        "metrics": {"latencyMs": 42},
                        "usage": {
                            "inputTokens": 1000,
                            "cacheReadInputTokens": 400,
                            "cacheWriteInputTokens": 200,
                            "outputTokens": 100,
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1000)
        self.assertEqual(output["cache_read_input_tokens"], 400)
        self.assertEqual(output["cache_creation_input_tokens"], 200)
        self.assertEqual(output["total_input_tokens"], 1600)
        self.assertEqual(output["accounting_semantics"], "additive")

    def test_analyze_usage_logs_inferrs_unlabeled_bedrock_converse_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "bedrock-converse-raw.json"
            log_path.write_text(
                json.dumps(
                    {
                        "usage": {
                            "inputTokens": 1000,
                            "cacheReadInputTokens": 400,
                            "cacheWriteInputTokens": 200,
                            "outputTokens": 100,
                        }
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1000)
        self.assertEqual(output["cache_read_input_tokens"], 400)
        self.assertEqual(output["cache_creation_input_tokens"], 200)
        self.assertEqual(output["total_input_tokens"], 1600)
        self.assertEqual(output["accounting_semantics"], "additive")
        self.assertEqual(output["warnings"], [])

    def test_analyze_usage_logs_reads_gemini_interactions_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "gemini-interactions.json"
            log_path.write_text(
                json.dumps(
                    {
                        "usage": {
                            "total_cached_tokens": 600,
                            "total_input_tokens": 1000,
                            "total_output_tokens": 100,
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1000)
        self.assertEqual(output["cached_tokens"], 600)
        self.assertEqual(output["output_tokens"], 100)
        self.assertEqual(output["total_input_tokens"], 1000)
        self.assertEqual(output["accounting_semantics"], "inclusive")
        self.assertEqual(output["warnings"], [])

    def test_analyze_usage_logs_accepts_gemini_interactions_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "gemini-interactions-miss.json"
            log_path.write_text(
                json.dumps(
                    {
                        "object": "interaction",
                        "usage": {
                            "total_cached_tokens": 0,
                            "total_input_tokens": 1000,
                            "total_output_tokens": 100,
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1000)
        self.assertEqual(output["cached_tokens"], 0)
        self.assertEqual(output["output_tokens"], 100)
        self.assertEqual(output["accounting_semantics"], "inclusive")
        self.assertEqual(output["warnings"], [])

    def test_analyze_usage_logs_reads_gemini_interactions_stream_total_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "gemini-interactions-stream.jsonl"
            log_path.write_text(
                json.dumps(
                    {
                        "event_type": "step.stop",
                        "metadata": {
                            "total_usage": {
                                "total_cached_tokens": 600,
                                "total_input_tokens": 1000,
                                "total_output_tokens": 100,
                            }
                        },
                    }
                )
            )

            result = run_script(
                "analyze_usage_logs.py", "--jsonl-normalized", log_path
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        event = json.loads(result.stdout)
        self.assertEqual(event["provider"], "gemini")
        self.assertEqual(event["input_tokens"], 1000)
        self.assertEqual(event["cached_tokens"], 600)
        self.assertEqual(event["output_tokens"], 100)
        self.assertEqual(event["total_input_tokens"], 1000)
        self.assertEqual(event["accounting_semantics"], "inclusive")
        self.assertEqual(event["warnings"], [])

    def test_analyze_usage_logs_preserves_gemini_generate_content_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "gemini-generate-content.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "gemini",
                        "usageMetadata": {
                            "promptTokenCount": 1000,
                            "cachedContentTokenCount": 600,
                            "candidatesTokenCount": 100,
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1000)
        self.assertEqual(output["cached_tokens"], 600)
        self.assertEqual(output["output_tokens"], 100)
        self.assertEqual(output["total_input_tokens"], 1000)
        self.assertEqual(output["accounting_semantics"], "inclusive")
        self.assertEqual(output["warnings"], [])

    def test_analyze_usage_logs_reads_flat_gemini_generate_content_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "gemini-generate-content-flat.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "gemini",
                        "prompt_token_count": 1000,
                        "cached_content_token_count": 600,
                        "candidates_token_count": 100,
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1000)
        self.assertEqual(output["cached_tokens"], 600)
        self.assertEqual(output["output_tokens"], 100)
        self.assertEqual(output["total_input_tokens"], 1000)
        self.assertEqual(output["accounting_semantics"], "inclusive")
        self.assertEqual(output["warnings"], [])

    def test_analyze_usage_logs_counts_openai_cache_writes_as_inclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "usage.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "usage": {
                            "input_tokens": 1000,
                            "input_tokens_details": {
                                "cached_tokens": 600,
                                "cache_write_tokens": 200,
                            },
                            "output_tokens": 50,
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["total_input_tokens"], 1000)
        self.assertEqual(output["cache_benefit_tokens"], 600)
        self.assertEqual(output["cache_write_tokens"], 200)
        self.assertEqual(output["cache_write_total_tokens"], 200)
        self.assertEqual(output["accounting_semantics"], "inclusive")
        self.assertEqual(output["warnings"], [])

    def test_analyze_usage_logs_reads_openai_chat_usage_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "usage.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "usage": {
                            "prompt_tokens": 1200,
                            "prompt_tokens_details": {
                                "cached_tokens": 700,
                                "cache_write_tokens": 300,
                            },
                            "completion_tokens": 80,
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["input_tokens"], 1200)
        self.assertEqual(output["cached_tokens"], 700)
        self.assertEqual(output["cache_write_tokens"], 300)
        self.assertEqual(output["output_tokens"], 80)
        self.assertEqual(output["total_input_tokens"], 1200)

    def test_analyze_usage_logs_reads_flat_openai_cache_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "usage.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "input_tokens": 1000,
                        "cached_tokens": 600,
                        "cache_write_tokens": 200,
                        "output_tokens": 50,
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["cached_tokens"], 600)
        self.assertEqual(output["cache_write_tokens"], 200)
        self.assertEqual(output["total_input_tokens"], 1000)
        self.assertEqual(output["accounting_semantics"], "inclusive")

    def test_analyze_usage_logs_marks_wrapper_accounting_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "usage.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "openrouter",
                        "usage": {
                            "input_tokens": 1000,
                            "cached_tokens": 600,
                            "cache_write_tokens": 200,
                            "output_tokens": 50,
                        },
                    }
                )
            )

            default = run_script("analyze_usage_logs.py", log_path)
            additive = run_script(
                "analyze_usage_logs.py",
                "--accounting-mode",
                "additive",
                log_path,
            )

        self.assertEqual(default.returncode, 0, default.stderr)
        default_output = json.loads(default.stdout)
        self.assertEqual(default_output["total_input_tokens"], 1000)
        self.assertEqual(default_output["accounting_semantics"], "ambiguous")
        self.assertEqual(
            default_output["warnings"][0]["code"],
            "AMBIGUOUS_ACCOUNTING_SEMANTICS",
        )
        self.assertEqual(additive.returncode, 0, additive.stderr)
        additive_output = json.loads(additive.stdout)
        self.assertEqual(additive_output["total_input_tokens"], 1800)
        self.assertEqual(additive_output["accounting_semantics"], "additive")

    def test_analyze_usage_logs_warns_when_openai_breakdown_exceeds_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "usage.json"
            log_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "usage": {
                            "input_tokens": 100,
                            "input_tokens_details": {"cache_write_tokens": 120},
                        },
                    }
                )
            )

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["total_input_tokens"], 100)
        self.assertEqual(
            output["warnings"][0]["code"],
            "OPENAI_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )
        self.assertEqual(output["denominator_status"], "invalid")
        self.assertNotIn("schema_version", output)

    def normalized_event(self, record, *args, name="usage.json"):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / name
            log_path.write_text(json.dumps(record))
            result = run_script(
                "analyze_usage_logs.py", "--jsonl-normalized", *args, log_path
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_analyze_usage_logs_reports_openai_chat_usage_provenance(self):
        event = self.normalized_event(
            {
                "provider": "openai",
                "usage": {
                    "prompt_tokens": 1200,
                    "prompt_tokens_details": {
                        "cached_tokens": 700,
                        "cache_write_tokens": 300,
                    },
                    "completion_tokens": 80,
                },
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "usage.prompt_tokens",
                "cached_tokens": "usage.prompt_tokens_details.cached_tokens",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": "usage.prompt_tokens_details.cache_write_tokens",
                "output_tokens": "usage.completion_tokens",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_anthropic_usage_provenance(self):
        event = self.normalized_event(
            {
                "usage": {
                    "input_tokens": 500,
                    "cache_read_input_tokens": 300,
                    "cache_creation_input_tokens": 200,
                    "output_tokens": 50,
                }
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "usage.input_tokens",
                "cached_tokens": None,
                "cache_read_input_tokens": "usage.cache_read_input_tokens",
                "cache_creation_input_tokens": "usage.cache_creation_input_tokens",
                "cache_write_tokens": None,
                "output_tokens": "usage.output_tokens",
            },
        )
        self.assertEqual(event["accounting_semantics"], "additive")
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_bedrock_metrics_provenance(self):
        event = self.normalized_event(
            {
                "metrics": {
                    "InputTokens": 1000,
                    "CacheReadInputTokens": 400,
                    "CacheWriteInputTokens": 200,
                    "OutputTokens": 100,
                }
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "metrics.InputTokens",
                "cached_tokens": None,
                "cache_read_input_tokens": "metrics.CacheReadInputTokens",
                "cache_creation_input_tokens": "metrics.CacheWriteInputTokens",
                "cache_write_tokens": None,
                "output_tokens": "metrics.OutputTokens",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_bedrock_converse_provenance(self):
        event = self.normalized_event(
            {
                "provider": "bedrock",
                "metrics": {"latencyMs": 42},
                "usage": {
                    "inputTokens": 1000,
                    "cacheReadInputTokens": 400,
                    "cacheWriteInputTokens": 200,
                    "outputTokens": 100,
                },
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "usage.inputTokens",
                "cached_tokens": None,
                "cache_read_input_tokens": "usage.cacheReadInputTokens",
                "cache_creation_input_tokens": "usage.cacheWriteInputTokens",
                "cache_write_tokens": None,
                "output_tokens": "usage.outputTokens",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_gemini_interactions_provenance(self):
        event = self.normalized_event(
            {
                "event_type": "step.stop",
                "metadata": {
                    "total_usage": {
                        "total_cached_tokens": 600,
                        "total_input_tokens": 1000,
                        "total_output_tokens": 100,
                    }
                },
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "metadata.total_usage.total_input_tokens",
                "cached_tokens": "metadata.total_usage.total_cached_tokens",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": None,
                "output_tokens": "metadata.total_usage.total_output_tokens",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_gemini_generate_content_provenance(self):
        event = self.normalized_event(
            {
                "provider": "gemini",
                "usageMetadata": {
                    "promptTokenCount": 1000,
                    "cachedContentTokenCount": 600,
                    "candidatesTokenCount": 100,
                },
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "usageMetadata.promptTokenCount",
                "cached_tokens": "usageMetadata.cachedContentTokenCount",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": None,
                "output_tokens": "usageMetadata.candidatesTokenCount",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_nested_wrapper_provenance(self):
        record = {
            "provider": "openrouter",
            "data": {
                "usage": {
                    "prompt_tokens": 1000,
                    "cached_tokens": 600,
                    "completion_tokens": 50,
                }
            },
        }

        event = self.normalized_event(record)
        overridden = self.normalized_event(record, "--accounting-mode", "inclusive")

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "data.usage.prompt_tokens",
                "cached_tokens": "data.usage.cached_tokens",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": None,
                "output_tokens": "data.usage.completion_tokens",
            },
        )
        self.assertEqual(event["accounting_semantics"], "ambiguous")
        self.assertEqual(event["denominator_status"], "ambiguous")
        self.assertEqual(overridden["accounting_semantics"], "inclusive")
        self.assertEqual(overridden["denominator_status"], "valid")

    def test_analyze_usage_logs_marks_inclusive_contradiction_invalid(self):
        event = self.normalized_event(
            {
                "provider": "gemini",
                "usageMetadata": {
                    "promptTokenCount": 1000,
                    "cachedContentTokenCount": 1200,
                    "candidatesTokenCount": 100,
                },
            }
        )

        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(
            event["warnings"][0]["code"],
            "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )
        self.assertEqual(event["warnings"][0]["field"], "cached_tokens")

    def test_analyze_usage_logs_aggregates_worst_denominator_status(self):
        valid_record = {
            "provider": "openai",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 600},
                "output_tokens": 50,
            },
        }
        ambiguous_record = {
            "provider": "openrouter",
            "usage": {"input_tokens": 1000, "cached_tokens": 600},
        }
        invalid_record = {
            "provider": "gemini",
            "usageMetadata": {
                "promptTokenCount": 100,
                "cachedContentTokenCount": 900,
            },
        }

        def summarize(*records):
            with tempfile.TemporaryDirectory() as tmp:
                log_path = Path(tmp) / "usage.jsonl"
                log_path.write_text(
                    "\n".join(json.dumps(record) for record in records)
                )
                result = run_script("analyze_usage_logs.py", log_path)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        self.assertEqual(summarize(valid_record)["denominator_status"], "valid")
        self.assertEqual(
            summarize(valid_record, ambiguous_record)["denominator_status"],
            "ambiguous",
        )
        self.assertEqual(
            summarize(valid_record, ambiguous_record, invalid_record)[
                "denominator_status"
            ],
            "invalid",
        )

    def test_analyze_usage_logs_reports_ambiguous_denominator_without_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "empty.jsonl"
            log_path.write_text("")

            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["records"], 0)
        self.assertEqual(output["denominator_status"], "ambiguous")

    def test_analyze_usage_logs_marks_evidence_free_record_ambiguous(self):
        evidence_free_record = {
            "provider": "openai",
            "model": "gpt-5.4",
            "route": "responses-api",
        }
        valid_record = {
            "provider": "openai",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 600},
                "output_tokens": 50,
            },
        }

        event = self.normalized_event(evidence_free_record)

        self.assertEqual(event["denominator_status"], "ambiguous")
        self.assertEqual(set(event["source_fields"].values()), {None})

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "usage.jsonl"
            log_path.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in (valid_record, evidence_free_record)
                )
            )
            result = run_script("analyze_usage_logs.py", log_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["denominator_status"], "ambiguous"
        )

    def test_analyze_usage_logs_keeps_additive_denominator_without_uncached_input(self):
        event = self.normalized_event(
            {
                "provider": "anthropic",
                "usage": {
                    "input_tokens": 0,
                    "cache_read_input_tokens": 800,
                    "output_tokens": 40,
                },
            }
        )

        self.assertEqual(event["total_input_tokens"], 800)
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_marks_zero_denominator_ambiguous(self):
        event = self.normalized_event(
            {
                "provider": "openai",
                "usage": {"input_tokens": 0, "output_tokens": 40},
            }
        )

        self.assertEqual(event["total_input_tokens"], 0)
        self.assertEqual(event["denominator_status"], "ambiguous")

    def test_analyze_usage_logs_keeps_inclusive_contradiction_over_zero_input(self):
        event = self.normalized_event(
            {
                "provider": "gemini",
                "usageMetadata": {
                    "promptTokenCount": 0,
                    "cachedContentTokenCount": 900,
                },
            }
        )

        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(
            event["warnings"][0]["code"],
            "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )

    def test_analyze_usage_logs_keeps_zero_valued_wrapper_alias_provenance(self):
        event = self.normalized_event(
            {
                "provider": "openrouter",
                "usage": {
                    "input_tokens": 1000,
                    "cached_tokens": 0,
                    "prompt_cache_hit_tokens": 0,
                    "output_tokens": 50,
                },
            }
        )

        self.assertEqual(event["cached_tokens"], 0)
        self.assertEqual(event["source_fields"]["cached_tokens"], "usage.cached_tokens")

    def test_analyze_usage_logs_flags_inclusive_override_contradiction(self):
        event = self.normalized_event(
            {
                "provider": "openrouter",
                "usage": {
                    "input_tokens": 100,
                    "cached_tokens": 400,
                    "output_tokens": 50,
                },
            },
            "--accounting-mode",
            "inclusive",
        )

        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(
            event["warnings"][0]["code"],
            "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )
        self.assertEqual(event["warnings"][0]["field"], "cached_tokens")

    def test_analyze_usage_logs_reports_flat_openai_provenance(self):
        event = self.normalized_event(
            {
                "provider": "openai",
                "input_tokens": 1000,
                "cached_tokens": 600,
                "cache_write_tokens": 200,
                "output_tokens": 50,
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "input_tokens",
                "cached_tokens": "cached_tokens",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": "cache_write_tokens",
                "output_tokens": "output_tokens",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_reports_gemini_interactions_usage_envelope_provenance(
        self,
    ):
        event = self.normalized_event(
            {
                "provider": "gemini",
                "usage": {
                    "total_input_tokens": 1000,
                    "total_cached_tokens": 600,
                    "total_output_tokens": 100,
                },
            }
        )

        self.assertEqual(
            event["source_fields"],
            {
                "input_tokens": "usage.total_input_tokens",
                "cached_tokens": "usage.total_cached_tokens",
                "cache_read_input_tokens": None,
                "cache_creation_input_tokens": None,
                "cache_write_tokens": None,
                "output_tokens": "usage.total_output_tokens",
            },
        )
        self.assertEqual(event["denominator_status"], "valid")

    def test_analyze_usage_logs_rejects_non_canonical_extraction_fields(self):
        analyzer = load_script_module("analyze_usage_logs.py")

        with self.assertRaises(ValueError):
            analyzer.extraction(cached_token=(600, "usage.cached_token"))

        _, source_fields = analyzer.extraction(
            cached_tokens=(600, "usage.cached_tokens")
        )
        self.assertEqual(
            tuple(source_fields), tuple(analyzer.CANONICAL_USAGE_FIELDS)
        )

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

    def test_estimate_cache_roi_prices_cache_writes(self):
        result = run_script(
            "estimate_cache_roi.py",
            "--static-tokens",
            "1000",
            "--dynamic-tokens",
            "100",
            "--output-tokens",
            "0",
            "--requests",
            "10",
            "--hit-rate",
            "0.5",
            "--cache-write-rate",
            "0.4",
            "--input-price-per-mtok",
            "1",
            "--cached-input-price-per-mtok",
            "0.1",
            "--cache-write-input-price-per-mtok",
            "3",
            "--output-price-per-mtok",
            "0",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["producer"], "estimate_cache_roi.py")
        self.assertEqual(output["cache_read_input_tokens"], 5000)
        self.assertEqual(output["cache_write_input_tokens"], 4000)
        self.assertEqual(output["ordinary_input_tokens"], 2000)
        self.assertEqual(output["cache_write_input_cost"], 0.012)
        self.assertEqual(output["total_baseline_cost"], 0.011)
        self.assertEqual(output["total_with_cache_cost"], 0.0145)
        self.assertEqual(output["total_savings"], -0.0035)

    def test_estimate_cache_roi_rejects_invalid_write_assumptions(self):
        common = (
            "--static-tokens",
            "1000",
            "--dynamic-tokens",
            "0",
            "--output-tokens",
            "0",
            "--requests",
            "10",
            "--input-price-per-mtok",
            "1",
            "--cached-input-price-per-mtok",
            "0.1",
            "--output-price-per-mtok",
            "0",
        )
        missing_price = run_script(
            "estimate_cache_roi.py",
            *common,
            "--hit-rate",
            "0.5",
            "--cache-write-rate",
            "0.2",
        )
        excess_rate = run_script(
            "estimate_cache_roi.py",
            *common,
            "--hit-rate",
            "0.8",
            "--cache-write-rate",
            "0.3",
            "--cache-write-input-price-per-mtok",
            "1",
        )

        self.assertEqual(missing_price.returncode, 2)
        self.assertIn("write price", missing_price.stderr)
        self.assertEqual(excess_rate.returncode, 2)
        self.assertIn("sum", excess_rate.stderr)

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

    def test_render_audit_report_distinguishes_unpriced_cache_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = Path(tmp) / "usage.json"
            usage_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "usage": {
                            "input_tokens": 1000,
                            "input_tokens_details": {
                                "cached_tokens": 500,
                                "cache_write_tokens": 250,
                            },
                            "output_tokens": 50,
                        },
                    }
                )
            )

            result = run_script("render_audit_report.py", "--usage-log", usage_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cache read tokens: 500", result.stdout)
        self.assertIn("Cache write tokens: 250", result.stdout)
        self.assertIn("Cost impact: unknown (no pricing supplied)", result.stdout)

    def test_render_audit_report_accepts_estimator_roi(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            usage_path = tmp_path / "usage.json"
            usage_path.write_text(
                json.dumps(
                    {
                        "provider": "openai",
                        "usage": {
                            "input_tokens": 1000,
                            "input_tokens_details": {"cache_write_tokens": 800},
                            "output_tokens": 0,
                        },
                    }
                )
            )
            roi_result = run_script(
                "estimate_cache_roi.py",
                "--static-tokens",
                "1000",
                "--dynamic-tokens",
                "0",
                "--output-tokens",
                "0",
                "--requests",
                "10",
                "--hit-rate",
                "0.1",
                "--cache-write-rate",
                "0.8",
                "--input-price-per-mtok",
                "1",
                "--cached-input-price-per-mtok",
                "0.1",
                "--cache-write-input-price-per-mtok",
                "2",
                "--output-price-per-mtok",
                "0",
            )
            self.assertEqual(roi_result.returncode, 0, roi_result.stderr)
            roi_path = tmp_path / "roi.json"
            roi_path.write_text(roi_result.stdout)

            result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--roi-json",
                roi_path,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cost impact: increased cost", result.stdout)
        self.assertIn("Priced Cache Scenario", result.stdout)

    def test_render_audit_report_rejects_untrusted_roi_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            usage_path = tmp_path / "usage.json"
            usage_path.write_text(json.dumps({"usage": {"input_tokens": 10}}))
            roi_path = tmp_path / "roi.json"
            roi_path.write_text(
                json.dumps(
                    {
                        "producer": "other.py",
                        "schema_version": 1,
                        "total_baseline_cost": 1,
                        "total_with_cache_cost": 0.5,
                        "total_savings": 0.5,
                        "pricing": {},
                    }
                )
            )

            result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--roi-json",
                roi_path,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("producer", result.stderr)

    @staticmethod
    def write_usage_log(directory, records):
        path = Path(directory) / "usage.jsonl"
        path.write_text("\n".join(json.dumps(record) for record in records))
        return path

    AMBIGUOUS_USAGE_RECORDS = (
        {
            "provider": "openai",
            "usage": {
                "input_tokens": 1000,
                "input_tokens_details": {"cached_tokens": 600},
                "output_tokens": 50,
            },
        },
        {"provider": "openai", "model": "gpt-5.4", "route": "responses-api"},
    )
    INVALID_USAGE_RECORDS = (
        {
            "provider": "gemini",
            "usageMetadata": {
                "promptTokenCount": 100,
                "cachedContentTokenCount": 900,
                "candidatesTokenCount": 10,
            },
        },
    )

    def test_render_audit_report_canonicalizes_cache_planes_and_clinic_statuses(self):
        result = run_script(
            "render_audit_report.py",
            "--json",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            "--cache-plane",
            "engine_kv",
            "--cache-plane",
            "gateway_response",
            "--cache-plane",
            "engine_kv",
            "--cache-plane",
            "provider_prompt",
            "--applicability",
            "pass",
            "--prefix-stability",
            "warning",
            "--isolation",
            "not_applicable",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(
            output["cache_planes"],
            ["gateway_response", "provider_prompt", "engine_kv"],
        )
        self.assertEqual(
            output["clinic_summary"],
            {
                "applicability": "pass",
                "evidence_quality": "unknown",
                "prefix_stability": "warning",
                "usage_accounting": "unknown",
                "routing_locality": "unknown",
                "economics": "unknown",
                "isolation": "not_applicable",
            },
        )

        markdown_result = run_script(
            "render_audit_report.py",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
            "--cache-plane",
            "engine_kv",
            "--cache-plane",
            "gateway_response",
            "--cache-plane",
            "engine_kv",
            "--cache-plane",
            "provider_prompt",
        )
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn(
            "Cache planes: gateway_response, provider_prompt, engine_kv",
            markdown_result.stdout,
        )

    def test_render_audit_report_markdown_renders_unknown_clinic_summary(self):
        result = run_script(
            "render_audit_report.py",
            "--usage-log",
            FIXTURES / "openai" / "repeated_prefix_usage.jsonl",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("## Cache Clinic Summary", result.stdout)
        self.assertLess(
            result.stdout.index("## Cache Clinic Summary"),
            result.stdout.index("## Findings"),
        )
        self.assertIn("Cache planes: unknown", result.stdout)
        for label in (
            "Applicability",
            "Evidence quality",
            "Prefix stability",
            "Usage accounting",
            "Routing locality",
            "Economics",
            "Isolation",
        ):
            self.assertIn(f"- {label}: unknown", result.stdout)

    def test_render_audit_report_rejects_invalid_clinic_choices(self):
        usage_log = FIXTURES / "openai" / "repeated_prefix_usage.jsonl"

        bad_status = run_script(
            "render_audit_report.py",
            "--usage-log",
            usage_log,
            "--economics",
            "excellent",
        )
        bad_plane = run_script(
            "render_audit_report.py",
            "--usage-log",
            usage_log,
            "--cache-plane",
            "cdn_cache",
        )

        self.assertEqual(bad_status.returncode, 2)
        self.assertIn("--economics", bad_status.stderr)
        self.assertIn("invalid choice", bad_status.stderr)
        self.assertEqual(bad_plane.returncode, 2)
        self.assertIn("--cache-plane", bad_plane.stderr)
        self.assertIn("invalid choice", bad_plane.stderr)

    def test_render_audit_report_rejects_pass_usage_accounting_on_bad_denominator(self):
        for records in (self.AMBIGUOUS_USAGE_RECORDS, self.INVALID_USAGE_RECORDS):
            with self.subTest(records=records):
                with tempfile.TemporaryDirectory() as tmp:
                    usage_path = self.write_usage_log(tmp, records)
                    result = run_script(
                        "render_audit_report.py",
                        "--usage-log",
                        usage_path,
                        "--usage-accounting",
                        "pass",
                    )

                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("usage_accounting", result.stderr)

    def test_render_audit_report_derives_usage_accounting_from_denominator(self):
        cases = (
            (self.AMBIGUOUS_USAGE_RECORDS, "ambiguous", "warning"),
            (self.INVALID_USAGE_RECORDS, "invalid", "fail"),
        )
        for records, denominator, expected_status in cases:
            with self.subTest(denominator=denominator):
                with tempfile.TemporaryDirectory() as tmp:
                    usage_path = self.write_usage_log(tmp, records)
                    json_result = run_script(
                        "render_audit_report.py",
                        "--json",
                        "--usage-log",
                        usage_path,
                    )
                    markdown_result = run_script(
                        "render_audit_report.py",
                        "--usage-log",
                        usage_path,
                    )

                self.assertEqual(json_result.returncode, 0, json_result.stderr)
                output = json.loads(json_result.stdout)
                self.assertEqual(output["usage"]["denominator_status"], denominator)
                self.assertEqual(
                    output["clinic_summary"]["usage_accounting"], expected_status
                )
                self.assertNotIn("Observed cache benefit on", output["expected_impact"])
                self.assertIn(denominator, output["expected_impact"])
                self.assertIn("must not support a savings claim", output["expected_impact"])

                self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
                self.assertIn(
                    f"- Usage accounting: {expected_status}", markdown_result.stdout
                )
                self.assertIn(
                    f"Usage denominator status: {denominator}", markdown_result.stdout
                )
                self.assertRegex(
                    markdown_result.stdout,
                    rf"Cache hit ratio: .*non-decision-grade; denominator {denominator}",
                )
                self.assertNotIn("Observed cache benefit on", markdown_result.stdout)

    def test_render_audit_report_qualifies_empty_evidence_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(tmp, ())
            result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "Cache hit ratio: 0 (non-decision-grade; denominator ambiguous)",
            result.stdout,
        )

    def test_render_audit_report_keeps_denominator_caveat_with_roi(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(tmp, self.INVALID_USAGE_RECORDS)
            roi_path = Path(tmp) / "roi.json"
            roi_path.write_text(
                json.dumps(
                    {
                        "producer": "estimate_cache_roi.py",
                        "schema_version": 1,
                        "pricing": {},
                        "cache_read_input_cost": 0.1,
                        "cache_write_input_cost": 0.0,
                        "total_baseline_cost": 1.0,
                        "total_with_cache_cost": 0.5,
                        "total_savings": 0.5,
                    }
                )
            )
            result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--roi-json",
                roi_path,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("estimates $0.500000 in savings", result.stdout)
        self.assertIn("Usage denominator status is invalid", result.stdout)
        self.assertIn("must not support a savings claim", result.stdout)

    def test_render_audit_report_has_no_aggregate_clinic_rollup(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(tmp, self.INVALID_USAGE_RECORDS)
            json_result = run_script(
                "render_audit_report.py",
                "--json",
                "--usage-log",
                usage_path,
                "--cache-plane",
                "engine_kv",
                "--applicability",
                "pass",
            )
            markdown_result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--cache-plane",
                "engine_kv",
                "--applicability",
                "pass",
            )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        output = json.loads(json_result.stdout)
        forbidden = ("score", "rank", "grade", "percentage", "rollup", "traffic_light")
        def nested_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from nested_keys(child)
            elif isinstance(value, list):
                for child in value:
                    yield from nested_keys(child)

        for key in nested_keys(output):
            self.assertFalse(
                any(
                    f"clinic_{token}" in key or f"{token}_clinic" in key
                    for token in forbidden
                ),
                f"unexpected aggregate key: {key}",
            )
        self.assertEqual(json_result.returncode, 0)

        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        lowered = markdown_result.stdout.lower()
        for token in ("clinic score", "overall score", "clinic grade", "clinic rank"):
            self.assertNotIn(token, lowered)

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

    def test_extract_llm_calls_detects_kv_events_and_hicache_tiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "compose.yaml").write_text(
                "\n".join(
                    [
                        "command: vllm serve model --enable-kv-cache-events",
                        "kv_transfer_config: {kv_connector: LMCacheConnectorV1}",
                        "command: sglang.launch_server --enable-hierarchical-cache",
                        "hicache_storage_backend: disk",
                        "disaggregation_mode: prefill",
                    ]
                )
            )

            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertGreaterEqual(output["providers"]["vllm"], 2)
        self.assertGreaterEqual(output["providers"]["sglang"], 3)

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
        for rule_id in ("AP-1", "AP-2", "AP-7", "AP-11"):
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

    def test_layout_linter_flags_bad_responses_prompt_layout(self):
        result = run_script(
            "layout_linter.py",
            FIXTURES / "layout" / "bad_openai_responses_request.json",
        )

        self.assertEqual(result.returncode, 1, result.stdout)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "findings")
        rule_ids = {finding["rule_id"] for finding in output["findings"]}
        self.assertIn("AP-1", rule_ids)

    def test_layout_linter_passes_good_responses_prompt_layout(self):
        result = run_script(
            "layout_linter.py",
            FIXTURES / "layout" / "good_openai_responses_request.json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "ok")
        self.assertEqual(output["findings"], [])
        self.assertIn("AP-1", output["clean_checks"])

    def test_layout_linter_flags_responses_string_input_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "responses-string.json"
            request_path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5.4",
                        "input": (
                            "Today is 2026-05-02. request_id=req_string_123. "
                            "Stable reusable policy: apply the same compliance "
                            "taxonomy for every request."
                        ),
                    }
                )
            )

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 1, result.stdout)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], "findings")
        self.assertEqual(output["findings"][0]["rule_id"], "AP-1")
        self.assertIn("input contains", output["findings"][0]["evidence"])

    def test_layout_linter_validates_direct_gpt56_explicit_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5.6-terra",
                        "messages": [
                            {
                                "role": "system",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Stable policy",
                                        "prompt_cache_breakpoint": {
                                            "mode": "explicit"
                                        },
                                    }
                                ],
                            }
                        ],
                        "prompt_cache_options": {
                            "mode": "explicit",
                            "ttl": "30m",
                        },
                    }
                )
            )

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["cache_policy"]["validated"])
        self.assertEqual(output["cache_policy"]["api_surface"], "chat")
        self.assertEqual(output["cache_policy"]["mode"], "explicit")
        self.assertEqual(output["cache_policy"]["explicit_breakpoints"], 1)
        self.assertIn("AP-11", output["clean_checks"])

    def test_layout_linter_flags_explicit_mode_without_breakpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5.6-terra",
                        "messages": [
                            {"role": "system", "content": "Stable policy"}
                        ],
                        "prompt_cache_options": {
                            "mode": "explicit",
                            "ttl": "30m",
                        },
                    }
                )
            )

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        finding = next(
            item
            for item in output["findings"]
            if item["rule_id"] == "AP-11"
        )
        self.assertEqual(finding["severity"], "medium")
        self.assertIn("no valid prompt_cache_breakpoint", finding["issue"])
        self.assertFalse(output["cache_policy"]["valid"])

    def test_layout_linter_reports_invalid_gpt56_cache_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5.6",
                        "input": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "Question",
                                        "prompt_cache_breakpoint": {
                                            "mode": "implicit"
                                        },
                                    }
                                ],
                            }
                        ],
                        "prompt_cache_options": {
                            "mode": "automatic",
                            "ttl": "24h",
                        },
                        "prompt_cache_retention": "24h",
                    }
                )
            )

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 1, result.stderr)
        output = json.loads(result.stdout)
        ap11 = [item for item in output["findings"] if item["rule_id"] == "AP-11"]
        evidence = "\n".join(item["evidence"] for item in ap11)
        self.assertIn("prompt_cache_options.mode", evidence)
        self.assertIn("prompt_cache_options.ttl", evidence)
        self.assertIn("prompt_cache_retention", evidence)
        self.assertIn("prompt_cache_breakpoint", evidence)

    def test_layout_linter_does_not_treat_write_slots_as_a_marker_limit(self):
        blocks = [
            {
                "type": "input_text",
                "text": f"Stable section {index}",
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
            for index in range(5)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "model": "gpt-5.6",
                        "input": [{"role": "user", "content": blocks}],
                        "prompt_cache_options": {"mode": "explicit"},
                    }
                )
            )

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["cache_policy"]["explicit_breakpoints"], 5)

    def test_layout_linter_leaves_provider_wrappers_unvalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "model": "openrouter/gpt-5.6",
                        "messages": [{"role": "user", "content": "Question"}],
                        "prompt_cache_options": {"mode": "made-up"},
                    }
                )
            )

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["cache_policy"]["validated"])
        self.assertEqual(output["cache_policy"]["model_support"], "unknown")
        self.assertNotIn("AP-11", output["clean_checks"])

    def test_layout_linter_returns_usage_error_for_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            request_path = Path(tmp) / "request.json"
            request_path.write_text("{")

            result = run_script("layout_linter.py", request_path)

        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid request JSON", result.stderr)

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
            "PYTHONDONTWRITEBYTECODE",
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
        self.assertIn("fixtures/layout/good_openai_responses_request.json", readme)
        self.assertIn("Responses-style", readme)
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
            "GPT-5.6 prompt_cache_options",
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
            "GPT-5.6",
            "prompt_cache_options",
            "cache_write_tokens",
            "pricing",
        ]:
            self.assertIn(required, combined_prompts + "\n" + combined_expected)

    def test_skill_routes_minimal_gpt56_cache_audit_tools(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "prompt_cache_options",
            "prompt_cache_breakpoint",
            "cache_write_tokens",
            "--accounting-mode",
            "--cache-write-rate",
            "--cache-write-input-price-per-mtok",
            "--roi-json",
            "whole-input comparison",
            "does not prove explicit breakpoint reuse",
        ]:
            self.assertIn(required, skill)

    def test_skill_requires_project_context_language_and_script_transparency(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "Project Context Gate",
            "Language Match Rule",
            "Script Transparency Rule",
            "Applicability Before Severity",
            "review hot paths, repeat cadence, prompt families, and cache applicability",
            "explain what each bundled script reads, writes, and whether it uses network",
        ]:
            self.assertIn(required, skill)

    def test_skill_links_operational_playbook_and_observability_references(self):
        skill_dir = ROOT / "audit-prompt-caching"
        skill = (skill_dir / "SKILL.md").read_text()
        operational = skill_dir / "references" / "operational-playbook.md"
        observability = skill_dir / "references" / "observability.md"

        self.assertTrue(operational.exists(), "missing operational playbook reference")
        self.assertTrue(observability.exists(), "missing observability reference")
        self.assertIn("references/operational-playbook.md", skill)
        self.assertIn("references/observability.md", skill)

        operational_text = operational.read_text()
        for required in [
            "Quick Operational Playbook",
            "low cache hit rate",
            "stable prefix",
            "sliding",
            "provider wrapper",
            "official docs",
        ]:
            self.assertIn(required, operational_text)

        observability_text = observability.read_text()
        for required in [
            "Minimum Telemetry Contract",
            "cache_read_tokens",
            "cache_write_tokens",
            "prefix_hash",
            "first_256_token_hash",
            "Do not log raw prompts",
            "dashboard",
            "alert",
        ]:
            self.assertIn(required, observability_text)

    def test_evals_cover_project_context_and_script_transparency_feedback(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        combined = "\n".join(
            item["prompt"] + "\n" + item["expected_output"] for item in evals["evals"]
        )

        for required in [
            "Сделай ревью на русском",
            "7 prompt families",
            "once per day",
            "Script Transparency Rule",
            "do not mark prefix-cache findings high severity",
        ]:
            self.assertIn(required, combined)

    def test_evals_cover_operational_playbook_and_telemetry_contract(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        trigger_eval = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "trigger_eval.json").read_text()
        )
        combined_evals = "\n".join(
            item["prompt"] + "\n" + item["expected_output"] for item in evals["evals"]
        )
        trigger_queries = "\n".join(item["query"] for item in trigger_eval)

        for required in [
            "quick operational playbook",
            "low cache hit rate",
            "provider wrapper ambiguity",
            "minimum telemetry contract",
            "prefix_hash",
            "first_256_token_hash",
            "Do not log raw prompts",
        ]:
            self.assertIn(required, combined_evals + "\n" + trigger_queries)

    def test_vllm_reference_covers_benchmark_validation(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "vllm.md"
        ).read_text()

        for required in [
            "Benchmark Validation",
            "Applicability Gate",
            "benchmarks/benchmark_prefix_caching.py",
            "vllm bench serve",
            "prefix_repetition",
            "--save-result",
            "--save-detailed",
            "vllm:prefix_cache_hits",
            "vllm:prefix_cache_queries",
            "vllm:prompt_tokens_cached",
            "synthetic benchmark speedup",
            "production ROI",
        ]:
            self.assertIn(required, reference)

    def test_skill_detects_vllm_benchmark_workflows(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

        for required in [
            "vllm bench serve",
            "prefix_repetition",
            "benchmark_prefix_caching.py",
        ]:
            self.assertIn(required, skill)

    def test_evals_cover_vllm_benchmark_validation(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        trigger_eval = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "trigger_eval.json").read_text()
        )
        combined = "\n".join(
            item["prompt"] + "\n" + item["expected_output"] for item in evals["evals"]
        )
        trigger_queries = "\n".join(item["query"] for item in trigger_eval)

        for required in [
            "benchmark vLLM APC",
            "vllm bench serve",
            "prefix_repetition",
            "vllm:prefix_cache_hits",
            "vllm:prefix_cache_queries",
            "do not claim production ROI",
        ]:
            self.assertIn(required, combined)

        self.assertIn("vllm bench serve", trigger_queries)
        self.assertIn("prefix_repetition", trigger_queries)

    def test_evals_preserve_provider_pressure_scenarios(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        combined = "\n".join(
            item["prompt"] + "\n" + item["expected_output"] for item in evals["evals"]
        )

        for required in [
            "datetime.now().isoformat()",
            "dynamic `requestId`",
            "tools_count changes",
            "four replicas",
            "--max-model-len 131072",
            "DashScope Qwen",
            "cache_creation_input_tokens",
            "RAG document-classification",
            "system instructions, then the user question",
            "OpenRouter usage shows `cache_write_tokens`",
            "Amazon Bedrock Converse",
            "top-level `cache_control`",
        ]:
            self.assertIn(required, combined)

    def test_trigger_eval_preserves_negative_non_cache_cases(self):
        trigger_eval = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "trigger_eval.json").read_text()
        )
        negative_queries = "\n".join(
            item["query"] for item in trigger_eval if not item["should_trigger"]
        )

        for required in [
            "Write a friendly system prompt",
            "generic RAG",
            "Count tokens",
            "JSON schema",
            "none of them are LLM inference replicas",
            "Kubernetes Service for a stateless API",
            "OpenRouter model routing basics",
        ]:
            self.assertIn(required, negative_queries)

    def test_rules_reference_has_actionable_antipattern_details(self):
        data = json.loads(
            (ROOT / "audit-prompt-caching" / "references" / "rules.json").read_text()
        )

        for rule in data["rules"]:
            for key in ("search", "fix", "avoid"):
                self.assertIn(key, rule, rule["id"])
                self.assertIsInstance(rule[key], str, rule["id"])
                self.assertTrue(rule[key].strip(), rule["id"])

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
            "GPT-5.6",
            "prompt_cache_options",
            "prompt_cache_breakpoint",
            '"mode": "explicit"',
            "cache_write_tokens",
            "30m",
            "four",
            "breakdowns of the reported input total",
            "minimum reuse lifetime",
            "not a Regional processing guarantee",
        ]:
            self.assertIn(required, reference)


if __name__ == "__main__":
    unittest.main()
