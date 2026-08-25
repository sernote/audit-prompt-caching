# Agent Tool Stability

Use this reference for agents, coding assistants, MCP clients, compaction, mode switching, and long tool loops.

## Core Risk

Agent prompts often grow append-only, which is cache-friendly, but tool lists, mode instructions, memory blocks, and compaction can rewrite early prefix content. A shorter per-step prompt can cost more when it destroys reuse over a long trajectory.

## Dynamic-tool decision rule

Run the global Applicability Gate and economics check, then pass the allowedTools capability gate before changing the catalog:

- If the endpoint and SDK support it, send a stable catalog and change an
  allowed-list; compare prefix hashes, provider usage, catalog size,
  latency, and cached versus uncached billing.
- A direct OpenAI Responses `allowed_tools` surface and Vercel
  `providerOptions.openai.allowedTools` are different API surfaces. Verify the
  installed version, model/tool capability, final wire body, and warnings.
- Chat Completions and an arbitrary OpenAI-compatible wrapper do not inherit
  Responses behavior. Keep `activeTools` as a measured option when a smaller
  catalog has better economics for a cold or low-reuse route.

Do not call a dynamic-tool change a cache fix merely because the callable set
got smaller: validate stable `tools`/prefix hashes and provider usage per step.

## Checks

- Log per step: cache read fields, `cached_tokens`, `prefix_hash`, `tools_count`, sorted tool-name hash, output tokens, first/final token timing, actual routed provider/model.
- Compare cache drops with tool-list changes, mode changes, compaction, memory injection, or provider fallback.
- Keep route-level tool bundles stable and sorted when possible.
- Use provider-supported allowed tools, tool search, or deferred loading only after checking the endpoint, current docs, and reuse economics.
- For self-hosted inference, consider masking/constrained decoding instead of changing `tools`.
- Preserve a stable anchor: system/developer instructions, tools, schemas, first stable messages.
- Compact bulky tool results before summarizing early history; preserve paths, IDs, URLs, and small structured facts.
- Treat MCP registry changes as schema changes. Freeze or version tool definitions for a session.
- Treat provider conversation and reasoning handles as cache-relevant state. Examples include Gemini `previous_interaction_id`, Qwen `previous_response_id`, and a provider's documented thinking/reasoning continuation. Preserve them only for the same intended conversation; an opaque handle may carry user context and must be logged as a keyed hash, not as a raw identifier.

## Fresh Ungrouped Restarts Reset an Auto-Generated Cache Key

A distinct failure mode from tool-list churn: the prompt prefix is perfectly stable, yet a
restarted agent loop can still start a fresh cache lineage.

SDKs that generate a `prompt_cache_key` for the caller resolve it from a grouping hierarchy and
only fall back to a per-run value when no grouping handle is supplied. In the OpenAI Agents SDK
(Python), the resolver in `agents/run_internal/prompt_cache_key.py` and `run_grouping.py` —
private SDK internals, not a public API, and version-sensitive — resolves, in order:
`conversation_id`, `session.session_id`, `RunConfig.group_id`, then a generated per-run UUID.
`PromptCacheKeyResolver` also persists `_generated_prompt_cache_key` on `RunState`, so a resume
from `RunState` reuses the key.

Two gates decide whether an SDK-generated key exists at all. Neither is affected by
auto-generated key churn, so check both before diagnosing restarts:

- **Model opt-in.** A key is generated only for models exposing a truthy
  `_supports_default_prompt_cache_key` (again a private, version-sensitive SDK attribute). A
  custom or third-party model that does not opt in sends no generated key.
- **Caller opt-out.** If `ModelSettings.extra_args` or `ModelSettings.extra_body` already carries
  a `prompt_cache_key`, the resolver forwards that value unchanged and generates nothing. A
  caller-supplied key is stable by construction.

So the boundary is not "every `Runner.run()` mints a new key". It is a **fresh, ungrouped**
invocation — a new run carrying no reused `conversation_id`, session, `group_id`, or `RunState`.

Affected:

- continuation loops that call the runner again with `to_input_list()` and no reused
  conversation, session, or group id
