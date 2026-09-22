# Routing evidence JSONL v1

This is a normalized export accepted by the new offline helper, not a native vllm-router log format. The pinned policy logs a character-based match separately from worker/load logs; declared metrics do not supply a complete request-to-worker-to-engine-outcome trace. Its match log can refer to a different candidate than the finally selected worker. Tracing can add an inherited request ID, but does not supply a reliable attempt identity for each policy decision. An exporter must map real trace identities and preserve absent measurements. Synthetic fixtures test this helper, not serving performance.

## Input

One JSON object per nonblank line. Exactly `schema_version: 1` and `event: "decision"` or `"outcome"`. Reject unrecognized fields to expose mapping errors. A nonempty string `run_id` namespaces request IDs; `(run_id, request_id, attempt_id)` identifies one upstream attempt. `model_id`, `pool_id`, `worker_id` identify its execution context and must agree across a joined pair. Multiple workers or retries require distinct attempt IDs. Do not join by timestamp proximity, model name alone, or row order.

Both record types require the following keys:

```json
{"schema_version":1,"event":"decision","run_id":"demo","request_id":"r1","attempt_id":"a1","model_id":"model-revision","pool_id":"p1","worker_id":"w1","source":"synthetic:decision-1","provenance":"synthetic"}
```

All identity/source strings are nonempty and whitespace-only values are invalid. `provenance` is `synthetic` or `observed`, supplied by the exporter; the helper does not independently verify that assertion. Joined pair provenance must agree. The export must use request/attempt identities that remain unique within `run_id`, including restarts and multiple routers. Model/worker revisions can be encoded in the supplied IDs; the helper cannot prove their accuracy.

Optional decision keys, omitted or null when unknown:

| Field | Type and semantics |
|---|---|
| `router_id` | Nonempty string; local routing process identity |
| `policy` | Nonempty string; descriptive only |
| `predicted_overlap` | Object with `matched`, `total`, `unit`, `kind`, `worker_id`; all keys required if object supplied. Counts are integers, `0 <= matched <= total`. An observed empty input has matched=total=0 and no defined ratio. Unit is `characters`, `tokens`, or `blocks`; kind is `request_history` or `kv_events`. Nested `worker_id` is the prediction target, a nonempty string or null when unknown. It can differ from the selected worker; never infer it from the event-level worker. Preserve without converting to observed KV reuse |
| `load` | Object with `value`, `kind`, `scope`; value is finite and nonnegative; kind is `active_requests` or `active_tokens`; scope is `router_local`, `pool`, or `unknown`. No inferred scope |

Optional outcome keys, omitted or null when unknown:

| Field | Type and semantics |
|---|---|
| `status` | `success`, `error`, or `cancelled`; null is unknown. Success means the intended response completed, including stream completion, not merely HTTP 2xx headers or circuit-breaker success |
| `client_ttft_ms` | Finite nonnegative client-observed time to first token for THIS attempt, excluding prior attempts. Unavailable client timing remains null; do not substitute engine prefill or upstream timing |
| `client_e2e_ms` | Finite nonnegative duration of THIS attempt; if both durations are known, TTFT must not exceed E2E |
| `queue_ms` | Finite nonnegative queue duration measured for this attempt, not a sampled aggregate gauge |
| `input_tokens` | Nonnegative integer observed by the engine for the attempt |
| `reused_tokens` | Nonnegative integer of actually reused input tokens for this attempt; if both token counts are known, reused must not exceed input |

TTFT and E2E use the same client observer and attempt-start boundary. First token excludes headers, heartbeat and empty stream events. E2E ends at response completion, error or cancellation. Unknown stream completion remains unknown; native HTTP response timing cannot substitute for these fields.

No boolean is a number. Reject numeric strings, NaN/Infinity, duplicate JSON object keys, nonobjects, unsupported versions/events, empty files, duplicate same-event attempt records, and conflicting joined context/provenance. Do not emit a partial success on malformed/conflicting input. Unknown outcomes are valid observations and remain unknown.

Example pair:

