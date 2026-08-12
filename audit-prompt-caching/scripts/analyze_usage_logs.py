#!/usr/bin/env python3
"""Summarize prompt-cache usage fields from JSONL, JSON, or CSV logs."""

import argparse
import csv
import json
import math
import sys
from pathlib import Path


FIELD_ALIASES = {
    "input_tokens": (
        "input_tokens",
        "prompt_tokens",
        "InputTokens",
        "inputTokens",
        "inputTokenCount",
        "prompt_token_count",
    ),
    "cached_tokens": (
        "cached_tokens",
        "prompt_cache_hit_tokens",
        "total_cached_tokens",
    ),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cache_read_tokens",
        "CacheReadInputTokens",
        "cacheReadInputTokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
        "cache_write_input_tokens",
        "CacheWriteInputTokens",
        "cacheWriteInputTokens",
    ),
    "cache_write_tokens": ("cache_write_tokens",),
    "output_tokens": (
        "output_tokens",
        "completion_tokens",
        "OutputTokens",
        "outputTokens",
        "outputTokenCount",
        "candidates_token_count",
    ),
}

CANONICAL_USAGE_FIELDS = tuple(FIELD_ALIASES)

SCHEMA_VERSION = 1

INCLUSIVE_CACHE_COMPONENTS = (
    "cached_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cache_write_tokens",
)

DENOMINATOR_PRECEDENCE = ("invalid", "ambiguous", "valid")

BEDROCK_USAGE_FIELDS = (
    "InputTokens",
    "CacheReadInputTokens",
    "CacheWriteInputTokens",
    "inputTokens",
    "cacheReadInputTokens",
    "cacheWriteInputTokens",
)


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


