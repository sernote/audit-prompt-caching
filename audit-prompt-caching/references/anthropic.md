# Anthropic Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-27.

Verify before exact claims:
- supported Claude models and model aliases
- minimum cacheable token counts by model
- cache write/read pricing, Batch API interactions, and TTL premiums
- `cache_control` syntax, limits, provider availability, and TTL ordering
- automatic caching support by surface: Claude API, Azure AI Foundry, Amazon Bedrock, Google Vertex AI, and managed routers
- tool search / `defer_loading` behavior
- usage object fields and streaming event fields
- data retention, ZDR, and cache isolation boundaries

Official sources:
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Tool use: https://platform.claude.com/docs/en/build-with-claude/tool-use
- Tool use with prompt caching: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
- Pricing: https://www.anthropic.com/pricing
- API reference: https://docs.anthropic.com/en/api/messages

## Stable Mechanics

Anthropic prompt caching is enabled with `cache_control`. Current docs describe two ways to place it:

- **Automatic caching**: add a single top-level `cache_control` field to the request. Anthropic applies a cache breakpoint to the last eligible cacheable block and moves that breakpoint forward as an append-only conversation grows.
- **Explicit cache breakpoints**: place `cache_control` on individual content blocks when the audit needs exact control over which prefix is cached.

Anthropic treats the prompt prefix hierarchy as:

```text
tools -> system -> messages
```

Changing an earlier level invalidates cache reuse for downstream levels. A tool definition change can invalidate system and message reuse; a system change can invalidate message reuse.

Cache writes happen only at the selected breakpoint. A write creates one cache entry for the full prefix ending at that block; it does not create independent entries for earlier stable blocks.

Cache reads use a backward search from the breakpoint. If there is no exact hit at the breakpoint, Anthropic walks backward over a **20-block lookback** window for entries that previous requests already wrote. The lookback finds prior writes, not merely stable content behind a changing breakpoint.

Cache entries become reusable only after the first response begins. This matters for parallel fan-out.

## Provider Checks

### Missing cache_control

If `cache_read_input_tokens` and `cache_creation_input_tokens` are both zero, first check whether the request has top-level or block-level `cache_control`. Also verify the prompt reaches the current model's minimum cacheable length; below-threshold caching failures are silent.

### Automatic caching

Prefer automatic caching for append-only multi-turn conversations where the final eligible block moves forward and earlier blocks do not change. It is the simplest path when each turn adds fewer than 20 blocks and the conversation continues within TTL.

Automatic caching can be wrong for a static prefix plus dynamic suffix. If the last eligible block contains a timestamp, per-request context, user-specific data, or the incoming user query, the system may write a new cache entry every request and never read it. In that layout, use an explicit breakpoint at the end of the stable prefix instead.

When combining automatic caching with explicit breakpoints, remember that automatic caching uses one of the available breakpoint slots. If all slots are already used, the API can reject the request.

### Explicit cache breakpoints

Use explicit breakpoints when different sections change at different frequencies, or when the prompt has a stable prefix followed by a dynamic suffix. Place `cache_control` on the last block whose full prefix should remain identical across the requests that should share a cache.

For long growing conversations, add additional breakpoints before they are needed if the active breakpoint can move more than 20 blocks beyond the most recent prior write. A later breakpoint cannot recover an entry that was never written in its lookback window.

### Tool Cascade

Tools sit before system/messages. Keep tool definitions stable and deterministic. Sort tool lists and schema keys where the SDK or language can vary output order. If a dynamic tool subset is needed, verify current Anthropic mechanisms such as allowed tools, tool search, or deferred loading before changing the `tools` array per step.

### TTL And Traffic Shape

Default prompt caching uses a short ephemeral TTL. Use extended 1-hour caching only when cadence, latency, or rate-limit needs justify the higher write cost. The request syntax is:

```json
{ "cache_control": { "type": "ephemeral", "ttl": "1h" } }
```

When mixing TTLs, longer TTL entries must appear before shorter TTL entries. In practical audits, check for 1-hour breakpoints before 5-minute breakpoints and inspect write/read usage by TTL when `usage.cache_creation` is present.

### Parallel Requests

Avoid launching many same-prefix requests before one cache-creating request has started generating. For parallel fan-out, a safe warm-up can create the entry first; if no safe warm-up exists, document the cold-cache cost.

### Thinking, Tool Choice, Web Search

Current docs distinguish direct cache targets from blocks that are cached only as part of surrounding content:

- thinking blocks cannot be directly marked with `cache_control`, but previous assistant thinking blocks can be cached as part of request content when they are passed back, and they count as input tokens when read from cache
- non-tool-result user content in extended-thinking flows can strip previous thinking blocks from context and invalidate message-cache assumptions
- empty text blocks cannot be cached
- sub-content blocks such as citations cannot be directly cached; cache the top-level document block instead

Changing tool definitions, web search, citations, speed settings, tool choice, images, or thinking parameters can affect different levels of cache reuse. Check current docs before making exact invalidation claims for a specific request surface.

### Cache Storage And Isolation

Prompt caching is ZDR eligible when the organization has the relevant arrangement. Do not treat caching as response caching: cached KV/hash representations affect prompt processing, not output generation.

As documented for the current Claude API, workspace-level isolation applies to prompt caches for Claude API and Azure AI Foundry preview. Amazon Bedrock and Google Vertex AI can have different cache isolation behavior. In audits, record workspace, organization, region, provider surface, and routing layer before treating cross-user or cross-workspace misses as bugs.

## Diagnostics

Inspect:

```python
usage = response.usage
cache_read = usage.cache_read_input_tokens
cache_creation = usage.cache_creation_input_tokens
uncached = usage.input_tokens
total = cache_read + cache_creation + uncached
ratio = cache_read / total if total else 0
```

Interpretation:
- `cache_creation > 0` and `cache_read == 0`: cache is being written but not reused yet, expired, routed differently, below a useful cadence, or the prefix/breakpoint is changing.
- both zero: likely missing `cache_control`, prompt below the model threshold, no eligible cacheable block, unsupported request surface, or caching skipped by automatic selection.
- creation spikes after deploy: prompt, tools, system content, model settings, route, breakpoint placement, or TTL changed.
- `input_tokens` is only the uncached portion after the last breakpoint for Anthropic-style usage; do not treat it as total input.

When TTL detail is available, inspect:

```python
creation = getattr(usage, "cache_creation", None)
ephemeral_5m = getattr(creation, "ephemeral_5m_input_tokens", 0) if creation else 0
ephemeral_1h = getattr(creation, "ephemeral_1h_input_tokens", 0) if creation else 0
```

`cache_creation_input_tokens` should match the sum of detailed cache-creation token buckets when those details are present.

## Monitoring

Track:
- `cache_read_input_tokens`
- `cache_creation_input_tokens`
- `input_tokens`
- `usage.cache_creation.ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens` when present
- breakpoint mode: automatic top-level vs explicit block-level
- breakpoint count and TTL order
- prompt/tool/schema hash
- final cacheable block hash and stable-prefix hash
- prompt block count between the current breakpoint and prior writes
- model, provider surface, workspace, region, and route
- TTL choice and request cadence
- thinking/tool/web-search/citations/speed/image settings when present

Use the full denominator: `cache_read + cache_creation + input_tokens`. Counting only `input_tokens` can overstate hit rate.
