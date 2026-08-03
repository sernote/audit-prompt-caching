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

## Harness Restarts Reset an Auto-Generated Cache Key

A distinct failure mode from tool-list churn: the prompt prefix is perfectly stable, yet every
harness-level restart of the agent loop starts a fresh cache lineage.

SDKs that generate a `prompt_cache_key` for the caller typically scope that key to **one run
invocation**, not to the logical session. The OpenAI Agents SDK (Python) states this directly in
`agents/run_internal/prompt_cache_key.py`: `PromptCacheKeyResolver` "provides one generated prompt
cache key for a runner invocation" and opts out only when the request already forwards a
user-supplied key.

Any harness that re-invokes the runner therefore mints a new key. Common causes:

- re-entering the loop after a recoverable guardrail or validation failure
- restarting the agent to break a repeated-tool-failure loop
- continuation loops that call the runner again with `to_input_list()`
- resume-after-pause flows that rebuild the run

Each re-invocation re-writes the whole accumulated context. On GPT-5.6 and later, where cache
writes bill at 1.25x the uncached input rate, that is a premium re-write of the full conversation,
not a free miss.

### Diagnostic signature

Count requests whose cache-read field is zero and compare with the number of harness restarts in
the same run:

```text
count(requests with cached_tokens == 0) == count(loop re-invocations) + 1
```

The `+ 1` is the initial write. An exact match across runs of different lengths is strong evidence
that key lineage, not prefix drift, is the cause — prefix drift produces misses that do not line up
with restart counts, and it also shows up on runs with zero restarts.

Observed on a long-running document-editing agent (~100 model calls per run, ~130k-token context):
misses tracked restarts exactly across twenty runs — 29/28, 25/24, 8/7 — and runs with no restarts
showed 1 miss in 100 requests, a 98.6% hit rate. Cost tracked the same axis: 24 restarts cost 2.8x
a 7-restart run on identical work.

### Checks

- Log the effective `prompt_cache_key` per request, not only per run, and diff it across restarts.
- Correlate zero-cache requests with harness events (guardrail recovery, restart, resume), not only
  with prompt or tool changes.
- If the key is auto-generated, treat every runner re-invocation as a cache boundary until proven
  otherwise.

### Fix

Supply your own key and scope it to the logical session rather than the invocation, so
continuations, recoveries and restarts share one cache lineage.

Pick granularity deliberately: one key per session of one work item. A single route-wide constant
concentrates traffic on one key, and OpenAI documents an approximate 15 requests per minute
envelope per key before requests begin to miss (see `openai.md`). A per-request key defeats the
purpose entirely.

## Report

Classify findings as confirmed, hypotheses, or not applicable. Severity depends on hotness, trajectory length, prefix size, and measured cache/TTFT impact.
