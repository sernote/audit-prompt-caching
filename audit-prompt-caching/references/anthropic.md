# Anthropic Prefix Cache Reference

Last reviewed: 2026-09-22. Verify official docs before exact claims about Claude model support, token minimums, pricing, Batch API, `cache_control`, TTLs, automatic caching, tool search, `defer_loading`, usage fields, ZDR, provider surfaces, or isolation.

Official sources:
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Cache diagnostics beta: https://platform.claude.com/docs/en/build-with-claude/cache-diagnostics
- Mid-conversation system messages: https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages
- Tool use with prompt caching: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
- API reference: https://docs.anthropic.com/en/api/messages
- Pricing: https://www.anthropic.com/pricing
- Claude Opus 5.5 model and migration: https://platform.claude.com/docs/en/models/opus-5-5/overview
- Claude Opus 5.5 changes: https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5

## Mechanics

Anthropic caching requires `cache_control`. Current docs describe:
- **Automatic caching** through top-level cache control, where Anthropic places/moves a breakpoint on the last eligible cacheable block in append-only conversations.
- **Explicit cache breakpoints** on content blocks when the stable prefix is followed by a dynamic suffix.

Prompt hierarchy is `tools -> system -> messages`; changing an earlier level invalidates downstream reuse. Cache reads search backward from the active breakpoint over a **20-block lookback** window for entries that were actually written. Writes become reusable only after the first response begins, so parallel cold fan-out can all pay prefill.

For `claude-opus-5-5`, the minimum cacheable prompt is 512 tokens. The default cache TTL is 5 minutes and refreshes on a hit; a 1-hour TTL is available with `"ttl": "1h"`. The model page lists $4 ordinary input, $5 for a 5-minute write, $8 for a 1-hour write, and $0.20 for a read per million tokens. Its read multiplier is **0.05×** ordinary input, unlike the 0.1× rate on most Claude models; Claude Fable 5.1 and Mythos 5.1 use 0.025×. These are model-specific rates, not a universal Claude discount. Recheck pricing before calculations.

## Audit Checklist

- Both `cache_read_input_tokens` and `cache_creation_input_tokens` zero: check missing `cache_control`, below-threshold prompt, unsupported model/surface, or no eligible block.
- `cache_creation_input_tokens > 0` but reads stay zero: inspect dynamic suffix, TTL, breakpoint placement, model/region/surface, routing, or block-count distance.
- Automatic caching can write every request when the final eligible block contains changing user text, timestamp, or request context; use an explicit breakpoint at the end of the stable prefix.
- Explicit cache breakpoints belong on the last block whose full prefix should remain identical.
- For long conversations, add additional breakpoints before the active breakpoint moves more than 20 blocks past a prior write.
- Mid-conversation `{"role": "system"}` messages preserve the top-level system prefix on supported routes, including Opus 5.5. The current prompt-caching guide explicitly excludes Sonnet 5. Verify model and platform support before relying on this.
- A top-level `output_config.effort` change invalidates message caches. On models supporting per-message effort, put the change in a mid-conversation system message to preserve the earlier prefix. Opus 5.5 defaults to `medium`; omitting effort and setting `medium` are equivalent for cache matching.
- Opus 5.5 supports mid-conversation tool additions; with the `inline-tools-2026-09-15` beta header, a `tool_addition` block can define or change a tool after the cached prefix. This does not make top-level `tools` mutations cache-safe.
- longer TTL entries must appear before shorter TTL entries when mixing 1h and 5m breakpoints. Syntax includes `"ttl": "1h"`.
- Thinking blocks cannot be directly marked with cache control, but thinking blocks passed back can be cached as part of surrounding content. On Opus 5.5, thinking is always adaptive; preserve returned blocks unchanged in agent loops. Model switches can drop incompatible thinking blocks, and edits before a bound block can cause a 400 error on newer accounts, so keep conversation history append-only.
- workspace-level isolation applies on documented Claude API/Azure surfaces; Bedrock and Vertex can differ.

## Diagnostics

```python
usage = response.usage
read = usage.cache_read_input_tokens
created = usage.cache_creation_input_tokens
uncached = usage.input_tokens
total = read + created + uncached
```

Use the full denominator above. Track breakpoint mode, breakpoint count, TTL order, block distance, prompt/tool/schema hashes, model, provider surface, workspace, region, route, and `usage.cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` when present.

On the Claude API beta only, send `cache-diagnosis-2026-04-07` and `diagnostics.previous_message_id` on consecutive requests to compare request fingerprints. Read `response.diagnostics.cache_miss_reason` for the first model, system, tools, or messages divergence; a matching fingerprint with low `cache_read_input_tokens` points instead to an unavailable cache entry. The comparison is not a cache-hit report, can be inconclusive, and is unavailable on Bedrock and Vertex. Use usage fields to confirm reads and cost.

For cost, `usage.input_tokens` is **uncached input only** on Claude; add `cache_read_input_tokens` and `cache_creation_input_tokens` for the full input denominator. Do not apply OpenAI's inclusive `input_tokens` accounting here. For cold-path prewarming on supported requests, the current prompt-caching guide shows `max_tokens: 0` with an explicit breakpoint on the shared prefix; streaming, extended thinking, structured output, and forced tool choice are incompatible with this request. Measure writes and subsequent reads rather than assuming a warm-up pays off.
