# vLLM Prefix Cache Reference

Last reviewed: 2026-08-23. Verify official docs and the deployed source/image before exact claims about defaults, CLI flags, metrics names, block size, hash behavior, chunked prefill, `cache_salt`, multimodal hashes, eviction, or production routing.

Official sources:
- Automatic Prefix Caching design: https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html
- APC feature docs: https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/
- Engine args: https://docs.vllm.ai/en/stable/configuration/engine_args.html
- vLLM bench serve: https://docs.vllm.ai/en/stable/cli/bench/serve/
- Metrics: https://docs.vllm.ai/en/stable/usage/metrics/
- Releases: https://github.com/vllm-project/vllm/releases
- Stable `v0.27.1` release (2026-08-11): https://github.com/vllm-project/vllm/releases/tag/v0.27.1
- Retention promotion/default change (`017e9f4`, 2026-08-17): https://github.com/vllm-project/vllm/commit/017e9f4448b700e85ee16023287b025693c72b9e
- Deterministic cryptographic hash default (`ef47a897`, 2026-08-18): https://github.com/vllm-project/vllm/commit/ef47a897e2ad9a404cce9c9e7df15934deb8ffbe
- KV spec classes and validator: https://github.com/vllm-project/vllm/blob/main/vllm/v1/kv_cache_interface.py and https://github.com/vllm-project/vllm/blob/main/vllm/v1/core/kv_cache_coordinator.py

## Version and capability gate

An exact retention or cross-process reuse recommendation starts with runtime
evidence. Collect these items in order; a manifest string or an image tag alone
is not feature evidence:

1. immutable image digest and `vllm --version`; for a source/nightly build,
   record the resolved commit SHA;
2. feature presence in `--help`, resolved config, or the source at that SHA;
3. effective retention value and its source: CLI, config, env, or release-line
   default;
4. the concrete KV spec class for every KV group, then its human-readable
   attention geometry;
5. `scheduler_block_size`, separately from each group's physical block size and
   the `prefix_match_unit`/`hash_block_size` used by the cache;
6. the shared-tier topology: local APC, FS, OBJ, P2P/PD, or another connector.

If feature presence is not proven, report `Change needed: unknown until
feature/version evidence`; do not guess a version floor or a value. The
presence of `VLLM_PREFIX_CACHE_RETENTION_INTERVAL` in a manifest does not prove
that the running binary consumes it, and absence of a CLI flag does not prove
that an env-only feature is absent.

### Upstream `main` versus stable release

The stable `v0.27.1` release (published 2026-08-11) already has an env-only
retention feature. Its `VLLM_PREFIX_CACHE_RETENTION_INTERVAL` default is
`None`; the coordinator consumes that value, but the CLI/config promotion in
`017e9f4` is not part of that release. `017e9f4` is therefore a promotion and
default change, not the introduction of retention.

Treat `017e9f4` and `ef47a897` as upstream `main` behavior until an official
release or a verified deployment SHA proves that they are included. A legacy or
other stable line is unknown until its source, `--help`, or resolved config is
checked.

### Version × retention behavior

| Runtime evidence | Feature surface | Default/meaning |
| --- | --- | --- |
| stable `v0.27.1` source/release | env `VLLM_PREFIX_CACHE_RETENTION_INTERVAL`; coordinator consumes it | default `None`; no CLI/config surface from `017e9f4` |
| source/nightly containing `017e9f4` | CLI/config `prefix_cache_retention_interval`; env is deprecated fallback | default `0`; resolved source must be shown |
| other stable/legacy line | unknown without source/help/resolved config | do not transfer either matrix |

Apply the following matrix per KV group, not once per model:

| Runtime | Effective value | Dense/non-eligible groups | SWA/Mamba/hybrid groups |
| --- | --- | --- | --- |
| stable `v0.27.1` env-only | `None` | interval does not apply | dense checkpoints on sparse groups |
| stable `v0.27.1` env-only | `0` | startup/config error: any non-`None` env value requires SWA/Mamba groups | semantic checkpoints: latest replay boundary and shared-prefix junctions |
| stable `v0.27.1` env-only | positive | startup/config error when no sparse group exists | additional periodic checkpoints; value is a multiple of effective `scheduler_block_size` |
| post-`017e9f4` source/main | `None` | interval does not apply | dense checkpoints on sparse groups |
| post-`017e9f4` source/main | `0` | permitted no-op | semantic checkpoints: latest replay boundary and shared-prefix junctions |
| post-`017e9f4` source/main | positive | startup/config error when no sparse group exists | additional periodic checkpoints; value is a multiple of effective `scheduler_block_size`; full-attention groups ignore it |

In the post-commit validator, `ChunkedLocalAttentionSpec` is in the
dense/non-eligible column. A pure dense configuration therefore has a
no-op interpretation for post-commit `0`, while a positive interval is an
error; it is not a sparse geometry merely because its name contains `Local`.
The stable env-only `0` row is a configuration error, not the post-commit
no-op semantics. `None` means the retention interval is disabled; it does not
make a group eligible.

Retention checkpoints on eligible SWA/Mamba groups are semantic checkpoints,
including the latest replay boundary and shared-prefix junctions. Do not
describe `0` as preserving exactly one last block. Positive values add periodic
checkpoints and must be checked against the effective scheduler granularity.

## Geometry eligibility

Eligibility comes from the concrete runtime class and the checked validator,
not from a model architecture name or the words `local`, `sliding`, or `sink`:

| Concrete KV spec class | Retention-interval eligibility |
| --- | --- |
| `SlidingWindowSpec`, including `SlidingWindowMLASpec` | eligible |
| `MambaSpec` | eligible |
| `FullAttentionSpec` and subclasses, including `RSWASpec` and `SinkFullAttentionSpec` | not eligible |
| `ChunkedLocalAttentionSpec` | not eligible in the checked validator |
| unknown/new spec | `unknown` until a source/runtime probe confirms it |

For a hybrid model, report every group separately: class, geometry, physical
block size, retention eligibility, and behavior under the selected runtime
matrix. Full-attention groups are not sparse groups and do not become eligible
because another group in the model is SWA or Mamba.

### Block-size evidence

Do not substitute one block-size field for another. `scheduler_block_size` is
the scheduling granularity used by the retention validator; each KV group's
physical block size and the `hash_block_size`/`prefix_match_unit` are separate
inputs. In the checked upstream change, scheduler granularity is required to
be compatible with `hash_block_size` and with every group's physical block
size. Record all values before accepting a positive interval.

## Version × hash compatibility

Hash compatibility and isolation are different decisions. Use this matrix for
the runtime evidence actually collected:

| Runtime evidence | Algorithm | Default seed without `PYTHONHASHSEED` | Cross-process reuse |
| --- | --- | --- | --- |
| stable `v0.27.1` | every supported algorithm | random `os.urandom(32)` per process | incompatible by default without a common effective seed |
| stable `v0.27.1` | any algorithm with an explicitly common `PYTHONHASHSEED` | deterministic from the supplied value | possible only with the same algorithm and all other inputs |
| post-`ef47a897` source/main | `sha256`, `sha256_cbor` | fixed deterministic default | possible with the same algorithm and all other inputs |
| post-`ef47a897` source/main | `xxhash`, `xxhash_cbor` | random per process | requires the same security-sensitive `PYTHONHASHSEED` and algorithm |

The P2P handshake advertises the effective seed and rejects a mismatch. That
is an operational validation of one compatibility input, not proof that
different algorithms are compatible. For FS/OBJ tiers there is no P2P
handshake: independently verify the config and perform a real cross-process
read.

algorithm and effective seed are necessary but insufficient for cross-version
compatibility. All cache-key inputs must match, including model/config/token
inputs and a compatible serialization/runtime. `sha256` uses Pickle, so Python
and vLLM runtime compatibility cannot be assumed. `sha256_cbor` makes
serialization more reproducible but does not remove the model/config/token
requirements.

Separate the three axes in an audit:

- hash algorithm: how a block key is calculated;
- effective seed: whether the block-hash chain can match across processes;
- `cache_salt`: an intentional request-level trust-boundary isolation mechanism.

