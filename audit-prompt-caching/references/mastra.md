# Mastra Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-05-26.

Verify before exact claims:
- `Agent` constructor option shape for `instructions`, `tools`, `memory`, `model`
- `agent.generate(...)` / `agent.stream(...)` option shape, especially `providerOptions` carry-over
- `@mastra/memory` injection behavior: working memory placement, semantic recall position, `lastMessages` window
- `MCPClient.listTools()` ordering guarantees and `toolsets` dynamic loading shape
- `ResponseCache` processor scope semantics (`scope: null` vs per-user `MASTRA_RESOURCE_ID_KEY`)
- which `ai` and `@ai-sdk/<provider>` majors the installed `@mastra/core` actually depends on

Official sources:
- Agents reference: https://mastra.ai/reference/agents/agent
- Memory overview: https://mastra.ai/docs/memory/overview
- Working memory: https://mastra.ai/docs/memory/working-memory
- Semantic recall: https://mastra.ai/docs/memory/semantic-recall
- Response caching: https://mastra.ai/docs/agents/response-caching
- MCP client reference: https://mastra.ai/reference/tools/mcp-client
- Provider options pattern (Anthropic example): https://mastra.ai/docs/models/providers/anthropic

## Stable Mechanics

Mastra is layered on Vercel AI SDK; load `references/vercel-ai-sdk.md` for the wire-level cache mechanics and provider behavior. Mastra adds Agent, Memory, Workflow, and ResponseCache surfaces that independently affect prefix stability and telemetry.

`Agent.generate(...)` and `Agent.stream(...)` return AI SDK result objects (`GenerateTextResult`, `StreamTextResult`). Mastra's agent loop can call the model multiple times per `generate` (initial → tool result → continuation), so the SDK-level rollup of cache fields is a sum across internal HTTP calls, not a per-request value.

## Provider Checks

### Detect Mastra Before Generic Vercel AI SDK

Mastra wraps the AI SDK but introduces its own surfaces (`Agent`, `Memory`, `Workflow`, `createTool`, `MCPClient`) that the AI SDK reference does not cover. Detection signals:

```bash
rg -n "@mastra/|from ['\"]@mastra|new Agent\(|Agent\(\{|agent\.generate\(|agent\.stream\(|new Memory\(|workingMemory|semanticRecall|MCPClient|createTool\(|createWorkflow\(" .
```

If present, load this reference and `references/vercel-ai-sdk.md` together; the underlying provider reference is still required for wire-level cache mechanics.

### instructions Is Re-Evaluated When It Is A Function

`Agent.instructions` accepts a string, an array of system messages, or a function `({ runtimeContext, mastra }) => string | SystemMessage[]`. Function form runs on every `generate()` / `stream()` call.

Deterministic functions produce byte-stable wire payloads; cache still works. The audit risk is volatile content interpolated into the function body. Worst-case failure shape:

```ts
new Agent({
  instructions: () => `Current time: ${new Date().toISOString()}\n\n${STATIC_BASE}`,
  model,
})
```

With `providerOptions.anthropic.cacheControl` on `agent.generate(...)`, both calls write a new cache entry (`cache_creation_input_tokens > 0`) and neither reads (`cache_read_input_tokens == 0`). Net cost: input plus the 1.25× cache-write premium on every call, zero savings.

Audit grep:

```bash
rg -n "instructions\s*:\s*\(|instructions\s*:\s*async\s*\(|tools\s*:\s*\(\s*\{|runtimeContext" .
```

For every function-form `instructions` or `tools`, follow the value chain and confirm the returned text does not interpolate `Date`, `now`, `uuid`, `randomUUID`, `runtimeContext.user.*`, `cwd`, `env`, or randomized few-shot selections. Move volatile content into a user-role message and keep `instructions` static.

### agent.generate({ providerOptions }) Lands At The Top Of The Wire Body

Cache directives are configured in user code via `providerOptions`. The auditable question is where AI SDK puts that directive on the wire after Mastra forwards it. When `providerOptions` is passed at the call site (not on the `instructions` object), the directive ends up at the top level of the Anthropic request body, not on a specific block.

User code:

```ts
agent.generate(USER_QUERY, {
  providerOptions: { anthropic: { cacheControl: { type: 'ephemeral' } } },
});
```

Resulting wire body sent to `https://api.anthropic.com/v1/messages` (captured via a logging `fetch`):

```json
{
  "model": "claude-sonnet-4-5",
  "max_tokens": 64000,
  "cache_control": { "type": "ephemeral" },
  "system": [{ "type": "text", "text": "..." }],
  "messages": [...],
  "tools": [{ "name": "...", ... }]
}
```

Top-level `cache_control` is not in the public Anthropic API spec. Anthropic accepts it and the cache engages. Auditable consequences:

- precise per-block anchoring (cache up to a specific message, cache only `tools`, etc.) is not reachable through Mastra's call-site shortcut
- a future Anthropic API tightening or an AI SDK rewrite can disable the shortcut without an error
- the instruction-level pattern is the portable form — `providerOptions` placed on the `instructions` object so AI SDK serializes it onto the system block:

