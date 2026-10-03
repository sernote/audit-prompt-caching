# Anthropic Prefix Cache Reference

Last reviewed: 2026-09-22. Verify official docs before exact claims about Claude model support, token minimums, pricing, Batch API, `cache_control`, TTLs, automatic caching, per-message effort, thinking block binding, tool search, `defer_loading`, usage fields, ZDR, provider surfaces, or isolation.

Official sources:
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Mid-conversation system messages: https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages
- Effort and per-message effort: https://platform.claude.com/docs/en/build-with-claude/effort
- Thinking and prompt caching: https://platform.claude.com/docs/en/build-with-claude/thinking#thinking-and-prompt-caching
- What's new in Claude Fable 5.1: https://platform.claude.com/docs/en/models/fable-5-1/whats-new-fable-5-1
- Tool use with prompt caching: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
- Cache Diagnostics beta: https://platform.claude.com/docs/en/build-with-claude/cache-diagnostics
- API reference: https://docs.anthropic.com/en/api/messages
- Pricing: https://www.anthropic.com/pricing
- Opus 5.5: https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5
- Sonnet 5.5: https://platform.claude.com/docs/en/models/sonnet-5-5/whats-new-sonnet-5-5

## Mechanics

Anthropic caching requires `cache_control`. Current docs describe:
- **Automatic caching** through top-level cache control, where Anthropic places/moves a breakpoint on the last eligible cacheable block in append-only conversations.
- **Explicit cache breakpoints** on content blocks when the stable prefix is followed by a dynamic suffix.

Prompt hierarchy is `tools -> system -> messages`; changing an earlier level invalidates downstream reuse. Cache reads search backward from the active breakpoint over a **20-block lookback** window for entries that were actually written. Writes become reusable only after the first response begins, so parallel cold fan-out can all pay prefill. The TTL is measured from the start of the request that wrote or read the entry, so a 4-minute streamed response leaves about 1 minute of the default 5-minute window for the follow-up.

## Claude 5 Family Snapshot (Fable 5.1, Mythos 5.1, Opus 5, Sonnet 5)

Verified 2026-09-11 against the pages above; re-check before quoting.

- **Minimum cacheable prompt** is model-specific: 512 tokens on Claude Fable 5.1, Claude Mythos 5.1, Claude Fable 5, Claude Mythos 5, Claude Opus 5.5, and Claude Opus 5; 1,024 on Claude Opus 4.8, Claude Sonnet 5, and Sonnet 4.6/4.5; 2,048 on Claude Opus 4.7 and Mythos Preview; 4,096 on Claude Opus 4.6/4.5 and Haiku 4.5. Below the minimum the request runs uncached with no error.
- **Cache read price** on Claude Fable 5.1 and Claude Mythos 5.1 is 0.025x base input; Claude Opus 5.5 is 0.05x; other Claude models use 0.1x. Cache writes stay 1.25x (5m) and 2x (1h). Feed current model rates into `estimate_cache_roi.py` explicitly.
- **Tokenizer**: Fable 5.1 shares the Opus 4.7+ tokenizer, roughly 30% more tokens for the same text than pre-4.7 models. Threshold and ROI math from older logs does not transfer.
- **Adaptive thinking is always on** for Fable 5/5.1 and Mythos 5/5.1; `thinking.enabled` with `budget_tokens` and `thinking.disabled` return 400. Effort is the only thinking-depth control there.
- **Thinking block binding (Fable 5.1 breaking change)**: editing anything before a Fable 5.1 thinking block (`system`, `tools`, an earlier message, an image whose bytes change) invalidates later thinking blocks; enforced (400 `The block is bound to a different conversation`) for accounts created on or after 2026-08-31, otherwise only when `thinking.block_binding.prefix_mismatch_behavior` is set. Earlier models cannot read Fable 5.1 thinking blocks; the API drops them, silently unless the `thinking-binding-controls-2026-08-01` beta reports it in `input_transformations`. A dropped block changes the cached prefix from that position onward, so a router or fallback that switches models mid-conversation is also a cache miss. Removing a leading run of thinking blocks, server-side compaction/context editing, moving `cache_control` markers, and changing `effort` between requests keep later blocks valid.
- **Mid-conversation system messages** (`{"role": "system"}` inside `messages`, no beta header) are available on Claude Fable 5.1, Mythos 5.1, Fable 5, Mythos 5, Opus 4.8, Opus 5, and Opus 5.5 on supported surfaces; not on Claude Sonnet 5, which must edit top-level `system` and restart the cache.
- **Turn-scoped system messages** (`clear_at: "next_user_message"`, beta `mid-conversation-system-clear-at-2026-08-21`) replace the inject-and-delete reminder pattern: the message is re-sent verbatim, so the prefix stays byte-identical and a cleared message costs no input tokens.
- **Mid-conversation tool changes** (`tool_addition`/`tool_removal` blocks in a system message, beta `mid-conversation-tool-changes-2026-07-01`) keep the `tools` array constant; use them instead of rewriting `tools`, which sits earliest in the prefix.
- **Forced tool use** (`tool_choice` `any`/`tool`) returns 400 on Fable 5.1 and Mythos 5.1; a `tool_choice` change is also a message-level cache miss on every model.
- **Fast mode** (`speed: "fast"`) invalidates system and message caches when toggled.

