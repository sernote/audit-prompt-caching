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

## Fresh Ungrouped Restarts Reset an Auto-Generated Cache Key

A distinct failure mode from tool-list churn: the prompt prefix is perfectly stable, yet a
restarted agent loop can still start a fresh cache lineage.

SDKs that generate a `prompt_cache_key` for the caller resolve it from a grouping hierarchy and
only fall back to a per-run value when no grouping handle is supplied. In the OpenAI Agents SDK
(Python), `agents/run_internal/prompt_cache_key.py` and `run_grouping.py` resolve, in order:
`conversation_id`, `session.session_id`, `group_id`, then a generated per-run UUID.
`PromptCacheKeyResolver` also persists `_generated_prompt_cache_key` on `RunState`, so a resume
from `RunState` reuses the key, and it opts out entirely when the request already forwards a
user-supplied key.

So the boundary is not "every `Runner.run()` mints a new key". It is a **fresh, ungrouped**
invocation — a new run carrying no reused `conversation_id`, session, `group_id`, or `RunState`.

Affected:

- continuation loops that call the runner again with `to_input_list()` and no reused
  conversation, session, or group id
- guardrail or validation recovery that rebuilds an ungrouped run instead of continuing the
  grouped one
- restarting the agent to break a repeated-tool-failure loop under the same condition

Not affected:

- re-invocations that share a `conversation_id`, `session.session_id`, or `group_id`
- resume from a persisted `RunState`

Grouping and fallback behavior here are SDK-internal, not a provider contract. Verify them against
the SDK version actually in use before relying on either branch.

Each ungrouped re-invocation re-writes the whole accumulated context. On GPT-5.6 and later, where
cache writes bill at 1.25x the uncached input rate, that is a premium re-write of the full
conversation, not a free miss.

### Diagnostic signature

First confirm the effective `prompt_cache_key` actually changes across the restarts. Only when it
does:

```text
if effective prompt_cache_key changes at each loop re-invocation:
    count(requests with cached_tokens == 0) == count(loop re-invocations) + 1
```

The `+ 1` is the initial write. An exact match across runs of different lengths is then strong
evidence that key lineage, not prefix drift, is the cause — prefix drift produces zero-cache
requests that do not line up with restart counts, and it also shows up on runs with zero restarts.
If the key is stable across restarts and zero-cache requests still track them, look elsewhere
(prefix drift, retention, routing).

Observed on a long-running document-editing agent (~100 model calls per run, ~130k-token context)
whose restarts did change the effective key: zero-cache requests tracked restarts exactly across
twenty runs — 29/28, 25/24, 8/7 — and runs with no restarts showed 1 zero-cache request in 100, a
99% hit rate on the request-count metric used above. Cost tracked the same axis: 24 restarts cost
2.8x a 7-restart run on identical work.

### Checks

- Log the effective `prompt_cache_key` per request, not only per run, and diff it across restarts.
- Log which grouping handle produced it: reused conversation, session, group id, `RunState`, or a
  per-run fallback.
- Correlate zero-cache requests with harness events (guardrail recovery, restart, resume), not only
  with prompt or tool changes.
- Treat a runner re-invocation as a cache boundary only where the effective key is observed to
  change.

### Fix

Reuse the grouping the SDK already offers: carry a stable `conversation_id`, `session`, or
`group_id` across continuations, recoveries and restarts, or resume from the persisted `RunState`.
Supply your own key only when no such handle spans the logical session.

Pick granularity deliberately: one key per session of one work item. A single route-wide constant
concentrates traffic on one key, and OpenAI documents an approximate 15 requests per minute
envelope per key before requests begin to miss (see `openai.md`). A per-request key defeats the
purpose entirely.

## Report

Classify findings as confirmed, hypotheses, or not applicable. Severity depends on hotness, trajectory length, prefix size, and measured cache/TTFT impact.
