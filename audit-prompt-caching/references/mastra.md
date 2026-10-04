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

## Released Prefix-Stability Contracts

Reviewed 2026-10-02 against the stable [`@mastra/core@1.72.0`](https://github.com/mastra-ai/mastra/releases/tag/%40mastra%2Fcore%401.72.0) tag, which ships `@mastra/core` 1.72.0 and `@mastra/memory` 1.33.0. This is a snapshot of that release, not the latest release or a guarantee for later versions. Check the resolved `@mastra/core`, `@mastra/memory`, `ai`, and `@ai-sdk/<provider>` versions and confirm each behavior in installed code. Do not assume every earlier version is defective or infer a universal first fixed release. Upstream tests use mocked models: they prove request shape, not provider hit rate, latency, savings, ROI, or causality.

Processor retry feedback ([PR #25171](https://github.com/mastra-ai/mastra/pull/25171)):

- A retry is taken only when `maxProcessorRetries` is set and the current retry count is below it; otherwise `abort(reason, { retry: true })` is treated as a plain abort. In the regular agent loop, a retry taken from `processOutputStep` appends `reason` verbatim after the history as a non-transient reactive `system-reminder` signal, not a system message ahead of the conversation. Each retry request should extend the previous one.
- Despite upstream docs listing input-step retries, the released `processInputStep` tripwire ends the step without this retry or reminder. Verify other processor phases and durable execution separately in installed code.
- Keep it non-transient. Transient signals with identical contents are deduplicated by moving the copy to the end, which rewrites the prefix on a second identical retry.
- The response message id rotates before the reminder is added and before the step rollback boundary opens. The reminder persists as a signal row in thread history; the old `[Processor Feedback]` wrapper text is gone.

ToolSearchProcessor `'context'` storage ([PR #25076](https://github.com/mastra-ai/mastra/pull/25076)):

- Active tools derive only from `loaded[]` or a `load_tool` result with `success: true` and `toolName`. Plain `search_tools` `results[].name` never activates; with the default `autoLoad: false`, only `load_tool` does. A failed single-tool `load_tool` (`success: false` with `toolName`) does not activate, but a bulk `toolNames` result still activates its `loaded[]` when partial misses make `success` false.
- `autoLoad: true` returns `loaded[]` and deliberately activates hits. Explicit loads also change tool exposure; neither mode makes the catalog universally stable.
- Threads saved with older autoLoad search results lack `loaded[]` and do not re-derive those tools after upgrade; search or load again and expect a tool-list change.

Observational Memory resource scope ([PR #24933](https://github.com/mastra-ai/mastra/pull/24933), [released docs](https://github.com/mastra-ai/mastra/blob/%40mastra%2Fcore%401.72.0/docs/src/content/en/docs/memory/observational-memory.mdx)):

- `observationalMemory.scope: 'resource'` is deprecated with a one-time warning, not removed; runtime behavior is unchanged. Threads share one observation record, so observing one thread can change other threads' early injected context and cached prefix.
- Switching to thread scope does not migrate resource-scoped observations, and messages already observed under resource scope are not observed again. Default thread scope needs a valid `threadId`.
- Continuity alternatives differ: `retrieval: true` gives an on-demand `recall` tool over other threads; resource-scoped working memory holds small durable facts every thread reads. Decide continuity before switching.

Before measured cache, latency, or ROI conclusions, capture the final rendered provider request order, prefix/tool/schema hashes, active tool names, raw per-call provider cache reads/writes, and routed provider/model and latency. Stored thread history can differ from the final wire request, so capture it even when history looks append-only.

## Diagnostics

Capture raw provider HTTP usage when cache numbers matter. SDK rollups can be zero, summed across multiple calls, or absent when Memory/tool continuations are involved. Track Mastra/AI SDK versions, instruction shape, memory settings, tool source, ResponseCache scope, raw `cache_read_input_tokens` / `cache_creation_input_tokens`, and `ResponseCache` hit ratio.
