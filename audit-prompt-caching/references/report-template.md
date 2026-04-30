# Prompt Caching Audit Report

Use this template when the user asks for a written audit, a handoff artifact, or a repeatable review format.

For repeatable runs, use `scripts/render_audit_report.py` to generate this Markdown shape and its JSON companion from normalized usage logs plus one-line findings.

## Executive Summary

- Provider/engine:
- Models:
- Audit mode:
- Provider facts: verified on YYYY-MM-DD / unverified
- Measurement change: yes / no / unknown
- Prompt behavior change: yes / no / pilot only / unknown
- Provider/routing change: yes / no / not yet / unknown
- Confidence: high / medium / low
- Main cache blocker:
- Expected impact:
- Do first:
- Do not do yet:
- Primary validation:
- Evidence Needed Next:

## Output Contract Selector

Use the smallest section set that fits the request:

- Quick triage: Executive Summary, Evidence Needed Next, Validation Plan.
- Code audit findings: Executive Summary, Findings, Before / After Prompt Layout, Validation Plan.
- Provider migration risk: Executive Summary, Cacheability Score, ROI Assumptions, Validation Plan.
- Agent loop audit: Executive Summary, Agent Loop Audit, Findings, Metrics To Track.
- Deployment audit: Executive Summary, Findings, Metrics To Track, Validation Plan.
- Not Worth Caching: Executive Summary, Not Worth Caching, Metrics To Track.

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
source | severity | provider/engine | issue | evidence | evidence_type | confidence | impact_condition | cache impact | safe_first_action | fix | validation | do_not_do_yet
```

Severity values: critical, high, medium, low.

Evidence types: `confirmed from code`, `confirmed from telemetry`, `provider-doc hypothesis`, `needs validation`.

Machine-readable companion fields should include `provider`, `engine`, `usage`, `findings`, and `expected_impact`. Each finding should preserve `evidence`, `evidence_type`, `confidence`, `impact_condition`, `safe_first_action`, and `do_not_do_yet` when available.

Use `medium` when the code shape can fragment cache but traffic, token count, repeat cadence, or cost impact is unknown. Use `high` when telemetry or hot-path evidence supports meaningful impact, or write the escalation condition in `impact_condition`.

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

## Agent Loop Audit

- Stable tool bundle:
- Tool ordering/schema serialization:
- Per-step `prefix_hash`:
- Per-step cache read/write fields:
- `tools_count` and tool-name hash:
- Mode switching or framework injection:
- Compaction strategy:
- Output-token and final-latency share:
- Actual route/model/provider:

## Not Worth Caching

Use this section when prompt caching is not the right lever.

- Gate that failed:
- Dominant cost or latency source:
- Risk of forcing cache reuse:
- Better optimization:
- Evidence that would reopen cache work:

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
- evidence type and confidence:
- safe first action:
- premature actions avoided:

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