def walk(value, prefix=()):
    """Yield every nested mapping together with its dot-path segments."""
    if isinstance(value, dict):
        yield value, prefix
        for key, child in value.items():
            yield from walk(child, (*prefix, str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, (*prefix, str(index)))


def dot_path(prefix, name):
    return ".".join((*prefix, name))


def extracted_value(value, names, prefix):
    """Return the first present canonical value and its exact raw dot path."""
    if isinstance(value, dict):
        for name in names:
            if name in value:
                return number(value[name]), dot_path(prefix, name)
    return 0, None


def first_number(record, names):
    """Return the first nonzero alias, keeping the first present alias as evidence."""
    present_path = None
    for obj, prefix in walk(record):
        for name in names:
            if name in obj:
                found = number(obj[name])
                if found:
                    return found, dot_path(prefix, name)
                if present_path is None:
                    present_path = dot_path(prefix, name)
    return 0, present_path


def blank_source_fields():
    return {field: None for field in CANONICAL_USAGE_FIELDS}


def extraction(**extracted):
    """Split per-field (value, path) pairs into canonical values and provenance."""
    unknown = [field for field in extracted if field not in FIELD_ALIASES]
    if unknown:
        raise ValueError(f"non-canonical usage fields: {', '.join(sorted(unknown))}")
    row = {field: 0 for field in CANONICAL_USAGE_FIELDS}
    source_fields = blank_source_fields()
    for field, (value, path) in extracted.items():
        row[field] = value
        source_fields[field] = path
    return row, source_fields


def usage_envelope(record):
    if not isinstance(record, dict):
        return {}, ()
    usage = record.get("usage")
    return (usage, ("usage",)) if isinstance(usage, dict) else (record, ())


def usage_object(record):
    return usage_envelope(record)[0]


GEMINI_INTERACTIONS_REQUEST_TOTAL_FIELDS = (
    "total_input_tokens",
    "totalInputTokens",
    "total_output_tokens",
    "totalOutputTokens",
)

GEMINI_INTERACTIONS_USAGE_FIELDS = (
    "total_cached_tokens",
    "totalCachedTokens",
    *GEMINI_INTERACTIONS_REQUEST_TOTAL_FIELDS,
)

GEMINI_GENERATE_CONTENT_USAGE_FIELDS = (
    "prompt_token_count",
    "promptTokenCount",
    "cached_content_token_count",
    "cachedContentTokenCount",
    "candidates_token_count",
    "candidatesTokenCount",
)


def provider_name(record):
    provider = record.get("provider") if isinstance(record, dict) else None
    return provider.lower() if isinstance(provider, str) else ""


def has_any_field(value, names):
    return isinstance(value, dict) and any(name in value for name in names)


def mapping_at(record, path):
    value = record
    for key in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(key)
    return value if isinstance(value, dict) else {}


def first_usage_envelope(record, paths, fields):
    """Return the first envelope carrying any of ``fields`` and its raw path."""
    for path in paths:
        value = mapping_at(record, path)
        if has_any_field(value, fields):
            return value, path
    return {}, ()


def has_bedrock_usage_fields(value):
    return has_any_field(value, BEDROCK_USAGE_FIELDS)


def bedrock_usage_envelope(record):
    metrics = mapping_at(record, ("metrics",))
    if has_bedrock_usage_fields(metrics):
        return metrics, ("metrics",)
    return usage_envelope(record)


def gemini_interactions_usage_envelope(record):
    return first_usage_envelope(
        record,
        (
            ("usage",),
            ("metadata", "total_usage"),
            ("metadata", "totalUsage"),
            (),
        ),
        GEMINI_INTERACTIONS_USAGE_FIELDS,
    )


def gemini_generate_content_usage_envelope(record):
    return first_usage_envelope(
        record,
        (("usage_metadata",), ("usageMetadata",), ("usage",), ()),
        GEMINI_GENERATE_CONTENT_USAGE_FIELDS,
    )


def openai_breakdown_value(usage, usage_prefix, details, details_prefix, names):
    value, path = extracted_value(details, names, details_prefix)
    if path:
        return value, path
    return extracted_value(usage, names, usage_prefix)


def extract_openai(record):
    usage, prefix = usage_envelope(record)
    if "prompt_tokens" in usage or "prompt_tokens_details" in usage:
        input_names, output_names = ("prompt_tokens",), ("completion_tokens",)
        details_key = "prompt_tokens_details"
    else:
        input_names, output_names = ("input_tokens",), ("output_tokens",)
        details_key = "input_tokens_details"
    details = usage.get(details_key)
    details = details if isinstance(details, dict) else {}
    details_prefix = (*prefix, details_key)
    return extraction(
        input_tokens=extracted_value(usage, input_names, prefix),
        cached_tokens=openai_breakdown_value(
            usage, prefix, details, details_prefix, ("cached_tokens",)
        ),
        cache_write_tokens=openai_breakdown_value(
            usage, prefix, details, details_prefix, ("cache_write_tokens",)
        ),
        output_tokens=extracted_value(usage, output_names, prefix),
    )


def extract_anthropic(record):
    usage, prefix = usage_envelope(record)
    return extraction(
        input_tokens=extracted_value(usage, ("input_tokens",), prefix),
        cache_read_input_tokens=extracted_value(
            usage, ("cache_read_input_tokens",), prefix
        ),
        cache_creation_input_tokens=extracted_value(
            usage, ("cache_creation_input_tokens",), prefix
        ),
        output_tokens=extracted_value(usage, ("output_tokens",), prefix),
    )


def extract_bedrock(record):
    metrics, prefix = bedrock_usage_envelope(record)
    return extraction(
        input_tokens=extracted_value(
            metrics, ("InputTokens", "inputTokens"), prefix
        ),
        cache_read_input_tokens=extracted_value(
            metrics, ("CacheReadInputTokens", "cacheReadInputTokens"), prefix
        ),
        cache_creation_input_tokens=extracted_value(
            metrics, ("CacheWriteInputTokens", "cacheWriteInputTokens"), prefix
        ),
        output_tokens=extracted_value(
            metrics, ("OutputTokens", "outputTokens"), prefix
        ),
    )


def extract_gemini_interactions(record):
    usage, prefix = gemini_interactions_usage_envelope(record)
    return extraction(
        input_tokens=extracted_value(
            usage, ("total_input_tokens", "totalInputTokens"), prefix
        ),
        cached_tokens=extracted_value(
            usage, ("total_cached_tokens", "totalCachedTokens"), prefix
        ),
        output_tokens=extracted_value(
            usage, ("total_output_tokens", "totalOutputTokens"), prefix
        ),
    )


def extract_gemini_generate_content(record):
    usage, prefix = gemini_generate_content_usage_envelope(record)
    return extraction(
        input_tokens=extracted_value(
            usage, ("prompt_token_count", "promptTokenCount"), prefix
        ),
        cached_tokens=extracted_value(
            usage, ("cached_content_token_count", "cachedContentTokenCount"), prefix
        ),
        output_tokens=extracted_value(
            usage, ("candidates_token_count", "candidatesTokenCount"), prefix
        ),
    )


def extract_unknown(record):
    return extraction(
        **{
            metric: first_number(record, aliases)
            for metric, aliases in FIELD_ALIASES.items()
        }
    )


class UsageSurfaceAdapter:
    shape = "unknown"
    provider = "unknown"
    semantics = "ambiguous"

    def matches(self, record):
        return False

    def extract(self, record):
        return extract_unknown(record)


class OpenAIUsageAdapter(UsageSurfaceAdapter):
    shape = "openai"
    provider = "openai"
    semantics = "inclusive"

    def matches(self, record):
        provider = provider_name(record)
        if provider:
            return provider == self.provider
        usage = usage_object(record)
        return "input_tokens_details" in usage or "prompt_tokens_details" in usage

    def extract(self, record):
        return extract_openai(record)


class AnthropicUsageAdapter(UsageSurfaceAdapter):
    shape = "anthropic"
    provider = "anthropic-compatible"
    semantics = "additive"

    def matches(self, record):
        provider = provider_name(record)
        if provider:
            return provider == "anthropic"
        usage = usage_object(record)
        return (
            "cache_read_input_tokens" in usage
            or "cache_creation_input_tokens" in usage
        )

    def extract(self, record):
        return extract_anthropic(record)


class BedrockUsageAdapter(UsageSurfaceAdapter):
    shape = "bedrock"
    provider = "bedrock"
    semantics = "additive"

    def matches(self, record):
        provider = provider_name(record)
        if provider:
            return provider == self.provider
        return has_bedrock_usage_fields(mapping_at(record, ("metrics",))) or (
            has_bedrock_usage_fields(usage_object(record))
        )

    def extract(self, record):
        return extract_bedrock(record)


class GeminiInteractionsUsageAdapter(UsageSurfaceAdapter):
    shape = "gemini-interactions"
    provider = "gemini"
    semantics = "inclusive"

    def matches(self, record):
        usage, _ = gemini_interactions_usage_envelope(record)
        if not usage:
            return False
        provider = provider_name(record)
        if provider:
            return provider == self.provider
        if mapping_at(record, ("metadata", "total_usage")) or mapping_at(
            record, ("metadata", "totalUsage")
        ):
            return True
        if has_any_field(usage, GEMINI_INTERACTIONS_REQUEST_TOTAL_FIELDS):
            return True
        return (
            record.get("object") == "interaction"
            if isinstance(record, dict)
            else False
        )

    def extract(self, record):
        return extract_gemini_interactions(record)


class GeminiGenerateContentUsageAdapter(UsageSurfaceAdapter):
    shape = "gemini-generate-content"
    provider = "gemini"
    semantics = "inclusive"

    def matches(self, record):
        provider = provider_name(record)
        if provider and provider != self.provider:
            return False
        return bool(gemini_generate_content_usage_envelope(record)[0])

    def extract(self, record):
        return extract_gemini_generate_content(record)


class UnknownUsageAdapter(UsageSurfaceAdapter):
    def matches(self, record):
        return True


USAGE_SURFACE_ADAPTERS = (
    OpenAIUsageAdapter(),
    AnthropicUsageAdapter(),
    BedrockUsageAdapter(),
    GeminiInteractionsUsageAdapter(),
    GeminiGenerateContentUsageAdapter(),
    UnknownUsageAdapter(),
)


def usage_adapter_for(record):
    return next(adapter for adapter in USAGE_SURFACE_ADAPTERS if adapter.matches(record))


def infer_shape(record):
    return usage_adapter_for(record).shape


def infer_provider(record):
    provider = record.get("provider") if isinstance(record, dict) else None
    if isinstance(provider, str) and provider:
        return provider
    return usage_adapter_for(record).provider


def inclusive_violations(row):
    """Return inclusive cache components that cannot fit inside the input total."""
    return [
        field
        for field in INCLUSIVE_CACHE_COMPONENTS
        if row[field] > row["input_tokens"]
    ]


def denominator_status(row, semantics, total_input_tokens):
    if semantics == "inclusive" and inclusive_violations(row):
        return "invalid"
    if semantics == "ambiguous":
        return "ambiguous"
    if total_input_tokens <= 0:
        return "ambiguous"
    return "valid"


def aggregate_denominator_status(statuses):
    for status in DENOMINATOR_PRECEDENCE:
        if status in statuses:
            return status
    return "ambiguous"


def normalization_warnings(adapter, row, semantics, index):
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
    if adapter.shape == "openai":
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
    elif semantics == "inclusive":
        for field in inclusive_violations(row):
            warnings.append(
                {
                    "code": "INCLUSIVE_CACHE_BREAKDOWN_EXCEEDS_INPUT",
                    "index": index,
                    "field": field,
                    "message": (
                        f"{field} exceeds the inclusive input token total"
                    ),
                }
            )
    return warnings


def normalize_record(record, accounting_mode=None, index=None):
    adapter = usage_adapter_for(record)
    row, source_fields = adapter.extract(record)
    semantics = (
        accounting_mode
        if adapter.semantics == "ambiguous" and accounting_mode
        else adapter.semantics
    )

    cache_benefit_tokens = row["cached_tokens"] + row["cache_read_input_tokens"]
    cache_write_total_tokens = (
        row["cache_write_tokens"] + row["cache_creation_input_tokens"]
    )
    total_input_tokens = row["input_tokens"]
    if semantics == "additive":
        total_input_tokens += cache_benefit_tokens + cache_write_total_tokens

    row.update(
        {
            "cache_benefit_tokens": cache_benefit_tokens,
            "cache_write_total_tokens": cache_write_total_tokens,
            "total_input_tokens": total_input_tokens,
            "accounting_semantics": semantics,
            "source_fields": source_fields,
            "denominator_status": denominator_status(
                row, semantics, total_input_tokens
            ),
            "warnings": normalization_warnings(adapter, row, semantics, index),
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
        "schema_version": SCHEMA_VERSION,
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
    totals["denominator_status"] = aggregate_denominator_status(
        {row["denominator_status"] for row in normalized}
    )
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
