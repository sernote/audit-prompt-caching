# Prompt Cache Audit Report Template

Use for reusable handoff artifacts or when findings need more structure than chat.

## Output Contract Selector

- Quick triage: likely blocker, missing evidence, safe next command.
- Code audit: decision summary, findings, clean checks, verification.
- Provider migration risk: source/target semantics, layout, fields, routing, cost.
- Agent Loop Audit: stable tools, early messages, prefix hashes, cache fields, output tokens, compaction.
- Not Worth Caching: why cache is not the lever and what evidence would reopen it.

## Header

```text
Provider/engine:
Mode:
Provider facts: verified on YYYY-MM-DD / unverified
Measurement change:
Prompt behavior change:
Provider/routing change:
Confidence:
Do first:
Do not do yet:
```

## Findings

```text
source | severity | provider/engine | issue | evidence | evidence_type | confidence | impact_condition | cache impact | safe_first_action | fix | validation | do_not_do_yet
```

## Evidence Needed Next

List rendered prompt pair, usage fields, route/model/provider, prefix/tool/schema hashes, TTFT/prefill, output tokens, and deployment/router/KV metrics needed to raise or lower severity.

## Clean Checks

Record anti-patterns that were inspected and ruled out, for example volatile prefix data, tool/schema order, routing locality, TTL/cadence, output-token dominance, or privacy-driven isolation.
