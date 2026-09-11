# MiniMax Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- which MiniMax models support passive (automatic) vs explicit caching
- the 512-token minimum and TTL behavior
- cache read/write prices per model and context tier
- usage field names per SDK/API surface

Official sources:
- Automatic prompt caching: https://platform.minimax.io/docs/api-reference/text-prompt-caching
- Explicit caching (Anthropic-compatible): https://platform.minimax.io/docs/api-reference/anthropic-api-compatible-cache
- Pricing: https://platform.minimax.io/docs/guides/pricing-paygo

## Stable Mechanics

MiniMax documents two mechanisms on separate pages, and the OpenAI-compatible chat reference does not mention caching at all, so an audit that reads only the chat reference will miss it:

- **Passive (automatic) caching** for MiniMax-M3, M2.7, M2.5, and M2.1 series: applies to calls with at least 512 input tokens, TTL "adjusted based on system load", no write charge. Fields: `usage.prompt_tokens_details.cached_tokens` (OpenAI SDK) or `cache_read_input_tokens`/`cache_creation_input_tokens` (Anthropic SDK).
- **Explicit caching** on the Anthropic-compatible endpoint `https://api.minimax.io/anthropic`: `cache_control` on tools, system, message content, `tool_use`, and `tool_result`; only the most recent 4 markers count; 5-minute lifetime refreshed on hit at no extra cost. Listed for M2.7/M2.5/M2.1/M2 (M3 was not in the explicit table at the last review). Fields: `cache_creation_input_tokens`, `cache_read_input_tokens`, and `input_tokens` for tokens neither read nor written (additive).

## Provider Checks

- Label usage records `provider: minimax` so `analyze_usage_logs.py` applies inclusive semantics to the OpenAI shape and additive semantics to the Anthropic shape.
- Do not gate cache handling on `"claude" in model`: MiniMax accepts Anthropic `cache_control` and is silently excluded by such checks in several agent frameworks.
- Pricing tiers matter: at the last review M3 cost $0.30 input / $0.06 cache read per MTok up to 512k context and double above it (cache reads included), a Priority tier at 1.5x, and M2.7 listed explicit writes at 1.25x; M3 had no published write price. Read the model row before estimating.
- Through OpenRouter, `minimax/*` endpoints publish `input_cache_read` but OpenRouter's caching table omits MiniMax; router probes have shown hits surviving, but treat router-level behavior as unverified per host.

## Diagnostics

Compare `cached_tokens` (or `cache_read_input_tokens`) against the 512-token minimum, marker count and placement (last 4 only), the 5-minute refresh window, model series, and endpoint. Writes without reads on the explicit route point to dynamic content before a marker or an idle gap over 5 minutes.

## Monitoring

Track cached/read tokens by model, endpoint, and context tier; marker count per request; prompt/tool/schema hash; cadence vs 5 minutes. Alert on drops after a model series or endpoint switch.
