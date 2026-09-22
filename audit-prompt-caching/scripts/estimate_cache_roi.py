#!/usr/bin/env python3
"""Estimate prompt-cache cost impact from token and pricing assumptions."""

import argparse
import json
import math
import sys


def money(value):
    return round(value, 6)


def pct(value):
    return round(value * 100, 2)


def require_nonnegative(name, value):
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def validate(args):
    for name in (
        "static_tokens",
        "dynamic_tokens",
        "output_tokens",
        "input_price_per_mtok",
        "cached_input_price_per_mtok",
        "output_price_per_mtok",
    ):
        require_nonnegative(name.replace("_", "-"), getattr(args, name))
    if args.cache_write_input_price_per_mtok is not None:
        require_nonnegative(
            "cache-write-input-price-per-mtok",
            args.cache_write_input_price_per_mtok,
        )
    if args.requests <= 0:
        raise ValueError("requests must be positive")
    for name in ("hit_rate", "cache_write_rate"):
        value = getattr(args, name)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name.replace('_', '-')} must be between 0 and 1")
    if args.hit_rate + args.cache_write_rate > 1:
        raise ValueError("hit-rate and cache-write-rate sum must not exceed 1")
    if (
        args.cache_write_rate > 0
        and args.cache_write_input_price_per_mtok is None
    ):
        raise ValueError("nonzero cache-write-rate requires an explicit write price")


def estimate(args):
    validate(args)
    requests = args.requests
    static_tokens = args.static_tokens * requests
    dynamic_tokens = args.dynamic_tokens * requests
    output_tokens = args.output_tokens * requests
    cache_read_input_tokens = static_tokens * args.hit_rate
    cache_write_input_tokens = static_tokens * args.cache_write_rate
    ordinary_static_tokens = max(
        0.0,
        static_tokens - cache_read_input_tokens - cache_write_input_tokens,
    )
    ordinary_input_tokens = ordinary_static_tokens + dynamic_tokens

    input_baseline_cost = (
        (static_tokens + dynamic_tokens) * args.input_price_per_mtok / 1_000_000
    )
    ordinary_input_cost = (
        ordinary_input_tokens * args.input_price_per_mtok / 1_000_000
    )
    cache_read_input_cost = (
        cache_read_input_tokens * args.cached_input_price_per_mtok / 1_000_000
    )
    write_price = args.cache_write_input_price_per_mtok or 0.0
    cache_write_input_cost = cache_write_input_tokens * write_price / 1_000_000
    input_with_cache_cost = (
        ordinary_input_cost + cache_read_input_cost + cache_write_input_cost
    )
    output_cost = output_tokens * args.output_price_per_mtok / 1_000_000
    total_baseline_cost = input_baseline_cost + output_cost
    total_with_cache_cost = input_with_cache_cost + output_cost
    input_savings = input_baseline_cost - input_with_cache_cost
    total_savings = total_baseline_cost - total_with_cache_cost

    return {
        "schema_version": 1,
        "producer": "estimate_cache_roi.py",
        "requests": requests,
        "static_tokens": args.static_tokens,
        "dynamic_tokens": args.dynamic_tokens,
        "output_tokens": args.output_tokens,
        "hit_rate": args.hit_rate,
        "cache_write_rate": args.cache_write_rate,
        "ordinary_input_tokens": ordinary_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "cache_write_input_tokens": cache_write_input_tokens,
        "ordinary_input_cost": money(ordinary_input_cost),
        "cache_read_input_cost": money(cache_read_input_cost),
        "cache_write_input_cost": money(cache_write_input_cost),
        "input_baseline_cost": money(input_baseline_cost),
        "input_with_cache_cost": money(input_with_cache_cost),
        "output_cost": money(output_cost),
        "total_baseline_cost": money(total_baseline_cost),
        "total_with_cache_cost": money(total_with_cache_cost),
        "input_savings": money(input_savings),
        "total_savings": money(total_savings),
        "input_savings_pct": (
            pct(input_savings / input_baseline_cost) if input_baseline_cost else 0
        ),
        "total_savings_pct": (
            pct(total_savings / total_baseline_cost) if total_baseline_cost else 0
        ),
        "output_share_of_baseline_cost": (
            pct(output_cost / total_baseline_cost) if total_baseline_cost else 0
        ),
        "pricing": {
            "input_price_per_mtok": args.input_price_per_mtok,
            "cached_input_price_per_mtok": args.cached_input_price_per_mtok,
            "cache_write_input_price_per_mtok": (
                args.cache_write_input_price_per_mtok
            ),
            "output_price_per_mtok": args.output_price_per_mtok,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Estimate cost impact from prompt-cache hit and write rates."
    )
    parser.add_argument("--static-tokens", type=float, required=True)
    parser.add_argument("--dynamic-tokens", type=float, required=True)
    parser.add_argument("--output-tokens", type=float, required=True)
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--hit-rate", type=float, required=True)
    parser.add_argument("--cache-write-rate", type=float, default=0.0)
    parser.add_argument("--input-price-per-mtok", type=float, required=True)
    parser.add_argument("--cached-input-price-per-mtok", type=float, required=True)
    parser.add_argument("--cache-write-input-price-per-mtok", type=float)
    parser.add_argument("--output-price-per-mtok", type=float, required=True)
    args = parser.parse_args(argv)

    try:
        result = estimate(args)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
