#!/usr/bin/env python3
"""Summarize prompt-cache usage fields from JSONL, JSON, or CSV logs."""

import argparse
import csv
import json
import math
import sys
from pathlib import Path


FIELD_ALIASES = {
    "input_tokens": ("input_tokens", "prompt_tokens", "InputTokens", "inputTokenCount"),
    "cached_tokens": ("cached_tokens", "prompt_cache_hit_tokens"),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cache_read_tokens",
        "CacheReadInputTokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
        "cache_write_input_tokens",
        "CacheWriteInputTokens",
    ),
    "cache_write_tokens": ("cache_write_tokens",),
    "output_tokens": (
        "output_tokens",
        "completion_tokens",
        "OutputTokens",
        "outputTokenCount",
    ),
}


def number(value):
    if value in (None, "") or isinstance(value, bool):
        return 0
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if not math.isfinite(parsed):
        return 0
    return int(parsed)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def first_number(record, names):
    for obj in walk(record):
        for name in names:
            if name in obj:
                found = number(obj[name])
                if found:
                    return found
    return 0


def usage_object(record):
    if not isinstance(record, dict):
        return {}
    usage = record.get("usage")
    return usage if isinstance(usage, dict) else record


def infer_shape(record):
    provider = record.get("provider") if isinstance(record, dict) else None
    provider = provider.lower() if isinstance(provider, str) else ""
    if provider == "openai":
        return "openai"
    if provider == "anthropic":
        return "anthropic"
    if provider == "bedrock":
        return "bedrock"
    if provider:
        return "unknown"

    usage = usage_object(record)
    metrics = record.get("metrics") if isinstance(record, dict) else None
    if isinstance(metrics, dict) and any(
        name in metrics
        for name in ("InputTokens", "CacheReadInputTokens", "CacheWriteInputTokens")
    ):
        return "bedrock"
    if "input_tokens_details" in usage or "prompt_tokens_details" in usage:
        return "openai"
    if "cache_read_input_tokens" in usage or "cache_creation_input_tokens" in usage:
        return "anthropic"
    return "unknown"


def infer_provider(record):
    provider = record.get("provider") if isinstance(record, dict) else None
    if isinstance(provider, str) and provider:
        return provider
    shape = infer_shape(record)
    if shape == "anthropic":
        return "anthropic-compatible"
    return shape


def extract_openai(record):
    usage = usage_object(record)
    if "prompt_tokens" in usage or "prompt_tokens_details" in usage:
        input_tokens = number(usage.get("prompt_tokens"))
        output_tokens = number(usage.get("completion_tokens"))
        details = usage.get("prompt_tokens_details")
    else:
        input_tokens = number(usage.get("input_tokens"))
        output_tokens = number(usage.get("output_tokens"))
        details = usage.get("input_tokens_details")
    details = details if isinstance(details, dict) else {}
    cached_tokens = details.get("cached_tokens", usage.get("cached_tokens"))
    cache_write_tokens = details.get(
        "cache_write_tokens", usage.get("cache_write_tokens")
    )
    return {
        "input_tokens": input_tokens,
        "cached_tokens": number(cached_tokens),
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_write_tokens": number(cache_write_tokens),
        "output_tokens": output_tokens,
    }


def extract_anthropic(record):
    usage = usage_object(record)
    return {
        "input_tokens": number(usage.get("input_tokens")),
        "cached_tokens": 0,
        "cache_read_input_tokens": number(usage.get("cache_read_input_tokens")),
        "cache_creation_input_tokens": number(
            usage.get("cache_creation_input_tokens")
        ),
        "cache_write_tokens": 0,
        "output_tokens": number(usage.get("output_tokens")),
    }


def extract_bedrock(record):
    metrics = record.get("metrics") if isinstance(record, dict) else None
    metrics = metrics if isinstance(metrics, dict) else record
    return {
        "input_tokens": number(metrics.get("InputTokens")),
        "cached_tokens": 0,
        "cache_read_input_tokens": number(metrics.get("CacheReadInputTokens")),
        "cache_creation_input_tokens": number(metrics.get("CacheWriteInputTokens")),
        "cache_write_tokens": 0,
        "output_tokens": number(metrics.get("OutputTokens")),
    }


def extract_unknown(record):
    return {
        metric: first_number(record, aliases)
        for metric, aliases in FIELD_ALIASES.items()
    }


