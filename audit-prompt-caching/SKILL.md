---
name: audit-prompt-caching
description: >
  Use whenever the user mentions LLM prompt/prefix cache misses,
  cached_tokens=0, cache_read_input_tokens/cache_creation_input_tokens,
  prompt_cache_key, cache_control/cachePoint placement, stable prefixes,
  tool/schema stability, TTFT/prefill latency, OpenAI/Claude/Bedrock/OpenRouter
  routing, vLLM/SGLang KV reuse, or LLM cost/speed regressions on repeated long
  prompts. Use when reviewing LLM request shape changes: prompt text, message
  order, request builders, tools, schemas, response_format, provider API
  surface, model/router settings, agent loop structure, context compaction, or
  inference deployment. Use for speeding up agents only when prompt-cache
  stability, TTFT, or cache cost is central. Do not use for generic prompt
  writing, generic RAG design, token counting, or non-LLM performance.
---

# Prompt Cache Audit

Diagnose and fix LLM prompt/prefix cache misses. Treat caching as an engineering property of the request path: stable prefix, cache-aware routing, and cache entries that live long enough to be reused.

Caching is an optimization only when the prefix is stable, long enough, repeated, measurable, and safe. Do not add cache controls, cache keys, or routing hints blindly.

## When to use

Use this skill when reviewing or designing LLM calls where repeated prompt prefixes may reduce cost or latency through provider-native prompt caching, managed-router cache locality, or self-hosted KV reuse.

Typical triggers:
- `cached_tokens=0`, `cache_read_input_tokens=0`, or cache writes without reads.
- Cache hit rate, TTFT, prefill latency, or input-token cost regressed.
- User says LLM cost or speed regressed around repeated long prompts, long-context agents, or shared static context.
- LLM request shape changed where repeated long prompts, TTFT, cached-token telemetry, or LLM cost matter.
- Prompt text, message order, request builders, tools, schemas, `response_format`, provider API surface, model/router settings, agent loop structure, context compaction, or inference deployment changed.
- The request uses long system prompts, tool catalogs, schemas, static documents, few-shot examples, or repeated RAG/CAG context.
- The app uses OpenAI `prompt_cache_key`, Anthropic `cache_control`, Bedrock `cachePoint`, OpenRouter routing, Gemini/Qwen/DeepSeek cache fields, or Azure OpenAI cached-token telemetry.
- An agent changes tools, compacts history, mutates early messages, or switches modes across steps.
- vLLM/SGLang/self-hosted deployments have multi-replica routing, KV pressure, tokenizer/chat-template drift, or cache-aware routing questions.

## When not to use

Do not use this skill for:
- generic prompt writing or prompt-quality editing without a caching concern
- ordinary short prompt edits where no repeated long prefix, TTFT, cache telemetry, or LLM cost concern exists
- generic RAG design unless repeated context placement/cacheability is part of the task
- token counting or context-window sizing only
- response caching only, unless comparing it with prompt prefix caching
- non-LLM frontend/backend performance or non-inference Kubernetes routing
- speculative savings claims without usage data or clearly stated assumptions

## Modes

- **Code audit**: inspect prompt construction, tool/schema serialization, history management, provider calls, routing, and engine config. Propose focused diffs and verify them.
- **Advisory**: if no codebase is available, ask targeted diagnostic questions and give provider-checked recommendations.
- **Agent audit**: when tools, tool routing, MCP, agent loops, compaction, or multi-step trajectories are present, always run the agent-specific checks.
- **Deployment audit**: when vLLM/SGLang, Kubernetes, Docker Compose, gateways, or multiple inference replicas are present, inspect routing and KV-cache capacity as first-class causes.

## Default Project Audit Workflow

When a project or repository is available, start with code and configuration. This is the primary workflow for the skill.

