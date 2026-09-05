#!/usr/bin/env python3
"""Join a custom normalized routing JSONL export into bounded offline evidence.

This is not a native vllm-router parser. Exporters assert source provenance and
measurement boundaries; the helper validates the supplied records, not serving
performance, cache residency, causality, or deployment readiness.
"""

import argparse
import json
import math
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NoReturn


IDENTITY_FIELDS = ("run_id", "request_id", "attempt_id")
CONTEXT_FIELDS = ("model_id", "pool_id", "worker_id", "provenance")
REQUIRED_FIELDS = (
    "schema_version", "event", *IDENTITY_FIELDS, *CONTEXT_FIELDS, "source",
)
DECISION_FIELDS = ("router_id", "policy", "predicted_overlap", "load")
MEASUREMENT_FIELDS = (
    "client_ttft_ms", "client_e2e_ms", "queue_ms", "input_tokens", "reused_tokens",
)
OUTCOME_FIELDS = ("status", *MEASUREMENT_FIELDS)
LIMIT_SCOPE = "per_attempt_client_ttft"
LIMITATIONS = [
    "Only a custom normalized routing export is supported; this is not a native vllm-router parser.",
    "Source, observed/synthetic provenance, and measurement boundaries are exporter assertions, not independently verified.",
    "Prediction units and target workers remain distinct from selected workers and actually reused tokens; cache residency is not inferred.",
    "Additional attempts do not establish retries; attempt timings are not request-wide client latency.",
    "Terminal success means the intended response completed, including stream completion; HTTP headers alone do not establish success.",
    "Only supplied per-attempt evidence is assessed; there is no percentile, capacity, SLO, causal, policy-switch, or deployment-approval verdict.",
]


class EvidenceError(ValueError):
    """A concise input error that never includes a raw record or field value."""

    def __init__(self, message: str, field: str = "record", line: int | None = None) -> None:
        super().__init__(message)
        self.field = field
        self.line = line


def require_string(value: Any, field: str) -> None:
    """Reject absent, nonstring, empty, and whitespace-only identifiers."""
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError("must be a nonempty string", field)


def require_choice(value: Any, choices: tuple[str, ...], field: str) -> None:
    """Check a declared enum without echoing untrusted input."""
    if not isinstance(value, str) or value not in choices:
        raise EvidenceError("unsupported value", field)


def require_number(value: Any, field: str, *, integer: bool = False) -> None:
    """Require a finite nonnegative JSON number; booleans are never numbers."""
    if type(value) is not int and (integer or type(value) is not float):
        expected = "integer" if integer else "number"
        raise EvidenceError(f"must be a nonnegative {expected}", field)
    # Integers are finite; converting a large integer to float could overflow.
    if value < 0 or (type(value) is float and not math.isfinite(value)):
        raise EvidenceError("must be finite and nonnegative", field)


def require_fields(
    value: Any,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
    prefix: str = "",
) -> None:
    """Check object keys, reporting only field names defined in this schema."""
    if not isinstance(value, dict):
        raise EvidenceError("must be a JSON object", prefix or "record")
    for name in required:
        if name not in value:
            raise EvidenceError("required field is missing", f"{prefix}.{name}" if prefix else name)
    if value.keys() - set(required + optional):
        raise EvidenceError("unrecognized field", prefix or "record")