- guardrail or validation recovery that rebuilds an ungrouped run instead of continuing the
  grouped one
- restarting the agent to break a repeated-tool-failure loop under the same condition

Not affected:

- re-invocations that share a `conversation_id`, `session.session_id`, or `RunConfig.group_id`
- resume from a persisted `RunState`
- models that do not opt into the SDK's default prompt cache key (no generated key is sent)
- runs that already pass a caller-supplied `prompt_cache_key` through `ModelSettings`

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
    count(requests with cached_tokens == 0) ~= count(loop re-invocations) + 1
```

The `+ 1` is the initial write. This is an observed diagnostic correlation, not an invariant. A
changed `prompt_cache_key` changes routing locality; it does not guarantee a miss, and a stable
key does not guarantee a hit. Expect the count to run high wherever another miss source is active:
cache TTL or retention expiry between requests, eviction under memory pressure, prefix drift from
tool or system-prompt edits, or hot-key locality overflow spreading traffic across replicas (see
`openai.md`). Near-equality across runs of different lengths is still strong evidence that key
lineage, not prefix drift, dominates — prefix drift produces zero-cache requests that do not track
restart counts, and it also shows up on runs with zero restarts. If the key is stable across
restarts and zero-cache requests still track them, look elsewhere (prefix drift, retention,
routing).

Observed on a long-running document-editing agent (~100 model calls per run, ~130k-token context)
whose restarts did change the effective key: zero-cache requests tracked restarts exactly across
twenty runs — 29/28, 25/24, 8/7 — and runs with no restarts showed 1 zero-cache request in 100, a
99% hit rate on the request-count metric used above. Exact agreement in that dataset is a reported
observation from one workload, not a rule to expect everywhere. Cost tracked the same axis: 24 restarts cost
2.8x a 7-restart run on identical work.

### Checks

- Log a keyed hash of the effective `prompt_cache_key` per request, not only per run, and diff the
  hashes across restarts. The diagnostic needs equality only, so use HMAC-SHA256 under a
  service-held key — never log the raw value. The key must be at least 32 bytes from a CSPRNG,
  generated for this audit, never derived from a value being digested, and never a reused
  production secret. Generated keys are derived from conversation,
  session, tenant, or user identifiers, and caller-supplied keys often are too; do not log raw
  session tokens, IDs, or user-derived key values (see `observability.md`).
- Log which grouping handle produced it: reused conversation, session, group id, `RunState`, or a
  per-run fallback. Log the handle kind, not its raw value.
- Correlate zero-cache requests with harness events (guardrail recovery, restart, resume), not only
  with prompt or tool changes.
- Treat a runner re-invocation as a cache boundary only where the effective key is observed to
  change.

### Fix

Reuse a grouping handle that spans the logical session — but match it to how the run already
manages history. Only one of the three handles is history-neutral:

- **`RunConfig.group_id`** is the handle for client-managed `to_input_list()` continuation loops.
  It is a trace-grouping id that links runs; it changes key resolution without changing where
  history comes from.
- **`session`** — reuse only on runs that are already session-managed. Do not add a session on top
  of a loop that replays `to_input_list()` history; the SDK would prepend stored history to
  history you already resent.
- **`conversation_id`** — reuse only on runs that are already server-managed, passing just the new
  turn. Do not combine it with replaying full `to_input_list()` history.
- Session persistence cannot be combined with `conversation_id`, `previous_response_id`, or
  `auto_previous_response_id` in the same run; pick one persistence strategy per call.
- A resume from a persisted `RunState` already carries the generated key, so it needs no extra
  handle.

Supply your own key only when no such handle spans the logical session.

Pick granularity deliberately: one key per session of one work item. A single route-wide constant
concentrates traffic on one key, and OpenAI documents an approximate 15 requests per minute
envelope per key before requests begin to miss (see `openai.md`). A per-request key defeats the
purpose entirely.

## Report

Classify findings as confirmed, hypotheses, or not applicable. Severity depends on hotness, trajectory length, prefix size, and measured cache/TTFT impact.