1. Scan the repo for provider calls, cache controls, routing hints, prompt builders, tool/schema registries, and self-hosted engine signals. Use `scripts/extract_llm_calls.py` when useful.
2. Inspect the request path in code: prompt rendering, system/developer messages, tool ordering, structured-output schemas, history management, compaction, and provider SDK parameters.
3. Inspect config and deployment files: environment defaults, feature flags, gateway/router settings, Docker Compose, Kubernetes, Helm, vLLM/SGLang flags, and replica topology.
4. Load only the relevant provider and scenario references, then apply the audit flow and anti-pattern checks.
5. Ask for usage logs, rendered request payloads, traces, or billing exports only when code/config review needs telemetry evidence, prefix comparison, ROI math, or incident correlation.

## Audit Inputs

Treat the repository, prompt code, and deployment configuration as the main audit inputs. Evidence artifacts such as provider usage logs, billing exports, rendered JSON request payloads, prompt snapshots, per-step agent traces, gateway route logs, and latency traces are supporting inputs for confirmation and measurement.

Bundled fixtures are only demo and regression-test data. Do not require users to convert production data into the repository's fixture layout before auditing. If a user asks whether fixtures are required, say no: the skill audits project code and configs first, and the scripts can also accept normal JSON, JSONL, CSV usage logs, or JSON request payloads directly.

This skill does not capture or intercept live traffic by itself. If telemetry is needed, ask the user to export or redact representative records from their own logging, tracing, provider dashboard, or billing pipeline.

## Applicability Gate

Before recommending prompt-cache changes, check:

1. **Reusable prefix**: Is there a static or semi-static prefix above the provider/model threshold or large enough to matter for self-hosted KV reuse?
2. **Repeat cadence**: Is the same prefix reused often enough before cache expiry or eviction?
3. **Exact stability**: Are tools, schemas, system/developer instructions, examples, images, and early messages byte/token stable across target requests?
4. **Telemetry**: Are cache-read/write fields, input/output tokens, TTFT/prefill timing, model/route, and prompt version available?
5. **Cost shape**: Is input prefill/input-token cost meaningful, or do output tokens/decode/tool latency dominate?
6. **Safety boundary**: Would broader cache reuse violate tenant, privacy, data residency, ZDR, or side-channel requirements?

If the gate fails, report why caching is not the right lever yet and recommend measurement, prompt restructuring, routing fixes, or a different optimization.

## Agent-First Output Contracts

Pick the smallest contract that answers the user's actual request. Do not bury the decision under general prompt-cache advice.

- **Quick triage**: use when artifacts are incomplete. Answer with provider/engine guess, most likely cache blocker, evidence needed next, and one safe next command or artifact request.
- **Code audit findings**: use when code is available. Lead with file-line findings in the report format, then clean checks, then verification commands.
- **Provider migration risk**: use when moving between OpenAI, Anthropic, Bedrock, OpenRouter, Azure OpenAI, Gemini, Qwen, DeepSeek, or self-hosted engines. Compare cache semantics, usage fields, prefix layout risk, routing risk, and cost assumptions before recommending edits.
- **Agent loop audit**: use for coding assistants, MCP clients, tool-using agents, compaction, mode switching, or long multi-step workflows. Always inspect stable tools, early messages, per-step prefix hashes, cache fields, output tokens, and compaction events.
- **Deployment audit**: use for vLLM, SGLang, Kubernetes, Docker Compose, gateways, autoscaling, or multi-replica inference. Treat routing locality and KV budget as first-class causes, not secondary deployment details.
- **Not worth caching**: use when the Applicability Gate fails or the evidence shows output decode, external tool latency, rate limits, or privacy isolation dominate. Say what should change instead and what evidence would reopen prompt-cache work.

For "do we need to change the project?" questions, answer first with `Change needed: yes`, `Change needed: no`, or `Change needed: unknown until <specific evidence>`. Then list exact files/settings to change or explicitly state that no project change is justified yet.

## Explicit Review Default

