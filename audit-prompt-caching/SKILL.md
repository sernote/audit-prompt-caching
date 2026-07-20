---
name: audit-prompt-caching
description: >
  Use whenever the user mentions LLM prompt/prefix cache misses, cached_tokens=0,
  cache_read_input_tokens/cache_creation_input_tokens, cache_write_tokens,
  prompt_cache_key, prompt_cache_options, prompt_cache_breakpoint,
  cache_control/cachePoint, TTFT/prefill latency, KV reuse, LLM cost or speed
  regressed on repeated long prompts, or speeding up agents through cache
  stability. Use for LLM request shape changes: prompt text/order/builders,
  tools, schemas, response_format, model/router, agent loops, or compaction.
  Not for generic prompt writing/RAG, token counts, or non-LLM perf.
---

# Prompt Cache Audit

Diagnose LLM prompt/prefix cache misses as request-path engineering problems:
stable reusable prefixes, provider telemetry, cache-aware routing, and cache
entries that live long enough to be reused. Caching is worth changing only when
the prefix is stable, long enough, repeated, measurable, and safe.

Do not add cache controls, cache keys, cache salts, provider pins, routing hints,
or broader cache sharing until the applicability, telemetry, and trust-boundary
checks justify them.

## When to use

Use this skill for LLM calls where repeated prompt prefixes may affect cost,
TTFT, prefill latency, or self-hosted KV reuse.

Typical triggers:
- `cached_tokens=0`, `cache_read_input_tokens=0`, `cache_write_tokens`, cache writes without reads, or unclear provider usage fields.
- GPT-5.6 `prompt_cache_options`, `prompt_cache_breakpoint`, paid-write behavior, or migration from `prompt_cache_retention`.
- Cache hit rate, TTFT, prefill latency, or input-token cost changed.
- LLM cost or speed regressed around repeated long prompts, shared static context, long-context agents, or tool-heavy loops.
- LLM request shape changed where repeated long prompts, TTFT, cached-token telemetry, or LLM cost matter.
- Prompt text, message order, request builders, tools, schemas, `response_format`, provider API surface, model/router settings, agent loop structure, or context compaction changed.
- The route uses long system prompts, tool catalogs, schemas, static documents, few-shot examples, repeated RAG/CAG context, or provider cache APIs.
- vLLM/SGLang/self-hosted deployments have multi-replica routing, KV pressure, tokenizer/chat-template drift, cache salts, or APC benchmark workflows such as `vllm bench serve`, `prefix_repetition`, or `benchmark_prefix_caching.py`.

## When not to use

Do not use this skill for:
- generic prompt writing, prompt-quality editing, or ordinary short prompt edits without repeated-prefix, TTFT, cache telemetry, or LLM cost concern
- generic RAG design unless repeated context placement/cacheability is part of the task
- token counting or context-window sizing only
- response caching only, unless comparing it with prompt prefix caching
- non-LLM frontend/backend performance or non-inference Kubernetes routing
- speculative savings claims without usage data or explicitly stated assumptions

## Modes

- **Code audit**: inspect prompt construction, tool/schema serialization, history management, provider SDK calls, routing, and engine config. Propose focused diffs and verify them.
- **Advisory**: when no codebase is available, ask only the missing diagnostic questions and give provider-checked recommendations.
- **Agent audit**: when tools, MCP, agent loops, compaction, or multi-step trajectories are present, run the agent-specific checks.
- **Deployment audit**: for vLLM/SGLang, Kubernetes, Docker Compose, gateways, or multiple inference replicas, inspect routing locality and KV capacity as first-class causes.

## Default Project Audit Workflow

When a repository is available, start with code and config:

