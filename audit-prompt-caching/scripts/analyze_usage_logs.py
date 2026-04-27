#!/usr/bin/env python3
"""Summarize prompt-cache usage fields from JSONL, JSON, or CSV logs."""

import argparse
import csv
import json
import sys
from pathlib import Path


FIELD_ALIASES = {
    "input_tokens": (
        "input_tokens",
        "prompt_tokens",
        "InputTokens",
        "inputTokenCount",
    ),
    "cached_tokens": (
        "cached_tokens",
        "prompt_cache_hit_tokens",
    ),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cache_read_tokens",
        "CacheReadInputTokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
        "cache_write_input_tokens",
        "cache_write_tokens",
        "CacheWriteInputTokens",
    ),
    "output_tokens": (
        "output_tokens",
        "completion_tokens",
        "OutputTokens",
        "outputTokenCount",
    ),
}


def number(value):
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


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


def normalize_record(record):
    row = {
        metric: first_number(record, aliases)
        for metric, aliases in FIELD_ALIASES.items()
    }
    has_explicit_read_write = (
        row["cache_read_input_tokens"] or row["cache_creation_input_tokens"]
    )
    if has_explicit_read_write and not row["cached_tokens"]:
        row["total_input_tokens"] = (
            row["input_tokens"]
            + row["cache_read_input_tokens"]
            + row["cache_creation_input_tokens"]
        )
    else:
        row["total_input_tokens"] = row["input_tokens"]
    return row


def infer_provider(record):
    provider = record.get("provider") if isinstance(record, dict) else None
    if isinstance(provider, str) and provider:
        return provider
    text = json.dumps(record, ensure_ascii=False)
    if "CacheReadInputTokens" in text or "CacheWriteInputTokens" in text:
        return "bedrock"
    if "cache_read_input_tokens" in text or "cache_creation_input_tokens" in text:
        return "anthropic-compatible"
    if "prompt_cache_hit_tokens" in text:
        return "deepseek-compatible"
    if "cached_tokens" in text:
        return "openai-compatible"
    return "unknown"


def metadata_value(record, name):
    if not isinstance(record, dict):
        return None
    value = record.get(name)
    if isinstance(value, (str, int, float)):
        return value
    return None


def normalize_event(record, index):
    row = normalize_record(record)
    event = {
        "index": index,
        "provider": infer_provider(record),
        "model": metadata_value(record, "model"),
        "route": metadata_value(record, "route"),
        "request_id": metadata_value(record, "request_id"),
        "prefix_hash": metadata_value(record, "prefix_hash"),
        "input_tokens": row["input_tokens"],
        "cached_tokens": row["cached_tokens"],
        "cache_read_input_tokens": row["cache_read_input_tokens"],
        "cache_creation_input_tokens": row["cache_creation_input_tokens"],
        "cache_benefit_tokens": (
            row["cached_tokens"] + row["cache_read_input_tokens"]
        ),
        "total_input_tokens": row["total_input_tokens"],
        "output_tokens": row["output_tokens"],
    }
    return event


def normalized_events(records):
    return [normalize_event(record, index) for index, record in enumerate(records)]


def read_json_records(path):
    text = Path(path).read_text().strip()
    if not text:
        return []
    if path.suffix == ".jsonl":
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


def summarize(records):
    normalized = [normalize_record(record) for record in records]
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
        "total_input_tokens": sum(row["total_input_tokens"] for row in normalized),
        "output_tokens": sum(row["output_tokens"] for row in normalized),
    }
    cache_benefit_tokens = (
        totals["cached_tokens"] + totals["cache_read_input_tokens"]
    )
    totals["cache_hit_ratio"] = (
        round(cache_benefit_tokens / totals["total_input_tokens"], 4)
        if totals["total_input_tokens"]
        else 0
    )
    totals["cache_write_read_ratio"] = (
        round(
            totals["cache_creation_input_tokens"] / totals["cache_read_input_tokens"],
            4,
        )
        if totals["cache_read_input_tokens"]
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
    parser = argparse.ArgumentParser(
        description="Analyze LLM prompt-cache usage logs."
    )
    parser.add_argument(
        "--jsonl-normalized",
        action="store_true",
        help="Emit one canonical usage event per input record as JSONL.",
    )
    parser.add_argument("path", help="JSON, JSONL, or CSV usage log")
    args = parser.parse_args(argv)
    records = read_records(Path(args.path))
    if args.jsonl_normalized:
        for event in normalized_events(records):
            print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        return 0
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
