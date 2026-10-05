# Moonshot AI / Kimi Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-10-05 (Chinese platform `platform.kimi.com` / `api.moonshot.cn` only; source pages undated, so the observation date is not an introduction date).

Verify before exact claims:
- the deployment host, model, and API surface, before transferring any rule below
- which Kimi models support Cache Write, and per-TTL write, hit, and miss prices for the exact model and billing scope
- usage field names per API surface (Chat Completions, Responses, Messages)
- whether international `api.moonshot.ai` / `platform.kimi.ai`, OpenRouter, or other hosts follow the Chinese-platform contract
- whether the legacy explicit Context Caching API still answers

Official sources (Chinese platform, observed 2026-10-05):
- Context caching guide: https://platform.kimi.com/docs/guide/context-caching
- Model inference pricing: https://platform.kimi.com/docs/pricing/chat

International sources from the 2026-09-12 review, not rechecked for this contract:
- Automatic context caching: https://platform.kimi.ai/docs/guide/use-context-caching-feature-of-kimi-api
- Chat Completions API: https://platform.kimi.ai/docs/api/chat
- Messages (Anthropic-compatible) API: https://platform.kimi.ai/docs/api/messages

## Stable Mechanics

Kimi API caching is **prefix caching** with no cache object or cache ID (on `api.moonshot.cn`, default automatic writes are documented only for Chat Completions and Responses on write-capable models listed below; see TTL Controls), and any change in the prefix makes everything after it unreusable. Put stable system prompts, tool definitions, reference material, and code first and per-turn content last; keep timestamps and random IDs out of the prefix.

