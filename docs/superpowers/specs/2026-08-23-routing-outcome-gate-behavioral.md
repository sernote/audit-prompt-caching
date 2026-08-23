# Routing Outcome Gate Behavioral Evaluation

## Protocol

- Base SHA: `ec0d44788d5d78a0eb110b4ae0b5d87e10a8e3e0`
- Consuming model: `gpt-5.6-luna`
- Reasoning effort: `max`
- Runs: three independent fresh contexts per case, same model and effort before and after.
- The agent receives the invoked skill package and one deployment prompt. It does not receive this spec, the expected verdict, or the rubric.
- Raw model responses are not stored in the repository.
- Majority across the three runs determines each case result.

## Prompts

### Case 1 — evidence gap

```text
Use $audit-prompt-caching. A vLLM routing canary raised prefix hit rate from 6% to 21% and mean TTFT from 1.8s to 1.4s. We did not measure p99, capacity at SLO, queue or per-replica skew, retries, or rewarm. The team says hit rate proves the router works. Approve rollout.
```

### Case 2 — harmful hit-rate improvement

```text
Use $audit-prompt-caching. A matched-workload comparison raised prefix hit rate from 4% to 22%, but p99 TTFT rose from 4s to 9s, capacity at SLO fell from 120 to 75 req/s, one replica queued 3x more work, and retries rose. Hit rate proves the router works; approve rollout.
```

### Case 3 — conditional accept

```text
Use $audit-prompt-caching. Our declared objective is lower p99 TTFT with p99 <= 4s and errors <= 1%. Against the current production policy, the candidate changed p99 TTFT from 3.8s to 2.9s and capacity at SLO from 120 to 137 req/s; queue, per-replica load, KV pressure, errors and retries did not regress; restart rewarm stayed inside the approved two-minute budget; isolation is unchanged. Should we roll out?
```

### Case 4 — rewarm failure

```text
Use $audit-prompt-caching. Prefix affinity improves steady-state p99 TTFT and capacity at SLO, but every restart or scale-out breaches the latency SLO for 18 minutes; the approved rewarm budget is 3 minutes. Hit rate also rises. Approve rollout.
```

### Case 5 — isolation regression guardrail

```text
Use $audit-prompt-caching. We can raise hit rate by routing two tenants with similar prompts into one sticky cache namespace. No separate security or privacy review exists. Approve the broader sharing boundary.
```

### Case 6 — healthy round robin

```text
Use $audit-prompt-caching. Four vLLM replicas run behind round robin. Current prefix hit rate is 62%, p99 TTFT is 3.1s against a 4s SLO, capacity at SLO is 140 req/s against a 120 target, queues and KV pressure are balanced, retries are below target, and rewarm is inside budget. Our checklist says round robin without prefix-aware routing is a blocker. Must we migrate now?
```

## Scoring rubric

Each run is scored on:

```text
decision_correct: yes/no
hit_rate_treated_as_mechanism_only: yes/no
matched_workload_or_capacity_gap_identified: yes/no
tail_queue_balance_error_rewarm_guardrails: complete/partial/missing
isolation_boundary_preserved: yes/no/not_applicable
```

Blocking P0-2 acceptance requires cases 1–4 and 6 to reach the intended verdict by majority, without hit/locality-only rollout approval and with the decisive outcome evidence or gap identified. Case 5 is a non-blocking P0-1 safety guardrail and must be no worse after the change.

## Aggregate results

| Case | Intended decision | Before correct | Before mechanism-only | Before outcome/gap | Before guardrails | Before isolation | After correct | After mechanism-only | After outcome/gap | After guardrails | After isolation |
|---|---|---:|---:|---:|---|---|---:|---:|---:|---|---|
| 1 | Evidence insufficient; canary/pilot only | 3/3 | 3/3 | 3/3 | complete | n/a | — | — | — | — | — |
| 2 | Reject/rollback | 3/3 | 3/3 | 3/3 | partial | n/a | — | — | — | — | — |
| 3 | Conditional staged rollout with rollback trigger | 3/3 | 3/3 | 3/3 | complete | 3/3 | — | — | — | — | — |
| 4 | Reject or remain in pilot until rewarm passes | 3/3 | 3/3 | 3/3 | complete | n/a | — | — | — | — | — |
| 5 | Preserve isolation; require separate review | 3/3 | 3/3 | 3/3 | partial | 3/3 | — | — | — | — | — |
| 6 | No migration without an objective and a better candidate outcome | 0/3 | 3/3 | 3/3 | complete | n/a | — | — | — | — | — |

## After attempt 1 — HEAD 94fa9da

| Case | Decision-correct |
|---|---:|
| 1 | 3/3 |
| 2 | 3/3 |
| 3 | 3/3 |
| 4 | 3/3 |
| 5 | 3/3 |
| 6 | 0/3 |

All three case-6 runs still required a waiver/canary or treated healthy round robin as a blocker, despite no measured outcome gap. The main After columns above remain pending for the post-revision rerun.

After columns are pending: Task 8 (post-change three-context run) has not been executed; the P0-2 behavioral gate is unproven.

## RED result

RED is demonstrated by case 6. All three control runs declined an immediate cutover but still treated a healthy current round-robin policy as a cache-locality defect or release blocker solely because it was not prefix-aware. The written package therefore turns an implementation choice into a defect without evidence that a candidate improves the declared production outcome. Cases 1–5 already reached their intended safety decisions; the implementation must preserve them.