## Compatibility is not isolation

Matching hash settings only permits a sharing group to use a common key space;
it does not authorize cross-tenant reuse. Preserve `cache_salt` as the
separate isolation boundary and choose its scope from the trust model. Do not
replace it with `PYTHONHASHSEED`, and do not recommend a shared hash seed as a
tenant-isolation mechanism.

For `xxhash` and `xxhash_cbor`, the effective seed is secret and unpredictable:
pass it only through protected secret configuration. Reports, telemetry, and
metric labels expose only `matched`, `mismatched`, `unknown`, boolean presence,
or a keyed fingerprint. For post-commit cryptographic algorithms the fixed
default is public and is not a secret. vLLM/runtime logs or a handshake may
still reveal an effective value; the audit must check that separate redaction
risk rather than promise that the runtime never emits it.

## Shared-tier validation and evidence contract

For local APC, FS, OBJ, P2P/PD, and other connectors, record `kv_tier_type`,
the image/version/SHA, resolved retention source/value, concrete group classes,
`scheduler_block_size`, hash algorithm, and seed compatibility status. For
P2P, require handshake/reject evidence and a config fingerprint/block length;
for FS/OBJ, require independently verified config plus a real cross-process
read. Never put a raw seed in an audit report, telemetry, recommended metric
label, or fixture.

Do not infer production ROI from this config evidence. Pair hit/TTFT and
prefill measurements with deployment version and route labels, and distinguish
retention/geometry mismatch from cross-process hash mismatch.

## Mechanics

vLLM Automatic Prefix Caching reuses KV blocks for identical token prefixes. Visible text is insufficient: tokenizer, chat template, BOS/EOS, adapters, multimodal hashes, and special-token handling can change the cache input.

## Audit Checklist

- `max_model_len` far above p99 input can reserve KV memory for rare long contexts and reduce cache capacity for common routes.
- Low available KV blocks, high eviction signals, and rising TTFT on stable long prefixes indicate KV block pressure, not necessarily prompt drift.
- Standard Kubernetes or gateway round robin is cache-blind; use prefix-aware routing, stable-prefix hashing, or a verified serving router.
- Pin model/tokenizer/chat template versions and smoke-test token IDs.
- Keep media representation stable for multimodal prefixes.
- Treat per-request `cache_salt` as intentional isolation that fragments reuse; choose the coarsest safe trust boundary.
- Do not force APC on unique prompts without measuring prefix hit metrics.
- Newer vLLM deployments can emit KV-cache events and use KV transfer/offload
  connectors. Inspect `--enable-kv-cache-events`, `kv_transfer_config`, and
  `kv_connector` before attributing a TTFT regression only to prompt drift:
  transfer, offload, or event loss can explain a cold-looking request.

## Benchmark Validation

Run benchmarks only after the Applicability Gate shows a repeated, stable, long-enough prefix with meaningful TTFT/prefill cost. From the vLLM repo, compare `benchmarks/benchmark_prefix_caching.py` with and without APC using fixed model, tokenizer, input length, output length, and repeat count.

For serving-path validation, use `vllm bench serve` with the `prefix_repetition` dataset, `--save-result`, and `--save-detailed`. Vary prefix length, suffix length, number of prefixes, output length, request rate, and concurrency to match the audited route.

Pair benchmark output with metrics: `vllm:prefix_cache_hits`, `vllm:prefix_cache_queries`, `vllm:prompt_tokens_cached`, `vllm:kv_cache_usage_perc`, TTFT/prefill latency, final latency, and route/replica labels. Do not claim production ROI from synthetic benchmark speedup alone.

## Monitoring

Track prefix hit/query ratio, available KV blocks, eviction indicators, TTFT/prefill by route, request length percentiles, prefix family cardinality, `max_model_len`, GPU memory utilization, replica count, router policy, tokenizer/model version, `cache_salt` cardinality, and multimodal representation.

When KV events are enabled, also track event delivery/drop rate, connector type,
and transfer/offload latency separately from prefix-hit ratio. Event streams are
observability, not proof that the destination worker reused a KV block.
