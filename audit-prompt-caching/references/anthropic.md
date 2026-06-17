# Anthropic Prefix Cache Reference

Last reviewed: 2026-04-27. Verify official docs before exact claims about Claude model support, token minimums, pricing, Batch API, `cache_control`, TTLs, automatic caching, tool search, `defer_loading`, usage fields, ZDR, provider surfaces, or isolation.

Official sources:
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Mid-conversation system messages: https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages
- Tool use with prompt caching: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
- API reference: https://docs.anthropic.com/en/api/messages
- Pricing: https://www.anthropic.com/pricing

## Mechanics

Anthropic caching requires `cache_control`. Current docs describe:
- **Automatic caching** through top-level cache control, where Anthropic places/moves a breakpoint on the last eligible cacheable block in append-only conversations.
- **Explicit cache breakpoints** on content blocks when the stable prefix is followed by a dynamic suffix.

Prompt hierarchy is `tools -> system -> messages`; changing an earlier level invalidates downstream reuse. Cache reads search backward from the active breakpoint over a **20-block lookback** window for entries that were actually written. Writes become reusable only after the first response begins, so parallel cold fan-out can all pay prefill.

## Audit Checklist

- Both `cache_read_input_tokens` and `cache_creation_input_tokens` zero: check missing `cache_control`, below-threshold prompt, unsupported model/surface, or no eligible block.
- `cache_creation_input_tokens > 0` but reads stay zero: inspect dynamic suffix, TTL, breakpoint placement, model/region/surface, routing, or block-count distance.
- Automatic caching can write every request when the final eligible block contains changing user text, timestamp, or request context; use an explicit breakpoint at the end of the stable prefix.
- Explicit cache breakpoints belong on the last block whose full prefix should remain identical.
- For long conversations, add additional breakpoints before the active breakpoint moves more than 20 blocks past a prior write.
- Mid-conversation `{"role": "system"}` messages preserve the top-level system prefix on supported routes; at review time this was `claude-opus-4-8` only, likely expanded since.
- longer TTL entries must appear before shorter TTL entries when mixing 1h and 5m breakpoints. Syntax includes `"ttl": "1h"`.
- Thinking blocks cannot be directly marked with cache control, but thinking blocks passed back can be cached as part of surrounding content; non-tool-result user content can strip prior thinking blocks.
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
