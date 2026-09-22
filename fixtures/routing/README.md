# Synthetic routing evidence examples

These hand-written fixtures exercise the offline analyzer. Every record declares
`provenance: "synthetic"`; none is a production export or a serving benchmark.
The format is a custom normalized JSONL export, not native vllm-router logs.

Run from the repository root:

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py fixtures/routing/slow-with-reuse.jsonl --attempt-ttft-limit-ms 500
python3 audit-prompt-caching/scripts/analyze_routing_logs.py fixtures/routing/within-limit.jsonl --attempt-ttft-limit-ms 500
python3 audit-prompt-caching/scripts/analyze_routing_logs.py fixtures/routing/insufficient-evidence.jsonl --attempt-ttft-limit-ms 500
```

The 500 ms limit is an example target for the **client TTFT of each attempt**.
It is not a request-wide SLO. All three commands exit 0 with `status: "ok"` because
the inputs are valid, including the example that violates the declared limit.

| Fixture | Supplied evidence | Expected result at 500 ms |
|---|---|---|
| `slow-with-reuse.jsonl` | One joined attempt; 900 reused tokens, TTFT 1200 ms | One violation; `reuse_with_ttft_violation: true` |
| `within-limit.jsonl` | One joined attempt; 900 reused tokens, TTFT 200 ms | No measured violation; `reuse_with_ttft_violation: false` |
| `insufficient-evidence.jsonl` | Decision only; prediction target unknown | Unknown assessment; outcome and joint violation flag remain `null` |

Each event requires schema version 1, its event type, run/request/attempt identity,
model/pool/worker context, source, and provenance. A join uses
`(run_id, request_id, attempt_id)`; context and provenance must agree. Source and
provenance are exporter assertions. Omitted or explicit `null` optional values
remain unknown; observed zero stays zero. A prediction's unit and target worker
remain separate from actual token reuse and the selected worker.

Read the [full input and measurement contract](../../audit-prompt-caching/references/routing-evidence.md)
before mapping real observations. Terminal success requires intended response
completion, including stream completion. TTFT excludes headers and heartbeat
events and shares the same attempt-start boundary as client E2E. An exporter must
supply those observations; the analyzer does not reconstruct them from native
HTTP timing or aggregate metrics.

Without the optional limit, assessment is unknown. With a limit but no supplied
TTFT, assessment is also unknown; the zero violation count means no violations
were measured. Additional attempts are counted without inferring retries. Invalid
input or options exit 2 with a JSON error and no partial report. These fixtures
establish analyzer behavior, not cache residency, causality, capacity, a policy
comparison, or deployment approval.