1. Scan for provider calls, cache controls, routing hints, prompt builders, tool/schema registries, and self-hosted engine signals. Use `scripts/extract_llm_calls.py` when deterministic scanning is useful.
2. Inspect prompt rendering, system/developer messages, tool ordering, structured-output schemas, history management, compaction, and SDK parameters.
3. Inspect environment defaults, feature flags, gateway/router settings, Docker Compose, Kubernetes, Helm, vLLM/SGLang flags, and replica topology.
4. Load only the relevant provider and scenario references.
5. Ask for usage logs, rendered payload pairs, traces, or billing exports only when telemetry is needed to confirm a finding, compare prefixes, calculate ROI, or correlate incidents.

Bundled fixtures are examples and regression data. Users do not need to convert
production data into fixture layout; scripts accept normal JSON, JSONL, CSV
usage logs, and JSON request payloads.

## Project Context Gate

Before assigning severity or recommending project changes, review hot paths, repeat cadence, prompt families, and cache applicability.

1. Map prompt families, request builders, model/provider routes, agent loops, deployment paths, and usage frequency.
2. Separate hot repeated paths from rare jobs, one-off prompts, admin flows, experiments, and prompt families with no shareable stable prefix.
3. Mark each finding as applicable, conditionally applicable, or not applicable to the reviewed path.
4. Ask for telemetry only after code/config context shows what evidence is missing.

If a route is rare, short, mostly unique, output/tool-latency dominated, privacy-isolated, or has no stable long prefix, say prompt caching is not the right lever for that route and remove generic cache warnings from actionable findings.

## Applicability Gate

Before recommending prompt-cache changes, check:

1. **Reusable prefix**: Is the static or semi-static prefix above the provider/model threshold or large enough to matter for self-hosted KV reuse?
2. **Repeat cadence**: Is the same prefix reused often enough before expiry or eviction?
3. **Exact stability**: Are tools, schemas, instructions, examples, media, documents, and early messages byte/token stable across target requests?
4. **Telemetry**: Are cache read/write fields, input/output tokens, TTFT/prefill timing, route/model, and prompt version available?
5. **Cost shape**: Is input prefill/input-token cost meaningful, or do output tokens, decode time, and tools dominate?
6. **Safety boundary**: Would broader reuse violate tenant, privacy, data residency, ZDR, or side-channel requirements?

If the gate fails, report why caching is not the right lever yet and recommend measurement, prompt restructuring, routing fixes, or a different optimization.

## Language Match Rule

Answer in the user's language by default. Preserve provider/API field names exactly, such as `cached_tokens`, `cache_write_tokens`, `prompt_cache_options`, `prompt_cache_breakpoint`, `cache_control`, `cachePoint`, `TTFT`, `prompt_cache_key`, and `response_format`, but explain them in the user's language.

## Agent-First Output Contracts

Pick the smallest contract that answers the request:

- **Quick triage**: provider/engine guess, most likely cache blocker, evidence needed next, and one safe next command or artifact request.
- **Code audit findings**: decision summary first, then file-line findings, clean checks, and verification commands.
- **Provider migration risk**: compare cache semantics, usage fields, prefix layout risk, routing risk, and cost assumptions before recommending edits.
- **Agent loop audit**: inspect stable tools, early messages, per-step prefix hashes, cache fields, output tokens, and compaction events.
- **Deployment audit**: treat routing locality and KV budget as first-class causes for vLLM, SGLang, Kubernetes, Docker Compose, gateways, autoscaling, or multi-replica inference.
- **Not worth caching**: use when the Applicability Gate fails or evidence shows output decode, external tools, rate limits, or privacy isolation dominate. State what should change instead and what evidence would reopen prompt-cache work.

For project-change questions, answer first with `Change needed: yes`, `Change needed: no`, or `Change needed: unknown until <specific evidence>` when a single answer is accurate. If change types differ, use:

```text
Measurement change:
Prompt behavior change:
Provider/routing change:
Confidence:
Do first:
Do not do yet:
```

## Evidence-Bearing Findings

Every actionable finding should expose uncertainty and a falsifiable validation path:

```text
source | severity | provider/engine | issue | evidence | evidence_type | confidence | impact_condition | cache impact | safe_first_action | fix | validation | do_not_do_yet
```

Use evidence types such as `confirmed from code`, `confirmed from telemetry`, `provider-doc hypothesis`, or `needs validation`. State impact conditions such as "matters if this path is hot, repeated, and has a long stable prefix" instead of implying guaranteed savings.

Group review output as:
- **Confirmed findings**: supported by code/config/telemetry and applicable to the project path.
- **Hypotheses**: plausible risks needing usage logs, rendered payloads, route metrics, or provider docs.
- **Not applicable**: generic cache advice ruled out by project context.

## Explicit Review Default

If this skill is explicitly invoked and the user asks only "review", "do a review", "сделай ревью", or equivalent, default to a cache-focused review of the available diff or repository. Treat the request as a prompt/prefix/KV cache audit and report cache-impact findings first. Do not perform a general code review unless the user explicitly asks for one.

## Use-Case Map

Classify the request before auditing. For the deeper artifact matrix, load `references/use-cases.md`.

| Scenario | Common triggers | Inspect first |
|---|---|---|
| Cost or migration audit | bill increased, provider comparison, cache discount not visible | usage logs, billing export, static/dynamic/output token estimates, provider references |
| Prompt/code audit | `cached_tokens=0`, prompt builder changed, schema drift | prompt renderers, SDK calls, tools, `response_format`, serialization |
| Mechanics/latency audit | cache hit did not reduce cost/latency, decode dominates | `references/mechanics.md`, token/TTFT traces, output length, streaming timestamps |
| Managed-router audit | OpenRouter cache writes without reads, fallback, sticky routing | OpenRouter request body, `provider` routing fields, model(s), plugins, usage metadata |
| Agent/coding-assistant audit | agent got expensive, dynamic tools, MCP routing, compaction | agent loop, tool registry, history compaction, per-step cache logs |
| Deployment audit | vLLM/SGLang cache misses, TTFT after scaling | Docker/Kubernetes/Helm/gateway config, engine flags, KV metrics |
| Observability/CI audit | need dashboard, release guardrail, prefix smoke test | `references/observability.md`, traces, snapshots, prefix/tool/schema hashes |
| Quick operational triage | low hit rate, high bill, TTL confusion, wrapper ambiguity | `references/operational-playbook.md`, usage fields, rendered request pair |

## Scenario References

Load only what the detected scenario needs:

- Quick triage: `references/operational-playbook.md`.
- Cost or migration: `references/economics.md`, plus provider references.
- Mechanics, latency, or self-hosted compute: `references/mechanics.md`.
- Observability, dashboards, alerts, or CI guardrails: `references/observability.md`.
- Release, incident, deploy, or monitoring: `references/predeploy-checklist.md`.
- OpenRouter or managed provider routing: `references/openrouter.md`.
- Agents, coding assistants, MCP, or dynamic tools: `references/agent-tools.md`.
- Self-hosted SGLang: `references/sglang.md`.
- Full report handoff: `references/report-template.md`.
- Machine-readable anti-pattern rules: `references/rules.json`.

## Bundled Scripts

Use scripts when deterministic evidence is better than prose:

- `scripts/prefix_stability_check.py`: perform a raw whole-input comparison; use `--canonical-json` only when sorted-key normalization is intentional. It does not prove explicit breakpoint reuse.
- `scripts/layout_linter.py`: inspect layout anti-patterns and validate direct GPT-5.6 `prompt_cache_options` and `prompt_cache_breakpoint` placement. Provider wrappers remain unvalidated.
- `scripts/analyze_usage_logs.py`: summarize JSON/JSONL/CSV usage, including OpenAI `cache_write_tokens`. Use `--accounting-mode` only to resolve wrapper fields whose inclusive/additive meaning is known externally.
- `scripts/estimate_cache_roi.py`: estimate read/write cost with caller-supplied prices. For paid writes, pass `--cache-write-rate` and `--cache-write-input-price-per-mtok`.
- `scripts/extract_llm_calls.py`: scan a repository for provider calls, cache-control fields, routing signals, and self-hosted engine hints.
- `scripts/render_audit_report.py`: combine usage summaries and findings into Markdown or JSON; pass estimator output through `--roi-json` before making a cost-direction claim.
- `scripts/validate_skill_package.py`: validate frontmatter, referenced files, eval JSON, and Python helper syntax.
- `scripts/run_trigger_eval.py`: summarize positive and negative trigger-eval coverage.