def validate_record(record: Any) -> dict[str, Any]:
    """Validate one v1 event without inventing omitted observations."""
    # First check common keys; event-specific allowed fields are checked below.
    require_fields(record, REQUIRED_FIELDS, DECISION_FIELDS + OUTCOME_FIELDS)
    if type(record["schema_version"]) is not int or record["schema_version"] != 1:
        raise EvidenceError("must be the integer 1", "schema_version")
    require_choice(record["event"], ("decision", "outcome"), "event")
    fields = DECISION_FIELDS if record["event"] == "decision" else OUTCOME_FIELDS
    require_fields(record, REQUIRED_FIELDS, fields)
    for name in (*IDENTITY_FIELDS, "model_id", "pool_id", "worker_id", "source"):
        require_string(record[name], name)
    require_choice(record["provenance"], ("synthetic", "observed"), "provenance")

    if record["event"] == "decision":
        for name in ("router_id", "policy"):
            if record.get(name) is not None:
                require_string(record[name], name)
        overlap = record.get("predicted_overlap")
        if overlap is not None:
            require_fields(overlap, ("matched", "total", "unit", "kind", "worker_id"), prefix="predicted_overlap")
            for name in ("matched", "total"):
                require_number(overlap[name], f"predicted_overlap.{name}", integer=True)
            if overlap["matched"] > overlap["total"]:
                raise EvidenceError("must not exceed total", "predicted_overlap.matched")
            require_choice(overlap["unit"], ("characters", "tokens", "blocks"), "predicted_overlap.unit")
            require_choice(overlap["kind"], ("request_history", "kv_events"), "predicted_overlap.kind")
            if overlap["worker_id"] is not None:
                require_string(overlap["worker_id"], "predicted_overlap.worker_id")
        load = record.get("load")
        if load is not None:
            require_fields(load, ("value", "kind", "scope"), prefix="load")
            require_number(load["value"], "load.value")
            require_choice(load["kind"], ("active_requests", "active_tokens"), "load.kind")
            require_choice(load["scope"], ("router_local", "pool", "unknown"), "load.scope")
    else:
        if record.get("status") is not None:
            require_choice(record["status"], ("success", "error", "cancelled"), "status")
        for name in MEASUREMENT_FIELDS:
            if record.get(name) is not None:
                require_number(record[name], name, integer=name in ("input_tokens", "reused_tokens"))
        ttft, e2e = record.get("client_ttft_ms"), record.get("client_e2e_ms")
        if ttft is not None and e2e is not None and ttft > e2e:
            raise EvidenceError("must not exceed client_e2e_ms for the same attempt", "client_ttft_ms")
        reused, total = record.get("reused_tokens"), record.get("input_tokens")
        if reused is not None and total is not None and reused > total:
            raise EvidenceError("must not exceed input_tokens", "reused_tokens")
    return record


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate JSON keys, including keys in nested objects."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(value: str) -> NoReturn:
    """JSON's nonstandard NaN and Infinity extensions are not observations."""
    raise EvidenceError("nonfinite JSON number is not allowed")


