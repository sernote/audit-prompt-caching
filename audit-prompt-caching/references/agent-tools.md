# Agent Tool Stability

Use this reference for agents, coding assistants, MCP clients, compaction, mode switching, and long tool loops.

## Core Risk

Agent prompts often grow append-only, which is cache-friendly, but tool lists, mode instructions, memory blocks, and compaction can rewrite early prefix content. A shorter per-step prompt can cost more when it destroys reuse over a long trajectory.

## Checks

- Log per step: cache read fields, `cached_tokens`, `prefix_hash`, `tools_count`, sorted tool-name hash, output tokens, first/final token timing, actual routed provider/model.
- Compare cache drops with tool-list changes, mode changes, compaction, memory injection, or provider fallback.
- Keep route-level tool bundles stable and sorted when possible.
- Use provider-supported allowed tools, tool search, or deferred loading only after checking current docs.
- For self-hosted inference, consider masking/constrained decoding instead of changing `tools`.
- Preserve a stable anchor: system/developer instructions, tools, schemas, first stable messages.
- Compact bulky tool results before summarizing early history; preserve paths, IDs, URLs, and small structured facts.
- Treat MCP registry changes as schema changes. Freeze or version tool definitions for a session.

## Report

Classify findings as confirmed, hypotheses, or not applicable. Severity depends on hotness, trajectory length, prefix size, and measured cache/TTFT impact.
