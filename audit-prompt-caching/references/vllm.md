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
- Stable `v0.31.0` release (2026-10-05): https://github.com/vllm-project/vllm/releases/tag/v0.31.0
- Block-hash extra keys at tags: https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/core/kv_cache_utils.py and https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/v1/core/kv_cache_utils.py
- Source-tagged extra keys (#51899): https://github.com/vllm-project/vllm/pull/51899; LoRA path in block hashes (#59335): https://github.com/vllm-project/vllm/pull/59335
- P/D prefill cache hits in `prompt_tokens_details` (#54222, merged 2026-09-16): https://github.com/vllm-project/vllm/pull/54222
- P-side write at `v0.31.0`: https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/v1/core/sched/scheduler.py#L2172-L2182
- D-side read and override at `v0.31.0`: https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/v1/engine/output_processor.py#L234-L245 and https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/v1/engine/output_processor.py#L697-L707
- Pre-change counterparts at `v0.30.0`: https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/core/sched/scheduler.py and https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/v1/engine/output_processor.py
- `enable_prompt_tokens_details` default at `v0.31.0`: https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/entrypoints/launchers/cli_args.py#L145
- Chat `prompt_tokens_details` emission gate at `v0.31.0`: https://github.com/vllm-project/vllm/blob/v0.31.0/vllm/entrypoints/openai/chat_completion/serving.py#L90-L107

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

| Runtime evidence | Algorithm | Effective default seed | Cross-process reuse |
| --- | --- | --- | --- |
| stable `v0.27.1` | every supported algorithm | random `os.urandom(32)` per process | incompatible by default without a common effective seed |
| stable `v0.27.1` | any algorithm with an explicitly common `PYTHONHASHSEED` | deterministic from the supplied value | possible only with the same algorithm and all other inputs |
| post-`ef47a897` source/main | `sha256`, `sha256_cbor` | fixed deterministic default | possible with the same algorithm and all other inputs |
| post-`ef47a897` source/main | `xxhash`, `xxhash_cbor` | random per process | requires the same security-sensitive `PYTHONHASHSEED` and algorithm |
| post-`ef47a897` source/main | any algorithm with an explicit `PYTHONHASHSEED` | explicit `PYTHONHASHSEED` wins before the algorithm split | possible only with the same algorithm and all other inputs |

An explicit `PYTHONHASHSEED` is resolved before the post-`ef47a897` algorithm
defaults, so the explicit-seed row also applies to `sha256` and `sha256_cbor`;
the default rows describe only the unset-environment case.

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
- `cache_salt`: an intentional request-level trust-boundary isolation
  mechanism, effective only if its block-hash extra key cannot equal another
  source's key (see `cache_salt` and LoRA extra-key namespace).

## Compatibility is not isolation

Matching hash settings only permits a sharing group to use a common key space;
it does not authorize cross-tenant reuse. Preserve `cache_salt` as the
separate isolation boundary and choose its scope from the trust model. Do not
replace it with `PYTHONHASHSEED`, and do not recommend a shared hash seed as a
tenant-isolation mechanism. On a LoRA-serving deployment, accept `cache_salt`
isolation only after the extra-key namespace check below at the deployed
version/SHA.

For `xxhash` and `xxhash_cbor`, the effective seed is secret and unpredictable:
pass it only through protected secret configuration. Reports, telemetry, and
metric labels expose only `matched`, `mismatched`, `unknown`, boolean presence,
or a keyed fingerprint. For post-commit cryptographic algorithms the fixed
default is public and is not a secret. vLLM/runtime logs or a handshake may
still reveal an effective value; the audit must check that separate redaction
risk rather than promise that the runtime never emits it.

### `cache_salt` and LoRA extra-key namespace

Source check: 2026-10-06, `vllm/v1/core/kv_cache_utils.py` at tags `v0.30.0`
and `v0.31.0`. `generate_block_hash_extra_keys()` puts LoRA, multimodal,
`cache_salt`, and prompt-embeds keys into one tuple that is hashed with the
parent hash and block tokens. The LoRA key is added to every block; the salt
only to the first block, and it reaches later blocks through the parent hash.

| Source | `v0.30.0` key | `v0.31.0` key |
| --- | --- | --- |
| LoRA | bare `lora_name` | `("lora", name, path)` |
| `cache_salt` | bare salt | `("cache_salt", salt)` |
| multimodal | `(identifier, offset)` | `("mm", identifier, offset)` |
| prompt embeds | digest | `("prompt_embeds", digest)` |

On verified `v0.30.0`, an unsalted request for adapter `support-acme` and a
base-model request with `cache_salt="support-acme"` over equal tokens have
identical first-block `extra_keys`, so the same first-block hash: either can
reuse KV computed with the other's weights, and a caller-chosen salt can land
in an adapter's namespace. Later blocks diverge because only the LoRA request
adds its key there. This is a structural namespace collision of untagged
inputs, not a cryptographic hash collision; changing the hash algorithm or
seed does not fix it, and healthy hit/TTFT metrics do not refute it.

On that path, caller-selected untagged salts are an isolation gap unless
salts are server-derived or namespaced so that no salt can equal any adapter
name. Safe changes: upgrade to `v0.31.0` or a verified backport, and enforce
salt selection at the trust boundary. Evidence is passive: source at the
deployed SHA, gateway salt provenance, and the adapter registry. Do not run an
active cross-tenant probe.

`v0.31.0` removes that collision and, by adding the path, stops a name
re-pointed to a different path from reusing old blocks; the `v0.30.0`
name-only key can serve the previous adapter's KV. The path is a string
identity, not a hash of adapter content: when changed files at the same path
are loaded, by an in-place reload, a restart, or another worker sharing a tier,
the key is unchanged and old-weight blocks are not invalidated. KV computed
with the previous weights can then be reused while those blocks remain
reachable locally or in a shared/offload tier and an equal-token prefix
arrives, so publish each adapter revision at a new versioned path. Neither
change makes salt scope correct or proves complete tenant isolation.

Only these two tags are verified here. For another release, backport, fork, or
source build, inspect `generate_block_hash_extra_keys()` and
`_gen_lora_extra_hash_keys()` at the deployed SHA; a version number or
merge-commit ancestry is not proof, because fixes can be cherry-picked.
Source tagging and the LoRA path are separate checks: a source-tagged build or
backport can still key LoRA by name only, so record the path result separately.

Upgrade effect: every block with LoRA, salt, multimodal, or prompt-embeds extra
keys changes hash, as does every later block chained to it. Persisted or
offloaded KV from `v0.30.0`, and a mixed `v0.30.0`/`v0.31.0` fleet sharing a
tier, miss rather than reuse until writers share the schema and all other
inputs. Equal-name adapters at different paths, such as the same files under
two mount points, no longer share blocks. Chains with no extra keys, such as
unsalted text-only base-model requests, are not changed by this schema, so do
not assert a blanket cold cache.

KV events are not the hash schema. In `v0.31.0`, `to_event_extra_keys()`
publishes the untagged pre-`v0.31.0` shapes, and the LoRA event key carries the
name but not the path; `BlockStored.block_hashes` carries the new hashes, so
use those emitted hashes directly. Event shape does not reveal the deployed
schema, so identical event `extra_keys` across versions or paths do not prove
identical engine keys. A LoRA block hash cannot be rebuilt from event metadata
alone, because the path is not published. For other keys, a consumer can
restore source tags from `lora_name` and the fixed order (LoRA, multimodal,
`cache_salt`, prompt embeds) only if it already knows the deployed schema and
every other hash input: tokens, parent hash, algorithm, seed, and
serialization. A router that recomputes request hashes with a name-only LoRA
key will not match `v0.31.0` path-bearing block hashes. Use source inspection
plus emitted block hashes, deployment identity, adapter name/path per worker,
and route evidence.

## Shared-tier validation and evidence contract

For local APC, FS, OBJ, P2P/PD, and other connectors, record `kv_tier_type`,
the image/version/SHA, resolved retention source/value, concrete group classes,
`scheduler_block_size`, hash algorithm, seed compatibility status, extra-key
schema status, whether the LoRA key includes the path, and LoRA name/path
identity compatibility. For
P2P, require handshake/reject evidence and a config fingerprint/block length;
for FS/OBJ, require independently verified config plus a real cross-process
read. Never put a raw seed in an audit report, telemetry, recommended metric
label, or fixture.

Do not infer production ROI from this config evidence. Pair hit/TTFT and
prefill measurements with deployment version and route labels, and distinguish
retention/geometry mismatch from cross-process hash mismatch.

## P/D cached-token accounting

Source check: 2026-10-07, tags `v0.30.0` (`ced6857a`) and `v0.31.0`
(`db9527a4`), plus PR #54222, which the `v0.31.0` release notes list under KV
connectors. In prefill/decode (P/D) disaggregation the P worker computes the
prompt KV and the D worker receives it through the KV connector; the client
usually receives D's response. D's own prefill stats count transferred KV as
cached. When D reports that local count (always at `v0.30.0`; at `v0.31.0`
whenever no integer `remote_prefill_cached_tokens` arrives with a truthy
`do_remote_prefill`), `cached_tokens` close to `prompt_tokens` (~100%) is
transfer accounting, not P-side APC hits or saved prefill. After a proven remote
override (chain below), a high count can be a real P-side count. A near-100%
count alone does not establish P-side hits.

| Step | `v0.30.0` | `v0.31.0` |
| --- | --- | --- |
| P worker, request finish | no `remote_prefill_cached_tokens` symbol | if the request has prefill stats and the `kv_transfer_params` it returns for D carry a truthy `do_remote_prefill`, writes `remote_prefill_cached_tokens = prefill_stats.num_cached_tokens` into them |
| proxy/gateway | no cached-token field to carry | must forward P's returned `kv_transfer_params` to D unchanged, keeping the field as a JSON integer |
| D worker, request state | local prefill stats only | reads the field from `sampling_params.extra_args["kv_transfer_params"]` only when `do_remote_prefill` is truthy and the value is an `int` |
| D worker, usage | `num_cached_tokens` from local prefill stats | local prefill stats first, then overridden by the remote count when one was read |

A dropped, rebuilt, or retyped field (missing, a string such as `"0"`, a float,
or `null`) is ignored, and D silently keeps its local transfer-inclusive count;
the checked code path raises no error or warning. P and D both need the change:
a `v0.30.0` P never writes the field, and a `v0.30.0` D never reads it. A
version label alone therefore does not prove that usage is fixed, and neither
does a proxy that forwards only `do_remote_prefill` and block IDs. On P, the
scheduler stores local and external-connector cached tokens in
`prefill_stats`, so with a P-side offload/connector tier the count is not pure
local APC; check the `PrefillStats` definition at the deployed SHA.

`prompt_tokens_details` is opt-in: the exact flag is
`--enable-prompt-tokens-details` (plural `tokens`; the PR description spells it
`--enable-prompt-token-details`), and `enable_prompt_tokens_details` defaults to
`False` at `v0.31.0`. The checked chat-completion path returns no details when
the flag is off, and also when no cached, cache-creation, or multimodal counts
are available; check other endpoints separately. An absent
`prompt_tokens_details` or absent/`null` `cached_tokens` is
unobserved, not a measured zero. Check the flag on the API server that returns
the client response, usually the one in front of D.

A present integer `cached_tokens: 0` is a measured P-side zero for that request
only after the whole chain is established:

1. provenance: the usage object is from that request's D response and is
   correlated by request ID and route with the P request;
2. version/source: the P and D images or SHAs contain both the P-side write and
   the D-side read;
3. `do_remote_prefill` is truthy in the `kv_transfer_params` that D received;
4. the proxy round-trips P's returned `kv_transfer_params`, with
   `remote_prefill_cached_tokens` still an integer;
5. emission: `--enable-prompt-tokens-details` is on for the responding server.

The same chain applies to non-zero counts. vLLM chat usage is inclusive, so a
`valid` denominator only shows that `cached_tokens <= prompt_tokens` is
consistent arithmetic. It does not show which worker produced the numerator,
and does not prove P-side hits, saved prefill, savings, latency, or rollout.
Do not treat `v0.31.0` as a universal release floor: for a backport, fork,
nightly, or other release, inspect the scheduler and output processor at the
deployed SHA.

Keep validation passive. Use source at the deployed SHAs; P/D/proxy launch
config, including the connector and the flag; proxy code or config that
handles `kv_transfer_params`; and redacted request-correlated traces that
record, on P's output and on D's input, key presence, JSON type, and
truthiness for the `do_remote_prefill` flag (not a token count), and key
presence, JSON type, and integer value for `remote_prefill_cached_tokens`,
never raw block IDs, engine hosts, or prompts. Corroborate a P-side count with
P-pool `vllm:prefix_cache_hits`/`vllm:prefix_cache_queries` and P prefill time/TTFT by
route. Do not run production experiments or active tenant probes to
manufacture hits. None of this evidence proves complete application or tenant
isolation.

## Mechanics

vLLM Automatic Prefix Caching reuses KV blocks for identical token prefixes. Visible text is insufficient: tokenizer, chat template, BOS/EOS, adapters, multimodal hashes, and special-token handling can change the cache input.

### Standalone router input depends on the API path

Router check: 2026-09-05, standalone `vllm-project/router` commit
[`1d10e71`](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/protocols/spec.rs#L535-L559).
Before interpreting `cache_aware`, trace the deployed endpoint through
`extract_text_for_routing()` to the policy. In this pinned regular HTTP path,
`/v1/chat/completions` supplies a nonempty `session_params.session_id`, or an
empty string when it is absent/blank; it does not extract the message prefix.
The policy can therefore report `input_chars=0` for a nonempty chat prompt.
That is not evidence of zero engine input tokens or zero engine cache reuse.

The [completion path](https://github.com/vllm-project/router/blob/1d10e71fb7bb4c0adc9f2c16ec77bf5dd4aa1586/src/protocols/spec.rs#L758-L770)
extracts from `prompt`; check its representation separately. Never transfer
the chat behavior to another endpoint, release, PD mode or router project.
Do not add a session ID solely to increase a reported match ratio: matching
session strings is an affinity signal, not proof of shared prompt tokens or KV.
For an offline export, preserve the actual routing input's meaning and use
`references/routing-evidence.md` for identity, units and outcome boundaries.

## Audit Checklist

- `max_model_len` far above p99 input can reserve KV memory for rare long contexts and reduce cache capacity for common routes.
- Low available KV blocks, high eviction signals, and rising TTFT on stable long prefixes indicate KV block pressure, not necessarily prompt drift.
- Cache-blind routing may scatter prefixes; prefix-aware/hash may improve locality or concentrate load. Treat both as candidates; compare via the `Routing Outcome Gate` in `references/mechanics.md` with model, replicas, and KV fixed; paper numbers are not defaults.
- Pin model/tokenizer/chat template versions and smoke-test token IDs.
- Keep media representation stable for multimodal prefixes.
- Treat per-request `cache_salt` as intentional isolation that fragments reuse; choose the coarsest safe trust boundary. With LoRA serving, first verify the extra-key namespace and adapter path identity at the deployed version/SHA (`cache_salt` and LoRA extra-key namespace).
- Do not force APC on unique prompts without measuring prefix hit metrics.
- Newer vLLM deployments can emit KV-cache events and use KV transfer/offload
  connectors. Inspect `--kv-events-config`, `kv_transfer_config`, and
  `kv_connector` before attributing a TTFT regression only to prompt drift:
  transfer, offload, or event loss can explain a cold-looking request.
- If a deployment line uses `--enable-kv-cache-events`, treat it as
  stale/integration-specific deployment guidance; verify exact runtime
  parser/version/startup acceptance, and do not assume upstream vLLM support.

## Benchmark Validation

Run benchmarks only after the Applicability Gate shows a repeated, stable, long-enough prefix with meaningful TTFT/prefill cost. From the vLLM repo, compare `benchmarks/benchmark_prefix_caching.py` with and without APC using fixed model, tokenizer, input length, output length, and repeat count.

For serving-path validation, use `vllm bench serve` with the `prefix_repetition` dataset, `--save-result`, and `--save-detailed`. Vary prefix length, suffix length, number of prefixes, output length, request rate, and concurrency to match the audited route.

Pair output with `vllm:prefix_cache_hits`, `vllm:prefix_cache_queries`, `vllm:prompt_tokens_cached`, and `vllm:kv_cache_usage_perc`; use `references/observability.md` for outcome fields and `references/mechanics.md` for comparison, capacity at SLO, queue/skew, retries, and rewarm. Synthetic benchmark speedup alone is not production ROI.

## Monitoring

Track prefix hit/query ratio, available KV blocks, eviction indicators, TTFT/prefill by route, request length percentiles, prefix family cardinality, `max_model_len`, GPU memory utilization, replica count, router policy, tokenizer/model version, `cache_salt` cardinality, LoRA name/path identity status, and multimodal representation. Use `references/observability.md` for Routing Outcome Gate fields, including capacity at SLO, queue/KV skew, errors/retries, and rewarm.

When KV events are enabled, also track event delivery/drop rate, connector type,
and transfer/offload latency separately from prefix-hit ratio. Event streams are
observability, not proof that the destination worker reused a KV block.