def normalize_record(record, accounting_mode=None, index=None):
    shape = infer_shape(record)
    if shape == "openai":
        row = extract_openai(record)
        semantics = "inclusive"
    elif shape == "anthropic":
        row = extract_anthropic(record)
        semantics = "additive"
    elif shape == "bedrock":
        row = extract_bedrock(record)
        semantics = "additive"
    else:
        row = extract_unknown(record)
        semantics = accounting_mode or "ambiguous"

    cache_benefit_tokens = row["cached_tokens"] + row["cache_read_input_tokens"]
    cache_write_total_tokens = (
        row["cache_write_tokens"] + row["cache_creation_input_tokens"]
    )
    total_input_tokens = row["input_tokens"]
    if semantics == "additive":
        total_input_tokens += cache_benefit_tokens + cache_write_total_tokens

    warnings = []
    if semantics == "ambiguous":
        warnings.append(
            {
                "code": "AMBIGUOUS_ACCOUNTING_SEMANTICS",
                "index": index,
                "message": (
                    "wrapper usage fields do not prove whether cache tokens are "
                    "inclusive or additive; reported input total was preserved"
                ),
            }
        )
    if shape == "openai":
        for field in ("cached_tokens", "cache_write_tokens"):
            if row[field] > row["input_tokens"]:
                warnings.append(
                    {
                        "code": "OPENAI_CACHE_BREAKDOWN_EXCEEDS_INPUT",
                        "index": index,
                        "field": field,
                        "message": (
                            f"OpenAI {field} exceeds the endpoint input token total"
                        ),
                    }
                )

    row.update(
        {
            "cache_benefit_tokens": cache_benefit_tokens,
            "cache_write_total_tokens": cache_write_total_tokens,
            "total_input_tokens": total_input_tokens,
            "accounting_semantics": semantics,
            "warnings": warnings,
        }
    )
    return row


def metadata_value(record, name):
    if not isinstance(record, dict):
        return None
    value = record.get(name)
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return value
    return None


def normalize_event(record, index, accounting_mode=None):
    row = normalize_record(record, accounting_mode=accounting_mode, index=index)
    return {
        "index": index,
        "provider": infer_provider(record),
        "model": metadata_value(record, "model"),
        "route": metadata_value(record, "route"),
        "request_id": metadata_value(record, "request_id"),
        "prefix_hash": metadata_value(record, "prefix_hash"),
        **row,
    }


def normalized_events(records, accounting_mode=None):
    return [
        normalize_event(record, index, accounting_mode=accounting_mode)
        for index, record in enumerate(records)
    ]


def read_json_records(path):
    text = Path(path).read_text().strip()
    if not text:
        return []
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return data["data"]
    return [data]


def read_csv_records(path):
    with Path(path).open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_records(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return read_csv_records(Path(path))
    return read_json_records(Path(path))


def summarize(records, accounting_mode=None):
    normalized = [
        normalize_record(record, accounting_mode=accounting_mode, index=index)
        for index, record in enumerate(records)
    ]
    totals = {
        "records": len(normalized),
        "input_tokens": sum(row["input_tokens"] for row in normalized),
        "cached_tokens": sum(row["cached_tokens"] for row in normalized),
        "cache_read_input_tokens": sum(
            row["cache_read_input_tokens"] for row in normalized
        ),
        "cache_creation_input_tokens": sum(
            row["cache_creation_input_tokens"] for row in normalized
        ),
        "cache_write_tokens": sum(row["cache_write_tokens"] for row in normalized),
        "cache_write_total_tokens": sum(
            row["cache_write_total_tokens"] for row in normalized
        ),
        "cache_benefit_tokens": sum(
            row["cache_benefit_tokens"] for row in normalized
        ),
        "total_input_tokens": sum(row["total_input_tokens"] for row in normalized),
        "output_tokens": sum(row["output_tokens"] for row in normalized),
        "warnings": [warning for row in normalized for warning in row["warnings"]],
    }
    semantics = {row["accounting_semantics"] for row in normalized}
    totals["accounting_semantics"] = (
        next(iter(semantics)) if len(semantics) == 1 else "mixed" if semantics else "unknown"
    )
    totals["cache_hit_ratio"] = (
        round(totals["cache_benefit_tokens"] / totals["total_input_tokens"], 4)
        if totals["total_input_tokens"]
        else 0
    )
    totals["cache_write_read_ratio"] = (
        round(totals["cache_write_total_tokens"] / totals["cache_benefit_tokens"], 4)
        if totals["cache_benefit_tokens"]
        else None
    )
    totals["output_share"] = (
        round(
            totals["output_tokens"]
            / (totals["total_input_tokens"] + totals["output_tokens"]),
            4,
        )
        if totals["total_input_tokens"] or totals["output_tokens"]
        else 0
    )
    return totals


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze LLM prompt-cache usage logs.")
    parser.add_argument(
        "--jsonl-normalized",
        action="store_true",
        help="Emit one canonical usage event per input record as JSONL.",
    )
    parser.add_argument(
        "--accounting-mode",
        choices=("inclusive", "additive"),
        help="Resolve otherwise ambiguous wrapper cache-token accounting.",
    )
    parser.add_argument("path", help="JSON, JSONL, or CSV usage log")
    args = parser.parse_args(argv)
    try:
        records = read_records(Path(args.path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        print(f"could not read usage log: {exc}", file=sys.stderr)
        return 2
    if args.jsonl_normalized:
        for event in normalized_events(records, accounting_mode=args.accounting_mode):
            print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        return 0
    print(
        json.dumps(
            summarize(records, accounting_mode=args.accounting_mode),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
