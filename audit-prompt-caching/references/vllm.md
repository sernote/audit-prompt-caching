# vLLM Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-05-25.

Verify before exact claims:
- whether prefix caching is enabled by default in the deployed vLLM version
- exact CLI/server parameters and defaults
- metrics names
- block size and hash algorithm behavior
- chunked prefill limitations
- cache salt behavior
- multimodal hash behavior
- eviction/free-queue behavior
- production-stack or router capabilities

Official sources:
- Automatic Prefix Caching design: https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html
- Automatic Prefix Caching feature docs: https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/
- Cache configuration API: https://docs.vllm.ai/en/stable/api/vllm/config/cache/
- Engine/server arguments: https://docs.vllm.ai/en/stable/configuration/engine_args.html
- vLLM bench serve CLI: https://docs.vllm.ai/en/stable/cli/bench/serve/
- Production metrics: https://docs.vllm.ai/en/stable/usage/metrics/
- Production stack docs: https://docs.vllm.ai/en/stable/serving/production_stack/

## Stable Mechanics

vLLM Automatic Prefix Caching reuses KV-cache blocks for identical token prefixes. Blocks are hashed with prefix context, so any early token mismatch prevents downstream reuse. Special tokens, chat templates, tokenizer versions, LoRA/adapters, and multimodal hashes can change the cache input even when visible text looks identical.

Eviction is driven by available KV blocks and cache policy. Prefix caching improves TTFT and GPU utilization only when prompts share prefixes often enough to repay overhead.

## Provider Checks

### max_model_len Over-Provisioning

Search:

```bash
rg -n "max.model.len|max_model_len|max-model-len" .
```

If `max_model_len` is set to the model's theoretical maximum while p99 requests are much shorter, KV memory may be reserved for rare long contexts and leave too little room for cached blocks.

Fix: size pools by workload. Use a short-context pool for most traffic and a long-context pool for rare long requests.

### KV Block Pressure And Eviction

Search:

```bash
rg -n "gpu.memory.utilization|gpu_memory_utilization|kv_cache|num_gpu_blocks|block_size|swap_space" .
```

Check whether useful prefixes are being evicted before reuse. Increase KV budget only after measuring.

vLLM's documented eviction/free-queue behavior can make cache effectiveness sensitive to block pressure and request shape. Treat low available KV blocks, high eviction indicators, and rising TTFT on long shared prefixes as a capacity issue, not only a prompt-stability issue.

### Multi-Replica Routing

Standard load balancing is cache-blind. Use a prefix-aware gateway, consistent hashing on the stable prefix, or a vLLM/SGLang/KubeAI/llm-d routing layer after verifying current docs.

### Tokenizer Or BOS Drift

Identical text is not identical cache input if token IDs differ. Pin tokenizer/model versions, chat templates, BOS/EOS handling, adapter settings, and smoke-test tokenization for representative prompts.

### Multimodal Hash Drift

For multimodal requests, image or media identity may participate in cache hashing. Keep URL/base64 representation, preprocessing, image detail, and media metadata stable for cacheable prefixes.

### cache_salt Isolation

If `cache_salt` is set per request or per user, cross-user reuse can disappear. Decide based on threat model, not habit. Prefer shared salt only inside a safe trust boundary; do not weaken required isolation for cache efficiency.

### APC On Unique Prompts

If every request is unique, APC can add overhead without benefit. Measure prefix hit metrics before forcing it on all workloads.

## Benchmark Validation

Use vLLM benchmarks only after the Applicability Gate shows a route has a repeated, stable, long-enough prefix and meaningful TTFT or prefill cost. A benchmark should validate engine behavior and workload shape; it should not replace production cache metrics.

For a local engine sanity check, run from the vLLM repository root and compare the same workload with and without APC:

```bash
python3 benchmarks/benchmark_prefix_caching.py \
  --model <model-or-local-path> \
  --enable-prefix-caching \
  --num-prompts 1 \
  --repeat-count 100 \
  --input-length-range 512:1024 \
  --output-len 128
```

Then run the same command with `--no-enable-prefix-caching`. Keep model, tokenizer, input length range, output length, tensor parallelism, and repeat count fixed. Use `--prefix-len` when the synthetic workload needs a controlled shared prefix, `--sort` only when length-sorted batches represent the target workload, and `--disable-detokenize` only when deliberately excluding detokenization overhead.

For serving-path validation, use `vllm bench serve` with the `prefix_repetition` dataset against a running server:

```bash
vllm bench serve \
  --backend openai \
  --model <served-model-name> \
  --dataset-name prefix_repetition \
  --num-prompts 100 \
  --prefix-repetition-prefix-len 512 \
  --prefix-repetition-suffix-len 128 \
  --prefix-repetition-num-prefixes 5 \
  --prefix-repetition-output-len 128 \
  --num-warmups 10 \
  --request-rate <requests-per-second-or-inf> \
  --max-concurrency <concurrency-limit> \
  --save-result \
  --save-detailed \
  --metadata prompt_family=<family> deployment=<version>
```

Vary `--prefix-repetition-prefix-len`, `--prefix-repetition-suffix-len`, `--prefix-repetition-num-prefixes`, `--prefix-repetition-output-len`, request rate, and concurrency to match the route being audited. If a gateway or multiple replicas sit in front of vLLM, record the routed worker or replica with the benchmark result.

Treat these as validation evidence only when they are paired with vLLM metrics and logs. Watch `vllm:prefix_cache_hits`, `vllm:prefix_cache_queries`, `vllm:prompt_tokens_cached`, `vllm:kv_cache_usage_perc`, TTFT/prefill latency, final latency, and route or replica labels where available. For external KV connectors, also check the external prefix-cache hit/query metrics documented for the deployed version.

Do not claim production ROI from synthetic benchmark speedup alone. Reopen prompt, routing, or capacity changes only when the benchmark and production telemetry agree on the same cacheable route, prefix family, worker locality, KV pressure, and output-token share.

## Diagnostics

Use vLLM metrics and logs. Confirm current metric names for the deployed version.

Watch:
- prefix cache hit/query ratio
- available KV/GPU blocks
- eviction indicators
- TTFT/prefill latency by route
- request length percentiles
- prefix family cardinality

## Monitoring

Correlate cache hit rate with:
- `max_model_len`
- GPU memory utilization
- replica count
- router policy
- tokenizer/model version
- chat template and special-token behavior
- `cache_salt` cardinality
- multimodal representation
- workload mix

For CI, keep a stable-tokenization smoke test for a reference prompt and fail on unexpected token ID changes.
