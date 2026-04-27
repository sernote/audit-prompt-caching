# Prompt Caching Audit Report

Use this template when the user asks for a written audit, a handoff artifact, or a repeatable review format.

For repeatable runs, use `scripts/render_audit_report.py` to generate this Markdown shape and its JSON companion from normalized usage logs plus one-line findings.

## Executive Summary

- Provider/engine:
- Models:
- Audit mode:
- Provider facts: verified on YYYY-MM-DD / unverified
- Confidence: high / medium / low
- Main cache blocker:
- Expected impact:
- Primary validation:

## Cacheability Score

| Dimension | Score | Notes |
|---|---:|---|
| Prefix length |  |  |
| Prefix stability |  |  |
| Request cadence |  |  |
| Provider support |  |  |
| Telemetry quality |  |  |
| Safety/privacy |  |  |

## Findings

Use this format:

```text
file:line | severity | provider/engine | issue | cache impact | fix | validation
```

Severity values: critical, high, medium, low.

Machine-readable companion fields should include `provider`, `engine`, `usage`, `findings`, and `expected_impact`.

## Before / After Prompt Layout

### Before

```text
[dynamic timestamp / request id]
[user or tenant metadata]
[system/developer instructions]
[tools / structured-output schema]
[few-shot examples]
[static context / document]
[user message]
```

### After

```text
[stable tools / structured-output schema]
[stable system/developer instructions]
[stable few-shot examples]
[stable context / document]
[conversation anchor]
[user message]
[dynamic metadata]
```

## Metrics To Track

- cache hit ratio:
- cache read/write ratio:
- input token cost per request:
- output token cost share:
- p50/p95 TTFT:
- p50/p95 final latency:
- prefix/tool/schema hash:
- model/provider/region/replica:
- cache miss reasons:

## ROI Assumptions

- static tokens per request:
- dynamic tokens per request:
- output tokens per request:
- request count:
- hit rate:
- input price:
- cached-input price:
- output price:
- TTL/write premium:
- safety or tenant boundary:

## Validation Plan

1. Render N representative requests and compare cacheable prefix fingerprints.
2. Run repeated requests with the same stable prefix and different late dynamic content.
3. Confirm provider cache-read/cached-token fields increase on repeated calls.
4. Compare TTFT/prefill latency and final latency separately.
5. Compare input cost and total cost, including output-token share.
6. Add a CI smoke check that fails when the stable cacheable prefix changes unexpectedly.