If this skill is explicitly invoked and the user asks only "review", "do a review", "сделай ревью", or equivalent, default to a cache-focused review of the available diff or repository. Treat the request as a prompt/prefix/KV cache audit: detect provider and engine signals, inspect LLM request shape, and report cache-impact findings first. Do not perform a general code review unless the user explicitly asks for one.

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
- **Full audit deliverable**: `references/report-template.md` when the user asks for a written report or when findings need a reusable handoff artifact.
- **Machine-readable rules**: `references/rules.json` when scripting, rendering, or validating findings by anti-pattern ID.

## Bundled Scripts

Use scripts when deterministic evidence is better than prose:

- `scripts/prefix_stability_check.py`: compare two rendered prompts or JSON request payloads as raw bytes by default and find the first divergent prefix location; use `--canonical-json` only when sorted-key normalization is intentional.
- `scripts/layout_linter.py`: inspect JSON request payloads for volatile early messages, unsorted tools, and dynamic schema fields before doing deeper manual layout review.
- `scripts/analyze_usage_logs.py`: summarize JSON/JSONL/CSV usage logs across OpenAI, Anthropic-compatible, Bedrock-style, and OpenAI-compatible cache fields; use `--jsonl-normalized` when a downstream report or dashboard needs per-record canonical events.
- `scripts/estimate_cache_roi.py`: estimate input-only and total-cost impact from static/dynamic/output tokens, hit rate, request count, and explicit pricing assumptions.
- `scripts/extract_llm_calls.py`: scan a repository for likely LLM provider calls, cache-control fields, routing signals, and self-hosted engine hints before choosing provider references.
- `scripts/render_audit_report.py`: combine usage-log summaries and one-line findings into a reusable Markdown or JSON audit report.
- `scripts/validate_skill_package.py`: validate frontmatter, referenced files, JSON evals, and Python helper syntax before sharing or publishing the skill.
- `scripts/run_trigger_eval.py`: summarize positive and negative trigger-eval coverage from `evals/trigger_eval.json`.

Do not treat these scripts as provider tokenizers or billing truth. Provider usage and billing exports remain authoritative.

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
| `openai`, `responses.create`, `chat.completions`, `prompt_cache_key`, `prompt_cache_retention` | OpenAI | `references/openai.md` |
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
4. Run the Applicability Gate.
5. Map prompt structure in order: tools, structured-output schemas, system/developer instructions, few-shot examples, static documents/context, retrieved context, conversation history, user-specific data, volatile values.
6. Mark each segment as static, semi-static, dynamic, or volatile.
7. Measure the symptom: cache ratio, TTFT/prefill latency, output/decode time, cache writes vs reads, and whether the drop correlates with deploys, SDK changes, prompt changes, replica count, or agent steps.
8. Scan universal anti-patterns below.
9. If an agent loop or tools are present, run the Agent Tool Stability checks.
10. Apply provider-specific checks from the loaded reference.
11. Report findings with evidence, severity, concrete fix, and validation steps.
12. When making code changes, verify prefix stability before claiming success.

## Audit Playbooks

Use these as starting paths for common support and review requests. Still run provider detection and the Freshness Gate before exact claims.