On the Chinese platform the guide documents (2026-10-05):
- Cache Write support: `kimi-k3` supports Cache Write; `kimi-k2.7`, `kimi-k2.7-highspeed`, and `kimi-k2.6` do not. Use these exact names; do not treat `kimi-k2.7` and `kimi-k2.7-code` as the same model, and do not infer write or hit behavior for unlisted models. This is a write-capability and billing statement only: no documented Cache Write is not evidence that reads are absent or that the cache is not populated automatically (the pricing page's K2-series table, which includes `kimi-k2.6`, has a cached-input price column but no write column). A price category does not prove deployment behavior; check reads on the actual deployment.
- Two TTLs, `5m` and `1h`. Documented mechanics: a TTL locks at first write and cannot be rewritten; hits renew the original TTL free, newly appended content is written at the locked TTL, and a different TTL can be written only after the existing entry fully expires. 5m and 1h are separate caches that do not interoperate.
- Not established by those rules: whether a request with a different TTL writes, what it costs, or any cold-start duration or upper bound for it. Changing the TTL setting does not establish that a new write happened or was charged, nor that none did. Do not derive a bound from an existing entry's remaining TTL. Draw write, cost, cold-period, or causal conclusions only from request/response evidence across the switch (read/write usage fields and their TTL attribution: Messages breakdown, write headers, console columns), not from guessing.
- Caches are isolated per organization (shared inside one org), cannot be purged manually, and expire after inactivity longer than the chosen TTL.
- Storage is block-based: a partial trailing block is not cached and bills as a miss. The guide gives no block size or minimum length.

The 256-token rule (a hit only when the previous prompt exceeded 256 tokens) and unofficial reports of 256-token alignment and a 5-30 minute TTL come from the international guide and probes at the 2026-09-12 review. Treat them as historical, unverified heuristics for that surface, not Chinese-platform guarantees.

The older explicit Context Caching API (`POST /v1/caching`, `role: "cache"` messages with `cache_id=...;reset_ttl=...`) was absent from the docs index at the earlier review and reportedly rejected `kimi-k2.*` models. If a codebase still uses it, verify it against the live API before treating cache reads as real, and do not port it to new models.

`prompt_cache_key` existed on international Chat Completions as a coding-agent session hint at the earlier review; the docs did not promise it changes cache decisions and probes reported it ignored. The Chinese guide does not mention it.

## Provider Checks

Unless marked historical or international, these checks describe `api.moonshot.cn` as documented on 2026-10-05; do not apply them to another host without a capture from it.

### TTL Controls

- Chat Completions and Responses: `prompt_cache_options: {"mode": "implicit", "ttl": "5m" | "1h"}`; `implicit` is the only mode. Omitting it uses 5m: eligible prefixes are written automatically and billed as cache writes.
- Messages (`/anthropic/v1/messages`): request-top-level `cache_control: {"type": "ephemeral", "ttl": "5m" | "1h"}` writes the prefix at that TTL. Omitting it makes the request read-only against the 5m cache, with no write. `cache_control` markers inside message content are ignored on this surface, so Anthropic-style block markers neither write nor choose a TTL; only the top-level field does.
- Because hits renew the original TTL free, a read-only Messages request that hits an existing eligible 5m entry renews it without Cache Write; it adds no new content, and a miss renews nothing. Zero `cache_creation_input_tokens` therefore proves neither expiry nor missing renewal, and keeping a hit entry warm does not require recurring writes. Judge decay from observed request gaps, read/miss counts, and prefix changes.

### Surfaces And Fields

Label records `provider: moonshot` so `analyze_usage_logs.py` applies the vendor adapter (nested write fields and Messages creation tokens are read; the per-TTL breakdown is not needed).

- Chat Completions: total `usage.prompt_tokens`, read `usage.prompt_tokens_details.cached_tokens`, write `usage.prompt_tokens_details.cache_write_tokens`.
- Responses: total `usage.input_tokens`, read/write in `usage.input_tokens_details.cached_tokens` / `.cache_write_tokens`.
- For both, read, write, and uncached are mutually exclusive parts of the total: `uncached = total - read - write`.
- Messages: total = `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`; `input_tokens` excludes reads and writes. `usage.cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` split `cache_creation_input_tokens` by TTL; never add them to the total again. Zero creation is expected when the top-level `cache_control` is omitted.
- Streaming Chat Completions needs `stream_options.include_usage=true`; the cache breakdown arrives in the final chunk's usage.
- Optional response headers `Msh-Usage-Cache-Write-Tokens-5m` and `Msh-Usage-Cache-Write-Tokens-1h` (documented with a Chat Completions example) give per-TTL writes (0 when nothing new was written). Console request details add per-TTL write-token columns, with input = miss + hit + write.

At the 2026-09-12 review, international `api.moonshot.ai` Chat Completions reported `usage.cached_tokens` at the top level (sometimes mirrored in `prompt_tokens_details.cached_tokens`) as a subset of `prompt_tokens`, and probes of its Messages route reported `cache_creation_input_tokens` always 0. Both are version-specific observations of that host; check them against a current capture, and keep an unlabeled top-level `cached_tokens` ambiguous.

### Reasoning Effort Changes Break Hits

At the earlier review the international Messages docs stated that changing the reasoning effort level between requests breaks prefix-cache hits. Until rechecked, audit effort/thinking settings as part of the prefix, alongside tools and system text.

### Pricing Shape

The Chinese pricing pages list Cache Write as a separate, TTL-dependent line item for the K3 series: a write is charged once when a prefix is first written at a TTL, same-TTL hits bill only at the cached-input price, and hit renewals carry no write fee. Do not describe the write fee as newly introduced or bill write tokens a second time as ordinary input. The guide claims the split itemizes write cost already inside input pricing and leaves existing requests' overall cost unchanged; attribute that claim to the Chinese guide and confirm it against the bill or billing export.

Cost per request, with one token unit and the exclusive partition above:

`ordinary_input * Pi + write * Pw(ttl) + read * Pr + output * Po`

`ordinary_input` is `total - read - write` (Messages: `input_tokens`); `Pw(ttl)` uses the write's TTL, split by the Messages breakdown, headers, or console columns. A numeric ROI needs verified rates scoped to provider, exact model/version, region, currency, deployment, and tier, with source and date; otherwise report the formula and missing inputs, per `references/economics.md`. Do not reuse guide example arithmetic or router multipliers as rates.

Break-even for an eligible prefix whose tokens are either written or read at one TTL: with `R = read / (read + write)`, `w = Pw(ttl) / Pi`, and `r = Pr / Pi`, caching saves input cost when `(1-R)*w + R*r < 1`; ordinary uncached and output terms are identical in both arms and cancel. Equality is neutral. The shortcut `R > (w-1)/(w-r)` applies only when `w > r`; otherwise use the general inequality.

### Through OpenRouter

`moonshotai/*` slugs fan out to many hosts with different cache-read prices, and only sticky routing keeps a warm prefix; router probes have shown `cached_tokens: 0` for Kimi where the direct API hits. The Chinese-platform TTL controls and write fields are not established for router hosts. Join usage with the served provider before comparing.

## Diagnostics

For decision-grade ratios, label records `provider: moonshot` and use `analyze_usage_logs.py --jsonl-normalized`. A quick check on a verified `api.moonshot.cn` Chat Completions capture (Responses: `input_tokens` / `input_tokens_details`) keeps missing fields unknown:

```python
usage = response.model_dump()["usage"]
details = usage.get("prompt_tokens_details") or {}
total = usage.get("prompt_tokens")
read = details.get("cached_tokens")  # usage.prompt_tokens_details.cached_tokens
write = details.get("cache_write_tokens")  # usage.prompt_tokens_details.cache_write_tokens
ratio = uncached = None  # absent telemetry stays unknown, never 0
if isinstance(total, int) and total > 0 and isinstance(read, int) and 0 <= read <= total:
    ratio = read / total  # quick read fraction; needs no write field
    if isinstance(write, int) and 0 <= write <= total - read:
        uncached = total - read - write  # writes are not uncached input
```

Read the historical top-level `usage.cached_tokens` only when a capture from that deployment shows it, and record that field path; with no write field, leave writes unknown rather than zero on an unverified international deployment.

If reads stay 0 on repeated calls: Messages traffic with no top-level `cache_control` or with markers only inside messages, when no earlier request wrote an eligible entry (read-only requests can hit and renew an existing entry but never populate one); a request TTL other than the warm entry's (5m and 1h caches do not interoperate); idle gap beyond the TTL; a different organization; prefix drift; effort/thinking change; host change through a router; or a legacy `/v1/caching` path. On international hosts, also check the historical 256-token rule.

## Monitoring

Track read, write (per TTL), and uncached tokens by model, host, surface, and TTL setting, plus reasoning effort, prompt/tool/schema hash, request cadence, and served provider when routed. The console's write amortization (cache-hit tokens / cache-write tokens) shows whether writes are reused. Alert on drops after model alias, TTL, effort, or host changes.