```jsonl
{"schema_version":1,"event":"decision","run_id":"demo","request_id":"r1","attempt_id":"a1","model_id":"model-revision","pool_id":"p1","worker_id":"w1","source":"synthetic:decision-1","provenance":"synthetic","router_id":"router-1","policy":"cache_aware","predicted_overlap":{"matched":900,"total":1000,"unit":"characters","kind":"request_history","worker_id":"w1"},"load":{"value":3,"kind":"active_requests","scope":"router_local"}}
{"schema_version":1,"event":"outcome","run_id":"demo","request_id":"r1","attempt_id":"a1","model_id":"model-revision","pool_id":"p1","worker_id":"w1","source":"synthetic:outcome-1","provenance":"synthetic","status":"success","client_ttft_ms":1200,"client_e2e_ms":2000,"queue_ms":1000,"input_tokens":1000,"reused_tokens":900}
```

## Output and commands

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py fixtures/routing/slow-with-reuse.jsonl --attempt-ttft-limit-ms 500
```

The helper reads only the specified UTF-8 JSONL file, writes JSON to stdout, uses no network and does not mutate the input. Runtime and memory scale with supplied records; it keeps attempt state for joining. CLI success is exit 0 with `status: "ok"`; invalid input/options is exit 2 with `status: "error"`, a concise error with line/field when applicable, and no raw input contents. Ordinary `--help` is text. A measured limit violation is a successful analysis, not an input error.

Successful output has `schema_version: 1`, counts and deterministic sorted attempt rows. Each row retains execution identity, input line/source provenance, `join_status` (`matched`, `decision_only`, `outcome_only`), and supplied decision/outcome fields with explicit null for absent optional measurements. Separate user requests from attempts: `additional_attempts = attempts - unique_requests`; this is not proof of retries rather than hedging or re-execution. Report event/attempt provenance, not a blanket claim that data was measured.

Counts include records, unique requests, attempts, matched/decision-only/outcome-only attempts, known/unknown terminal status, success/error/cancelled outcomes, and supplied TTFT/reuse measurement coverage. Missing outcome does not count as success. Zero reused tokens and unknown reused tokens remain distinct.

When the optional limit is supplied, report its scope as a per-attempt client TTFT limit, known measurements, violations and unknown measurements. A row may flag `reuse_with_ttft_violation` only when actual `reused_tokens > 0` and client TTFT exceeds the declared limit. Without a limit, assessment is unknown. Do not compute p99/capacity, call the service healthy, infer a root cause, recommend a policy switch, or approve a deployment. Do not subtract a character prediction from token reuse or aggregate ratios over different models/pools. Preserve model/pool context on each row.

## Acceptance examples

1. The pair above, either file order, limit 500: one request, one matched attempt, one known TTFT and violation, actual reuse 900, `reuse_with_ttft_violation`; no claimed router causality.
2. Change TTFT to 200, keep E2E 2000: no limit violation for the measured attempt; no general no-change/rollout approval.
3. Keep only the decision: one request, one decision-only attempt, unknown outcome/TTFT/reuse and no fabricated zeros.
4. Keep only the outcome: one outcome-only attempt. Outcome observations are retained but no decision association is fabricated.
5. Add a distinct attempt ID for the same request with a different worker: one request, two attempts, one additional attempt. Do not sum or average attempts into a fabricated client request TTFT.
6. Repeat the same decision, change joined worker, or mix synthetic/observed provenance within one attempt: invalid input, exit 2, no partial report.
7. Put `reused_tokens: 0` in an outcome without `input_tokens`: observed zero is retained, denominator remains unknown; no computed ratio.
8. Negative, nonfinite, bool or string numeric fields; TTFT above E2E; reused above input: invalid input. Test zero values and explicit null separately.
9. The prediction targets w2 or an unknown worker while the selected worker is w1: retain both facts. No cache prediction claim about w1 follows from that overlap log.

Native event delivery/replay, actual KV residency, offload transfer timing and alternative-policy outcomes remain outside v1. The established Routing Outcome Gate still governs real routing changes.
