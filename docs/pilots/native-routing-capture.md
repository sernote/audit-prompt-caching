# Obtaining real routing evidence

Use this checklist when the [participant guide](README.md) reaches a routing
question but there is no export for the [normalized analyzer](../../audit-prompt-caching/references/routing-evidence.md).
Start with one existing, redacted request. A metrics dashboard, benchmark summary
or repository source snapshot cannot supply a missing request/attempt join.

This source inspection covers **standalone vllm-router**, commit
[`1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586`](https://github.com/vllm-project/router/tree/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586),
whose Cargo package version is `0.1.15`. It does not identify the version deployed
in anyone's infrastructure. Check the deployed revision and effective settings
before applying the mapping.

## What this source exposes

First inspect the endpoint's input to the policy. In the pinned regular HTTP
`/v1/chat/completions` path, `extract_text_for_routing()` returns a nonempty
`session_params.session_id` or an empty string, not text from `messages`.
Repeated nonempty chat prompts without that parameter can therefore produce
`matched_chars=0, input_chars=0`. This says nothing about engine input tokens or
KV reuse. The completion endpoint extracts from `prompt`; inspect other APIs
and deployments separately. Do not add a session key just to manufacture a
match ratio. See [chat extraction](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/protocols/spec.rs#L535-L559)
and [completion extraction](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/protocols/spec.rs#L758-L770).

| Observation | What it supports | What is still missing |
|---|---|---|
| `matched_chars`, `input_chars`, `match_rate` in the cache policy debug log | A character-based best match over the routing input supplied by this API path | Actual engine reuse; the best-match worker is not printed by that message; the eventual selection can differ |
| `max_load`, `min_load`, `is_imbalanced` in that policy | Local worker counters used by this router's policy | A selected-worker load record and evidence of the engine queue or global load |
| Policy metrics labelled by worker | Aggregate policy-decision counts for that worker | A specific request/attempt identity |
| Request ID middleware and optional OTel HTTP spans | Request context and upstream HTTP observations, when enabled and captured | A guaranteed policy-to-attempt link, client first token, intended stream completion and engine reuse |
| HTTP response status and circuit-breaker outcome | HTTP/worker-health classification in that path | Success of the complete intended response |

The policy branches are in
[`cache_aware.rs`](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/policies/cache_aware.rs#L240-L352).
`BaseWorker::load()` reads the object's atomic counter in
[`worker.rs`](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/core/worker.rs#L445-L455).
The HTTP retry closure receives but discards its numeric attempt argument, then
selects a worker. Its status-based outcome accounting occurs before the client
has consumed a streaming body. See
[`route_typed_request`](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/routers/http/router.rs#L540-L639).

Do not promise a native JSON-log switch from this checkout: the logging library
supports JSON, but server startup passes `json_format: false`. The CLI exposes
`--log-level`, `--log-dir` and `--enable-trace`; the last enables OTel, not a
complete audit export. Request tracing is conditional on OTel being enabled.
See [startup configuration](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/server.rs#L810-L830),
[application construction](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/server.rs#L1013-L1033)
and [CLI flags](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/main.rs#L181-L211).
These are source-level findings, not observations of an installed deployment.
Record `RUST_LOG` as well as the CLI flags: a valid environment filter overrides
the fallback derived from `--log-level`. An inherited `RUST_LOG=warn` can suppress
the debug policy messages despite `--log-level debug`. See
[`logging.rs`](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/logging.rs#L67-L99).

## Smallest useful capture

Keep raw observations and the mapping description together. Redact values
consistently so identity relationships remain intact; do not share credentials,
customer prompt bodies or internal endpoint names.

1. **Run manifest.** Exact router and engine revisions or image digests; effective
   policy, balancing thresholds, retry and timeout configuration; model revision,
   pool alias, router instance and worker incarnation/DP identity. Preserve whether
   tracing was enabled and any sampling or filtering that can remove events.
2. **Decision.** Original record for the selected worker and its decision context.
   Keep the prediction's unit, kind and target separate from the selected worker.
   An absent prediction target remains `null`; an absent decision remains absent.
3. **Attempt mapping.** An identity established where the router actually makes
   each outbound attempt, with an explicit relationship to the ingress request,
   selected worker and corresponding engine request. Propagate or record that
   relationship across each boundary. A shared ingress request ID alone does not
   distinguish retries, hedges or re-execution. Never create attempt IDs from
   nearby timestamps, row order or a client request counter.
4. **Worker observation.** Matching engine request and worker incarnation, with
   input/reused-token measurements and their precise field definitions if the
   deployed engine exposes them. A prefix prediction is not such a measurement.
   Aggregate token counters cannot be assigned to an individual request.
5. **Client observation.** From one observer, record the start, first meaningful
   output token, and completion/error/cancellation boundary. Ignore response
   headers, heartbeats and empty chunks when detecting the first token. Record
   intended stream completion independently of HTTP status. If the client can
   only measure the whole logical request across retries, do not put that duration
   into an individual attempt's `client_ttft_ms` or `client_e2e_ms`.
6. **Mapping and gaps.** For every normalized field, name the raw artifact and
   record/field that supports it. Record missing, sampled-out and conflicting
   observations. Keep unknown measurements absent or `null`, including engine
   reuse. Preserve every observed attempt even when it did not succeed.

An upstream HTTP client span can help identify an outbound operation. Its span
ID is usable as an attempt identity only after verifying its exact relationship
to the policy decision and worker operation in the deployed path. In this source,
the HTTP client span is created after worker selection, and `.send()` observes
the response before consuming its body; neither the mapping nor client TTFT is
automatic. See
[`otel_http.rs`](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/otel_http.rs#L23-L123).

## If instrumentation is needed

The smallest change to design is a structured decision event at the actual
attempt boundary, followed by a linked worker outcome and a separately measured
client outcome. Create the attempt identity there and carry it through the
selected operation; record both prediction target and selected worker. Keep
router-local load explicitly scoped. Audit retry, cancellation and worker-restart
paths as well as success.

This is an instrumentation contract, not a patch included in the skill. Deploying
it needs its own review and tests. A normalized row's `provenance: "observed"` is
an exporter assertion; the analyzer cannot validate the raw capture on its own.
Do not label a mixture of mock measurements and router observations as a real
production outcome. The v1 format has row-level provenance, so retain mixed lab
observations in their original artifacts rather than forcing them into it.

Once genuine mapping is available, run:

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py /path/to/routing.jsonl
```

Run from the pinned skill repository in the participant guide. Success here
means valid analysis, not complete coverage or acceptable latency. Review joined,
decision-only and outcome-only records and their unknown fields. If the mapping
is unavailable, the useful pilot result is this precise capture requirement;
do not fabricate a parser output to make the audit appear finished.

For a controlled example of these boundaries, see the
[loopback lab](../../examples/router-observation/README.md) and its
[recorded run](../../examples/router-observation/recorded/2026-09-05/README.md).
They use a real router with a synthetic HTTP worker and cannot replace the real
deployment capture described here.