### Effort changes and the cache

The thinking configuration and the resolved effort level are rendered into the prompt. Changing top-level `output_config.effort`, `thinking.type`, or `budget_tokens` between requests always invalidates message-level breakpoints, and invalidates tool and system breakpoints too on models that render the configuration ahead of them. Setting a value explicitly to the model default (`effort: "high"`) is equivalent to omitting it and does not invalidate.

**Per-message effort (beta)** on Claude Fable 5.1, Claude Mythos 5.1, Claude Opus 5.5, Claude Opus 5, and Claude Sonnet 5.5 (see its `between_tools` limit below) keeps the cache: append `{"role": "system", "content": [], "output_config": {"effort": "<level>"}}` to `messages` and send the `mid-conversation-output-config-2026-07-01` beta header. The level applies from the next `user` turn until a later message changes it; everything before it is unchanged, so the cached prefix still matches. Check surface support before using it; Claude Code documents that the cache-preserving path does not apply on Amazon Bedrock, Google Cloud's Agent Platform, gateways, or HIPAA configurations. Models without per-message effort, including Claude Fable 5, return 400 `output_config.effort requires a model that supports per-turn effort`. Levels are `low`, `medium`, `high`, `xhigh`, `max`; `xhigh`/`max` availability is per model.

## Claude Opus 5.5 Cache Snapshot

`claude-opus-5-5` has a 512-token cache minimum and 5-minute default TTL. Current prices per million tokens: $4 ordinary input, $5 for a 5-minute write, $8 for a 1-hour write, $0.20 for a read, and $20 output. Its 0.05x read price is 60% lower than Opus 5's $0.50/MTok read price, but actual task savings depend on write/read counts and output. `usage.input_tokens` is uncached input only; add `cache_read_input_tokens` and `cache_creation_input_tokens` for the full input denominator.

Opus 5.5 defaults to `medium` effort, and setting that value explicitly is cache-equivalent to omitting it. Adaptive thinking is always on; preserve returned thinking blocks unchanged in agent loops. The `inline-tools-2026-09-15` beta lets a `tool_addition` block in a mid-conversation system message add or change a tool while keeping top-level `tools` unchanged. If the initial `tools` array has no non-deferred tool, defining the first one this way costs one full cache miss. Check beta and platform support before using this path.

Opus 5.5 binds thinking blocks to the prefix. Replaying after prefix edits returns 400 by default for accounts created from 2026-08-31. Model switches can drop unreadable blocks, breaking cache reuse.

Audit rule AP-15: a per-step effort router on a cached conversation is a repeated write-without-read pattern unless it uses per-message effort on a supported model and surface. `layout_linter.py` reports `effort_policy` and validates the message shape and model; it cannot see request headers, so confirm the beta header in the SDK call or gateway config.

## Claude Sonnet 5.5 Cache Snapshot

Verified 2026-10-02 against the Sonnet 5.5, effort, prompt caching, mid-conversation system message, and pricing pages; only this section was re-verified.

`claude-sonnet-5-5` (launched 2026-09-28) has a 512-token cache minimum, a 5-minute default TTL, and a 1-hour option. Claude Sonnet 5 lacks per-message effort, mid-conversation system messages, and mid-conversation tool changes, and keeps a 1,024-token minimum. Prices per million tokens match Sonnet 5: $2 input, $2.50 for a 5-minute write, $4 for a 1-hour write, $0.20 for a read, and $10 output. The tokenizer matches Sonnet 5; effort levels are recalibrated.