These scripts are provider-tokenizer and billing approximations. Provider usage and billing exports remain authoritative.

### Script Transparency Rule

Before running any bundled script, explain what each bundled script reads, writes, and whether it uses network. Also state why the script is needed, whether it scans the whole repository or a targeted path, and the expected runtime class: seconds, tens of seconds, or minutes.

Default to targeted scans for large repos or narrow questions. If a script may read secrets, environment files, generated artifacts, large logs, or production exports, say so explicitly and ask for approval unless the user already requested that exact scan. Bundled scripts do not send files to a network service.

## Freshness Gate

Provider facts are volatile. Before exact provider claims, open the relevant provider reference and verify official sources when browsing is available.

Verify before exact claims about pricing, cache discounts, storage or write premiums, current models, regional availability, cache thresholds, granularity, TTL, retention, usage fields, API parameters, tool-search, allowed-tools, defer-loading, or cache-control semantics.

If official docs cannot be checked, say provider facts are unverified and avoid exact numbers. Use bundled references as heuristics, not current truth.

## Provider Detection

Search SDK imports, API base URLs, model names, deployment manifests, and engine flags. Load wrapper/router references before generic provider advice when signals overlap.

- OpenRouter: `openrouter`, `openrouter.ai/api/v1`, `openrouter/auto` -> `references/openrouter.md`.
- Azure, Bedrock, Qwen/DashScope, Vercel AI SDK, and Mastra wrappers: load `references/azure-openai.md`, `references/bedrock.md`, `references/qwen.md`, `references/vercel-ai-sdk.md`, or `references/mastra.md` before direct-provider references.
- Direct providers: OpenAI -> `references/openai.md`; Anthropic -> `references/anthropic.md`; DeepSeek -> `references/deepseek.md`; Gemini -> `references/gemini.md`; YandexGPT -> `references/yandexgpt.md`; z.ai -> `references/zai.md`.
- Self-hosted engines: `vllm`, `vllm bench serve`, `prefix_repetition`, `benchmark_prefix_caching.py` -> `references/vllm.md`; SGLang/RadixAttention/HiCache -> `references/sglang.md`.

If detection is ambiguous, ask which provider/engine is in use.

## Audit Flow

1. Detect mode, provider, and use-case scenario.
2. Load only the relevant scenario and provider references.
3. Apply the Freshness Gate for provider facts.
4. Run the Project Context Gate and Applicability Gate.
5. Map prompt structure in order: tools, schemas, system/developer instructions, examples, static documents/context, retrieved context, conversation history, user-specific data, volatile values.
6. Mark segments as static, semi-static, dynamic, or volatile.
7. Measure cache ratio, TTFT/prefill latency, output/decode time, cache writes vs reads, and correlation with deploys, SDK changes, prompt changes, replica count, or agent steps.
8. Apply anti-patterns from `references/rules.json`.
9. For agents, log per-step `cached_tokens` or `cache_read_input_tokens`, `prefix_hash`, `tools_count`, sorted tool-name hash, output tokens, streaming timestamps, compaction events, and actual managed-router provider/model.
10. Apply provider-specific checks from the loaded reference.
11. Report findings with evidence type, confidence, impact condition, safe first action, fix, validation, and `do_not_do_yet`.
12. When making code changes, verify prefix stability before claiming success.

## Audit Playbooks

Use these starts after provider detection and Freshness Gate:

