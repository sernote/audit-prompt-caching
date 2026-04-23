---
name: audit-prompt-caching
description: >
  Use when LLM prefix/prompt caching, cached_tokens/cache read fields, cache hit
  rate, TTFT, prefill latency, KV cache reuse, prompt cost, tool/schema prompt
  stability, OpenRouter routing, Bedrock cache checkpoints, agent tool routing,
  context compaction, vLLM/SGLang deployment, or multi-replica LLM routing may
  affect behavior, latency, or inference cost.
---

# Prompt Cache Audit

Diagnose and fix LLM prompt/prefix cache misses. Treat caching as an engineering property of the request path: stable prefix, cache-aware routing, and cache entries that live long enough to be reused.

## Modes

- **Code audit**: inspect prompt construction, tool/schema serialization, history management, provider calls, routing, and engine config. Propose focused diffs and verify them.
- **Advisory**: if no codebase is available, ask targeted diagnostic questions and give provider-checked recommendations.
- **Agent audit**: when tools, tool routing, MCP, agent loops, compaction, or multi-step trajectories are present, always run the agent-specific checks.
- **Deployment audit**: when vLLM/SGLang, Kubernetes, Docker Compose, gateways, or multiple inference replicas are present, inspect routing and KV-cache capacity as first-class causes.

## Use-Case Map

Classify the work before auditing so you inspect the right artifacts. For a deeper role/artifact matrix, load `references/use-cases.md`.

| Scenario | Common triggers | Inspect first |
|---|---|---|
| Cost or migration audit | bill increased, provider comparison, cache discount not visible | usage logs, billing export, static/dynamic/output token estimates, provider reference |
| Prompt/code audit | `cached_tokens=0`, prompt builder changed, schema drift | prompt renderers, SDK calls, `tools`, `response_format`, JSON/schema serialization |
| Mechanics/latency audit | cache hit did not reduce cost/latency, decode dominates, unclear prefill vs output | `references/mechanics.md`, token/TTFT traces, output length, streaming timestamps |
| Managed-router audit | OpenRouter cache writes without reads, provider fallback, sticky routing, `openrouter/auto` | OpenRouter request body, `provider` routing fields, model(s), plugins, usage metadata |
| Agent/coding-assistant audit | agent got more expensive, dynamic tools, MCP routing, compaction | agent loop, tool registry, tool selection, history compaction, per-step cache logs |
| Deployment audit | vLLM/SGLang cache misses, TTFT after scaling, multi-replica routing | `docker-compose.yml`, Helm values, Kubernetes manifests, gateway config, engine flags |
| Observability/CI audit | need cache dashboard, release guardrail, prefix smoke test | traces, dashboards, rendered prompt snapshots, prefix/tool/schema hashes |

## Scenario References

Load only the reference needed for the detected scenario:

- **Cost or migration**: `references/economics.md` for effective-cost variables, output-share checks, TTL/write-premium break-even, and migration cache risk.
- **Mechanics, latency, or self-hosted compute**: `references/mechanics.md` for prefill vs decode, KV reuse, and what cache hits can and cannot improve.
- **Release, incident, deploy, or monitoring**: `references/predeploy-checklist.md` for blocking checks, triage order, and observability dimensions.
- **OpenRouter or managed provider routing**: `references/openrouter.md` for sticky routing, provider fallback/order, cache usage fields, and provider-specific cache controls through OpenRouter.
- **Agents, coding assistants, MCP, or dynamic tools**: `references/agent-tools.md` for tool strategy selection, mode switching, and context compaction.
- **Self-hosted SGLang**: `references/sglang.md` for RadixAttention, SGLang router, HiCache, tokenizer/chat-template drift, and cache-aware deployment checks.

## Freshness Gate

Provider facts are volatile. Before making exact provider claims, open the relevant provider reference and verify its official sources when browsing is available.

Verify before exact claims about:
- pricing, cache discounts, storage charges, or write premiums
- current model names, support matrices, and availability by region
- minimum cacheable tokens, cache granularity, TTL, and retention
- usage field names and API parameters
- tool-search, allowed-tools, defer-loading, or cache-control semantics

If official docs cannot be checked, say the provider facts are unverified and avoid exact numbers. Use bundled references as heuristics, not current truth. Never copy prices or model names from articles/posts as current facts.

## Provider Detection

Search SDK imports, API base URLs, model names, deployment manifests, and config files. For self-hosted deployments, also search `docker-compose.yml`, `Dockerfile`, Helm values, Kubernetes `Deployment`/`Service`/`Ingress`, gateway config, and engine CLI flags.

