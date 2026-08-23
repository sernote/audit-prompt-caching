# Prompt Cache Mechanics

## Core Model

Prefill creates KV; decode generates output. Prefix caching saves stable-prefix prefill, not decode.

## Audit Implications

```text
cache_hit_latency ~= cache_lookup_or_read + dynamic_tail_prefill + decode + tools/network
cache_miss_latency ~= full_prefill + decode + tools/network
total_cost ~= input_miss + cache_write + cache_read + output
```

Separate input/output, TTFT/prefill, decode, tools/network, and cache read/write. A hit can lower TTFT while output/tools keep total cost high; high total input is not proof of a miss.

## Common Misdiagnoses

High hit rate with low savings: output-heavy bills may make input-cache savings small; load `references/economics.md`. TTFT without total-latency improvement: inspect output, streaming, decode, tools, and network. High total input: inspect provider cache-read fields. Good vLLM/SGLang hits with bad throughput: inspect dynamic prefill, decode, KV pressure/eviction, routing, transfer, scheduler, and per-route concurrency.

## Routing Outcome Gate

For routing-policy changes, cache-blind and cache-aware policies are candidates; neither round robin nor prefix-aware/sticky/hash routing is a default or defect. Hit/locality/affinity/cached-token share are mechanism evidence only.

Baseline=current production; candidate=proposed; either may be cache-aware. Require:

- **matched-workload comparison:** same open-loop arrivals, prefix families, lengths, model/tokenizer, replica count, and KV; compare p95/p99 TTFT/end-to-end latency, queue, replica/KV skew, errors, retries, and fallbacks. Closed-loop requires concurrency/throughput/latency together.
- **capacity at SLO:** separate open-loop arrival-rate sweep for maximum sustainable throughput while latency/error SLOs hold; never infer it from one point or hit rate.
- **rewarm:** restart, scale, and failover tests measuring cache/route loss, recovery time, and SLO violations.

Predeclare objective, SLO guardrails, and rollback. Conditionally accept only when objective improves, gates/guardrails pass, and isolation is unchanged. Missing evidence is pilot/canary only; guardrail failure is reject/rollback even with hit/locality gains.

CacheRoute ([arXiv:2608.19677](https://arxiv.org/abs/2608.19677)) supports: hit/locality and capacity are separate; residual imbalance can erase affinity gains; matched replay beats workload statistics. It supplies no algorithm, threshold, or performance number.

## Observability

Collect request start, p50/p95/p99 TTFT/end-to-end latency, input/cache-read/cache-write/output tokens, route/model/replica, queue, throughput/capacity at SLO, replica/KV skew, errors/retries, and rewarm/recovery.
