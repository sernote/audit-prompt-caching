# SGLang Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- RadixAttention and radix-cache behavior in the deployed SGLang version
- router package and configuration parameters
- HiCache support and cache tiers
- metrics names
- tokenizer, chat template, multimodal, and page-size behavior
- cache flush and cache-disabling flags

Official sources:
- SGLang docs: https://docs.sglang.io/
- SGLang router/model gateway: https://docs.sglang.io/advanced_features/router.html
- SGLang model gateway/router: https://docs.sglang.io/advanced_features/sgl_model_gateway.html
- HiCache design: https://docs.sglang.ai/advanced_features/hicache_design.html

## Stable Mechanics

SGLang uses RadixAttention/radix-cache style prefix reuse. Dynamic content at the beginning can create a different root/path in the prefix structure, so later static content may not be reused.

Visible text identity is not enough. Tokenizer, chat template, BOS/EOS behavior, multimodal preprocessing, and framework-injected metadata can change what the runtime sees.

## Provider Checks

### Radix Prefix Stability

Search for dynamic values before stable context:

```bash
rg -n "datetime|uuid|request_id|trace_id|run_id|user_id|tenant|company|cwd|git status|platform" .
```

Move volatile values late in the request or into supported metadata. Verify by rendering representative requests and comparing the stable prefix fingerprint.

### Router And Multi-Replica Locality

When multiple SGLang runtimes serve traffic, check whether routing is cache-aware. SGLang router docs describe cache-aware routing using approximate radix trees and balancing thresholds. A generic round-robin gateway can scatter shared prefixes across workers.

Inspect:
- `sglang_router`
- `launch_router`
- `launch_server`
- gateway/load balancer config
- `cache_threshold`, balance thresholds, service discovery, session affinity

Keep this advice scoped to SGLang and generic cache-aware routing.

### Tokenizer, Chat Template, And BOS Drift

Pin model/tokenizer versions and chat templates. Smoke-test token IDs for representative prompts after engine, tokenizer, or model upgrades. Treat BOS/EOS and special-token changes as cache-breaking until verified.

### HiCache And Capacity

If the workload has long contexts or sparse repeats, check whether HiCache or cache tiers are used and whether cache eviction/capacity metrics support the traffic shape. Do not assume GPU-only cache can hold every useful prefix.

### Cache Disabled Or Flushed

Search for flags or endpoints that disable/flush radix cache. Use them for determinism/debugging only with awareness that they remove cache benefits.

```bash
rg -n "disable.radix|disable_radix|flush_cache|radix|hicache|cache_threshold" .
```

## Diagnostics

Watch:
- cache hit rate or prefix/radix cache metrics for the deployed version
- TTFT/prefill latency by route and worker
- worker selected by router
- tokenizer/chat-template version
- cache-aware routing thresholds
- cache flush/disable events
- request prefix family cardinality

## Monitoring

Correlate cache drops with:
- prompt/template changes
- tokenizer or chat-template upgrades
- router strategy or threshold changes
- replica count or service discovery changes
- HiCache/cache tier changes
- mode switching or dynamic tool selection

For CI, render representative prompts through the same chat template the SGLang server uses and fail when stable prefix token IDs change unexpectedly.