| Signal | Provider/engine | Load |
|---|---|---|
| `openrouter`, `openrouter.ai/api/v1`, `OPENROUTER_API_KEY`, `@openrouter/sdk`, `OpenRouter`, `openrouter/auto` | OpenRouter | `references/openrouter.md` |
| `AzureOpenAI`, `AZURE_OPENAI_ENDPOINT`, `azure.ai.openai`, `api-version`, Azure OpenAI endpoint URLs | Azure OpenAI | `references/azure-openai.md` |
| `openai`, `responses.create`, `chat.completions`, `prompt_cache_key` | OpenAI | `references/openai.md` |
| `bedrock-runtime`, `BedrockRuntime`, `boto3.client("bedrock-runtime")`, `client.converse`, `converse_stream`, `InvokeModelCommand`, `ConverseCommand`, `invoke_model`, `cachePoint`, `CacheReadInputTokens`, `CacheWriteInputTokens` | Amazon Bedrock | `references/bedrock.md` |
| `anthropic`, `messages.create`, `cache_control` | Anthropic | `references/anthropic.md` |
| `vllm`, `--enable-prefix-caching`, `AsyncLLMEngine`, `LLM(` | vLLM | `references/vllm.md` |
| `sglang`, `sglang_router`, `RadixAttention`, `--disable-radix-cache`, `HiCache` | SGLang | `references/sglang.md` |
| `deepseek`, `api.deepseek.com`, `prompt_cache_hit_tokens` | DeepSeek | `references/deepseek.md` |
| `google.genai`, `google.generativeai`, `vertexai`, `CachedContent` | Gemini | `references/gemini.md` |
| `dashscope`, `qwen`, `bailian`, `aliyun` | Qwen/DashScope | `references/qwen.md` |
| `yandexgpt`, `foundationModels`, `llm.api.cloud.yandex.net` | YandexGPT | `references/yandexgpt.md` |
| `z.ai`, `zai`, `glm-`, `api.z.ai` | z.ai | `references/zai.md` |

Load only the relevant provider files. If OpenRouter, Azure, or Bedrock signals appear alongside OpenAI/Anthropic-compatible calls, prefer the router/provider wrapper reference over the generic direct-provider reference. If detection is ambiguous, ask which provider/engine is in use.

## Audit Flow

1. Detect mode, provider, and use-case scenario.
2. Load the relevant scenario reference and provider reference; do not load unrelated references.
3. Apply the Freshness Gate for provider-specific facts.
4. Measure the symptom: cache ratio, TTFT/prefill latency, output/decode time, cache writes vs reads, and whether the drop correlates with deploys, SDK changes, prompt changes, replica count, or agent steps.
5. Scan universal anti-patterns below.
6. If an agent loop or tools are present, run the Agent Tool Stability checks.
7. Apply provider-specific checks from the loaded reference.
8. Report findings with evidence, severity, and concrete verification steps.
9. When making code changes, verify prefix stability before claiming success.

## Severity

Assign severity from impact and evidence, not from the anti-pattern name alone:

- **Critical**: confirmed metric drop or cache miss on a large shared prefix, expensive model, high traffic, long agent trajectory, or multi-replica production path.
- **Strong**: likely cache killer found in a hot path but metrics are incomplete.
- **Moderate**: pattern can fragment cache but impact depends on traffic shape.
- **Low**: defensive cleanup or monitoring improvement.

## Universal Anti-Patterns

### AP-1: Volatile Data In Prefix

Dynamic values near the beginning make every request unique.

Search for: `datetime`, `time`, `uuid`, `session_id`, `request_id`, `trace_id`, `run_id`, `user.name`, `user_id`, `tenant`, `company`, `cwd`, `git status`, `platform` in system prompts, tool schemas, or early messages.

Fix:

```python
# bad
system = f"Today: {datetime.now()}. You help {user.name}. {BASE_PROMPT}"

# good
system = BASE_PROMPT
user_msg = f"[ctx: time={datetime.now()}, user={user.name}] {query}"
```

Verify: render the cacheable prefix for multiple users/timestamps and confirm its fingerprint does not change.

### AP-2: Non-Deterministic Tools, Schemas, Or Serialization

Tool definitions, JSON schemas, or structured-output formats change order or include dynamic constants.

Search for: `json.dumps` without `sort_keys=True`, dict/set-derived tool lists, registry iteration without sorting, dynamic `requestId` or timestamps in `response_format` / JSON schema.

Fix:

```python
tools = sorted(registry.values(), key=lambda t: t["function"]["name"])
schema_text = json.dumps(response_format, ensure_ascii=False, sort_keys=True)
```

Keep `request_id`, tenant, trace, and telemetry outside cacheable schemas.

### AP-3: Template, Whitespace, Media, Or SDK Drift

Multiple code paths render the same prompt differently.

Search for: duplicated system templates, manual string concatenation, inconsistent `.strip()`, different markdown wrappers, image `detail` changes, signed URLs with rotating query strings, URL vs base64 differences.

Fix: create one canonical render function for the cacheable prefix. Normalize whitespace and media parameters. Pin image representation and detail level where applicable.

### AP-4: Dynamic Tool Set Inside Agent Loop

Changing the `tools` array between agent steps rewrites early prompt content. A shorter prompt can be more expensive if it destroys reuse for the growing trajectory.

Search for: per-step tool retrieval, `get_active_tools`, `select_tools`, dynamic MCP tool lists, feature-flagged tool inclusion, unordered subagent/tool descriptions.

Fix options:
- Keep compact tools stable for the session and sort by name.
- Use masking/constrained decoding in self-hosted inference.
- Use provider mechanisms such as allowed-tools, tool search, or deferred loading only after checking current docs.
- Route to fixed tool bundles before the agent loop for multi-domain apps.

Do not move tool definitions into user messages as a cache workaround unless the provider explicitly supports that pattern.

### AP-5: History Mutation Instead Of Append-Only Growth

Rewriting early messages breaks the prefix chain.

Search for: `summarize`, `compaction`, `truncate`, `messages.pop`, `del messages`, replacement of early turns, system prompt mutation mid-session.

Fix: preserve an anchor and mutate later content only.

```python
def manage_context(messages, max_tokens):
    anchor = messages[:2]  # system + first stable turn
    tail = messages[2:]
    while tail and count_tokens(anchor + tail) > max_tokens:
        tail.pop(0)
    if count_tokens(anchor + tail) > max_tokens:
        raise ValueError("stable prefix anchor exceeds context budget")
    return anchor + tail
```

For agents: prefer raw history, then compact bulky tool results by preserving paths/IDs/URLs, and use lossy summarization only when compaction is insufficient. If the stable anchor alone exceeds the budget, do not silently drop it; choose a provider-specific strategy, split the route/tool bundle, or fail closed with a clear diagnostic.

### AP-6: Mode Switching Or Framework Injection Mutates The Prefix

Mode changes or framework metadata appear before the growing history.

Search for: plan/debug/read-only modes implemented by swapping system prompts or tool lists, framework-injected `run_id`, `trace_id`, timestamps, `cwd`, platform, git status, or user/session metadata in the cacheable prefix.

Fix: keep base instructions and tool definitions stable. Put mode state and dynamic environment facts later in messages or non-cacheable metadata when the provider supports it.

### AP-7: Cache-Blind Routing Across Replicas

Stable prompts still miss if requests reach different machines.

Search for: k8s Services with multiple replicas, round-robin gateways, autoscaling LLM pods, multiple vLLM/SGLang replicas, no sticky/prefix-aware routing.

Fix depends on stack:
- Managed API: use provider-supported cache key or routing hint only after checking docs.
- OpenRouter: inspect sticky routing, `provider.order`, `provider.only`, `provider.ignore`, fallback/model routing, and first-message conversation identity.
- vLLM/SGLang/self-hosted: use prefix-aware routing, consistent hashing, or a gateway that hashes the stable prefix.
- Minimum viable: route by stable prefix family while monitoring hot spots.

### AP-8: Parallel Fan-Out On A Cold Prefix

Concurrent requests sharing a prefix can all pay full prefill if they start before cache creation is visible.

Search for: `asyncio.gather`, `Promise.all`, `ThreadPoolExecutor`, batch LLM calls, map/reduce fan-out without warm-up.

Fix:

```python
await warm_cache(shared_prefix, max_tokens=1, tools=[])
results = await asyncio.gather(*[call(shared_prefix, q) for q in batch])
```

Warm-up must be safe: disable tools or constrain them to read-only/no-op behavior, avoid prompts that can mutate external state, and verify the provider exposes cache creation before relying on this pattern. If no safe warm-up call exists, skip warm-up and report the trade-off. Verify with usage metadata on the second wave, not just latency.

### AP-9: Cache Lifetime, KV Budget, Or Eviction Mismatch

The prefix is stable but cache entries expire or get evicted before reuse.

Search for: sparse traffic, batch windows separated by long pauses, large number of prefix families, overlarge `max_model_len`, low KV cache capacity, eviction metrics, available GPU blocks near zero.