```ts
new Agent({
  instructions: {
    role: 'system',
    content: STABLE_BASE,
    providerOptions: { anthropic: { cacheControl: { type: 'ephemeral' } } },
  },
  model,
});
```

For agents with both static and dynamic system content, use an array of system messages and place the breakpoint on the last static one.

### Memory({ workingMemory: { enabled: true } }) Injects Extra Prefix Content

Enabling working memory adds two things to every `agent.generate(...)` request, on the first turn, without explicit caller code:

1. a second system block whose text starts `WORKING_MEMORY_SYSTEM_INSTRUCTION:` (~2,100 chars)
2. an `updateWorkingMemory` tool prepended to the `tools` array

Wire shape:

```text
system[0] = the caller's `instructions` text
system[1] = "WORKING_MEMORY_SYSTEM_INSTRUCTION:\n..." (Mastra-injected)
tools     = [updateWorkingMemory, ...the caller's tools]
messages  = ... (grows between turns; tool_use + tool_result accumulate)
```

The injected system text and tool definition are byte-stable while no working memory has been written yet. After `updateWorkingMemory` runs, the stored state becomes part of the working-memory system content on subsequent calls. Place the Anthropic breakpoint on the caller's `instructions` system block — before any memory-driven content — so it survives state updates.

### Semantic Recall Position Is Not Documented

`semanticRecall` retrieves past messages by vector search per query. Where the retrieved set lands in `messages[]` is not specified in the public docs. The retrieved content changes per query, so anything after the semantic-recall insertion point is volatile by design. Cache breakpoints placed after semantic recall do not produce reuse — place the breakpoint on the last system block before any memory injection runs.

### Workflow Steps Do Not Share LLM Prefix

`createWorkflow` / `createStep` issue independent LLM calls. There is no shared prompt prefix between two steps that call different agents, and no automatic prefix sharing between sibling steps that call the same agent. Reuse comes only from each individual agent's stable `instructions + tools` across many calls.

### MCP Tools

`MCPClient.listTools()` at agent construction is cache-friendly when the result is frozen for the agent's lifetime. The per-call alternative — `toolsets: await mcp.listToolsets()` passed into `generate()`/`stream()` — fetches tools on every call and invalidates the tools block. In serverless deployments where the `Agent` is reconstructed per request, `listTools()` also runs per request and can return different schemas if the MCP server changed. Tool ordering from `MCPClient.listTools()` is not documented as deterministic — sort by name in the agent definition if cross-deploy stability matters.

### ResponseCache Is Not Prompt Caching

The `ResponseCache` processor skips the model entirely on hit and returns the previous response. It is keyed on `{agentId, scope, model, prompt, stepNumber}`, not on prompt prefix bytes. A `ResponseCache` hit has no `providerMetadata` because no LLM call happened. Do not measure prompt-cache effectiveness over a population that includes `ResponseCache` hits; filter them out first.

## Diagnostics

The SDK rollup at `result.providerMetadata.anthropic.cacheReadInputTokens` is not a reliable per-request value inside Mastra's agent loop. Common mismatches:

- single `generate` that internally made one HTTP call but the rollup reports 0 while raw `cache_read_input_tokens` in the response body is large (telemetry lost in some Memory-enabled paths)
- single `generate` that internally made multiple HTTP calls and the rollup reports a sum larger than any single wire response (the rollup adds reads across the tool-call → continuation hop)

For accurate per-request numbers, wrap the model provider's `fetch` (see `references/vercel-ai-sdk.md` § Diagnostics) and read raw `usage.cache_read_input_tokens` from each HTTP response body. The SDK rollup is acceptable for "is the cache working at all" sanity checks.

Symptom → first check:

- function-form `instructions` and high cache-write spend, low cache-read: grep the function body for `Date`, `now`, `uuid`, `runtimeContext`, `random`
- working memory enabled and `cache_read_input_tokens` drops after `updateWorkingMemory` is called for the first time in a thread: confirm the breakpoint sits on the caller's `instructions` system block, not after the working-memory injection point
- `result.providerMetadata` shows fewer cached tokens than the bill suggests: cross-check against raw HTTP usage; the rollup is unreliable in multi-step `generate`

## Monitoring

Track per agent and per route:
- `@mastra/core`, `@mastra/memory`, `@mastra/ai-sdk`, `ai`, and `@ai-sdk/<provider>` versions
- `instructions` shape (string / array / function) — flag function form for review
- `memory` enabled: `workingMemory`, `semanticRecall`, `lastMessages.windowSize`
- `tools` source: static, MCP `listTools`, MCP `listToolsets`
- presence of `ResponseCache` processor and its `scope`
- per-call wire body capture for the first request in a session: confirm `cache_control` location, system block count, tools count, and tool ordering
- raw provider `cache_read_input_tokens` / `cache_creation_input_tokens` from the wire, not the SDK rollup
- ratio of `agent.generate(...)` calls that engaged `ResponseCache` vs hit the model (so prompt-cache metrics are computed over the right denominator)
