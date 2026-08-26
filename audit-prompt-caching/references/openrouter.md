# OpenRouter Prompt Cache Reference

Last reviewed: 2026-08-27. Recheck current docs before exact claims.

Sources: https://openrouter.ai/docs/guides/best-practices/prompt-caching;
https://openrouter.ai/docs/guides/features/response-caching;
https://openrouter.ai/docs/guides/features/router-metadata;
https://openrouter.ai/docs/guides/features/zdr.

## Provider Prompt Cache

OpenRouter is a router. Keep downstream `provider_prompt` evidence separate
from OpenRouter `gateway_response` replay.

- Sticky sessions expire after 10 minutes idle; success resets the timer and
  provider errors do not update it. Locality is not a hit.
- Chat/Responses routing keys: body `session_id`, header `x-session-id`,
  `prompt_cache_key`, then opening messages.
- `provider.order` disables automatic stickiness. Fallbacks, filters, and
  router models can change provider/model; retain both.
- Chat reports `cached_tokens` and `cache_write_tokens` under
  `usage.prompt_tokens_details`; Responses uses `usage.input_tokens_details`.
  Missing fields remain unresolved.
- OpenRouter translates `cache_control` and `prompt_cache_breakpoint` on
  supported routes, but not their TTLs. Verify the final provider and wire.
- Concurrent Anthropic `:batch` lines need not share a fresh write. Sync
  warm-up or successive-batch plans are active changes.

## Response Cache Boundary

OpenRouter response caching is opt-in and runs before the provider. A HIT cannot
warm the provider prompt cache. Partition HITs before provider-cache ratios,
TTFT, cost, or warm-up analysis.

Prove a HIT with `X-OpenRouter-Cache-Status: HIT` or corroborating
`X-OpenRouter-Cache-Source-Id`. HIT usage is zeroed, but all-zero usage alone is
not proof. Cache hits omit `openrouter_metadata`; absence is still not proof
because router metadata is opt-in.

## Audit Evidence

Retained `X-OpenRouter-Metadata: enabled` data exposes endpoint, attempts,
strategy, and pipeline stages. Record route/provider/model, cache usage, and
keyed prefix hashes; never raw prompts, credentials, sessions, or cache keys.

Account-level ZDR disables OpenRouter response caching. Per-request
`provider.zdr` filters provider routes but does not itself disable that gateway
cache; provider in-memory prompt caching may still be allowed under ZDR.

If writes exist but reads stay low, check prefix drift, route/fallback changes,
provider support, marker translation, context compression, TTL, and eviction.