def read_events(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Read only the supplied UTF-8 file and retain physical source lines."""
    try:
        with path.open("r", encoding="utf-8") as stream:
            for number, text in enumerate(stream, 1):
                if not text.strip():
                    continue
                try:
                    record = json.loads(text, object_pairs_hook=unique_object, parse_constant=reject_constant)
                    record = validate_record(record)
                except EvidenceError as exc:
                    exc.line = number
                    raise
                except (ValueError, RecursionError):
                    raise EvidenceError("invalid JSON or unsupported JSON depth/number size", line=number) from None
                yield number, record
    except EvidenceError:
        raise
    except UnicodeError:
        raise EvidenceError("input must be UTF-8", "input") from None
    except (OSError, ValueError):
        raise EvidenceError("cannot read the supplied file", "input") from None


def summarize(
    rows: list[dict[str, Any]],
    records: int,
    record_provenance: dict[str, int],
    limit_ms: float | None,
) -> dict[str, Any]:
    """Count evidence coverage and assess only declared per-attempt TTFT."""
    terminal = {"known": 0, "unknown": 0, "success": 0, "error": 0, "cancelled": 0}
    coverage = {name: {"known": 0, "unknown": 0} for name in MEASUREMENT_FIELDS}
    joins = {"matched": 0, "decision_only": 0, "outcome_only": 0}
    provenance = {"observed": 0, "synthetic": 0}
    assessed = violations = 0

    for row in rows:
        provenance[row["provenance"]] += 1
        if row["decision"] is not None and row["outcome"] is not None:
            join_status = "matched"
        else:
            join_status = "decision_only" if row["decision"] is not None else "outcome_only"
        row["join_status"] = join_status
        joins[join_status] += 1
        outcome = row["outcome"] or {}
        status = outcome.get("status")
        terminal["unknown" if status is None else "known"] += 1
        if status is not None:
            terminal[status] += 1
        for name in MEASUREMENT_FIELDS:
            coverage[name]["unknown" if outcome.get(name) is None else "known"] += 1

        ttft, reused = outcome.get("client_ttft_ms"), outcome.get("reused_tokens")
        row["ttft_assessment"] = "unknown"
        row["reuse_with_ttft_violation"] = None
        if limit_ms is not None and ttft is not None:
            violation = ttft > limit_ms
            assessed += 1
            violations += int(violation)
            row["ttft_assessment"] = "violation" if violation else "within_limit"
            if reused is not None:
                row["reuse_with_ttft_violation"] = reused > 0 and violation

    requests = len({(row["run_id"], row["request_id"]) for row in rows})
    return {
        "schema_version": 1,
        "status": "ok",
        "counts": {
            "records": records,
            "unique_requests": requests,
            "attempts": len(rows),
            "additional_attempts": len(rows) - requests,
            **joins,
            "terminal_status": terminal,
            "measurement_coverage": coverage,
        },
        "provenance": {"records": record_provenance, "attempts": provenance},
        "attempt_ttft_limit": {
            "limit_ms": limit_ms,
            "scope": LIMIT_SCOPE,
            "assessment": "evaluated" if assessed else "unknown",
            "known": assessed,
            "unknown": len(rows) - assessed,
            "violations": violations if limit_ms is not None else None,
        },
        "attempts": rows,
        "limitations": LIMITATIONS,
    }


def analyze(path: Path, limit_ms: float | None = None) -> dict[str, Any]:
    """Join one export by run/request/attempt, rejecting all ambiguous input.

    Raises EvidenceError before returning any report if any record is invalid.
    Runtime and memory scale with the supplied records and attempt state.
    """
    if limit_ms is not None:
        require_number(limit_ms, "attempt_ttft_limit_ms")
    attempts: dict[tuple[str, str, str], dict[str, Any]] = {}
    record_provenance = {"observed": 0, "synthetic": 0}
    records = 0
    for number, record in read_events(path):
        key = (record["run_id"], record["request_id"], record["attempt_id"])
        kind = record["event"]
        if key not in attempts:
            attempts[key] = {
                **{name: record[name] for name in (*IDENTITY_FIELDS, *CONTEXT_FIELDS)},
                "decision": None,
                "outcome": None,
            }
        row = attempts[key]
        if row[kind] is not None:
            raise EvidenceError("duplicate event for this attempt", "event", number)
        for name in CONTEXT_FIELDS:
            if row[name] != record[name]:
                raise EvidenceError("conflicts with the joined event", name, number)
        fields = DECISION_FIELDS if kind == "decision" else OUTCOME_FIELDS
        row[kind] = {
            "line": number,
            "source": record["source"],
            **{name: record.get(name) for name in fields},
        }
        records += 1
        record_provenance[record["provenance"]] += 1
    if not records:
        raise EvidenceError("input contains no events")
    rows = [attempts[key] for key in sorted(attempts)]
    return summarize(rows, records, record_provenance, limit_ms)


class JsonArgumentParser(argparse.ArgumentParser):
    """Keep invalid options on the same JSON/exit-2 path as invalid exports."""

    def error(self, message: str) -> NoReturn:
        # argparse's message can contain arbitrary supplied options or values.
        raise EvidenceError("invalid arguments; use --help for usage", "arguments")


def parse_limit(text: str) -> float:
    """Parse the explicit CLI limit, without quoting invalid supplied text."""
    try:
        value = float(text)
    except ValueError:
        raise EvidenceError("must be a finite nonnegative number", "attempt_ttft_limit_ms") from None
    require_number(value, "attempt_ttft_limit_ms")
    return value


def main(argv: list[str] | None = None) -> int:
    """Print deterministic JSON; a measured limit violation still exits 0."""
    parser = JsonArgumentParser(
        description="Analyze one custom normalized routing JSONL export offline (not native vllm-router logs).",
        allow_abbrev=False,
    )
    parser.add_argument("input", type=Path, help="supplied UTF-8 JSONL export file")
    parser.add_argument("--attempt-ttft-limit-ms", metavar="MS", help="finite nonnegative per-attempt client TTFT limit")
    try:
        args = parser.parse_args(argv)
        limit_ms = parse_limit(args.attempt_ttft_limit_ms) if args.attempt_ttft_limit_ms is not None else None
        result = analyze(args.input, limit_ms)
    except EvidenceError as exc:
        result = {
            "schema_version": 1,
            "status": "error",
            "error": {"line": exc.line, "field": exc.field, "message": str(exc)},
        }
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
