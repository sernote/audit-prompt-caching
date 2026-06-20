# Mastra Prefix Cache Reference

Last reviewed: 2026-05-26. Verify Mastra, `ai`, and `@ai-sdk/<provider>` versions before exact claims about `Agent`, `agent.generate`, `agent.stream`, `providerOptions`, Memory injection, MCP tool ordering, or ResponseCache.

Official sources:
- Agents: https://mastra.ai/reference/agents/agent
- Memory: https://mastra.ai/docs/memory/overview
- Working memory: https://mastra.ai/docs/memory/working-memory
- Semantic recall: https://mastra.ai/docs/memory/semantic-recall
- Response caching: https://mastra.ai/docs/agents/response-caching
- MCP client: https://mastra.ai/reference/tools/mcp-client

## Mechanics

Mastra wraps Vercel AI SDK; load `references/vercel-ai-sdk.md` for wire-level behavior and the provider reference for cache semantics. A single `agent.generate(...)` can include multiple model calls, so SDK rollups can hide per-call cache reads/writes.

Detect Mastra before generic AI SDK advice:

```bash
rg -n "@mastra/|new Agent\\(|agent\\.generate\\(|agent\\.stream\\(|new Memory\\(|workingMemory|semanticRecall|MCPClient|createTool\\(" .
```

## Audit Checklist

- Function-form `instructions` runs every call. Audit for `Date`, `now`, `uuid`, `randomUUID`, `runtimeContext`, `cwd`, `env`, randomized examples, user/tenant facts, or other volatile data.
- Call-site `providerOptions.anthropic.cacheControl` can land at top-level request body through AI SDK. Prefer block-level `providerOptions` on system/messages when a load-bearing breakpoint needs portability.
- Working memory injects an extra system instruction and `updateWorkingMemory` tool. Place breakpoints before memory-driven content if that state changes.
- Semantic recall is query-dependent; treat anything after its insertion point as volatile.
- Workflow steps do not share LLM prefixes except through each agent's stable `instructions + tools`.
- Freeze and sort MCP tools. Per-call `listToolsets()` or serverless reconstruction can change tool order/schema.
- ResponseCache is not prompt caching; filter response-cache hits out of prompt-cache telemetry.

## Diagnostics

Capture raw provider HTTP usage when cache numbers matter. SDK rollups can be zero, summed across multiple calls, or absent when Memory/tool continuations are involved. Track Mastra/AI SDK versions, instruction shape, memory settings, tool source, ResponseCache scope, raw `cache_read_input_tokens` / `cache_creation_input_tokens`, and `ResponseCache` hit ratio.
