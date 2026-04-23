# Prompt Cache Mechanics

Use this reference when the symptom is latency, throughput, self-hosted compute, or "cache hits work but cost/latency did not improve enough."

## Core Model

LLM inference has two different phases:

- **Prefill/input processing**: the model processes the prompt and creates KV tensors for the input tokens.
- **Decode/output generation**: the model generates new tokens, usually one step at a time, using the existing KV state.

Prompt/prefix caching mostly saves prefill work for a stable prefix. It does not make output tokens disappear, and it usually does not remove decode cost for long generated answers.

## Audit Implications

When cache hits are visible but the user still sees high cost or latency, split the request shape:

```text
cache_hit_latency ~= cache_lookup_or_read + dynamic_tail_prefill + decode + tools/network
cache_miss_latency ~= full_prefill + decode + tools/network
total_cost ~= input_miss + cache_write + cache_read + output
```

Check:
- static input tokens
- dynamic input tokens after the cached prefix
- output tokens
- TTFT or prefill latency
- time between first token and final token
- cache read/write fields
- whether output tokens dominate cost

## Common Misdiagnoses

### High Hit Rate, Low Savings

If output tokens dominate the bill, input-cache savings may be working but financially small. Load `references/economics.md` and calculate cost share before changing prompt caching.

### TTFT Improved, Total Latency Did Not

If cache hits reduce TTFT but final response time is still high, inspect output length, streaming cadence, tool execution time, and decode bottlenecks.

### Total Prompt Tokens Look High

Some providers still count cached tokens in total prompt/input fields. Do not treat high total input tokens as proof of cache miss; inspect provider-specific cache-read fields.

### Self-Hosted Hit Rate Looks Good, Throughput Still Bad

For vLLM/SGLang, a prefix hit can still leave bottlenecks in dynamic prefill, decode, KV memory pressure, replica routing, CPU/GPU transfer, or scheduler behavior. Inspect TTFT, decode throughput, KV block pressure, and per-route concurrency together.

## Observability

For latency audits, collect:
- `request_start`
- provider first-token timestamp or TTFT
- final-token timestamp
- input tokens, cached-read tokens, cache-write tokens, output tokens
- prefix family/route/model/provider
- worker/replica for self-hosted inference
- tool execution timing for agents
- network/provider overhead when measured separately

For cost audits, collect raw usage records. Averages hide the difference between routes with long static prefixes and routes with unique prompts.
