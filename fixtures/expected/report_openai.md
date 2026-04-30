# Prompt Cache Audit

## Executive Summary

- Provider/engine: openai
- Engine/API surface: Responses API
- Records reviewed: 3
- Cache hit ratio: 0.5962
- Output share: 0.0717
- Measurement change: unknown
- Prompt behavior change: unknown
- Provider/routing change: unknown
- Confidence: low
- Do first: analyze usage logs and validate prefix stability
- Do not do yet: make provider/routing changes without telemetry

## Findings

fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | cold request has zero cached tokens | first request pays full prefill | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase

## Expected Impact

Observed cache benefit on 0.5962 of input tokens. Validate TTFT and total cost separately before claiming savings.

## Validation Plan

1. Re-run usage analysis on repeated requests.
2. Compare cache-read/cached-token fields with TTFT and total cost.
3. Confirm prefix/tool/schema hashes stay stable across warm calls.