- **OpenAI cached_tokens=0**: check prompt length/threshold, first-prefix drift, `responses.create` vs Chat usage fields, `prompt_cache_key` granularity, `prompt_cache_retention`, output-token dominance, and whether an OpenAI-compatible wrapper is actually in use.
- **Claude/Bedrock/OpenRouter writes without reads**: distinguish cache creation/write fields from read/hit fields, then inspect cache breakpoint placement, dynamic content before the breakpoint, TTL/retention, model/region/API support, fallback routing, and actual routed provider/model.
- **Dynamic tools in long agent loops**: compare `tools_count`, sorted tool-name hash, `prefix_hash`, mode state, and cache fields per step. Prefer stable route-level tool bundles, sorted schemas, provider-supported allowed tools/tool search/deferred loading, or self-hosted masking after checking current docs.
- **High hit rate but no savings**: separate input savings from total cost and final latency. Check output-token share, decode time, external tool time, TPM/rate-limit behavior, and cache read/write pricing assumptions before changing prompt layout.
- **OpenAI-compatible wrapper ambiguity**: if `base_url`, Azure, OpenRouter, Bedrock, DashScope/Qwen, or another gateway wraps an OpenAI SDK, load the wrapper reference first and do not recommend direct OpenAI-only parameters until the wrapper docs support them.
- **Self-hosted multi-replica miss**: inspect gateway/service routing, prefix-aware hashing, tokenizer/chat-template drift, `max_model_len`, KV block pressure, eviction metrics, and route/replica-level hit metrics.
- **New provider docs project-change audit**: compare the new provider facts against current code, references, evals, and tests. Recommend no code change when the project already encodes the behavior or when the fact is not applicable to this provider path.

## Rule Categories

Use this taxonomy to keep audits consistent:

| Priority | Category | Examples |
|---|---|---|
| P0 | Provider correctness | OpenAI automatic caching, Responses vs Chat usage fields, Anthropic `cache_control`, Bedrock `cachePoint`, provider thresholds, TTL/retention |
| P1 | Prefix stability | static-first ordering, dynamic-last placement, no volatile early values, stable tools/schemas, deterministic document order |
| P2 | Measurement | cache hit ratio, cache write/read distinction, output-token share, TTFT vs final latency, prompt/tool/schema hashes |
| P3 | Architecture | prompt cache vs response cache, RAG vs CAG, multi-tenant boundaries, managed routing, self-hosted replica locality |
| P4 | Reporting | file-line findings, before/after prompt layout, ROI assumptions, validation commands |

## Severity

Assign severity from impact and evidence, not from the anti-pattern name alone:

- **Critical**: confirmed metric drop or cache miss on a large shared prefix, expensive model, high traffic, long agent trajectory, or multi-replica production path.
- **High**: likely cache killer found in a hot path but metrics are incomplete.
- **Medium**: pattern can fragment cache but impact depends on traffic shape.
- **Low**: defensive cleanup, documentation, or monitoring improvement.

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

Default to terse findings first. Use this one-line format when file/line evidence exists:

```text
file:line | severity | provider/engine | issue | cache impact | fix | validation
```

When structure is the issue, include compact before/after prompt layout.

```markdown
## Prefix Cache Audit Report

Provider/engine: ...
Mode: code audit / advisory / agent audit
Provider facts: verified on YYYY-MM-DD / unverified
Confidence: high / medium / low

### Findings

path/to/file.py:42 | critical | OpenAI | tool schema order changes between calls | tools are before the growing conversation, so every order change invalidates downstream prefix reuse | sort tools by stable name and serialize schemas with sorted keys | compare prefix fingerprints across three requests and confirm cached-token fields increase

### Clean Checks

- AP-1 volatile prefix data: clean
- AP-7 routing: not applicable, single managed endpoint

### Monitoring

- cache ratio definition for this provider
- prefill/TTFT vs decode/output split
- prefix hash dimensions
- deploy/change correlation to watch
```

## Agent-First Quality Bar

Before finalizing an audit response:

- Answer the decision the user asked for: change needed, no change, or evidence missing.
- Prefer wrapper/router references over generic provider references when both signals exist.
- Do not make exact provider claims without loading the relevant reference and applying the Freshness Gate.
- Distinguish cache miss, cache write-without-read, uneconomic cache hit, decode-bound latency, rate-limit pressure, and privacy-driven isolation.
- Include validation that can falsify the recommendation: prefix fingerprints, provider usage fields, route/replica metrics, or cost/latency split.
- Do not propose cache controls, cache keys, or routing hints when the Not worth caching contract applies.

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
