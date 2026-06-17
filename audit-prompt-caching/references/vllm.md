# vLLM Prefix Cache Reference

Last reviewed: 2026-05-25. Verify official docs before exact claims about defaults, CLI flags, metrics names, block size, hash behavior, chunked prefill, `cache_salt`, multimodal hashes, eviction, or production routing.

Official sources:
- Automatic Prefix Caching design: https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html
- APC feature docs: https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/
- Engine args: https://docs.vllm.ai/en/stable/configuration/engine_args.html
- vLLM bench serve: https://docs.vllm.ai/en/stable/cli/bench/serve/
- Metrics: https://docs.vllm.ai/en/stable/usage/metrics/

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

## Benchmark Validation

Run benchmarks only after the Applicability Gate shows a repeated, stable, long-enough prefix with meaningful TTFT/prefill cost. From the vLLM repo, compare `benchmarks/benchmark_prefix_caching.py` with and without APC using fixed model, tokenizer, input length, output length, and repeat count.

For serving-path validation, use `vllm bench serve` with the `prefix_repetition` dataset, `--save-result`, and `--save-detailed`. Vary prefix length, suffix length, number of prefixes, output length, request rate, and concurrency to match the audited route.

Pair benchmark output with metrics: `vllm:prefix_cache_hits`, `vllm:prefix_cache_queries`, `vllm:prompt_tokens_cached`, `vllm:kv_cache_usage_perc`, TTFT/prefill latency, final latency, and route/replica labels. Do not claim production ROI from synthetic benchmark speedup alone.

## Monitoring

Track prefix hit/query ratio, available KV blocks, eviction indicators, TTFT/prefill by route, request length percentiles, prefix family cardinality, `max_model_len`, GPU memory utilization, replica count, router policy, tokenizer/model version, `cache_salt` cardinality, and multimodal representation.
