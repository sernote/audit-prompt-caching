"""Behavior checks for the custom normalized routing export, never native logs."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "audit-prompt-caching" / "scripts" / "analyze_routing_logs.py"
FIXTURES = ROOT / "fixtures" / "routing"


def event(kind="decision", **fields):
    """Make a fresh minimal synthetic event; tests specify their observations."""
    return {
        "schema_version": 1,
        "event": kind,
        "run_id": "run-1",
        "request_id": "request-1",
        "attempt_id": "attempt-1",
        "model_id": "model-revision-1",
        "pool_id": "pool-1",
        "worker_id": "worker-1",
        "source": f"synthetic:{kind}",
        "provenance": "synthetic",
        **fields,
    }


class RoutingLogsTest(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def invoke_text(self, content, *args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "export.jsonl"
            original = content if isinstance(content, bytes) else content.encode("utf-8")
            path.write_bytes(original)
            result = self.invoke(path, *args)
            self.assertEqual(path.read_bytes(), original, "analysis mutated its input")
            return result

    def invoke_events(self, *records, args=()):
        return self.invoke_text("\n".join(json.dumps(row) for row in records), *args)

    def result(self, process, exit_code=0):
        self.assertEqual(process.returncode, exit_code, process.stderr)
        self.assertEqual(process.stderr, "", "CLI errors must use JSON stdout")
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError:
            self.fail(f"expected JSON stdout, got {process.stdout!r}")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["status"], "ok" if exit_code == 0 else "error")
        return result

    def error(self, process, *, field=None, line=1):
        result = self.result(process, exit_code=2)
        self.assertNotIn("attempts", result, "invalid exports must not yield partial evidence")
        self.assertNotIn("counts", result)
        self.assertEqual(result["error"]["line"], line)
        if field is not None:
            self.assertEqual(result["error"]["field"], field)
        self.assertTrue(result["error"]["message"])
        return result

    def test_joins_reversed_events_and_retains_lines_and_source(self):
        decision = event(router_id="router-1", policy="cache_aware")
        outcome = event("outcome", status="success", client_ttft_ms=200, client_e2e_ms=900)
        result = self.result(self.invoke_events(outcome, decision))
        self.assertEqual(result["counts"]["records"], 2)
        self.assertEqual(result["counts"]["unique_requests"], 1)
        self.assertEqual(result["counts"]["attempts"], 1)
        self.assertEqual(result["counts"]["matched"], 1)
        row = result["attempts"][0]
        self.assertEqual(row["join_status"], "matched")
        self.assertEqual(row["run_id"], "run-1")
        self.assertEqual(row["request_id"], "request-1")
        self.assertEqual(row["attempt_id"], "attempt-1")
        self.assertEqual(row["model_id"], "model-revision-1")
        self.assertEqual(row["pool_id"], "pool-1")
        self.assertEqual(row["worker_id"], "worker-1")
        self.assertEqual(row["decision"]["line"], 2)
        self.assertEqual(row["decision"]["source"], "synthetic:decision")
        self.assertEqual(row["decision"]["router_id"], "router-1")
        self.assertEqual(row["decision"]["policy"], "cache_aware")
        self.assertEqual(row["outcome"]["line"], 1)
        self.assertEqual(row["outcome"]["source"], "synthetic:outcome")
        self.assertEqual(row["outcome"]["status"], "success")
        self.assertEqual(row["outcome"]["client_ttft_ms"], 200)

    def test_missing_counterparts_do_not_invent_outcomes_or_decisions(self):
        result = self.result(self.invoke_events(
            event(), event("outcome", request_id="request-2", status="error")
        ))
        self.assertEqual(result["counts"]["matched"], 0)
        self.assertEqual(result["counts"]["decision_only"], 1)
        self.assertEqual(result["counts"]["outcome_only"], 1)
        self.assertEqual(result["counts"]["terminal_status"], {
            "known": 1, "unknown": 1, "success": 0, "error": 1, "cancelled": 0,
        })
        first, second = result["attempts"]
        self.assertEqual(first["join_status"], "decision_only")
        self.assertIsNone(first["outcome"])
        self.assertEqual(second["join_status"], "outcome_only")
        self.assertIsNone(second["decision"])
        self.assertEqual(second["outcome"]["status"], "error")

    def test_counts_requests_by_run_and_preserves_distinct_attempts(self):
        result = self.result(self.invoke_events(
            event("outcome", attempt_id="attempt-2", worker_id="worker-2", status="success"),
            event("outcome", status="cancelled"),
            event(run_id="run-2", model_id="different-model", pool_id="different-pool"),
            event(attempt_id="attempt-2", worker_id="worker-2"),
            event(),
        ))
        counts = result["counts"]
        self.assertEqual(counts["records"], 5)
        self.assertEqual(counts["unique_requests"], 2)
        self.assertEqual(counts["attempts"], 3)
        self.assertEqual(counts["additional_attempts"], 1)
        self.assertEqual(counts["matched"], 2)
        self.assertEqual(counts["terminal_status"], {
            "known": 2, "unknown": 1, "success": 1, "error": 0, "cancelled": 1,
        })
        self.assertEqual(
            [(row["run_id"], row["request_id"], row["attempt_id"]) for row in result["attempts"]],
            [("run-1", "request-1", "attempt-1"), ("run-1", "request-1", "attempt-2"),
             ("run-2", "request-1", "attempt-1")],
        )
        self.assertEqual(result["attempts"][1]["worker_id"], "worker-2")
        self.assertEqual(result["attempts"][2]["model_id"], "different-model")
        self.assertEqual(result["attempts"][2]["pool_id"], "different-pool")

    def test_provenance_counts_distinguish_records_from_attempts(self):
        result = self.result(self.invoke_events(
            event(), event("outcome"),
            event(request_id="observed-request", provenance="observed", source="trace:12"),
        ))
        self.assertEqual(result["provenance"], {
            "records": {"observed": 1, "synthetic": 2},
            "attempts": {"observed": 1, "synthetic": 1},
        })
        self.assertEqual(result["attempts"][0]["provenance"], "observed")
        self.assertEqual(result["attempts"][0]["decision"]["source"], "trace:12")
        self.assertEqual(result["attempts"][1]["provenance"], "synthetic")

    def test_absent_and_explicit_null_fields_stay_unknown(self):
        omitted = self.result(self.invoke_events(event(), event("outcome")))
        explicit = self.result(self.invoke_events(
            event(router_id=None, policy=None, predicted_overlap=None, load=None),
            event("outcome", status=None, client_ttft_ms=None, client_e2e_ms=None,
                  queue_ms=None, input_tokens=None, reused_tokens=None),
        ))
        self.assertEqual(omitted, explicit)
        row = omitted["attempts"][0]
        for field in ("router_id", "policy", "predicted_overlap", "load"):
            self.assertIsNone(row["decision"][field])
        for field in ("status", "client_ttft_ms", "client_e2e_ms", "queue_ms", "input_tokens", "reused_tokens"):
            self.assertIsNone(row["outcome"][field])
        self.assertEqual(row["ttft_assessment"], "unknown")
        self.assertIsNone(row["reuse_with_ttft_violation"])

    def test_observed_zero_is_known_even_with_unknown_input_denominator(self):
        result = self.result(self.invoke_events(
            event("outcome", client_ttft_ms=0, client_e2e_ms=0, queue_ms=0, reused_tokens=0),
            args=("--attempt-ttft-limit-ms", "0"),
        ))
        row = result["attempts"][0]
        for field in ("client_ttft_ms", "client_e2e_ms", "queue_ms", "reused_tokens"):
            self.assertEqual(row["outcome"][field], 0)
            self.assertEqual(result["counts"]["measurement_coverage"][field], {"known": 1, "unknown": 0})
        self.assertIsNone(row["outcome"]["input_tokens"])
        self.assertEqual(result["counts"]["measurement_coverage"]["input_tokens"], {"known": 0, "unknown": 1})
        self.assertEqual(row["ttft_assessment"], "within_limit")
        self.assertIs(row["reuse_with_ttft_violation"], False)

    def test_measurement_coverage_counts_attempts_with_missing_outcomes(self):
        result = self.result(self.invoke_events(
            event(),
            event("outcome", request_id="request-2", client_ttft_ms=12, input_tokens=50, reused_tokens=10),
            event("outcome", request_id="request-3", client_e2e_ms=20, queue_ms=0),
        ))
        for field in ("client_ttft_ms", "client_e2e_ms", "queue_ms", "input_tokens", "reused_tokens"):
            self.assertEqual(result["counts"]["measurement_coverage"][field], {"known": 1, "unknown": 2})

    def test_empty_prediction_is_preserved_without_an_undefined_ratio(self):
        overlap = {"matched": 0, "total": 0, "unit": "characters", "kind": "request_history", "worker_id": None}
        result = self.result(self.invoke_events(event(predicted_overlap=overlap)))
        self.assertEqual(result["attempts"][0]["decision"]["predicted_overlap"], overlap)

    def test_prediction_units_and_target_are_separate_from_selected_worker_and_reuse(self):
        for unit, kind, target in (
            ("characters", "request_history", "worker-2"),
            ("tokens", "kv_events", None),
            ("blocks", "kv_events", "worker-1"),
        ):
            with self.subTest(unit=unit, target=target):
                overlap = {"matched": 900, "total": 1000, "unit": unit, "kind": kind, "worker_id": target}
                result = self.result(self.invoke_events(
                    event(predicted_overlap=overlap),
                    event("outcome", input_tokens=10, reused_tokens=5),
                ))
                row = result["attempts"][0]
                self.assertEqual(row["worker_id"], "worker-1")
                self.assertEqual(row["decision"]["predicted_overlap"], overlap)
                self.assertEqual(row["outcome"]["reused_tokens"], 5)

    def test_load_kind_and_scope_are_preserved(self):
        for kind, scope in (("active_requests", "router_local"), ("active_tokens", "pool"), ("active_requests", "unknown")):
            with self.subTest(kind=kind, scope=scope):
                load = {"value": 0.5, "kind": kind, "scope": scope}
                result = self.result(self.invoke_events(event(load=load)))
                self.assertEqual(result["attempts"][0]["decision"]["load"], load)

    def test_high_actual_reuse_with_slow_ttft_is_valid_analysis(self):
        result = self.result(self.invoke_events(
            event(),
            event("outcome", status="success", client_ttft_ms=1200, client_e2e_ms=2000,
                  queue_ms=1000, input_tokens=1000, reused_tokens=900),
            args=("--attempt-ttft-limit-ms", "500"),
        ))
        self.assertEqual(result["attempt_ttft_limit"], {
            "limit_ms": 500, "scope": "per_attempt_client_ttft", "assessment": "evaluated",
            "known": 1, "unknown": 0, "violations": 1,
        })
        row = result["attempts"][0]
        self.assertEqual(row["ttft_assessment"], "violation")
        self.assertIs(row["reuse_with_ttft_violation"], True)
        self.assertEqual(row["outcome"]["status"], "success")

    def test_ttft_at_declared_limit_is_not_a_violation(self):
        result = self.result(self.invoke_events(
            event("outcome", client_ttft_ms=500, reused_tokens=1),
            args=("--attempt-ttft-limit-ms", "500"),
        ))
        self.assertEqual(result["attempts"][0]["ttft_assessment"], "within_limit")
        self.assertIs(result["attempts"][0]["reuse_with_ttft_violation"], False)
        self.assertEqual(result["attempt_ttft_limit"]["violations"], 0)

    def test_no_limit_means_unknown_assessment_despite_measured_ttft(self):
        result = self.result(self.invoke_events(event("outcome", client_ttft_ms=1200, reused_tokens=900)))
        self.assertEqual(result["attempt_ttft_limit"], {
            "limit_ms": None, "scope": "per_attempt_client_ttft", "assessment": "unknown",
            "known": 0, "unknown": 1, "violations": None,
        })
        self.assertEqual(result["attempts"][0]["ttft_assessment"], "unknown")
        self.assertIsNone(result["attempts"][0]["reuse_with_ttft_violation"])
        self.assertEqual(result["counts"]["measurement_coverage"]["client_ttft_ms"], {"known": 1, "unknown": 0})

    def test_missing_ttft_or_actual_reuse_never_infers_joint_violation(self):
        result = self.result(self.invoke_events(
            event("outcome", request_id="request-1", client_ttft_ms=1200),
            event("outcome", request_id="request-2", reused_tokens=900),
            event("outcome", request_id="request-3", client_ttft_ms=1200, reused_tokens=0),
            event(request_id="request-4", predicted_overlap={
                "matched": 900, "total": 1000, "unit": "tokens", "kind": "kv_events", "worker_id": "worker-1",
            }),
            args=("--attempt-ttft-limit-ms", "500"),
        ))
        self.assertEqual(result["attempt_ttft_limit"]["known"], 2)
        self.assertEqual(result["attempt_ttft_limit"]["unknown"], 2)
        self.assertEqual(result["attempt_ttft_limit"]["violations"], 2)
        self.assertEqual([row["reuse_with_ttft_violation"] for row in result["attempts"]], [None, None, False, None])

    def test_declared_limit_without_any_ttft_has_unknown_assessment(self):
        result = self.result(self.invoke_events(
            event(),
            event("outcome", request_id="request-2", reused_tokens=900),
            args=("--attempt-ttft-limit-ms", "500"),
        ))
        self.assertEqual(result["attempt_ttft_limit"], {
            "limit_ms": 500, "scope": "per_attempt_client_ttft", "assessment": "unknown",
            "known": 0, "unknown": 2, "violations": 0,
        })
        self.assertEqual([row["ttft_assessment"] for row in result["attempts"]], ["unknown", "unknown"])

    def test_identical_input_has_deterministic_output_and_physical_line_numbers(self):
        content = "\n" + json.dumps(event(request_id="z")) + "\n \n" + json.dumps(event(request_id="a"))
        first = self.invoke_text(content)
        second = self.invoke_text(content)
        result = self.result(first)
        self.result(second)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(result["counts"]["records"], 2)
        self.assertEqual([row["request_id"] for row in result["attempts"]], ["a", "z"])
        self.assertEqual([row["decision"]["line"] for row in result["attempts"]], [4, 2])

    def test_rejects_duplicate_same_event_even_if_identical(self):
        for kind in ("decision", "outcome"):
            with self.subTest(kind=kind):
                self.error(self.invoke_events(event(kind), event(kind)), field="event", line=2)

    def test_rejects_conflicting_join_context_or_provenance(self):
        for field, value in (("model_id", "other"), ("pool_id", "other"), ("worker_id", "other"), ("provenance", "observed")):
            with self.subTest(field=field):
                self.error(self.invoke_events(event(), event("outcome", **{field: value})), field=field, line=2)

    def test_rejects_missing_required_fields(self):
        for field in event():
            with self.subTest(field=field):
                record = event()
                del record[field]
                self.error(self.invoke_events(record), field=field)

    def test_rejects_nonstring_or_empty_required_identity_and_source(self):
        for field in ("run_id", "request_id", "attempt_id", "model_id", "pool_id", "worker_id", "source"):
            for value in (None, "", " \t", 1, False, []):
                with self.subTest(field=field, value=value):
                    self.error(self.invoke_events(event(**{field: value})), field=field)

    def test_rejects_unsupported_schema_event_provenance_and_status(self):
        for field, values in (
            ("schema_version", (True, 1.0, 2, "1", None)),
            ("event", ("other", None, 2, [])),
            ("provenance", ("inferred", "", None, [])),
            ("status", ("running", "", False, [])),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    kind = "outcome" if field == "status" else "decision"
                    self.error(self.invoke_events(event(kind, **{field: value})), field=field)

    def test_rejects_nonstring_or_empty_optional_strings(self):
        for field in ("router_id", "policy"):
            for value in ("", " ", 1, False):
                with self.subTest(field=field, value=value):
                    self.error(self.invoke_events(event(**{field: value})), field=field)

    def test_rejects_nonfinite_negative_boolean_and_string_measurements(self):
        for field in ("client_ttft_ms", "client_e2e_ms", "queue_ms", "input_tokens", "reused_tokens"):
            for value in (-1, True, "1", float("nan"), float("inf"), float("-inf"), [], {}):
                with self.subTest(field=field, value=value):
                    self.error(self.invoke_events(event("outcome", **{field: value})))
        for field in ("input_tokens", "reused_tokens"):
            with self.subTest(field=field, value=1.0):
                self.error(self.invoke_events(event("outcome", **{field: 1.0})), field=field)

    def test_rejects_ttft_after_attempt_end_and_reuse_above_input(self):
        self.error(self.invoke_events(event("outcome", client_ttft_ms=2, client_e2e_ms=1)), field="client_ttft_ms")
        self.error(self.invoke_events(event("outcome", input_tokens=1, reused_tokens=2)), field="reused_tokens")

    def test_rejects_incomplete_invalid_and_extra_prediction_fields(self):
        valid = {"matched": 1, "total": 2, "unit": "characters", "kind": "request_history", "worker_id": None}
        for field in valid:
            with self.subTest(missing=field):
                overlap = dict(valid)
                del overlap[field]
                self.error(self.invoke_events(event(predicted_overlap=overlap)), field=f"predicted_overlap.{field}")
        for field, values in (
            ("matched", (-1, True, "1", 1.0, None, 3)),
            ("total", (-1, False, "2", 2.0, None)),
            ("unit", ("bytes", "", None, [])),
            ("kind", ("estimated", "", None, [])),
            ("worker_id", ("", " ", 1, False)),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    overlap = {**valid, field: value}
                    self.error(self.invoke_events(event(predicted_overlap=overlap)), field=f"predicted_overlap.{field}")
        self.error(self.invoke_events(event(predicted_overlap={**valid, "extra": 3})), field="predicted_overlap")
        self.error(self.invoke_events(event(predicted_overlap=[])), field="predicted_overlap")

    def test_rejects_incomplete_invalid_and_extra_load_fields(self):
        valid = {"value": 1, "kind": "active_requests", "scope": "router_local"}
        for field in valid:
            with self.subTest(missing=field):
                load = dict(valid)
                del load[field]
                self.error(self.invoke_events(event(load=load)), field=f"load.{field}")
        for field, values in (
            ("value", (-1, True, "1", None, [])),
            ("kind", ("queue", "", None, [])),
            ("scope", ("cluster", "", None, [])),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.error(self.invoke_events(event(load={**valid, field: value})), field=f"load.{field}")
        self.error(self.invoke_events(event(load={**valid, "extra": 2})), field="load")
        self.error(self.invoke_events(event(load=[])), field="load")
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(nonfinite=value):
                self.error(self.invoke_events(event(load={**valid, "value": value})))

    def test_rejects_unknown_and_wrong_event_fields_without_echoing_values(self):
        for record in (event(secret="sensitive-prompt"), event(status="success"), event("outcome", policy="cache_aware")):
            with self.subTest(record=record):
                process = self.invoke_events(record)
                self.error(process, field="record")
                self.assertNotIn("sensitive-prompt", process.stdout)
                self.assertNotIn("synthetic:decision", process.stdout)

    def test_rejects_duplicate_json_keys_including_nested_objects(self):
        base = json.dumps(event())[:-1]
        for extra in (
            ', "worker_id": "other"}',
            ', "predicted_overlap": {"matched": 0, "matched": 1, "total": 1, "unit": "tokens", "kind": "kv_events", "worker_id": null}}',
        ):
            with self.subTest(extra=extra):
                self.error(self.invoke_text(base + extra), field="record")

    def test_rejects_empty_nonobject_and_malformed_json_without_partial_success(self):
        for content in ("", "\n \n", "null", "[]", "12", '"text"', '{"prompt":"private-content"', "{", "{} {}"):
            with self.subTest(content=content):
                prefix = json.dumps(event()) + "\n" if content.strip() else ""
                process = self.invoke_text(prefix + content)
                self.error(process, field="record", line=2 if prefix else None)
                self.assertNotIn("private-content", process.stdout)

    def test_rejects_non_utf8_file_as_json_error(self):
        self.error(self.invoke_text(b'\xff\n'), field="input", line=None)

    def test_rejects_json_number_overflow_without_traceback(self):
        content = json.dumps(event("outcome"))[:-1] + ', "client_ttft_ms": 1e999}'
        self.error(self.invoke_text(content), field="client_ttft_ms")

    def test_missing_file_and_directory_input_are_json_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            self.error(self.invoke(Path(directory) / "missing.jsonl"), field="input", line=None)
            self.error(self.invoke(directory), field="input", line=None)

    def test_bad_cli_flags_and_missing_arguments_are_json_errors(self):
        for args in ((), ("--unknown-secret-option",), ("--attempt-ttft-limit-ms",), ("--attempt-ttft-limit-ms", "12")):
            with self.subTest(args=args):
                process = self.invoke(*args)
                self.error(process, field="arguments", line=None)
                self.assertNotIn("--unknown-secret-option", process.stdout)
        self.error(self.invoke_events(event(), args=("--bad-flag",)), field="arguments", line=None)

    def test_invalid_limits_are_json_errors(self):
        for value in ("-1", "nan", "inf", "-inf", "not-a-number", "1e999"):
            with self.subTest(value=value):
                self.error(
                    self.invoke_events(event(), args=(f"--attempt-ttft-limit-ms={value}",)),
                    field="attempt_ttft_limit_ms", line=None,
                )

    def test_help_is_ordinary_text(self):
        process = self.invoke("--help")
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        self.assertIn("--attempt-ttft-limit-ms", process.stdout)
        self.assertIn("normalized", process.stdout)
        self.assertFalse(process.stdout.lstrip().startswith("{"))

    def test_synthetic_fixtures_exercise_slow_within_limit_and_unknown_paths(self):
        for name, join, assessment, violations, flag, records in (
            ("slow-with-reuse", "matched", "violation", 1, True, 2),
            ("within-limit", "matched", "within_limit", 0, False, 2),
            ("insufficient-evidence", "decision_only", "unknown", 0, None, 1),
        ):
            with self.subTest(fixture=name):
                result = self.result(self.invoke(
                    FIXTURES / f"{name}.jsonl", "--attempt-ttft-limit-ms", "500",
                ))
                self.assertEqual(result["counts"]["attempts"], 1)
                self.assertEqual(result["counts"]["unique_requests"], 1)
                self.assertEqual(result["counts"]["records"], records)
                self.assertEqual(result["provenance"], {
                    "records": {"observed": 0, "synthetic": records},
                    "attempts": {"observed": 0, "synthetic": 1},
                })
                row = result["attempts"][0]
                self.assertEqual(row["join_status"], join)
                self.assertEqual(row["ttft_assessment"], assessment)
                self.assertIs(row["reuse_with_ttft_violation"], flag)
                self.assertEqual(result["attempt_ttft_limit"]["violations"], violations)
                if join == "decision_only":
                    self.assertIsNone(row["outcome"])
                    self.assertEqual(result["attempt_ttft_limit"]["assessment"], "unknown")


if __name__ == "__main__":
    unittest.main()
