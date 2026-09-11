# OpenRouter Prompt Cache Reference

Last reviewed: 2026-09-12. Recheck current docs before exact claims.

Sources: https://openrouter.ai/docs/guides/best-practices/prompt-caching;
https://openrouter.ai/docs/guides/features/response-caching;
https://openrouter.ai/docs/guides/features/router-metadata;
https://openrouter.ai/docs/guides/features/zdr;
https://openrouter.ai/docs/guides/routing/routers/auto-router;
https://openrouter.ai/docs/guides/routing/routers/pareto-router;
https://openrouter.ai/docs/guides/features/in-region-routing;
https://openrouter.ai/docs/cookbook/administration/usage-accounting.

## Provider Prompt Cache

OpenRouter is a router. Keep downstream `provider_prompt` evidence separate
from OpenRouter `gateway_response` replay.

- Sticky sessions expire after 10 minutes idle in the prompt-caching guide,
  while the Pareto router page says 5 minutes; record which router served the
  request and retain both figures. Success resets the timer and provider
  errors do not update it. Locality is not a hit.
- Chat/Responses routing keys, in precedence order: body `session_id` (max
  256 chars; wins over the header), header `x-session-id`,
  `prompt_cache_key`, then a hash of the first system/developer message and
  the first non-system message. With `session_id`, stickiness starts on the
  first success; without it, only after a detected cache hit.
- `provider.order` disables automatic stickiness. Fallbacks, filters, and
  router models can change provider/model; retain both. Router models
  (`openrouter/auto`, `openrouter/pareto-code`, `:nitro`) reuse the resolved
  model only while it stays in the candidate set, and rebuilding the input
  cache after a model switch is a documented cost. Regional hosts
  (`us.openrouter.ai`, `eu.openrouter.ai`) exclude multi-model routers and
  fail closed; whether sticky state is shared across hosts is undocumented.
- Chat reports `cached_tokens` and `cache_write_tokens` under
  `usage.prompt_tokens_details`; Responses uses `usage.input_tokens_details`.
  `cache_write_tokens` appears only on models with explicit caching and
  paid writes; `cache_discount` is a top-level response field, not usage.
  Usage is now always included (`usage.include` is a no-op; streams carry it
  in the last SSE chunk). Missing fields remain unresolved.
- OpenRouter translates `cache_control` and `prompt_cache_breakpoint` on
  supported routes, but not their TTLs; `prompt_cache_options` stays
  OpenAI-only and `prompt_cache_breakpoint` needs GPT-5.6+. A top-level
  `cache_control` on Anthropic routes auto-advances one breakpoint to the
  last cacheable block. Verify the final provider and wire.
- Concurrent Anthropic `:batch` lines need not share a fresh write. Sync
  warm-up or successive-batch plans are active changes.

## Per-Provider Caching Table

The prompt-caching guide's table at the last review (multipliers are
router-published and can differ from the vendor's own price list):

| Provider | Mode | Min tokens | TTL | Write | Read |
|---|---|---|---|---|---|
| OpenAI | automatic; explicit on GPT-5.6+ | 1,024 | 30m minimum | free before 5.6, 1.25x on 5.6+ | 0.25x-0.5x |
| Anthropic | explicit `cache_control` (top-level or up to 4 blocks) | 1,024-4,096 by model | 5m or `ttl: "1h"` | 1.25x / 2x | 0.1x |
| Google Gemini | implicit on 2.5+; explicit via `cache_control` | 1,024-4,096 | ~3-5 min implicit; 5m explicit, no refresh | none implicit | 0.25x |
| DeepSeek | automatic | unstated | unstated | 1.0x | 0.1x |
| Moonshot AI | automatic | unstated | unstated | none | 0.25x |
| xAI Grok | automatic | unstated | unstated | none | 0.25x |
| Groq | automatic (Kimi K2 models) | unstated | unstated | none | 0.5x |
| Alibaba Qwen | explicit `cache_control` per block | unstated | 5m | 1.25x | 0.1x |
| Z.AI | automatic | unstated | unstated | free (limited time) | per model page |

MiniMax, Mistral, Tencent, Xiaomi, and Upstage are absent from the table even
though their endpoint listings carry `input_cache_read` prices; treat their
router-level cache behavior as unverified and read the vendor reference
(`references/minimax.md`, `references/mistral.md`, `references/tencent.md`,
`references/xiaomi.md`; Moonshot and Grok in `references/moonshot.md` and
`references/xai.md`). Upstage documents `prompt_cache_key` as a distinct key
per conversational context (the opposite of OpenAI's shared-prefix grouping)
with `prompt_tokens_details.cached_tokens` at about 0.2x; NVIDIA publishes no
vendor-side prompt caching, so Nemotron cache reads on the router belong to
the hosting provider, not NVIDIA.
The same slug can fan out to many hosts with different cache-read prices, so
join `cached_tokens` with the served provider before any savings claim.

## Response Cache Boundary

OpenRouter response caching is opt-in and runs before the provider. A HIT cannot
warm the provider prompt cache. Partition HITs before provider-cache ratios,
TTFT, cost, or warm-up analysis.

Prove a HIT with `X-OpenRouter-Cache-Status: HIT` or corroborating
`X-OpenRouter-Cache-Source-Id`, `X-OpenRouter-Cache-Age`, or a shrinking
`X-OpenRouter-Cache-TTL` (`X-Generation-Id` stays unique per response). The
key hashes the exact request body, so property order matters. HIT usage is
zeroed, but all-zero usage alone is not proof. Cache hits omit
`openrouter_metadata`; absence is still not proof because router metadata is
opt-in. Concurrent identical requests are not coalesced and eviction can
precede the TTL.

## Audit Evidence

Retained `X-OpenRouter-Metadata: enabled` data exposes endpoint, attempts,
strategy (`direct`, `auto`, `pareto`, `fusion`, `fallback`, ...), and pipeline
stages including `context_compression`, which rewrites the served prefix.
Record route/provider/model, cache usage, and keyed prefix hashes; never raw
prompts, credentials, sessions, or cache keys.

Account-level ZDR disables OpenRouter response caching. Per-request
`provider.zdr` filters provider routes (OR-composed with account and guardrail
settings) but does not itself disable that gateway cache; OpenRouter treats
provider in-memory prompt caching as compatible with ZDR.

If writes exist but reads stay low, check prefix drift, route/fallback changes,
provider support, marker translation, context compression, TTL, and eviction.
