# Routing evidence exports

Load for an offline router/worker evidence audit. Use `scripts/analyze_routing_logs.py` only with this normalized JSONL format; raw vllm-router logs and Prometheus snapshots do not match it. The helper reads one supplied file, emits JSON to stdout, uses no network and writes no files. Work and memory scale with records; small exports take seconds.

```bash
python3 scripts/analyze_routing_logs.py path/to/routing.jsonl --attempt-ttft-limit-ms 500
```

This command is relative to the installed skill directory. The limit is an explicit **per-attempt client TTFT** target, not a percentile SLO. Omit it when none is declared. Valid analysis exits 0 even with observed violations; invalid input/options exits 2 with JSON `status: "error"`. `--help` prints text.

## Export contract v1

One object per nonblank JSONL line. Both event types require:

```jsonl
{"schema_version":1,"event":"decision","run_id":"demo","request_id":"r1","attempt_id":"a1","model_id":"model-revision","pool_id":"p1","worker_id":"worker-incarnation-1","source":"synthetic:decision-1","provenance":"synthetic"}
{"schema_version":1,"event":"outcome","run_id":"demo","request_id":"r1","attempt_id":"a1","model_id":"model-revision","pool_id":"p1","worker_id":"worker-incarnation-1","source":"synthetic:outcome-1","provenance":"synthetic","status":"success","client_ttft_ms":1200,"client_e2e_ms":2000,"queue_ms":1000,"input_tokens":1000,"reused_tokens":900}
```

This pair is synthetic. `source` identifies the original artifact/record; `provenance` is `observed` or `synthetic`, an exporter assertion the helper cannot independently verify. All identity/source strings must be nonempty. Namespace request IDs with `run_id`; preserve retries, worker incarnation/DP identity and multiple-router correlation. Do not fabricate attempt IDs from line order or temporal proximity.

Join key: `(run_id, request_id, attempt_id)`. Model/pool/worker and provenance must agree across the pair. Unmatched events remain visible. Duplicate decisions/outcomes or conflicting context fail validation; they are not silently deduplicated or merged. A different worker within the same user request needs a distinct attempt ID.

Optional fields may be omitted or null. Unknown is never measured zero.

| Event | Optional fields |
|---|---|
| decision | `router_id`, `policy`: nonempty strings |
| decision | `predicted_overlap`: object with integer `matched`, `total` (`0 <= matched <= total`), `unit` (`characters`, `tokens`, `blocks`), `kind` (`request_history`, `kv_events`), and prediction-target `worker_id` (string or null). All nested keys required; 0/0 counts are valid with no defined ratio |
| decision | `load`: object with finite nonnegative `value`, `kind` (`active_requests`, `active_tokens`) and `scope` (`router_local`, `pool`, `unknown`); all nested keys required. It describes the selected worker, with no inferred global scope |
| outcome | `status`: `success`, `error`, `cancelled`; success means completed intended response including stream completion |
| outcome | `client_ttft_ms`, `client_e2e_ms`, `queue_ms`: finite nonnegative durations for this attempt |
| outcome | `input_tokens`, `reused_tokens`: nonnegative integer engine measurements; reused cannot exceed input when both are known |

Client TTFT/E2E use the same observer and attempt-start boundary; TTFT cannot exceed E2E when both are known. First token excludes headers, heartbeats and empty events. E2E ends on completion/error/cancellation. Never rename upstream response-header timing or aggregate queue gauges into these measurements.

Unknown keys, unsupported versions, duplicate JSON keys, invalid types, booleans as numbers, numeric strings, nonfinite/negative numbers and empty exports are rejected. Do not discard inconvenient records to manufacture a valid report: repair the mapping or document unavailable evidence.

## Reading the result

Inspect joined/decision-only/outcome-only coverage, separate request/attempt counts, known/unknown terminal status and supplied measurement coverage. Additional attempts are not automatically retries; they may represent hedging or re-execution. Each attempt retains model/pool/worker, sources and provenance. A missing outcome is not success.

`reuse_with_ttft_violation` requires actual reused tokens and client TTFT above the declared limit. It observes their coexistence; it does not establish that cache routing caused the delay. Do not compare character overlap with engine token reuse, or assign an untargeted/other-worker prediction to the selected worker. Do not claim cost, capacity, p99, deployment approval or global health from these counts. Apply `references/mechanics.md` → Routing Outcome Gate separately for actual policy changes.

## vllm-router mapping boundary

Inspect the endpoint's routing input before interpreting overlap. In the pinned
regular HTTP chat path below, `extract_text_for_routing()` uses
`session_params.session_id` or an empty string, not the messages. Thus character
overlap can describe a session key, and 0/0 can accompany a nonempty prompt.
See `references/vllm.md` for the API-specific source and limits. The v1 export
does not encode the routing input representation; preserve it in the source
mapping, and never relabel session-key overlap as prompt-token/KV reuse.

At commit [1d10e71](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/policies/cache_aware.rs), the match log is a best-match character estimate; selection can fall back to another worker. Tracing may provide an inherited request ID, but does not guarantee a correlated policy-attempt ID. Inspect the [HTTP route](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/routers/http/router.rs) and [middleware](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/middleware.rs) for the deployed version.

An exporter needs genuine request/attempt mapping and worker/client observations. Leave prediction target or measurements unknown when absent. Do not derive engine reuse from a router metric name, or terminal success from HTTP headers/circuit-breaker status. This v1 helper does not reconstruct KV-event replay, offload timing or counterfactual outcomes of another policy.
