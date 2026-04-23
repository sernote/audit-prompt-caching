# Anthropic Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- supported Claude models
- minimum cacheable token counts by model
- cache write/read pricing and TTL premiums
- beta headers and syntax for extended TTL
- `cache_control` limits and block behavior
- tool search / `defer_loading` behavior
- usage object fields

Official sources:
- Prompt caching: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- Tool use: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview
- Tool reference / tool search / deferred loading: https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/tool-reference
- Pricing: https://www.anthropic.com/pricing
- API reference: https://docs.anthropic.com/en/api/messages

## Stable Mechanics

Anthropic prompt caching is explicit. Mark cacheable content with `cache_control`; otherwise do not assume caching is active.

Anthropic treats the prompt prefix hierarchy as:

```text
tools -> system -> messages
```

Changing an earlier level invalidates cache reuse for downstream levels. A tool change can invalidate system and message reuse; a system change can invalidate message reuse.

Cache entries become reusable only after the first response begins. This matters for parallel fan-out.

## Provider Checks

### Missing Or Misplaced cache_control

Confirm cache breakpoints are placed after reusable static content. Do not mark dynamic per-request content as cacheable unless reuse is intentional.

### Tool Cascade

Tools sit before system/messages. Keep tool definitions stable and deterministic. If a dynamic tool subset is needed, verify current Anthropic mechanisms such as tool search or deferred loading before changing the tools array per step.

### Parallel Requests

Avoid launching many same-prefix requests before one cache-creating request has started generating.

### TTL And Traffic Shape

Compare TTL with actual request cadence. Sparse traffic can repeatedly pay cache writes without enough reads. Verify current 5-minute/1-hour behavior and pricing before recommending a TTL.

### Thinking, Tool Choice, Web Search

Changing thinking/tool/search settings can affect cache reuse. Check current docs for invalidation behavior before making exact claims.

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
- `cache_creation > 0` and `cache_read == 0`: cache is being written but not reused yet, expired, or prefix changed.
- both zero: likely missing `cache_control`, prompt below threshold, or unsupported path.
- creation spikes after deploy: prompt/tool/system changed.

## Monitoring

Track:
- `cache_read_input_tokens`
- `cache_creation_input_tokens`
- `input_tokens`
- cache creation details when available
- prompt/tool/schema hash
- TTL choice and request cadence

Use the full denominator: `cache_read + cache_creation + input_tokens`. Counting only `input_tokens` can overstate hit rate.