Fix: match TTL/retention to traffic cadence for managed APIs. For self-hosted inference, size KV cache for the working set, not the theoretical model context window.

### AP-9b: Over-Isolation Fragments Shared Prefixes

Security or tenant isolation can intentionally prevent reuse across users. This may be correct, but it should be an explicit trade-off.

Search for: per-request `cache_salt`, per-user cache keys, tenant-specific routing keys, `user_id` in cache key, cache namespace by session, full cache isolation flags.

Fix: choose the coarsest safe trust boundary. Prefer route/team/tenant prefixes only when the data isolation model allows it; use per-user isolation when compliance or side-channel risk requires it. Report the expected cache-efficiency loss instead of treating it as a bug.

### AP-10: Experiment Or Config Fragmentation

A/B tests, prompt variants, model settings, managed-router settings, or reasoning/tool settings split reuse into many small caches.

Search for: `variant`, `experiment`, `feature_flag`, prompt version per request, changing reasoning effort, changing tool choice, random few-shot examples, `openrouter/auto`, multiple `models`, `provider.order`, provider fallback settings.

Fix: test sequentially where possible, move differences after the stable prefix, or bucket by stable route/version and measure each bucket separately.

## Agent Tool Stability Checks

Run these whenever the app is an agent, coding assistant, MCP client, tool-using assistant, or multi-step workflow.

- Log `cached_tokens` / `cache_read_input_tokens` on each step.
- Log `prefix_hash` for canonical `system + tools + stable early messages`.
- Log `tools_count` and a sorted list/hash of tool names.
- Log output tokens and streaming timestamps when latency is the symptom.
- Check whether cache drops exactly when the tool list changes.
- Confirm tool descriptions are fixed at session start or loaded via provider-supported deferred mechanisms.
- Confirm compaction does not rewrite `system + tools + first messages`.
- Confirm framework metadata is not injected before the cacheable prefix.
- For managed routers such as OpenRouter, log actual model/provider route when available.

Use this diagnostic helper when project-specific tokenization is unavailable:

```python
import hashlib
import json


def prefix_fingerprint(system, tools=None, response_format=None, early_messages=None):
    payload = {
        "system": system,
        "tools": tools or [],
        "response_format": response_format,
        "early_messages": early_messages or [],
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:12]
```

This is a guardrail, not a provider tokenizer. Provider usage metadata remains the source of truth.

## Report Format

```markdown
## Prefix Cache Audit Report

Provider/engine: ...
Mode: code audit / advisory / agent audit
Provider facts: verified on YYYY-MM-DD / unverified

### Findings

[Critical] AP-2: Tool schema order changes between calls
Evidence: `tools = list(registry.values())` in path/to/file.py:42
Impact: tools are before the growing conversation, so every order change invalidates downstream prefix reuse.
Fix: sort tools by stable name and serialize schemas with sorted keys.
Verify: compare prefix fingerprints across three requests and confirm provider cached-token fields increase on repeated calls.

### Clean Checks

- AP-1 volatile prefix data: clean
- AP-7 routing: not applicable, single managed endpoint

### Monitoring

- cache ratio definition for this provider
- prefill/TTFT vs decode/output split
- prefix hash dimensions
- deploy/change correlation to watch
```

## Verification

Do not claim a fix works until one of these is true:

- Prefix-stability fixes: rendered cacheable prefix fingerprint is unchanged across different users/timestamps/queries.
- Provider fixes: repeated calls show cache-read/cached-token fields increasing according to the provider reference.
- Routing fixes: repeated prefix families land on the intended route and cache metrics improve by route.
- vLLM/self-hosted fixes: prefix cache hit metrics and KV block pressure metrics improve under a representative workload.

Recommend a CI/smoke check that renders representative prompts and fails when the cacheable prefix changes unexpectedly.

## Advisory Questions

If no codebase is available, ask only the missing questions needed to diagnose:

1. Which provider or inference engine?
2. Is this a cost/migration, prompt/code, agent, deployment, or observability/CI audit?
3. What artifacts are available: request code, rendered prompts, usage logs, deployment config, dashboards, evals?
4. What are median/p95 input tokens, static prefix tokens, output tokens, and agent steps?
5. What cache usage fields are visible in responses?
6. Are there multiple replicas or gateways?
7. Are tools/schemas stable across requests and agent steps?
8. Is history append-only, compacted, or summarized?
9. Are cache keys, salts, or routing hints per-user/per-request or shared by prefix family?
10. What changed before the cache hit rate or TTFT regressed?
