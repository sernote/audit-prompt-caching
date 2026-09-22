#!/usr/bin/env python3
"""Estimate prompt-cache cost impact from token and pricing assumptions."""

import argparse
import json
import sys


def money(value):
    return round(value, 6)


def pct(value):
    return round(value * 100, 2)


def estimate(args):
    requests = args.requests
    hit_rate = max(0.0, min(1.0, args.hit_rate))

    static_tokens = args.static_tokens * requests
    dynamic_tokens = args.dynamic_tokens * requests
    output_tokens = args.output_tokens * requests
    cached_static_tokens = static_tokens * hit_rate
    uncached_static_tokens = static_tokens - cached_static_tokens
    uncached_input_tokens = uncached_static_tokens + dynamic_tokens
    cache_write_tokens = args.cache_write_tokens

    input_baseline_cost = (
        (static_tokens + dynamic_tokens) * args.input_price_per_mtok / 1_000_000
    )
    cache_write_price = (
        args.cache_write_price_per_mtok
        if args.cache_write_price_per_mtok is not None
        else args.input_price_per_mtok
    )
    input_with_cache_cost = (
        (uncached_input_tokens - cache_write_tokens) * args.input_price_per_mtok
        + cache_write_tokens * cache_write_price
        + cached_static_tokens * args.cached_input_price_per_mtok
    ) / 1_000_000
    output_cost = output_tokens * args.output_price_per_mtok / 1_000_000
    total_baseline_cost = input_baseline_cost + output_cost
    total_with_cache_cost = input_with_cache_cost + output_cost
    input_savings = input_baseline_cost - input_with_cache_cost
    total_savings = total_baseline_cost - total_with_cache_cost

    return {
        "requests": requests,
        "hit_rate": hit_rate,
        "cache_write_tokens": cache_write_tokens,
        "input_baseline_cost": money(input_baseline_cost),
        "input_with_cache_cost": money(input_with_cache_cost),
        "output_cost": money(output_cost),
        "total_baseline_cost": money(total_baseline_cost),
        "total_with_cache_cost": money(total_with_cache_cost),
        "input_savings": money(input_savings),
        "total_savings": money(total_savings),
        "input_savings_pct": pct(input_savings / input_baseline_cost)
        if input_baseline_cost
        else 0,
        "total_savings_pct": pct(total_savings / total_baseline_cost)
        if total_baseline_cost
        else 0,
        "output_share_of_baseline_cost": pct(output_cost / total_baseline_cost)
        if total_baseline_cost
        else 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Estimate cost impact from prompt-cache hit rate."
    )
    parser.add_argument("--static-tokens", type=float, required=True)
    parser.add_argument("--dynamic-tokens", type=float, required=True)
    parser.add_argument("--output-tokens", type=float, required=True)
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--hit-rate", type=float, required=True)
    parser.add_argument("--input-price-per-mtok", type=float, required=True)
    parser.add_argument("--cached-input-price-per-mtok", type=float, required=True)
    parser.add_argument("--cache-write-tokens", type=float, default=0)
    parser.add_argument("--cache-write-price-per-mtok", type=float)
    parser.add_argument("--output-price-per-mtok", type=float, required=True)
    args = parser.parse_args(argv)

    uncached_input = (
        args.static_tokens * args.requests * (1 - max(0.0, min(1.0, args.hit_rate)))
        + args.dynamic_tokens * args.requests
    )
    if args.cache_write_tokens < 0 or args.cache_write_tokens > uncached_input:
        parser.error("cache-write-tokens cannot exceed uncached input or be negative")
    if args.cache_write_tokens and args.cache_write_price_per_mtok is None:
        parser.error("cache-write-price-per-mtok is required when cache-write-tokens is set")

    print(json.dumps(estimate(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
