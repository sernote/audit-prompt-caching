import csv
import importlib.util
import json
import math
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "audit-prompt-caching" / "scripts"
FIXTURES = ROOT / "fixtures"

# plugin-eval 0.1.2 reports static token estimates as len(text) / 4. Mirroring
# that arithmetic keeps the budget guardrails in-suite without shelling out to
# plugin-eval, which is not a repository test dependency.
# plugin-eval measures the parsed description value, not its YAML source slice.
# The former 0.85 character heuristic was retired: the required complete
# provider/vLLM trigger surface plus lexical separators cannot fit that ratio.
PLUGIN_EVAL_TRIGGER_TOKEN_BUDGET = 147
# Restoring the operational prompt-segment classification and the truthful
# lexical-locator policy raises the baseline only to the measured 5979 tokens.
PLUGIN_EVAL_SKILL_TOKEN_BASELINE = 5979
BASELINE_DESCRIPTION_CHARS = 679


def estimated_plugin_eval_tokens(text):
    return math.ceil(len(text) / 4)


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


def parse_markdown_table(text, header):
    """Parse one pipe table by its exact header using only the stdlib."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows = []
        for row_line in lines[index + 2 :]:
            if not row_line.strip().startswith("|"):
                break
            values = [cell.strip() for cell in row_line.strip().strip("|").split("|")]
            if len(values) != len(headers):
                break
            rows.append(dict(zip(headers, values)))
        return rows
    raise AssertionError(f"missing Markdown table header: {header}")


def extract_markdown_section(text, heading):
    """Return one level-two Markdown section without unrelated sections."""
    pattern = rf"^## {re.escape(heading)}\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise AssertionError(f"missing Markdown section: {heading}")
    body_start = match.end()
    next_heading = re.search(r"^## (?!#)", text[body_start:], re.MULTILINE)
    body_end = body_start + next_heading.start() if next_heading else len(text)
    return text[body_start:body_end]


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

    def test_analyze_usage_logs_flags_inclusive_read_aliases_exceeding_input(self):
        record = {
            "data": {
                "usage": {
                    "prompt_tokens": 1000,
                    "cached_tokens": 600,
                    "cache_read_tokens": 700,
                    "completion_tokens": 50,
                }
            }
        }

        event = self.normalized_event(record, "--accounting-mode", "inclusive")

        self.assertEqual(event["cached_tokens"], 600)
        self.assertEqual(event["cache_read_input_tokens"], 700)
        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(len(event["warnings"]), 1)
        self.assertEqual(
            event["warnings"][0]["code"],
            "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )
        self.assertEqual(event["warnings"][0]["field"], "cache_benefit_tokens")

        with tempfile.TemporaryDirectory() as tmp:
            log_path = self.write_usage_log(tmp, (record,))
            result = run_script(
                "analyze_usage_logs.py", "--accounting-mode", "inclusive", log_path
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        totals = json.loads(result.stdout)
        self.assertEqual(totals["denominator_status"], "invalid")
        self.assertEqual(totals["cache_hit_ratio"], 1.3)

    def test_analyze_usage_logs_keeps_exact_inclusive_split_valid(self):
        event = self.normalized_event(
            {
                "data": {
                    "usage": {
                        "prompt_tokens": 1000,
                        "cached_tokens": 400,
                        "cache_read_tokens": 600,
                        "completion_tokens": 50,
                    }
                }
            },
            "--accounting-mode",
            "inclusive",
        )

        self.assertEqual(event["cache_benefit_tokens"], 1000)
        self.assertEqual(event["denominator_status"], "valid")
        self.assertEqual(event["warnings"], [])

    def test_analyze_usage_logs_flags_inclusive_write_total_exceeding_input(self):
        event = self.normalized_event(
            {
                "data": {
                    "usage": {
                        "prompt_tokens": 1000,
                        "cache_write_tokens": 600,
                        "cache_creation_input_tokens": 700,
                        "completion_tokens": 50,
                    }
                }
            },
            "--accounting-mode",
            "inclusive",
        )

        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(len(event["warnings"]), 1)
        self.assertEqual(
            event["warnings"][0]["code"],
            "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )
        self.assertEqual(event["warnings"][0]["field"], "cache_write_total_tokens")

    def test_analyze_usage_logs_flags_inclusive_read_write_split_exceeding_input(self):
        event = self.normalized_event(
            {
                "data": {
                    "usage": {
                        "prompt_tokens": 1000,
                        "cached_tokens": 600,
                        "cache_write_tokens": 600,
                        "completion_tokens": 50,
                    }
                }
            },
            "--accounting-mode",
            "inclusive",
        )

        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(len(event["warnings"]), 1)
        self.assertEqual(
            event["warnings"][0]["code"],
            "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
        )
        self.assertEqual(
            event["warnings"][0]["field"], "cache_accounted_input_tokens"
        )

    def test_analyze_usage_logs_prefers_individual_openai_breakdown_violation(self):
        event = self.normalized_event(
            {
                "provider": "openai",
                "usage": {
                    "input_tokens": 100,
                    "input_tokens_details": {
                        "cached_tokens": 120,
                        "cache_write_tokens": 90,
                    },
                    "output_tokens": 50,
                },
            }
        )

        self.assertEqual(event["denominator_status"], "invalid")
        self.assertEqual(len(event["warnings"]), 1)
        self.assertEqual(
            event["warnings"][0]["code"],
            "OPENAI_CACHE_BREAKDOWN_EXCEEDS_INPUT",
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
    UNKNOWN_WRAPPER_USAGE_RECORDS = (
        {
            "data": {
                "usage": {
                    "prompt_tokens": 1000,
                    "cached_tokens": 600,
                    "completion_tokens": 50,
                }
            }
        },
    )
    CONTRADICTORY_WRAPPER_USAGE_RECORDS = (
        {
            "data": {
                "usage": {
                    "prompt_tokens": 100,
                    "cached_tokens": 900,
                    "completion_tokens": 10,
                }
            }
        },
    )
    AGGREGATE_CONTRADICTORY_WRAPPER_USAGE_RECORDS = (
        {
            "data": {
                "usage": {
                    "prompt_tokens": 1000,
                    "cached_tokens": 600,
                    "cache_read_tokens": 700,
                    "completion_tokens": 50,
                }
            }
        },
    )
    VALID_USAGE_RECORDS = (
        {
            "provider": "anthropic",
            "usage": {
                "input_tokens": 400,
                "cache_read_input_tokens": 600,
                "cache_creation_input_tokens": 100,
                "output_tokens": 50,
            },
        },
    )
    ROI_JSON = {
        "producer": "estimate_cache_roi.py",
        "schema_version": 1,
        "pricing": {},
        "cache_read_input_cost": 0.1,
        "cache_write_input_cost": 0.0,
        "total_baseline_cost": 1.0,
        "total_with_cache_cost": 0.5,
        "total_savings": 0.5,
    }

    def write_roi_json(self, directory):
        path = Path(directory) / "roi.json"
        path.write_text(json.dumps(self.ROI_JSON))
        return path

    def test_render_audit_report_keeps_unknown_wrapper_ambiguous_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(
                tmp, self.UNKNOWN_WRAPPER_USAGE_RECORDS
            )
            json_result = run_script(
                "render_audit_report.py", "--json", "--usage-log", usage_path
            )
            pass_result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--usage-accounting",
                "pass",
            )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        output = json.loads(json_result.stdout)
        self.assertEqual(output["usage"]["denominator_status"], "ambiguous")
        self.assertEqual(output["clinic_summary"]["usage_accounting"], "warning")
        self.assertEqual(pass_result.returncode, 2, pass_result.stdout)
        self.assertIn("usage_accounting", pass_result.stderr)

    def test_render_audit_report_accepts_operator_supplied_accounting_mode(self):
        for mode in ("inclusive", "additive"):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as tmp:
                    usage_path = self.write_usage_log(
                        tmp, self.UNKNOWN_WRAPPER_USAGE_RECORDS
                    )
                    result = run_script(
                        "render_audit_report.py",
                        "--json",
                        "--usage-log",
                        usage_path,
                        "--accounting-mode",
                        mode,
                        "--usage-accounting",
                        "pass",
                    )

                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                self.assertEqual(output["usage"]["denominator_status"], "valid")
                self.assertEqual(
                    output["clinic_summary"]["usage_accounting"], "pass"
                )

    def test_render_audit_report_rejects_pass_on_inclusive_contradiction(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(
                tmp, self.CONTRADICTORY_WRAPPER_USAGE_RECORDS
            )
            json_result = run_script(
                "render_audit_report.py",
                "--json",
                "--usage-log",
                usage_path,
                "--accounting-mode",
                "inclusive",
            )
            pass_result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--accounting-mode",
                "inclusive",
                "--usage-accounting",
                "pass",
            )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        output = json.loads(json_result.stdout)
        self.assertEqual(output["usage"]["denominator_status"], "invalid")
        self.assertEqual(output["clinic_summary"]["usage_accounting"], "fail")
        self.assertEqual(pass_result.returncode, 2, pass_result.stdout)
        self.assertIn("usage_accounting", pass_result.stderr)

    def test_render_audit_report_rejects_pass_on_aggregate_inclusive_contradiction(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(
                tmp, self.AGGREGATE_CONTRADICTORY_WRAPPER_USAGE_RECORDS
            )
            json_result = run_script(
                "render_audit_report.py",
                "--json",
                "--usage-log",
                usage_path,
                "--accounting-mode",
                "inclusive",
            )
            markdown_result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--accounting-mode",
                "inclusive",
            )
            pass_result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--accounting-mode",
                "inclusive",
                "--usage-accounting",
                "pass",
            )

        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        output = json.loads(json_result.stdout)
        self.assertEqual(output["usage"]["denominator_status"], "invalid")
        self.assertEqual(output["usage"]["cache_hit_ratio"], 1.3)
        self.assertEqual(output["clinic_summary"]["usage_accounting"], "fail")
        self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
        self.assertIn(
            "- Cache hit ratio: 1.3 (non-decision-grade; denominator invalid)",
            markdown_result.stdout,
        )
        self.assertIn(
            "(usage ratio non-decision-grade; denominator invalid)",
            markdown_result.stdout,
        )
        self.assertEqual(pass_result.returncode, 2, pass_result.stdout)
        self.assertIn("usage_accounting", pass_result.stderr)

    def test_render_audit_report_rejects_unknown_accounting_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(
                tmp, self.UNKNOWN_WRAPPER_USAGE_RECORDS
            )
            result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--accounting-mode",
                "guess",
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--accounting-mode", result.stderr)
        self.assertIn("invalid choice", result.stderr)

    def test_render_audit_report_qualifies_cost_lines_on_bad_denominator(self):
        cases = (
            (self.AMBIGUOUS_USAGE_RECORDS, "ambiguous"),
            (self.INVALID_USAGE_RECORDS, "invalid"),
        )
        for records, denominator in cases:
            with self.subTest(denominator=denominator):
                with tempfile.TemporaryDirectory() as tmp:
                    usage_path = self.write_usage_log(tmp, records)
                    roi_path = self.write_roi_json(tmp)
                    result = run_script(
                        "render_audit_report.py",
                        "--usage-log",
                        usage_path,
                        "--roi-json",
                        roi_path,
                    )

                self.assertEqual(result.returncode, 0, result.stderr)
                qualifier = (
                    f"(usage ratio non-decision-grade; denominator {denominator})"
                )
                self.assertIn(
                    f"- Cost impact: savings of $0.500000 {qualifier}",
                    result.stdout,
                )
                self.assertIn(
                    f"- Assessment: savings of $0.500000 {qualifier}",
                    result.stdout,
                )
                self.assertIn("estimates $0.500000 in savings", result.stdout)
                self.assertIn("must not support a savings claim", result.stdout)

    def test_render_audit_report_keeps_plain_cost_lines_on_valid_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = self.write_usage_log(tmp, self.VALID_USAGE_RECORDS)
            roi_path = self.write_roi_json(tmp)
            result = run_script(
                "render_audit_report.py",
                "--usage-log",
                usage_path,
                "--roi-json",
                roi_path,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- Cost impact: savings of $0.500000\n", result.stdout)
        self.assertIn("- Assessment: savings of $0.500000\n", result.stdout)
        self.assertNotIn("non-decision-grade", result.stdout)

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

    def test_extract_llm_calls_elides_arbitrary_source_shapes_from_json(self):
        cases = {
            "serve.sh": (
                "VLLM_API_KEY=48915732 vllm serve model --enable-prefix-caching",
                "vllm serve model --api-key 1234567890 --enable-prefix-caching",
                'AUTH_TOKEN=00000000 vllm serve model --prefix-caching-hash-algo sha256',
                'api_key: str = "sk-type-SECRET-01" vllm serve model',
                'if os.environ["OPENAI_API_KEY"] == "sk-eq-SECRET-02": vllm serve model',
                'export ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY} vllm serve model',
                'vllm serve model --api-key `sk-backtick-SECRET-03` --enable-prefix-caching',
                'http -u admin:http-SECRET-04 https://api.anthropic.com/v1 # vllm',
            ),
            "app.py": (
                'password: 987654321  # anthropic',
                'cfg = {"openrouter": {"api_keys": ["sk-array-SECRET-05", "sk-array-SECRET-06"]}}',
                'client = Anthropic(api_key=f"sk-f-SECRET-07")',
            ),
            "Makefile": (
                'serve:\n\t$(CURL) --user svc:make-SECRET-08 https://openrouter.ai/api/v1/models # openrouter',
            ),
        }
        sentinels = {
            "48915732",
            "1234567890",
            "00000000",
            "sk-type-SECRET-01",
            "sk-eq-SECRET-02",
            "sk-backtick-SECRET-03",
            "http-SECRET-04",
            "987654321",
            "sk-array-SECRET-05",
            "sk-array-SECRET-06",
            "sk-f-SECRET-07",
            "make-SECRET-08",
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for filename, lines in cases.items():
                (tmp_path / filename).write_text("\n".join(lines) + "\n")

            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        rendered = result.stdout

        self.assertEqual(output.get("source_snippet_policy"), "elided")
        self.assertGreater(output["matches"], 0)
        for finding in output["findings"]:
            self.assertEqual(finding["text"], "[SOURCE_SNIPPET_ELIDED]")
            self.assertIn("path", finding)
            self.assertIn("line", finding)
            self.assertIn("provider", finding)
            self.assertIn("pattern", finding)
        self.assertIn("signals", output["findings"][0])
        for sentinel in sentinels:
            self.assertNotIn(sentinel, rendered)

    def test_extract_llm_calls_is_lexical_locator_without_value_or_comment_claims(self):
        module = load_script_module("extract_llm_calls.py")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "compose.yaml").write_text(
                "command: vllm serve model --enable-prefix-caching=false "
                "--prefix-caching-hash-algo xxhash # old setting\n"
                "# command: vllm serve model --enable-prefix-caching\n"
                "args: --no-enable-prefix-caching\n"
            )

            output = module.find_matches(tmp_path)

        self.assertEqual(output["matches"], 3)
        for finding in output["findings"]:
            self.assertEqual(
                set(finding),
                {"path", "line", "provider", "pattern", "text", "signals"},
            )
            self.assertEqual(finding["text"], "[SOURCE_SNIPPET_ELIDED]")
        self.assertIn("--enable-prefix-caching", output["findings"][0]["signals"])
        self.assertIn("--prefix-caching-hash-algo", output["findings"][0]["signals"])
        self.assertIn("--no-enable-prefix-caching", output["findings"][2]["signals"])

    def test_extract_llm_calls_uses_real_vllm_spellings_as_labels(self):
        module = load_script_module("extract_llm_calls.py")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "unknown-env.yaml").write_text(
                "VLLM_ENABLE_PREFIX_CACHING=0\n"
                "VLLM_ENABLE_KV_CACHE_EVENTS=0\n"
                "VLLM_KV_CACHE_EVENTS=0\n"
                "VLLM_PREFIX_CACHING_HASH_ALGO=sha256\n"
            )
            (tmp_path / "stale-flag.sh").write_text(
                "--enable-kv-cache-events\n"
            )
            (tmp_path / "real-config.yaml").write_text(
                "enable_prefix_caching: true\n"
                "enable_kv_cache_events: true\n"
                "prefix_caching_hash_algo: sha256\n"
                "prefix_cache_retention_interval: 300\n"
                "VLLM_PREFIX_CACHE_RETENTION_INTERVAL=300\n"
            )
            (tmp_path / "serve.sh").write_text(
                "vllm serve model --enable-prefix-caching "
                "--no-enable-prefix-caching --kv-events-config config.json "
                "--prefix-caching-hash-algo sha256 "
                "--prefix-cache-retention-interval 300\n"
            )
            output = module.find_matches(tmp_path)

        unknown = [
            finding
            for finding in output["findings"]
            if finding["path"] == "unknown-env.yaml"
        ]
        self.assertEqual(unknown, [])
        stale = [
            finding
            for finding in output["findings"]
            if finding["path"] == "stale-flag.sh"
        ]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["signals"], ["--enable-kv-cache-events"])
        by_path = {
            path: {
                signal
                for finding in output["findings"]
                if finding["path"] == path
                for signal in finding["signals"]
            }
            for path in ("real-config.yaml", "serve.sh")
        }
        self.assertEqual(
            by_path["real-config.yaml"],
            {
                "enable_prefix_caching",
                "enable_kv_cache_events",
                "prefix_caching_hash_algo",
                "prefix_cache_retention_interval",
                "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
            },
        )
        self.assertEqual(
            by_path["serve.sh"],
            {
                "vllm",
                "--enable-prefix-caching",
                "--no-enable-prefix-caching",
                "--kv-events-config",
                "--prefix-caching-hash-algo",
                "--prefix-cache-retention-interval",
            },
        )
        for pattern, label in module.SIGNAL_LABELS.items():
            if pattern in module.PROVIDER_PATTERNS["vllm"]:
                token = label[2:] if label.startswith("--") else label
                self.assertIn(
                    token,
                    pattern.replace("\\b", ""),
                    f"label {label!r} is not represented by pattern {pattern!r}",
                )

    def test_extract_llm_calls_signal_labels_cover_patterns_without_regex_source(self):
        module = load_script_module("extract_llm_calls.py")
        self.assertFalse(hasattr(module, "VLLM_SIGNAL_LABELS"))
        patterns = {
            pattern
            for provider_patterns in module.PROVIDER_PATTERNS.values()
            for pattern in provider_patterns
        }
        self.assertEqual(patterns, set(module.SIGNAL_LABELS))
        for label in module.SIGNAL_LABELS.values():
            self.assertNotRegex(label, r"[\\()]")

    def test_extract_llm_calls_preserves_legacy_pattern_for_split_signals(self):
        module = load_script_module("extract_llm_calls.py")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "bedrock.py").write_text("CacheWriteInputTokens = 128\n")
            (tmp_path / "vllm.yaml").write_text("connector: LMCacheConnector\n")
            (tmp_path / "sglang.py").write_text("pd_disaggregation = true\n")
            output = module.find_matches(tmp_path)

        by_provider = {
            finding["provider"]: finding for finding in output["findings"]
        }
        self.assertEqual(
            by_provider["bedrock"]["pattern"],
            r"\bCache(Read|Write)InputTokens\b",
        )
        self.assertEqual(
            by_provider["vllm"]["pattern"],
            r"\b(kv_transfer_config|kv_connector|LMCacheConnector)\b",
        )
        self.assertEqual(
            by_provider["sglang"]["pattern"],
            r"\b(disaggregation_mode|pd_disaggregation)\b",
        )
        self.assertIn("CacheWriteInputTokens", by_provider["bedrock"]["signals"])
        self.assertIn("LMCacheConnector", by_provider["vllm"]["signals"])
        self.assertIn("pd_disaggregation", by_provider["sglang"]["signals"])

    def test_extract_llm_calls_output_has_recursive_structural_allowlist(self):
        module = load_script_module("extract_llm_calls.py")
        sentinel = "recursive-source-secret-7f4a"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "serve.sh").write_text(
                f"vllm serve model --api-key {sentinel} --enable-prefix-caching\n"
            )
            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertNotIn(sentinel, result.stdout)
        allowed_keys = {
            "root",
            "files_scanned",
            "matches",
            "providers",
            "findings",
            "source_snippet_policy",
            "path",
            "line",
            "provider",
            "pattern",
            "text",
            "signals",
        }
        allowed_values = set(module.SIGNAL_LABELS.values())

        def assert_structure(value, key=None):
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    if key == "providers":
                        self.assertIn(child_key, module.PROVIDER_PATTERNS)
                        assert_structure(child_value, "provider_count")
                        continue
                    self.assertIn(child_key, allowed_keys)
                    assert_structure(child_value, child_key)
            elif isinstance(value, list):
                for child_value in value:
                    assert_structure(child_value, key)
            elif isinstance(value, str):
                if key in {"root", "path", "pattern"}:
                    return
                if key == "text":
                    self.assertEqual(value, "[SOURCE_SNIPPET_ELIDED]")
                elif key == "signals":
                    self.assertIn(value, allowed_values)
                else:
                    self.assertIn(value, allowed_values | {"elided"})

        assert_structure(output)

    def test_extract_llm_calls_docs_describe_locator_only_contract(self):
        module = load_script_module("extract_llm_calls.py")
        expected = (
            "lexical locator only",
            "snippets are always elided",
            "comments, dead code, or overridden configuration",
            "never resolves active/effective values or source precedence",
            "path:line",
            "verify the resolved runtime configuration",
        )
        documents = (
            module.__doc__,
            (ROOT / "README.md").read_text(),
            (ROOT / "audit-prompt-caching" / "SKILL.md").read_text(),
        )
        for document in documents:
            document = " ".join(document.split())
            for phrase in expected:
                self.assertIn(phrase, document)
        for document in documents:
            document = " ".join(document.split())
            self.assertNotIn("closed signal/value allow-lists", document)
            self.assertNotIn("allow-listed vLLM values", document)
            self.assertNotRegex(document, r"bare boolean flags? mean")

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
                        "command: vllm serve model --kv-events-config config.json",
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

    def test_extract_llm_calls_collects_vllm_retention_and_hash_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "deployment.yaml").write_text(
                "prefix_cache_retention_interval: 0\n"
                "prefix_caching_hash_algo: sha256\n"
                "VLLM_PREFIX_CACHE_RETENTION_INTERVAL: 0\n"
            )
            (tmp_path / "engine.py").write_text(
                "prefix_cache_retention_interval = 0\n"
                "prefix_caching_hash_algo = 'sha256_cbor'\n"
            )
            (tmp_path / "serve.sh").write_text(
                "vllm serve model --prefix-cache-retention-interval 0 "
                "--prefix-caching-hash-algo sha256\n"
            )
            (tmp_path / "vllm.service").write_text(
                "ExecStart=/usr/bin/vllm serve model "
                "--prefix-cache-retention-interval 64\n"
            )
            (tmp_path / "Makefile").write_text(
                "serve:\n\tvllm serve model --prefix-caching-hash-algo xxhash\n"
            )

            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["files_scanned"], 5)
        self.assertIn("vllm", output["providers"])
        signals = {
            signal
            for finding in output["findings"]
            for signal in finding["signals"]
        }
        for signal in (
            "--prefix-cache-retention-interval",
            "prefix_cache_retention_interval",
            "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
            "--prefix-caching-hash-algo",
            "prefix_caching_hash_algo",
        ):
            self.assertIn(signal, signals)

    def test_extract_llm_calls_keeps_generic_and_specific_vllm_signals_additive(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "compose.yaml").write_text(
                "command: vllm serve model --prefix-cache-retention-interval 0 "
                "--prefix-caching-hash-algo sha256\n"
            )

            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["providers"]["vllm"], 1)
        self.assertEqual(output["matches"], 1)
        finding = output["findings"][0]
        self.assertEqual(finding["provider"], "vllm")
        self.assertIn("vllm", finding["signals"])
        self.assertIn("--prefix-cache-retention-interval", finding["signals"])
        self.assertIn("--prefix-caching-hash-algo", finding["signals"])

    def test_extract_llm_calls_does_not_classify_generic_pythonhashseed_as_vllm(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "service.py").write_text(
                "import os\nos.environ['PYTHONHASHSEED'] = '42'\n"
            )

            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertNotIn("vllm", output["providers"])

    def test_extract_llm_calls_elides_source_snippet_for_long_lines(self):
        module = load_script_module("extract_llm_calls.py")
        long_line = "vllm " + ("A-" * 6000) + "\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "long.yaml").write_text(long_line)

            started = time.monotonic()
            output = module.find_matches(tmp_path)
            elapsed = time.monotonic() - started

        self.assertLess(elapsed, 2.0, f"long-line scan took {elapsed:.3f}s")
        self.assertEqual(output["providers"].get("vllm"), 1)
        self.assertEqual(len(output["findings"]), 1)
        self.assertEqual(output["findings"][0]["text"], "[SOURCE_SNIPPET_ELIDED]")
        self.assertEqual(output["source_snippet_policy"], "elided")

    def test_extract_llm_calls_excludes_dotenv_files_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".env").write_text(
                "VLLM_PREFIX_CACHE_RETENTION_INTERVAL=0\n"
                "PYTHONHASHSEED=dotenv-secret\n"
            )
            (tmp_path / ".env.production").write_text(
                "vllm serve model --prefix-cache-retention-interval 0\n"
            )
            (tmp_path / ".env.yaml").write_text(
                "command: vllm serve model --prefix-cache-retention-interval 0\n"
            )
            (tmp_path / ".env.sh").write_text(
                "vllm serve model --prefix-cache-retention-interval 0\n"
            )
            (tmp_path / ".env.json").write_text(
                '{"command": "vllm serve model --prefix-cache-retention-interval 0"}\n'
            )
            (tmp_path / ".env.d").mkdir()
            (tmp_path / ".env.d" / "production.yaml").write_text(
                "command: vllm serve model --prefix-cache-retention-interval 0\n"
            )
            (tmp_path / ".envs").mkdir()
            (tmp_path / ".envs" / "serve.sh").write_text(
                "vllm serve model --prefix-cache-retention-interval 0\n"
            )
            (tmp_path / "serve.sh").write_text(
                "vllm serve model --prefix-cache-retention-interval 0\n"
            )

            result = run_script("extract_llm_calls.py", tmp_path)

        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["files_scanned"], 1)
        scanned_paths = "\n".join(f["path"] for f in output["findings"])
        for env_name in (
            ".env",
            ".env.production",
            ".env.yaml",
            ".env.sh",
            ".env.json",
            ".env.d",
            ".envs",
        ):
            self.assertNotIn(env_name, scanned_paths)
        self.assertNotIn("dotenv-secret", result.stdout)

    def test_extract_llm_calls_excludes_dotenv_root_target(self):
        module = load_script_module("extract_llm_calls.py")
        with tempfile.TemporaryDirectory() as tmp:
            env_root = Path(tmp) / ".env.d"
            env_root.mkdir()
            (env_root / "serve.sh").write_text(
                "vllm serve model --prefix-cache-retention-interval 0\n"
            )

            output = module.find_matches(env_root)

        self.assertEqual(output["files_scanned"], 0)
        self.assertEqual(output["matches"], 0)

    def test_extract_llm_calls_scans_root_under_skipped_named_ancestor(self):
        module = load_script_module("extract_llm_calls.py")
        with tempfile.TemporaryDirectory() as tmp:
            service_root = Path(tmp) / "build" / "pkg"
            service_root.mkdir(parents=True)
            (service_root / "serve.sh").write_text(
                "vllm serve model --prefix-cache-retention-interval 0\n"
            )

            output = module.find_matches(service_root)

        self.assertEqual(output["files_scanned"], 1)
        self.assertEqual(output["matches"], 1)

    def test_skill_frontmatter_description_is_yaml_safe_and_retains_trigger_terms(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()
        frontmatter = skill.split("---", 2)[1]
        lines = frontmatter.splitlines()
        description_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("description:")
        )
        description_line = lines[description_index]
        self.assertRegex(description_line, r'^description:\s+".*"$')
        description = json.loads(description_line.split("description:", 1)[1].strip())
        for required in (
            "Use whenever the user mentions",
            "cached_tokens=0",
            "total_cached_tokens",
            "prompt_cache_options",
            "previous_interaction_id",
            "tools",
            "schemas",
            "response_format",
            "model/router",
            "prefix_cache_retention_interval",
            "prefix_caching_hash_algo",
            "Mamba/SWA/hybrid",
            "cross-process block hash",
        ):
            self.assertIn(required, description)
        self.assertNotIn("provider API surface", description)

    def test_skill_frontmatter_trigger_terms_keep_lexical_boundaries(self):
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()
        frontmatter = skill.split("---", 2)[1]
        description_line = next(
            line for line in frontmatter.splitlines() if line.startswith("description:")
        )
        self.assertRegex(description_line, r'^description:\s+".*"$')
        description = json.loads(description_line.split("description:", 1)[1].strip())

        self.assertNotIn("provider API surface", description)
        for required in (
            "cached_tokens=0",
            "total_cached_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "cache_write_tokens",
            "prompt_cache_key",
            "prompt_cache_options",
            "prompt_cache_breakpoint",
            "previous_interaction_id",
            "cache_control/cachePoint",
        ):
            self.assertRegex(
                description,
                rf"(?<![A-Za-z0-9_]){re.escape(required)}(?![A-Za-z0-9_])",
            )
        for left, right in (
            ("cached_tokens=0", "total_cached_tokens"),
            ("total_cached_tokens=0", "cache_read_input_tokens"),
            ("total_cached_tokens", "cache_read_input_tokens"),
            ("TTFT", "KV reuse"),
            ("KV reuse", "prefix_cache_retention_interval"),
            ("tools", "schemas"),
            ("schemas", "response_format"),
            ("Not for generic prompt writing", "RAG"),
            ("RAG", "token counts"),
            ("token counts", "non-LLM perf"),
        ):
            self.assertNotIn(
                f"{left}{right}",
                description,
                f"glued trigger terms: {left!r} + {right!r}",
            )

        for term in (
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "cache_write_tokens",
            "prompt_cache_key",
            "prompt_cache_options",
            "prompt_cache_breakpoint",
            "previous_interaction_id",
            "cache_control/cachePoint",
            "TTFT",
            "KV reuse",
            "prefix_cache_retention_interval",
            "prefix_caching_hash_algo",
            "Mamba/SWA/hybrid",
            "cross-process block hash",
            "LLM cost or speed regressed",
            "repeated long prompts",
            "speeding up agents",
            "LLM request shape changes",
            "tools",
            "schemas",
            "response_format",
            "model/router",
            "agent loops",
            "compaction",
            "Not for generic prompt writing",
            "RAG",
            "token counts",
            "non-LLM perf",
        ):
            with self.subTest(term=term):
                self.assertRegex(
                    description,
                    rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])",
                )

    def test_vllm_contract_rows_encode_version_geometry_and_hash_upgrade_delta(self):
        reference = (ROOT / "audit-prompt-caching" / "references" / "vllm.md").read_text()
        feature_rows = parse_markdown_table(
            reference,
            "| Runtime evidence | Feature surface | Default/meaning |",
        )
        feature_by_runtime = {row["Runtime evidence"]: row for row in feature_rows}
        self.assertEqual(
            feature_by_runtime["stable `v0.27.1` source/release"]["Feature surface"],
            "env `VLLM_PREFIX_CACHE_RETENTION_INTERVAL`; coordinator consumes it",
        )
        self.assertIn(
            "default `None`",
            feature_by_runtime["stable `v0.27.1` source/release"]["Default/meaning"],
        )
        self.assertIn(
            "CLI/config `prefix_cache_retention_interval`",
            feature_by_runtime["source/nightly containing `017e9f4`"]["Feature surface"],
        )
        self.assertIn(
            "default `0`",
            feature_by_runtime["source/nightly containing `017e9f4`"]["Default/meaning"],
        )

        retention_rows = parse_markdown_table(
            reference,
            "| Runtime | Effective value | Dense/non-eligible groups | SWA/Mamba/hybrid groups |",
        )
        retention = {
            (row["Runtime"], row["Effective value"]): row for row in retention_rows
        }
        stable_none = retention[("stable `v0.27.1` env-only", "`None`")]
        stable_zero = retention[("stable `v0.27.1` env-only", "`0`")]
        stable_positive = retention[("stable `v0.27.1` env-only", "positive")]
        post_zero = retention[("post-`017e9f4` source/main", "`0`")]
        post_positive = retention[("post-`017e9f4` source/main", "positive")]
        self.assertIn("interval does not apply", stable_none["Dense/non-eligible groups"])
        self.assertIn("dense checkpoints", stable_none["SWA/Mamba/hybrid groups"])
        self.assertIn("startup/config error", stable_zero["Dense/non-eligible groups"])
        self.assertIn("semantic checkpoints", stable_zero["SWA/Mamba/hybrid groups"])
        self.assertIn("latest replay boundary", stable_zero["SWA/Mamba/hybrid groups"])
        self.assertIn("shared-prefix junctions", stable_zero["SWA/Mamba/hybrid groups"])
        self.assertIn("startup/config error", stable_positive["Dense/non-eligible groups"])
        self.assertIn("multiple of effective `scheduler_block_size`", stable_positive["SWA/Mamba/hybrid groups"])
        self.assertIn("permitted no-op", post_zero["Dense/non-eligible groups"])
        self.assertIn("semantic checkpoints", post_zero["SWA/Mamba/hybrid groups"])
        self.assertIn("startup/config error", post_positive["Dense/non-eligible groups"])
        self.assertIn("full-attention groups ignore it", post_positive["SWA/Mamba/hybrid groups"])

        geometry_rows = parse_markdown_table(
            reference,
            "| Concrete KV spec class | Retention-interval eligibility |",
        )
        geometry = {row["Concrete KV spec class"]: row["Retention-interval eligibility"] for row in geometry_rows}
        self.assertEqual(
            geometry["`SlidingWindowSpec`, including `SlidingWindowMLASpec`"],
            "eligible",
        )
        self.assertEqual(geometry["`MambaSpec`"], "eligible")
        self.assertEqual(
            geometry["`FullAttentionSpec` and subclasses, including `RSWASpec` and `SinkFullAttentionSpec`"],
            "not eligible",
        )
        self.assertEqual(geometry["`ChunkedLocalAttentionSpec`"], "not eligible in the checked validator")
        self.assertEqual(geometry["unknown/new spec"], "`unknown` until a source/runtime probe confirms it")

        hash_rows = parse_markdown_table(
            reference,
            "| Runtime evidence | Algorithm | Effective default seed | Cross-process reuse |",
        )
        hash_by_key = {(row["Runtime evidence"], row["Algorithm"]): row for row in hash_rows}
        self.assertIn(
            "random `os.urandom(32)` per process",
            hash_by_key[("stable `v0.27.1`", "every supported algorithm")]["Effective default seed"],
        )
        self.assertIn(
            "deterministic from the supplied value",
            hash_by_key[("stable `v0.27.1`", "any algorithm with an explicitly common `PYTHONHASHSEED`")]["Effective default seed"],
        )
        self.assertIn(
            "fixed deterministic default",
            hash_by_key[("post-`ef47a897` source/main", "`sha256`, `sha256_cbor`")]["Effective default seed"],
        )
        self.assertIn(
            "random per process",
            hash_by_key[("post-`ef47a897` source/main", "`xxhash`, `xxhash_cbor`")]["Effective default seed"],
        )
        self.assertIn(
            "explicit `PYTHONHASHSEED` wins",
            hash_by_key[("post-`ef47a897` source/main", "any algorithm with an explicit `PYTHONHASHSEED`")]["Effective default seed"],
        )
        self.assertIn(
            "same algorithm and all other inputs",
            hash_by_key[("post-`ef47a897` source/main", "`sha256`, `sha256_cbor`")]["Cross-process reuse"],
        )

    def test_vllm_version_geometry_contract_is_documented(self):
        root = ROOT / "audit-prompt-caching"
        vllm = (root / "references" / "vllm.md").read_text()
        skill = (root / "SKILL.md").read_text()
        checklist = (root / "references" / "predeploy-checklist.md").read_text()
        observability = (root / "references" / "observability.md").read_text()
        report = (root / "references" / "report-template.md").read_text()
        rules = json.loads((root / "references" / "rules.json").read_text())

        vllm_locator_docs = " ".join(vllm.split())
        self.assertIn("--kv-events-config", vllm_locator_docs)
        self.assertIn(
            "If a deployment line uses `--enable-kv-cache-events`, treat it as "
            "stale/integration-specific deployment guidance; verify exact runtime "
            "parser/version/startup acceptance, and do not assume upstream vLLM "
            "support.",
            vllm_locator_docs,
        )

        for required in (
            "Version and capability gate",
            "v0.27.1",
            "017e9f4",
            "ef47a897",
            "prefix_cache_retention_interval",
            "SlidingWindowSpec",
            "SlidingWindowMLASpec",
            "MambaSpec",
            "RSWASpec",
            "ChunkedLocalAttentionSpec",
            "scheduler_block_size",
            "prefix_match_unit",
            "sha256_cbor",
            "xxhash_cbor",
            "P2P handshake",
            "FS/OBJ",
            "Compatibility is not isolation",
            "cache_salt",
            "raw seed",
        ):
            self.assertIn(required, vllm, required)

        for required in (
            "image digest",
            "feature presence",
            "effective retention",
            "KV-group topology",
            "scheduler block size",
            "hash algorithm",
            "seed compatibility status",
            "tier type",
            "retention/geometry mismatch",
            "cross-process hash mismatch",
            "feature detection",
            "prefix_cache_retention_interval",
            "prefix_caching_hash_algo",
            "AP-1 through AP-14",
            "AP-9b",
            "AP-14",
        ):
            self.assertIn(required, skill, required)

        for required in (
            "retention flag/env",
            "positive interval",
            "different algorithms",
            "different effective seeds",
            "PYTHONHASHSEED",
            "rolling upgrade",
            "image digest",
            "resolved cache config",
            "compatibility status",
        ):
            self.assertIn(required, checklist, required)

        for required in (
            "engine_version",
            "engine_commit",
            "image_digest",
            "retention_feature_present",
            "retention_effective_value",
            "attention_geometry",
            "scheduler_block_size",
            "hash_algorithm",
            "seed_compatibility_status",
            "pythonhashseed_present",
            "pythonhashseed_match_status",
            "kv_tier_type",
            "cache_salt_boundary_fingerprint",
            "matched",
            "mismatched",
            "unknown",
            "Raw seed",
            "bounded cardinality",
        ):
            self.assertIn(required, observability, required)

        for required in (
            "Deployment Audit",
            "Engine version/commit/image:",
            "Capability evidence:",
            "Attention/KV geometry:",
            "Effective retention and source:",
            "Scheduler block size:",
            "Hash algorithm:",
            "Seed compatibility status:",
            "KV tier:",
            "Isolation/cache_salt boundary:",
        ):
            self.assertIn(required, report, required)

        rule_map = {rule["id"]: rule for rule in rules["rules"]}
        for rule_id in ("AP-13", "AP-14"):
            self.assertIn(rule_id, rule_map)
            self.assertEqual(rule_map[rule_id]["default_severity"], "medium")
        self.assertIn("raw seed", rule_map["AP-14"]["avoid"].lower())
        self.assertIn("cache_salt", rule_map["AP-14"]["avoid"])

    def test_vllm_contract_rejects_shortcuts_and_raw_isolation_identifiers(self):
        root = ROOT / "audit-prompt-caching"
        vllm = (root / "references" / "vllm.md").read_text()
        observability = (root / "references" / "observability.md").read_text()
        rules = json.loads((root / "references" / "rules.json").read_text())
        rule_map = {rule["id"]: rule for rule in rules["rules"]}

        def assert_retention_semantics(reference_text):
            retention_rows = parse_markdown_table(
                reference_text,
                "| Runtime | Effective value | Dense/non-eligible groups | SWA/Mamba/hybrid groups |",
            )
            retention = {
                (row["Runtime"], row["Effective value"]): row
                for row in retention_rows
            }
            self.assertIn(
                "startup/config error",
                retention[("stable `v0.27.1` env-only", "`0`")]["Dense/non-eligible groups"],
            )
            self.assertIn(
                "startup/config error",
                retention[("stable `v0.27.1` env-only", "positive")]["Dense/non-eligible groups"],
            )
            self.assertIn(
                "permitted no-op",
                retention[("post-`017e9f4` source/main", "`0`")]["Dense/non-eligible groups"],
            )
            self.assertIn(
                "full-attention groups ignore it",
                retention[("post-`017e9f4` source/main", "positive")]["SWA/Mamba/hybrid groups"],
            )

        assert_retention_semantics(vllm)
        for original, replacement in (
            (
                "startup/config error: any non-`None` env value requires SWA/Mamba groups",
                "permitted no-op",
            ),
            ("permitted no-op", "startup/config error"),
            ("full-attention groups ignore it", "full-attention groups keep it"),
        ):
            mutated_reference = vllm.replace(original, replacement, 1)
            self.assertNotEqual(mutated_reference, vllm)
            with self.subTest(original=original):
                with self.assertRaises(AssertionError):
                    assert_retention_semantics(mutated_reference)

        self.assertIn("algorithm and effective seed are necessary but insufficient", vllm)
        self.assertIn("serialization/runtime", vllm)
        self.assertIn("tenant ID", observability)
        self.assertIn("unbounded metric cardinality", observability)
        self.assertIn("PYTHONHASHSEED", rule_map["AP-14"]["avoid"])

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

    def test_vercel_allowed_tools_contract_is_responses_only_and_version_aware(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "vercel-ai-sdk.md"
        ).read_text()
        section = extract_markdown_section(reference, "OpenAI Responses allowedTools")
        normalized = " ".join(section.split())

        self.assertIn("stable full `tools` catalog", normalized)
        self.assertIn("providerOptions.openai.allowedTools", normalized)
        self.assertIn("Responses-only", normalized)
        self.assertIn("mode: `auto`", normalized)
        self.assertIn("mode: `required`", normalized)
        self.assertIn("toolChoice", normalized)
        self.assertIn("model capability", normalized)
        self.assertIn("tool class", normalized)
        self.assertIn("package.json", normalized)
        self.assertIn("lockfile", normalized)
        self.assertIn("allowedTools capability gate", normalized)
        self.assertIn("allowedTools capability and economics gates", normalized)
        self.assertNotIn("applicability and economics gates", normalized)
        self.assertIn("corrected-mapping gate", normalized)

        chronology = re.search(
            r"May 5, 2026.*?29e6ac6.*?base Responses option.*?"
            r"Aug 18, 2026.*?a062795.*?corrected.*?3\.0\.98.*?4\.0\.43",
            " ".join(section.split()),
        )
        self.assertIsNotNone(
            chronology,
            "base introduction and Aug 18 correction must be distinct chronological evidence",
        )

        rows = parse_markdown_table(
            reference,
            "| `@ai-sdk/openai` line | Availability | Corrected provider-tool mapping |",
        )
        self.assertEqual(len(rows), 4)
        by_line = {row["`@ai-sdk/openai` line"]: row for row in rows}
        self.assertIn("`allowedTools` is absent", by_line["`2.x` / AI SDK v5"]["Availability"])
        self.assertIn("not applicable", by_line["`2.x` / AI SDK v5"]["Corrected provider-tool mapping"])
        self.assertEqual(
            by_line["`3.x` / AI SDK v6"]["Availability"],
            "available from `3.0.62`",
        )
        self.assertEqual(
            by_line["`3.x` / AI SDK v6"]["Corrected provider-tool mapping"],
            "corrected at `>=3.0.98`",
        )
        self.assertEqual(
            by_line["`4.x`"]["Corrected provider-tool mapping"],
            "corrected at `>=4.0.43`",
        )
        self.assertIn("unknown line", by_line)
        self.assertIn("do not transfer floors", by_line["unknown line"]["Corrected provider-tool mapping"])
        self.assertRegex(
            normalized,
            r"For Azure.*references/azure-openai\.md.*endpoint.*deployment/model.*api-version.*Responses tool_choice schema.*final wire",
        )
        self.assertIn("Vercel SDK's name-resolution", normalized)
        self.assertIn("warnings, drop, or error semantics", normalized)
        self.assertNotIn("Do not transfer this behavior to direct OpenAI Responses", normalized)

    def test_vercel_allowed_tools_contract_covers_wire_mapping_and_failure_modes(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "vercel-ai-sdk.md"
        ).read_text()
        section = extract_markdown_section(reference, "OpenAI Responses allowedTools")
        rows = parse_markdown_table(
            section,
            "| Tool class | Entry in `allowed_tools.tools` |",
        )
        self.assertEqual(
            rows,
            [
                {
                    "Tool class": "function",
                    "Entry in `allowed_tools.tools`": "`{type: \"function\", name}`",
                },
                {
                    "Tool class": "custom",
                    "Entry in `allowed_tools.tools`": "`{type: \"custom\", name}`",
                },
                {
                    "Tool class": "MCP",
                    "Entry in `allowed_tools.tools`": "`{type: \"mcp\", server_label}`",
                },
                {
                    "Tool class": "supported built-in/provider-defined tool",
                    "Entry in `allowed_tools.tools`": "`{type}`",
                },
            ],
        )

        normalized = " ".join(section.split())
        for required in [
            "`tool_search`",
            "`deferLoading`",
            "namespaced tools",
            "ambiguous",
            "declared tool name has priority",
            "server-level",
            "empty allow-list",
            "fails with an error",
        ]:
            self.assertIn(required, normalized, required)

    def test_dynamic_tool_references_use_wrapper_aware_economics_gate(self):
        agent_tools = (
            ROOT / "audit-prompt-caching" / "references" / "agent-tools.md"
        ).read_text()
        skill = (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()
        rules = json.loads(
            (ROOT / "audit-prompt-caching" / "references" / "rules.json").read_text()
        )

        agent_section = extract_markdown_section(agent_tools, "Dynamic-tool decision rule")
        agent_normalized = " ".join(agent_section.split())
        self.assertRegex(
            agent_normalized,
            r"global Applicability Gate.*allowedTools capability gate.*stable catalog.*allowed-list.*prefix hashes.*provider usage",
        )
        self.assertRegex(
            agent_normalized,
            r"A direct OpenAI Responses.*Vercel.*different API surfaces",
        )
        self.assertRegex(
            agent_normalized,
            r"Chat Completions.*arbitrary OpenAI-compatible wrapper.*do not inherit",
        )
        self.assertIn("activeTools", agent_normalized)
        self.assertIn("cold or low-reuse route", agent_normalized)
        self.assertNotIn("blanket ban on `activeTools`", agent_normalized)

        playbooks = extract_markdown_section(skill, "Audit Playbooks")
        dynamic_line = next(
            line for line in playbooks.splitlines() if "Dynamic tools in long agent loops" in line
        )
        self.assertIn("economics", dynamic_line)
        self.assertIn("version/model-verified allow-list", dynamic_line)
        self.assertIn("wire proof", dynamic_line)

        ap4 = next(rule for rule in rules["rules"] if rule["id"] == "AP-4")
        self.assertRegex(
            ap4["fix"],
            r"After the global Applicability Gate and economics check, use a stable full catalog plus an endpoint/version-verified allow-list",
        )
        self.assertIn("Mutating activeTools without prefix/economics measurement", ap4["avoid"])
        self.assertIn("provider cache usage", ap4["validation"])
        self.assertNotIn("ban activeTools", ap4["fix"].lower())

    def test_provider_aggregate_evidence_contract_keeps_dashboard_usage_and_request_scopes_separate(self):
        root = ROOT / "audit-prompt-caching"
        openai = (root / "references" / "openai.md").read_text()
        observability = (root / "references" / "observability.md").read_text()
        report = (root / "references" / "report-template.md").read_text()
        evals_text = (root / "evals" / "evals.json").read_text()
        for source_text in (openai, observability, report, evals_text):
            self.assertNotIn(
                "unless its denominator is explicitly defined and recorded",
                source_text,
            )
        openai_section = extract_markdown_section(
            openai, "Prompt Caching dashboard and aggregate evidence"
        )
        marker = "The documented OpenAI Organization Usage API is a separate"
        self.assertIn(marker, openai_section)
        dashboard, _, usage = openai_section.partition(marker)
        self.assertIn("provider_dashboard_aggregate", dashboard)
        self.assertRegex(
            " ".join(dashboard.split()),
            r"evidence_definition_status.*unknown.*evidence_denominator_status.*unknown.*evidence_accounting_semantics.*unknown",
        )
        self.assertIn("provider_usage_api_aggregate", usage)
        usage_normalized = " ".join(usage.split())
        self.assertIn("evidence_definition_status=provider_documented", usage_normalized)
        self.assertIn("evidence_denominator_status=unknown", usage_normalized)
        self.assertIn("evidence_accounting_semantics=provider_defined", usage_normalized)
        self.assertRegex(
            usage_normalized,
            r"input_tokens.*inclusive.*input_uncached_tokens.*uncached input.*excluding cache-write.*neither cache reads nor writes",
        )
        self.assertIn("OpenAI Organization Usage API", usage_normalized)
        self.assertIn("OpenAI prompt-caching guide", usage_normalized)
        self.assertIn("read/write/neither partition", usage_normalized)
        self.assertIn(
            "do not add breakdowns onto inclusive `input_tokens`",
            usage_normalized.lower(),
        )
        self.assertIn("mismatched bucket/group/filter scope", usage_normalized)
        self.assertRegex(
            usage_normalized.lower(),
            r"documented mixed decomposition.*not permission to sum|do not naively sum",
        )
        self.assertRegex(
            usage_normalized.lower(),
            r"optional or missing.*absent/unknown.*never.*zero",
        )
        self.assertNotIn("provider_documented", dashboard)

        observability_section = extract_markdown_section(
            observability, "Provider aggregate evidence boundary"
        )
        contract = re.search(r"```text\n(.*?)\n```", observability_section, re.DOTALL)

        def parse_contract(match, label):
            self.assertIsNotNone(match, label)
            values = {}
            for line in match.group(1).splitlines():
                self.assertRegex(
                    line,
                    r"^[a-z][a-z0-9_]*: .+$",
                    f"malformed {label} line: {line!r}",
                )
                key, value = line.split(":", 1)
                self.assertNotIn(key, values, f"duplicate {label} field: {key}")
                values[key] = value.strip()
            return values

        contract_values = parse_contract(contract, "observability provenance block")
        contract_fields = set(contract_values)
        self.assertEqual(
            contract_fields,
            {
                "evidence_source",
                "provider",
                "time_window",
                "granularity",
                "filters",
                "displayed_metric",
                "displayed_value",
                "evidence_definition_status",
                "evidence_denominator_status",
                "evidence_accounting_semantics",
                "request_correlation",
                "route_correlation",
            },
        )
        observability_normalized = " ".join(observability_section.split())
        self.assertIn("provider_dashboard_aggregate", observability_normalized)
        self.assertIn("provider_usage_api_aggregate", observability_normalized)
        self.assertIn("evidence_definition_status=provider_documented", observability_normalized)
        self.assertIn("evidence_denominator_status=unknown", observability_normalized)
        self.assertIn("evidence_accounting_semantics=provider_defined", observability_normalized)
        self.assertIn("optional or missing fields remain absent/unknown", observability_normalized.lower())
        self.assertIn("never zero", observability_normalized)

        report_section = extract_markdown_section(report, "Evidence Needed Next")
        report_normalized = " ".join(report_section.split())
        report_contract = re.search(r"```text\n(.*?)\n```", report_section, re.DOTALL)
        report_values = parse_contract(report_contract, "report provenance block")
        self.assertEqual(
            report_values,
            contract_values,
            "report-template provenance block must mirror observability schema and enums",
        )
        self.assertIn("Dashboard aggregate", report_normalized)
        self.assertIn("Usage API aggregate", report_normalized)
        for key in (
            "evidence_definition_status",
            "evidence_denominator_status",
            "evidence_accounting_semantics",
        ):
            self.assertIn(key, report_normalized)
        self.assertIn("provider_documented", report_normalized)
        self.assertIn("provider_defined", report_normalized)
        self.assertIn("OpenAI Organization Usage API", report_normalized)
        self.assertIn("OpenAI prompt-caching guide", report_normalized)
        self.assertIn(
            "input_uncached_tokens` is uncached input excluding cache-write tokens",
            report_normalized,
        )
        self.assertIn("read/write/neither partition", report_normalized)
        self.assertIn(
            "optional/missing fields: absent/unknown, never zero",
            report_normalized.lower(),
        )
        self.assertIn("Dashboard statuses remain unknown", report_normalized)

    def test_additive_provider_aggregate_rule_preserves_documented_denominators(self):
        root = ROOT / "audit-prompt-caching"
        observability = (root / "references" / "observability.md").read_text()
        report = (root / "references" / "report-template.md").read_text()
        for reference in (observability, report):
            normalized = " ".join(reference.split())
            self.assertRegex(
                normalized,
                r"additive provider.*full total/denominator.*"
                r"evidence_accounting_semantics=additive.*"
                r"evidence_denominator_status=provider_documented",
            )
            self.assertIn("mismatched bucket/group/filter scopes", normalized)
            self.assertIn("keep the denominator unknown", normalized)
            self.assertIn("Do not apply this additive rule to OpenAI", normalized)

    def test_usage_api_accounting_contract_is_not_reused_for_dashboard_ratios(self):
        openai = (
            ROOT / "audit-prompt-caching" / "references" / "openai.md"
        ).read_text()
        section = extract_markdown_section(
            openai, "Prompt Caching dashboard and aggregate evidence"
        )
        marker = "The documented OpenAI Organization Usage API is a separate"
        self.assertIn(marker, section)
        dashboard, _, usage = section.partition(marker)
        dashboard_normalized = " ".join(dashboard.split())
        usage_normalized = " ".join(usage.split())
        self.assertIn("Dashboard UI", dashboard_normalized)
        self.assertIn("not causal proof", dashboard_normalized)
        self.assertIn("input_tokens` is inclusive", usage_normalized)
        self.assertIn(
            "input_uncached_tokens` is uncached input excluding cache-write tokens",
            usage_normalized,
        )
        self.assertIn("neither cache reads nor writes", usage_normalized)
        self.assertIn("read/write/neither partition", usage_normalized)
        self.assertIn("No same formula is assumed", usage_normalized)
        self.assertIn("denominator is not inferred", usage_normalized)
        self.assertIn("evidence_denominator_status=unknown", usage_normalized)
        self.assertIn("unless the provider documents the denominator", usage_normalized)
        self.assertIn("auditor-defined ratio", usage_normalized)
        self.assertNotIn("input_tokens` is inclusive", dashboard_normalized)

    def test_dynamic_evals_cover_version_wire_contrast_and_aggregate_evidence(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        by_id = {item["id"]: item for item in evals["evals"]}
        required_ids = {25, 26, 27, 28, 29}
        for eval_id in sorted(required_ids):
            self.assertIn(eval_id, by_id, f"missing eval id {eval_id}")

        vercel = by_id[25]
        self.assertIn("activeTools", vercel["prompt"])
        self.assertIn("providerOptions.openai.allowedTools", vercel["prompt"])
        self.assertNotIn("server_label", vercel["prompt"])
        for tool_class in ("function", "custom", "MCP", "web-search"):
            self.assertIn(tool_class, vercel["prompt"])
        self.assertNotIn("{type:", vercel["prompt"])
        self.assertRegex(vercel["expected_output"], r"stable full tools catalog.*Responses")
        self.assertIn("mode: auto", vercel["expected_output"])
        self.assertIn("mode: required", vercel["expected_output"])
        self.assertIn("tool_choice wire mapping", vercel["expected_output"])
        self.assertIn("allowedTools capability", vercel["expected_output"])
        self.assertNotIn("tool applicability", vercel["expected_output"])
        for wire_anchor in (
            '{type: "function", name}',
            '{type: "custom", name}',
            '{type: "mcp", server_label}',
            '{type: "web_search"}',
        ):
            self.assertIn(wire_anchor, vercel["expected_output"])
        for unsupported in ("tool_search", "deferLoading", "namespaced tools"):
            self.assertIn(unsupported, vercel["expected_output"])
        self.assertIn("empty allow-list", vercel["expected_output"])
        self.assertIn("fails with an error", vercel["expected_output"])

        version = by_id[26]
        self.assertIn("@ai-sdk/openai ^3.0.70", version["prompt"])
        self.assertIn("openai.responses()", version["prompt"])
        self.assertIn("openai.tools.webSearch()", version["prompt"])
        self.assertIn("Which version evidence and version floors decide", version["prompt"])
        for leaked_floor in ("2.x unavailable", "3.0.62", "3.0.98", "4.0.43"):
            self.assertNotIn(leaked_floor, version["prompt"])
        self.assertRegex(
            version["expected_output"],
            r"2\.x unavailable.*3\.x.*3\.0\.62.*3\.0\.98.*4\.0\.43",
        )

        dashboard = by_id[27]["expected_output"]
        self.assertRegex(
            dashboard,
            r"provider_dashboard_aggregate.*Dashboard aggregate.*evidence_definition_status.*unknown.*evidence_denominator_status.*unknown.*evidence_accounting_semantics.*unknown",
        )
        self.assertNotIn("provider_documented", dashboard)
        self.assertIn("request-level usage", dashboard)
        self.assertIn("route correlation", dashboard)

        usage = by_id[28]["expected_output"]
        self.assertRegex(
            usage,
            r"provider_usage_api_aggregate.*Usage API aggregate.*evidence_definition_status.*provider_documented.*evidence_denominator_status.*unknown.*input_tokens.*inclusive.*input_uncached_tokens.*uncached input.*excluding cache-write.*neither cache reads nor writes",
        )
        self.assertIn("Dashboard UI", usage)
        self.assertIn("filters", usage)
        self.assertIn("not permission to sum", usage)
        self.assertIn("read/write/neither partition", usage)
        self.assertIn("auditor-defined ratio", usage)
        self.assertIn("OpenAI Organization Usage API", usage)

        contrast = by_id[29]["expected_output"]
        self.assertRegex(
            contrast,
            r"Azure.*references/azure-openai\.md.*endpoint.*deployment/model.*api-version",
        )
        self.assertIn("Responses tool_choice schema", contrast)
        self.assertIn("final wire", contrast)
        self.assertIn("without claiming universal support", contrast)

    def test_dynamic_trigger_eval_adds_positive_tool_and_dashboard_pressure(self):
        trigger_eval = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "trigger_eval.json").read_text()
        )
        positives = [item["query"] for item in trigger_eval if item["should_trigger"]]
        self.assertTrue(any("activeTools" in query and "allowedTools" in query for query in positives))
        self.assertTrue(any("Prompt Caching dashboard" in query for query in positives))

    def test_wire_mapping_is_not_duplicated_outside_vercel_reference(self):
        root = ROOT / "audit-prompt-caching"
        vercel = (root / "references" / "vercel-ai-sdk.md").read_text()
        section = extract_markdown_section(vercel, "OpenAI Responses allowedTools")
        table_header = "| Tool class | Entry in `allowed_tools.tools` |"
        self.assertEqual(section.count(table_header), 1)
        self.assertEqual(vercel.count(table_header), 1)
        self.assertEqual(
            parse_markdown_table(section, table_header)[0]["Tool class"],
            "function",
        )
        for path in root.rglob("*"):
            if path == root / "references" / "vercel-ai-sdk.md":
                continue
            if path.suffix not in {".md", ".json"}:
                continue
            self.assertNotIn(table_header, path.read_text(), str(path.relative_to(root)))

    def test_azure_responses_capability_gate_has_destination_content(self):
        azure = (
            ROOT / "audit-prompt-caching" / "references" / "azure-openai.md"
        ).read_text()
        self.assertIn("Last reviewed: 2026-08-11.", azure)
        section = extract_markdown_section(azure, "Responses endpoint capability gate")
        normalized = " ".join(section.split())
        self.assertIn("Section reviewed: 2026-08-23.", normalized)
        for required in (
            "Responses endpoint",
            "endpoint",
            "deployment/model",
            "api-version",
            "Responses `tool_choice` schema",
            "final request wire",
            "no universal Azure support claim",
        ):
            self.assertIn(required, normalized)


    def skill_text(self):
        return (ROOT / "audit-prompt-caching" / "SKILL.md").read_text()

    def skill_frontmatter_description(self):
        frontmatter = self.skill_text().split("---", 2)[1]
        self.assertIn("description:", frontmatter)
        description_line = next(
            line for line in frontmatter.splitlines() if line.startswith("description:")
        )
        self.assertRegex(description_line, r'^description:\s+".*"$')
        return json.loads(description_line.split("description:", 1)[1].strip())

    def test_skill_description_is_shorter_but_keeps_trigger_boundaries(self):
        description = self.skill_frontmatter_description()

        self.assertEqual(
            PLUGIN_EVAL_TRIGGER_TOKEN_BUDGET,
            147,
            "the trigger ceiling must stay at the smallest measured parsed-description value",
        )
        self.assertEqual(
            BASELINE_DESCRIPTION_CHARS,
            679,
            "the historical description baseline must remain a fixed contract",
        )

        self.assertLessEqual(
            estimated_plugin_eval_tokens(description),
            PLUGIN_EVAL_TRIGGER_TOKEN_BUDGET,
            "frontmatter description exceeds the plugin-eval moderate trigger ceiling",
        )
        self.assertLess(
            len(description),
            BASELINE_DESCRIPTION_CHARS,
            "frontmatter description exceeds the historical character baseline",
        )

        for required in [
            "Use whenever the user mentions",
            "cached_tokens=0",
            "total_cached_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "cache_write_tokens",
            "prompt_cache_key",
            "prompt_cache_options",
            "prompt_cache_breakpoint",
            "previous_interaction_id",
            "cache_control",
            "cachePoint",
            "TTFT",
            "KV reuse",
            "LLM cost or speed regressed",
            "repeated long prompts",
            "speeding up agents",
            "LLM request shape",
            "response_format",
            "agent loops",
            "compaction",
            "Not for generic prompt writing",
            "RAG",
            "token counts",
            "non-LLM perf",
        ]:
            self.assertIn(required, description)

    def test_skill_description_keeps_provider_telemetry_anchors(self):
        description = self.skill_frontmatter_description()
        body = self.skill_text().split("---", 2)[2]

        for anchor in [
            "cached_tokens=0",
            "total_cached_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "cache_write_tokens",
            "prompt_cache_key",
            "prompt_cache_options",
            "prompt_cache_breakpoint",
            "previous_interaction_id",
        ]:
            with self.subTest(anchor=anchor):
                self.assertIn(
                    anchor,
                    description,
                    f"{anchor} must be a frontmatter trigger anchor, not body-only",
                )

        self.assertNotIn("description:", body)

    def test_skill_preserves_operational_audit_flow_order_and_classification(self):
        skill = self.skill_text()
        required_flow = (
            "Map prompt structure in order: tools, schemas, system/developer instructions, "
            "examples, static documents, retrieved context, history, user data, volatile values; "
            "mark each segment static, semi-static, dynamic, or volatile."
        )
        self.assertIn(required_flow, skill)
        self.assertLess(
            skill.index("Map prompt structure in order:"),
            skill.index("Ask for usage logs"),
        )
        for required in (
            "a reported hit rate is not trusted",
            "cache salts",
            "tokenizer/chat-template drift",
            "KV pressure",
            "OpenAI-compatible wrapper ambiguity",
        ):
            self.assertIn(required, skill)

    def test_skill_stays_within_invoked_token_baseline(self):
        self.assertEqual(
            PLUGIN_EVAL_SKILL_TOKEN_BASELINE,
            5979,
            "the whole-skill baseline must equal the measured restored content",
        )
        self.assertLessEqual(
            estimated_plugin_eval_tokens(self.skill_text()),
            PLUGIN_EVAL_SKILL_TOKEN_BASELINE,
            "SKILL.md grew above the plugin-eval invoked-token baseline",
        )

    def test_skill_defines_explicit_cache_plane_gate(self):
        skill = self.skill_text()

        for required in [
            "Cache Plane Gate",
            "gateway_response",
            "provider_prompt",
            "engine_kv",
            "external_kv",
            "semantic_response",
            "several planes at once",
            "Do not infer a plane from provider or model names",
        ]:
            self.assertIn(required, skill)

    def test_skill_defines_usage_evidence_contract(self):
        skill = self.skill_text()

        for required in [
            "Usage Evidence Contract",
            "schema_version",
            "source_fields",
            "accounting_semantics",
            "denominator_status",
            "`warnings`",
            "decision-grade",
            "valid",
            "ambiguous",
            "invalid",
            "Do not build a second normalizer",
        ]:
            self.assertIn(required, skill)

    def test_skill_defines_no_score_clinic_summary(self):
        skill = self.skill_text()

        for required in [
            "Cache Clinic Summary",
            "applicability",
            "evidence_quality",
            "prefix_stability",
            "usage_accounting",
            "routing_locality",
            "economics",
            "isolation",
            "pass/warning/fail/unknown/not_applicable",
            "Leave every unproven dimension `unknown`",
            "never aggregate them into a score, rank, or grade",
        ]:
            self.assertIn(required, skill)

    def test_skill_bounds_prefix_plan_and_isolation_evidence(self):
        skill = self.skill_text()

        for required in [
            "observed rendered payload",
            "request-construction",
            "universal provider-internal serialization order",
            "Isolation review is passive",
            "separate authorization",
            "out of scope",
        ]:
            self.assertIn(required, skill)

    def test_observability_reference_documents_usage_evidence_contract(self):
        reference = (
            ROOT / "audit-prompt-caching" / "references" / "observability.md"
        ).read_text()

        for required in [
            "Usage Evidence Contract",
            "schema_version",
            "source_fields",
            "accounting_semantics",
            "denominator_status",
            "usage.prompt_tokens_details.cached_tokens",
            "human-readable dot paths",
            "not machine-resolvable JSONPath",
            "dynamic map keys",
            "Paths never contain leaf values or raw envelopes",
            "Backward Compatibility",
            "additive",
            "strict JSON consumers must allow new event, summary, and report fields",
            "aggregate and report schema versioning remains deferred",
        ]:
            self.assertIn(required, reference)

    def test_report_template_documents_plane_and_clinic_contract(self):
        template = (
            ROOT / "audit-prompt-caching" / "references" / "report-template.md"
        ).read_text()

        for required in [
            "Cache Planes",
            "--cache-plane",
            "repeatable",
            "gateway_response",
            "provider_prompt",
            "engine_kv",
            "external_kv",
            "semantic_response",
            "Cache Clinic Summary",
            "applicability",
            "evidence_quality",
            "prefix_stability",
            "usage_accounting",
            "routing_locality",
            "economics",
            "isolation",
            "pass/warning/fail/unknown/not_applicable",
            "--usage-accounting",
            "--evidence-quality",
            "non-decision-grade",
            "no aggregate score",
        ]:
            self.assertIn(required, template)

    def test_readme_documents_cache_plane_and_clinic_flags(self):
        readme = (ROOT / "README.md").read_text()

        for required in [
            "--cache-plane gateway_response",
            "--cache-plane provider_prompt",
            "--evidence-quality",
            "--usage-accounting",
            "non-decision-grade",
            "no aggregate score",
        ]:
            self.assertIn(required, readme)

    def test_evals_cover_plane_denominator_and_unknown_dimension_pressure(self):
        evals = json.loads(
            (ROOT / "audit-prompt-caching" / "evals" / "evals.json").read_text()
        )
        combined = "\n".join(
            item["prompt"] + "\n" + item["expected_output"] for item in evals["evals"]
        )

        for required in [
            "gateway response-cache hit rate",
            "cached_tokens stays 0",
            "gateway_response",
            "provider_prompt",
            "unknown OpenAI-compatible wrapper",
            "95 percent cache hit rate",
            "denominator_status",
            "ambiguous",
            "no savings claim",
            "no usage logs",
            "cache clinic summary",
            "unknown",
            "no aggregate score",
        ]:
            self.assertIn(required, combined)

if __name__ == "__main__":
    unittest.main()