- Adaptive thinking is on by default (omitting `thinking` equals `{"type": "adaptive"}`), and effort defaults to `high` on the Claude API. Per-message effort (beta `mid-conversation-output-config-2026-07-01`) varies effort per turn without changing the cached prefix.
- `thinking: {"type": "between_tools"}` replaces `disabled` (which returns 400) and is accepted at `low`, `medium`, and `high`. With it, effort cannot change mid-conversation: a per-message `output_config.effort` that differs from the level in effect (explicit top-level effort, else `high`) returns 400; repeating that level is accepted. Use adaptive thinking to vary effort per turn. Top-level effort or thinking changes between requests still invalidate message caches.
- Mid-conversation system messages (no beta) and tool changes (`inline-tools-2026-09-15` on the Claude API; `mid-conversation-tool-changes-2026-07-01` for by-reference changes) keep `system` and `tools` unchanged. Forced tool use returns 400.
- Thinking blocks are bound to model, conversation, and account. Sonnet 5.5 reads its own blocks and those from Sonnet 5, Opus 4.8, Haiku 4.5, and earlier; the only other model that reads Sonnet 5.5 blocks is Opus 5.5 on the Claude API and Google Cloud. Unreadable blocks are dropped and the request succeeds, but the cached prefix changes from that block onward: after a model switch (the `thinking-binding-controls-2026-08-01` beta reports drops in `input_transformations`), or when sent from an unlinked account (on the Claude API and Google Cloud, the same beta lists them with `reason: "organization_binding_mismatch"`). Replaying a block after editing `system`, `tools`, or an earlier message returns 400 by default for accounts created from 2026-08-31 on the Claude API, Amazon Bedrock, and Google Cloud; to drop the affected blocks instead, use adaptive thinking with the same beta and `thinking.block_binding.prefix_mismatch_behavior: "drop_block"` (older accounts opt in to the check by setting that field). Keep history append-only.
- Available on the Claude API, Amazon Bedrock (`anthropic.claude-sonnet-5-5`; AWS lists 512 tokens, 4 checkpoints, 5m/1h TTL), Claude Platform on AWS, Google Cloud, and Microsoft Foundry. Check per-message effort and other beta support on each surface independently; Cache Diagnostics remains a Claude API beta. `layout_linter.py` applies this contract only to the exact `claude-sonnet-5-5` ID and reports `effort_policy.between_tools_effort`; it cannot see headers or the served surface.

## Audit Checklist

- Both `cache_read_input_tokens` and `cache_creation_input_tokens` zero: check missing `cache_control`, below-threshold prompt, unsupported model/surface, or no eligible block.
- `cache_creation_input_tokens > 0` but reads stay zero: inspect dynamic suffix, TTL, breakpoint placement, model/region/surface, routing, or block-count distance.
- Automatic caching can write every request when the final eligible block contains changing user text, timestamp, or request context; use an explicit breakpoint at the end of the stable prefix.
- Explicit cache breakpoints belong on the last block whose full prefix should remain identical.
- For long conversations, add additional breakpoints before the active breakpoint moves more than 20 blocks past a prior write.
- Mid-conversation `{"role": "system"}` messages preserve the top-level system prefix on supported routes (see the Claude 5 Family Snapshot and the Claude Sonnet 5.5 Cache Snapshot); Claude Sonnet 5 is excluded.
- Effort or thinking configuration changed between requests: message breakpoints miss by design (AP-15). On Fable 5.1, Mythos 5.1, Opus 5.5, Opus 5, and Sonnet 5.5 check for the per-message effort form and beta header (Sonnet 5.5 `between_tools` requires the level in effect); on other models recommend holding effort constant within a cached conversation.
- Model switch, fallback, or router mid-conversation on a Fable 5.1 or Sonnet 5.5 history: the API drops thinking blocks the target model cannot read and the prefix changes from that block onward; check `input_transformations` before blaming prompt drift.
- Fable 5.1 route with `cache_read_input_tokens` high but cost estimates off: confirm the 0.025x read multiplier and the Opus 4.7+ tokenizer before comparing with older routes.
- longer TTL entries must appear before shorter TTL entries when mixing 1h and 5m breakpoints. Syntax includes `"ttl": "1h"`.
- Thinking blocks cannot be directly marked with cache control, but thinking blocks passed back can be cached as part of surrounding content. On Opus 4.5+ and Sonnet 4.6+ thinking blocks are preserved by default and stay cached; on earlier Opus/Sonnet and all Haiku models a non-tool-result user message strips prior thinking blocks and the messages after them leave the cache.
- workspace-level isolation applies on documented Claude API/Azure surfaces; Bedrock and Vertex can differ.
- Cache Diagnostics is a Claude API beta: send `cache-diagnosis-2026-04-07` and `diagnostics.previous_message_id` on consecutive requests to identify the first model, system, tools, or messages divergence. A matching fingerprint with low `cache_read_input_tokens` points to an unavailable entry; the comparison is not a cache-hit report. Keep usage telemetry as the production source of cache ratios. Bedrock and Google Cloud do not expose this beta.
- Server tool results can cause an automatic 5-minute cache write. Do not add a redundant `cache_control` solely to cache those returned tool results; verify the tool type and current API surface first.

## Diagnostics

```python
usage = response.usage
read = usage.cache_read_input_tokens
created = usage.cache_creation_input_tokens
uncached = usage.input_tokens
total = read + created + uncached
```

Use the full denominator above. Track breakpoint mode, breakpoint count, TTL order, block distance, prompt/tool/schema hashes, model, provider surface, workspace, region, route, effort level and effort change type (top-level vs per-message), `input_transformations` drops, and `usage.cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` when present.
