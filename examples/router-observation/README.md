# Router observation lab

Two observations from standalone `vllm-router` commit `1d10e71` matter when
auditing cache metrics:

- In its regular HTTP chat path, the cache policy receives a session ID or an
  empty string. Nonempty messages can therefore accompany `input_chars=0`;
  that value does not measure engine input tokens or KV reuse.
- HTTP 200 and circuit-breaker success do not establish completion of the
  intended stream. A controlled run produced three such successes but only
  two complete streams.

Read the [recorded findings and raw artifacts](recorded/2026-09-05/README.md)
without building anything. The source references and observations are pinned
to that revision; check your deployed API path and version separately.

## How the example works

Run an unmodified standalone `vllm-router` against one Python HTTP mock worker.
The probe sends the same synthetic chat body three times, with distinct
client-generated `x-request-id` headers. A forwarded `x-lab-mode` tells the worker
to finish the first two SSE streams and omit both `finish_reason` and `[DONE]`
on the third. All three mock responses use HTTP 200.

This is an observation exercise, not vLLM inference, a GPU benchmark, a cache
warm-up experiment or a routing-policy comparison. It needs no model download.
The probe neither modifies upstream source nor produces normalized routing JSONL.

## Reproduce the observations (optional)

Use Python 3.10+ and a working Rust/Cargo native build environment. Building the
router downloads source and Rust dependencies and consumes compiler time and
disk space; it is separate from the offline unit tests. Upstream's native build
dependencies also apply. Run these commands from this repository's root:

```bash
(
set -eu
audit_repo="$PWD"
lab_root="$(mktemp -d)"
git clone --filter=blob:none --no-checkout \
  https://github.com/vllm-project/router.git "$lab_root/router"
git -C "$lab_root/router" checkout --detach \
  1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586
test "$(git -C "$lab_root/router" rev-parse HEAD)" = \
  "1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586"
(
  cd "$lab_root/router"
  CARGO_HOME="$lab_root/cargo" CARGO_TARGET_DIR="$lab_root/target" \
    cargo build --locked --bin vllm-router -j 2
)
python3 -B "$audit_repo/examples/router-observation/probe.py" \
  --router-binary "$lab_root/target/debug/vllm-router" \
  --router-revision "$(git -C "$lab_root/router" rev-parse HEAD)" \
  --output-dir "$lab_root/capture"
)
```

An existing binary can be supplied instead. `--router-revision` is the operator's
source-provenance statement: the binary SHA-256 recorded by the probe does not
verify its Git revision. Keep build provenance when reusing a binary. The pinned
[upstream source](https://github.com/vllm-project/router/tree/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586)
defines this reproduction's CLI and behavior; other revisions need verification.

The runtime binds only `127.0.0.1`, choosing ephemeral worker, router and metrics
ports. It uses direct stdlib HTTP connections, disables router retries, gives
router startup 15 seconds, and sets request/socket timeouts to 10 seconds
(metrics: 5 seconds). Child environment overrides explicitly set
`RUST_LOG=vllm_router_rs=debug`, `NO_PROXY=127.0.0.1` and `no_proxy=127.0.0.1`;
these overrides are recorded in the manifest. Other environment values are
inherited without being exported into the manifest. No external endpoint is
configured. A port can be taken between reservation and router startup; inspect
the error artifacts and rerun with a new output directory if that happens.

## Read the artifacts

The output directory must be new; the probe refuses to overwrite existing data.

| File | Evidence |
| --- | --- |
| `router.log` | Unmodified router stdout/stderr, with its native log fields. |
| `client.json` | Sent bodies/headers, received headers and SSE lines, HTTP status, content-arrival/EOF timings and terminal markers. |
| `worker.json` | Requests received by the synthetic worker; its `usage` is explicitly unknown. |
| `metrics.txt` | Raw router Prometheus response; aggregate counters are not per-request trace joins. |
| `manifest.json` | Binary hash, operator-supplied revision, exact router arguments, Python/platform, environment overrides and experiment status. |

`first_content_delta_ms` starts before the HTTP request and stops on the first
nonempty content delta. Heartbeats, empty content and events containing only the
assistant role do not stop this timer. `headers_ms` and `eof_ms` measure separate
events. The worker inserts synthetic delays: these values are client observations
of mock content arrival, never GPU or engine TTFT.

The SSE reader supports only this worker's one-JSON-line events and `[DONE]`;
it is not a general SSE/SDK adapter. `stream_complete` requires HTTP 200, content,
transport EOF, `finish_reason` and `[DONE]`. HTTP 200 or EOF alone is insufficient.
Exit 0 and manifest `status: complete` mean the expected **two complete streams
and one intentional truncation** were observed. The third request still has
`stream_complete: false`. Unexpected patterns and runtime errors return nonzero,
preserve partial records, and stop the router and worker. Empty artifacts can
mean that execution failed before that observation was available.

No engine usage is measured. The probe does not invent an upstream attempt ID,
attach a prediction to a worker by log order, or interpret identical request
bodies as evidence of cache reuse. Consult the pinned router's API-specific
routing-input path before interpreting cache-policy logs.

## Offline checks

```bash
python3 -B -m unittest discover -s tests -p 'test_router_observation_lab.py'
```

These tests use controlled responses and resource fakes. They need no Rust,
network sockets, GPU, downloaded models or running router. Actual router
observations require the explicit build/run above and retained artifacts.
