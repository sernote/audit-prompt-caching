# Agent Tool Strategy

Use this reference when auditing agents, coding assistants, MCP clients, dynamic tool selection, mode switching, or context compaction.

## Core Rule

Do not optimize one agent step in isolation. In long trajectories, stable early tokens can matter more than reducing the current request by a few tool definitions.

Before changing tool strategy, estimate the cost of a late-step cache miss:

```text
late_step_miss_cost ~= late_input_tokens * uncached_input_price
late_step_hit_cost  ~= late_input_tokens * cached_input_price
```

Use provider docs for current prices and cache semantics. For self-hosted inference, translate miss cost into prefill compute, TTFT, and throughput.

## Strategy Table

| Situation | Prefer | Watchouts |
|---|---|---|
| Up to 10 compact tools | stable full tool list | sort tools and schema keys |
| 10-50 tools, self-hosted decoding control | stable tools + masking/constrained decoding | mask only at tool-name selection positions |
| Many tools, managed API | provider-supported `allowed_tools`, `tool_search`, or deferred loading | verify current provider semantics before claiming cache safety |
| Independent product domains | route before the agent loop to fixed tool bundles | define fallback for cross-domain tasks |
| Prototype, short agent, cheap model | dynamic tool selection can be acceptable | keep monitoring so it does not ship unnoticed into long trajectories |
| Per-step RAG over tool docs | avoid if it rewrites early `tools` | safe only when retrieved tools are appended or provider-supported |

## Dynamic Tool Selection Smell

Symptoms:
- `tools_count` changes on most steps
- `prefix_hash` changes when tool set changes
- raw prompt tokens decreased but total cost or TTFT increased
- the agent has 15+ steps or high input/output ratio
- tool calls in history refer to tools that later disappear

Safer alternatives:
- stable compact tool list sorted by name
- route-level fixed tool bundles selected before the agent loop
- provider-supported allowed tools separate from the full tool list
- provider-supported tool search or deferred loading
- self-hosted masking/constrained decoding

Do not move tool definitions into user messages as a cache workaround unless current provider docs explicitly support the pattern.

## Mode Switching

Plan/debug/read-only modes should not swap the base system prompt or rewrite the tool list.

Safer patterns:
- keep base instructions stable
- express mode state in a later message or supported metadata
- add mode-enter/mode-exit tools when that preserves the stable prefix
- use allowed-tools or masking for dynamic permissions

Audit for:
- `PLAN_SYSTEM_PROMPT`, `DEBUG_SYSTEM_PROMPT`, or role-specific system replacements
- read-only mode implemented by removing write tools from `tools`
- injected `cwd`, `platform`, date, git status, run IDs, or trace IDs before the cacheable prefix

## History And Compaction

Use this ladder:

1. Raw append-only history while it fits.
2. Compact bulky tool results while preserving paths, IDs, URLs, checksums, and small structured facts.
3. Summarize only when compaction is insufficient.

Preserve:
- `system`
- tool definitions or provider-supported tool references
- first stable user/assistant messages
- route and mode identity if stable

Avoid:
- replacing early turns with a summary
- mutating previous tool calls
- deleting evidence needed by later tool calls
- treating summarization as a free cache optimization

If the stable anchor alone exceeds the context budget, fail closed or split the route/tool bundle instead of silently dropping it.

## Required Agent Logs

Log per step:
- provider cache read field, such as `cached_tokens` or `cache_read_input_tokens`
- cache creation/write field when available
- `prefix_hash`
- `tools_count`
- sorted tool-name hash
- prompt version and route
- mode state
- compaction event and compaction strategy
- TTFT/prefill latency

Alert when:
- prefix hash changes unexpectedly
- cached tokens reset after tool selection or compaction
- tool count changes inside a long trajectory
- TTFT rises on late steps

## Synthetic Agent Eval

Add a 3-5 step smoke test:

1. Render step 1 with full stable system/tools.
2. Append a tool call and result.
3. Render step 2 and confirm the stable prefix hash did not change.
4. Trigger mode switch or compaction and confirm only allowed late content changes.
5. Fail when dynamic tool retrieval, framework metadata, or early summarization mutates the stable prefix.