- **OpenAI cached_tokens=0**: check prompt length/threshold, first-prefix drift, Responses vs Chat usage fields, `prompt_cache_key`, model-specific cache controls, output-token dominance, and wrapper ambiguity.
- **GPT-5.6 paid writes**: validate `prompt_cache_options` and marked content blocks, separate inclusive `cached_tokens`/`cache_write_tokens` from input totals, and require current pricing before claiming savings. Prefer explicit mode when implicit latest-message writes churn on a volatile suffix.
- **Claude/Bedrock/OpenRouter writes without reads**: distinguish write/create fields from read/hit fields, then inspect breakpoint placement, dynamic content before breakpoint, TTL/retention, model/region/API support, fallback routing, and actual routed provider/model.
- **Dynamic tools in long agent loops**: compare `tools_count`, sorted tool-name hash, `prefix_hash`, mode state, and cache fields per step. Prefer stable route-level tool bundles, sorted schemas, provider-supported allowed tools/tool search/deferred loading, or self-hosted masking after checking current docs.
- **High hit rate but no savings**: separate input savings from total cost and final latency. Check output-token share, decode time, external tool time, TPM/rate limits, and cache read/write pricing assumptions.
- **OpenAI-compatible wrapper ambiguity**: if `base_url`, Azure, OpenRouter, Bedrock, DashScope/Qwen, or another gateway wraps an OpenAI SDK, load the wrapper reference first.
- **Self-hosted multi-replica miss**: inspect gateway/service routing, prefix-aware hashing, tokenizer/chat-template drift, `max_model_len`, KV block pressure, eviction metrics, and route/replica-level hit metrics.
- **New provider docs project-change audit**: compare new provider facts against current code, references, evals, and tests. Recommend no code change when the project already encodes the behavior or the fact is not applicable.

## Rule Categories

Use `references/rules.json` for the machine-readable AP-1 through AP-11 anti-pattern inventory. Use this priority taxonomy when turning rules into findings:

| Priority | Category | Examples |
|---|---|---|
| P0 | Provider correctness | usage fields, provider thresholds, cache activation, TTL/retention |
| P1 | Prefix stability | static-first ordering, no volatile early values, stable tools/schemas |
| P2 | Measurement | cache ratio, writes vs reads, output-token share, TTFT vs final latency |
| P3 | Architecture | RAG/CAG, response cache distinction, multi-tenant boundaries, routing locality |
| P4 | Reporting | file-line findings, before/after layout, ROI assumptions, validation commands |

## Severity

### Applicability Before Severity

Assign severity only after the Project Context Gate and Applicability Gate. A real anti-pattern in a cold, sparse, single-run, output-bound, or non-cacheable route is not automatically high severity.

- **Critical**: confirmed metric drop or cache miss on a large shared prefix, expensive model, high traffic, long agent trajectory, or multi-replica production path.
- **High**: likely cache killer found in a hot path, or telemetry/traffic/token evidence shows meaningful cache/cost/TTFT impact but metrics are incomplete.
- **Medium**: pattern can fragment cache but impact depends on traffic shape.
- **Low**: defensive cleanup, documentation, or monitoring improvement.

If hotness, prefix length, repeat cadence, or cost impact is unknown, prefer `medium` or `needs validation` and state what would escalate or lower severity.

## Report Format

Default to terse findings first. Use the evidence-bearing format when possible:

```text
file:line | severity | provider/engine | issue | cache impact | fix | validation
```

For full handoff reports, load `references/report-template.md`.

## Agent-First Quality Bar

Before finalizing:
- Answer the decision the user asked for: change needed, no change, or evidence missing.
- Prefer wrapper/router references over generic provider references when both signals exist.
- Do not make exact provider claims without the relevant reference and Freshness Gate.
- Distinguish cache miss, write-without-read, uneconomic hit, decode-bound latency, rate-limit pressure, and privacy-driven isolation.
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
