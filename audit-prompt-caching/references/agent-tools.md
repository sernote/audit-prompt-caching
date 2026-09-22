# Agent Tool Stability

Use this reference for agents, coding assistants, MCP clients, compaction, mode switching, and long tool loops.

## Core Risk

Agent prompts often grow append-only, which is cache-friendly, but tool lists, mode instructions, memory blocks, and compaction can rewrite early prefix content. A shorter per-step prompt can cost more when it destroys reuse over a long trajectory.

## Checks

- Log per step: cache read fields, `cached_tokens`, `prefix_hash`, `tools_count`, sorted tool-name hash, output tokens, first/final token timing, actual routed provider/model.
- Compare cache drops with tool-list changes, mode changes, compaction, memory injection, or provider fallback.
- On GPT-6 Responses in supported single-agent mode, append a `configuration_update` input item for effort changes; changing request-level `reasoning.effort` can rewrite the hidden prefix. Preserve update items in replayed history. Keep top-level tools stable and use supported `allowed_tools`, `tool_choice: "none"`, deferred tool search, or append-only `additional_tools` for changing availability.
- On Claude Opus 5.5, a top-level `output_config.effort` change invalidates message caches; per-message effort in a mid-conversation system message can preserve the earlier prefix. Its `inline-tools-2026-09-15` beta permits a `tool_addition` block after the prefix on supported routes. Keep existing `tools` unchanged. Check model and beta support before recommending either path.
- For GPT-5.6+ OpenAI, monitor both `cached_tokens` and `cache_write_tokens`. A cache write has a 1.25× input charge, so dynamic early content can raise cost even when subsequent reads sometimes succeed.
- Keep route-level tool bundles stable and sorted when possible.
- Use provider-supported allowed tools, tool search, or deferred loading only after checking current docs.
- For self-hosted inference, consider masking/constrained decoding instead of changing `tools`.
- Preserve a stable anchor: system/developer instructions, tools, schemas, first stable messages.
- Compact bulky tool results before summarizing early history; preserve paths, IDs, URLs, and small structured facts.
- Treat MCP registry changes as schema changes. Freeze or version tool definitions for a session.

## Report

Classify findings as confirmed, hypotheses, or not applicable. Severity depends on hotness, trajectory length, prefix size, and measured cache/TTFT impact.
