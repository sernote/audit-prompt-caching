---
name: audit-prompt-caching
description: "Use whenever the user mentions cached_tokens=0,total_cached_tokens,cache_read_input_tokens,cache_creation_input_tokens,cache_write_tokens,prompt_cache_key,prompt_cache_options,prompt_cache_breakpoint,previous_interaction_id,cache_control/cachePoint,TTFT,KV reuse; prefix_cache_retention_interval,prefix_caching_hash_algo,Mamba/SWA/hybrid,cross-process block hash; LLM cost or speed regressed,repeated long prompts,speeding up agents; LLM request shape changes: tools,schemas,response_format,model/router,agent loops,compaction; Not for generic prompt writing,RAG,token counts,non-LLM perf"
---

# Prompt Cache Audit

Diagnose LLM prompt/prefix cache misses as request-path engineering problems:
stable reusable prefixes, provider telemetry, cache-aware routing, and entries
that live long enough to be reused. Caching is worth changing only when the
prefix is stable, long enough, repeated, measurable, and safe. Do not add cache
controls, keys, salts, provider pins, routing hints, or broader cache sharing
until the applicability, telemetry, and trust-boundary checks justify them.

## When to use

Use this skill for LLM calls where repeated prompt prefixes may affect cost,
TTFT, prefill latency, or self-hosted KV reuse. Typical triggers:

- `cached_tokens=0`, `cache_read_input_tokens=0`, `cache_write_tokens`, writes without reads, or unclear usage fields; GPT-5.6 `prompt_cache_options`/`prompt_cache_breakpoint`; or migration from `prompt_cache_retention`.
- Cache hit rate, TTFT, prefill latency, or input-token cost changed; LLM cost or speed regressed around repeated long prompts, shared context, long agents, or tool loops.
- LLM request shape changed where repeated long prompts, TTFT, cached-token telemetry, or LLM cost matter: inspect prompt text, message order, request builders, tools, schemas, `response_format`, provider API surface, model/router settings, agent loops, or context compaction.
- Long system prompts, tool catalogs, schemas, static documents, few-shot/RAG context, provider cache APIs, or vLLM/SGLang multi-replica KV deployments (including `vllm bench serve`, `prefix_repetition`, and `benchmark_prefix_caching.py`).

## When not to use

Do not use this skill for:
- generic prompt writing, prompt-quality editing, or ordinary short prompt edits without repeated-prefix, TTFT, cache telemetry, or LLM cost concern
- generic RAG design unless repeated context placement/cacheability is part of the task
- token counting or context-window sizing only
- response caching only, unless comparing it with prompt prefix caching
- non-LLM frontend/backend performance or non-inference Kubernetes routing
- speculative savings claims without usage data or explicitly stated assumptions

Modes: code audit (repository available), advisory (no codebase, ask only the
missing diagnostic questions), agent audit (tools, MCP, loops, compaction), and
deployment audit (vLLM/SGLang, Kubernetes, gateways, replicas).

vLLM audits: image digest/version/SHA, feature presence, effective
retention/source, KV-group topology/geometry, effective
scheduler block size (`scheduler_block_size`), hash algorithm, seed compatibility status, and tier
type. Keep retention/geometry mismatch distinct from cross-process hash mismatch.
Source/nightly builds use feature detection, not a guessed version
floor; see `references/vllm.md` for the version × behavior matrices.

## Cache Plane Gate

State which cache planes are in scope before diagnosing;
several planes at once is normal, and each needs its own evidence:

- `gateway_response`: response reuse at a gateway or proxy.
- `provider_prompt`: provider-managed prompt/prefix caching in usage telemetry.
- `engine_kv`: attention KV reuse inside a self-hosted engine.
- `external_kv`: KV blocks persisted or moved outside the serving process.
- `semantic_response`: similarity-based reuse of a prior response.

Do not infer a plane from provider or model names, routes, or usage fields, and
do not merge planes: a gateway response-cache hit is not provider prefix reuse.
Pass every in-scope plane to `render_audit_report.py --cache-plane` and name the
affected plane in findings.

## Usage Evidence Contract

Before treating a hit rate as decision-grade, read the normalized event fields
from `analyze_usage_logs.py --jsonl-normalized`: `schema_version`,
`source_fields` (which raw field produced each canonical value),
`accounting_semantics` (`inclusive`, `additive`, `ambiguous`),
`denominator_status`, and `warnings`.

- `valid`: the ratio is usable evidence.
- `ambiguous`: wrapper semantics unresolved or no measured input; call the ratio
  non-decision-grade and make no savings claim.
- `invalid`: an adapter invariant is contradicted; fix accounting first.

Aggregates take the worst status (`invalid > ambiguous > valid`).
Do not build a second normalizer or hand-compute a ratio around this
contract; extend the existing adapter. Paths: `references/observability.md`.

## Cache Clinic Summary

Report `applicability`, `evidence_quality`, `prefix_stability`,
`usage_accounting`, `routing_locality`, `economics`, and `isolation`, each with
exactly one status of `pass/warning/fail/unknown/not_applicable`.
Leave every unproven dimension `unknown` instead of dropping it, and
never aggregate them into a score, rank, or grade. An ambiguous or invalid
denominator is never `usage_accounting: pass`. See `references/report-template.md`.

## Evidence Boundaries

A stable-prefix plan needs an observed rendered payload or an identified
request-construction boundary. Separate stable instructions and tools, bounded
semi-stable context, and request-specific history and user input. Describe
ordering as an observed application payload property, never as a
universal provider-internal serialization order without cited provider evidence.

Isolation review is passive and evidence-based: cache-key scope, tenant and
credential boundaries, and redaction risks visible in config or traces. Active
cross-tenant probes need separate authorization and are out of scope.

## Project Context Gate

Before assigning severity or recommending project changes, review hot paths, repeat cadence, prompt families, and cache applicability.

Map prompt families, request builders, model/provider routes, agent loops, deployment paths, and usage frequency. Separate hot repeated paths from rare jobs, one-off prompts, admin flows, experiments, and families with no shareable stable prefix. Mark each finding applicable, conditionally applicable, or not applicable to the reviewed path, and ask for telemetry only after code/config context shows what evidence is missing.

If a route is rare, short, mostly unique, output/tool-latency dominated, privacy-isolated, or has no stable long prefix, say prompt caching is not the right lever there and drop generic cache warnings from actionable findings.

## Applicability Gate

Before recommending prompt-cache changes, check:

1. **Reusable prefix**: is the static or semi-static prefix above the provider/model threshold, or large enough for self-hosted KV reuse?
2. **Repeat cadence**: is the same prefix reused often enough before expiry or eviction?
3. **Exact stability**: are tools, schemas, instructions, examples, media, documents, and early messages byte/token stable across target requests?
4. **Telemetry**: are cache read/write fields, input/output tokens, TTFT/prefill timing, route/model, and prompt version available?
5. **Cost shape**: is input prefill cost meaningful, or do output tokens, decode time, and tools dominate?
6. **Safety boundary**: would broader reuse violate tenant, privacy, data residency, ZDR, or side-channel requirements?

If the gate fails, report why caching is not the right lever yet and recommend measurement, prompt restructuring, routing fixes, or a different optimization.

## Language Match Rule

Answer in the user's language by default. Preserve provider/API field names exactly, such as `cached_tokens`, `cache_write_tokens`, `prompt_cache_options`, `prompt_cache_breakpoint`, `cache_control`, `cachePoint`, `TTFT`, and `prompt_cache_key`, but explain them in the user's language.

## Agent-First Output Contracts

Pick the smallest contract that answers the request:

- **Quick triage**: provider/engine guess, planes in scope, likeliest blocker, evidence needed next, one safe next command.
- **Code audit findings**: decision summary first, then file-line findings, clean checks, and verification commands.
- **Provider migration risk**: compare cache semantics, usage fields, prefix layout, routing, and cost assumptions before recommending edits.
- **Agent loop audit**: stable tools, early messages, per-step prefix hashes, cache fields, output tokens, compaction events.
- **Deployment audit**: routing locality and KV budget as first-class causes for vLLM, SGLang, Kubernetes, gateways, autoscaling, or multi-replica inference.
- **Not worth caching**: when the Applicability Gate fails or output decode, external tools, rate limits, or privacy isolation dominate. State what should change instead and what evidence would reopen prompt-cache work.

For project-change questions, answer first with `Change needed: yes`, `Change needed: no`, or `Change needed: unknown until <specific evidence>` when a single answer is accurate. If change types differ, split the answer into `Measurement change`, `Prompt behavior change`, `Provider/routing change`, `Confidence`, `Do first`, and `Do not do yet`.

## Evidence-Bearing Findings

Every actionable finding should expose uncertainty and a falsifiable validation path:

```text
source | severity | provider/engine | issue | evidence | evidence_type | confidence | impact_condition | cache impact | safe_first_action | fix | validation | do_not_do_yet
```

Use evidence types such as `confirmed from code`, `confirmed from telemetry`, `provider-doc hypothesis`, or `needs validation`. Keep `provider-dashboard aggregate` and `provider-usage-api aggregate` separate; make no causal claim without request/route correlation.

Group output as **Confirmed findings** (code/config/telemetry evidence applicable to this path), **Hypotheses** (need usage logs, rendered payloads, route metrics, or provider docs), and **Not applicable** (generic advice ruled out by project context).

## Explicit Review Default

If this skill is explicitly invoked and the user asks only "review", "сделай ревью", or equivalent, default to a cache-focused review of the available diff or repository, treating it as a prompt/prefix/KV cache audit and reporting cache-impact findings first. Do not perform a general code review unless the user explicitly asks for one.

## Use-Case Map

Classify the request before auditing. Deeper artifact matrix: `references/use-cases.md`.

| Scenario | Common triggers | Inspect first |
|---|---|---|
| Cost or migration | bill increased, provider comparison, discount not visible | usage logs, billing export, token estimates, provider references |
| Prompt/code | `cached_tokens=0`, builder changed, schema drift | prompt renderers, SDK calls, tools, `response_format`, serialization |
| Mechanics/latency | hit did not cut cost/latency, decode dominates | `references/mechanics.md`, TTFT traces, output length, stream timestamps |
| Deployment | vLLM/SGLang misses, TTFT after scaling | Docker/Kubernetes/Helm/gateway config, engine flags, KV metrics |
| Observability/CI | dashboard, release guardrail, prefix smoke test | `references/observability.md`, traces, snapshots, prefix/tool/schema hashes |
| Quick triage | low hit rate, high bill, TTL confusion, wrapper ambiguity | `references/operational-playbook.md`, usage fields, rendered request pair |

## Scenario References

Beyond the Use-Case Map column above, load `references/economics.md` for cost or
migration, `references/predeploy-checklist.md` for release or incident work,
`references/agent-tools.md` for agents, MCP, and dynamic tools, and
`references/rules.json` for anti-pattern rules.

## Bundled Scripts

Use scripts when deterministic evidence is better than prose:

- `scripts/prefix_stability_check.py`: whole-input comparison; `--canonical-json` is opt-in and does not prove explicit breakpoint reuse.
- `scripts/layout_linter.py`: GPT-5.6 layout and cache-control placement checks; wrappers remain unvalidated.
- `scripts/analyze_usage_logs.py`: normalize JSON/JSONL/CSV usage and `cache_write_tokens`; use `--accounting-mode` only with known wrapper semantics.
- `scripts/estimate_cache_roi.py`: estimate read/write cost; paid writes require `--cache-write-rate` and `--cache-write-input-price-per-mtok`.
- `scripts/extract_llm_calls.py`: scan provider/cache/routing/engine signals, including vLLM retention/hash in YAML/Python/Compose, `.sh`, `.service`, and `Makefile`; `.env` is excluded and no runtime probe runs.
- `scripts/render_audit_report.py`: combine usage/findings with repeatable `--cache-plane`, clinic status flags, and optional `--roi-json`.
- `scripts/validate_skill_package.py`: validate frontmatter, references, eval JSON, and Python syntax; `scripts/run_trigger_eval.py` summarizes trigger coverage.

These scripts are tokenizer and billing approximations; provider usage and billing exports remain authoritative.

### Script Transparency Rule

Before any bundled script, explain what each bundled script reads, writes, and whether it uses network; state why it is needed, targeted versus whole-repository scope, and runtime (seconds, tens of seconds, or minutes). Default to targeted scans. If it may read secrets, environment files, generated artifacts, large logs, or production exports, say so and ask approval unless that exact scan was requested. Bundled scripts do not send files to a network service.

## Freshness Gate

Provider facts are volatile. Before exact claims about pricing, cache discounts, storage or write premiums, current models, regional availability, thresholds, granularity, TTL, retention, usage fields, API parameters, tool-search, allowed-tools, defer-loading, or cache-control semantics, open the relevant provider reference and verify official sources when browsing is available.

If official docs cannot be checked, say provider facts are unverified and avoid exact numbers; bundled references are heuristics, not current truth.

## Provider Detection

Search SDK imports, API base URLs, model names, deployment manifests, and engine flags. Load wrapper/router references before generic provider advice when signals overlap.

- OpenRouter: `openrouter`, `openrouter.ai/api/v1`, `openrouter/auto` -> `references/openrouter.md`.
- Wrappers first: `references/azure-openai.md`, `references/bedrock.md`, `references/qwen.md`, `references/vercel-ai-sdk.md`, `references/mastra.md`.
- Direct: OpenAI -> `references/openai.md`; Anthropic -> `references/anthropic.md`; DeepSeek -> `references/deepseek.md`; Gemini -> `references/gemini.md`; YandexGPT -> `references/yandexgpt.md`; z.ai -> `references/zai.md`.
- Self-hosted: `vllm`, `vllm bench serve`, `prefix_repetition`, `benchmark_prefix_caching.py`, KV-cache events, or KV transfer connectors -> `references/vllm.md`; SGLang/RadixAttention/HiCache/PD disaggregation -> `references/sglang.md`.

If detection is ambiguous, ask which provider/engine is in use.

## Audit Flow

1. Detect mode, provider/engine, cache planes, and scenario; load matching references and apply the Freshness Gate.
2. Run the Project Context and Applicability Gates, then scan code/config with `scripts/extract_llm_calls.py` when deterministic evidence helps.
3. Inspect provider calls, prompt builders, cache controls, SDK parameters, env defaults, gateway/router, Compose/Kubernetes/Helm, engine flags, and replica topology.
4. Map prompt structure and ask for logs, rendered pairs, traces, or billing only where they confirm a finding, compare prefixes, calculate ROI, or correlate an incident.
5. Apply the Usage Evidence Contract and measure reads/writes, TTFT/prefill, decode, route/replica, deploy, and agent-step effects; for agents include `prefix_hash`, `tools_count`, hashes, output, streaming, compaction, and routed provider/model.
6. Apply `references/rules.json`; report evidence type, confidence, impact condition, safe action, fix, validation, and `do_not_do_yet` plus the Clinic Summary.
7. For vLLM, verify version/SHA and feature surface before retention; audit per-group geometry, `scheduler_block_size`, tier, and hash compatibility, keeping retention/geometry, cross-process hash, and `cache_salt` isolation distinct.
8. When changing code, verify prefix stability before claiming success.

Bundled fixtures are examples and regression data; scripts accept normal JSON,
JSONL, CSV usage logs and request payloads.

## Audit Playbooks

Use these starts after provider detection and Freshness Gate:

- **OpenAI cached_tokens=0**: check prompt length/threshold, first-prefix drift, Responses vs Chat usage fields, `prompt_cache_key`, model cache controls, output-token dominance, and wrapper ambiguity.
- **GPT-5.6 paid writes**: validate `prompt_cache_options` and marked blocks, separate inclusive `cached_tokens`/`cache_write_tokens` from input totals, and require current pricing before claiming savings. Prefer explicit mode when implicit writes churn on a volatile suffix.
- **Claude/Bedrock/OpenRouter writes without reads**: distinguish write/create from read/hit fields, then inspect breakpoint placement, dynamic content before it, TTL/retention, model/region/API support, fallback routing, and the routed provider/model.
- **Gemini Interactions or managed session cache**: distinguish an explicit cache object from an opaque continuation handle (`previous_interaction_id`, `previous_response_id`), keep it inside the intended conversation, and normalize `total_cached_tokens` as inclusive before comparing routes.
- **KV events, HiCache, or PD disaggregation**: separate prefix mismatch from eviction, tier transfer/offload, event delivery, and decode-side KV reuse. Compare TTFT/prefill and worker/tier metrics first.
- **Dynamic tools in long agent loops**: inspect per-step tool/prefix hashes, mode, usage, and economics; for direct OpenAI Responses or Vercel use a version/model-verified allow-list with a stable catalog; Chat Completions/unsupported wrapper/endpoint needs wire proof.
- **High hit rate but no savings**: separate input savings from total cost and final latency. Check output-token share, decode time, external tool time, TPM/rate limits, and read/write pricing assumptions.
- **OpenAI-compatible wrapper ambiguity**: if `base_url`, Azure, OpenRouter, Bedrock, DashScope/Qwen, or another gateway wraps an OpenAI SDK, load the wrapper reference first.
- **Self-hosted multi-replica miss**: inspect gateway/service routing, prefix-aware hashing, tokenizer/chat-template drift, `max_model_len`, KV block pressure, eviction, and route/replica hit metrics.
- **vLLM retention and cross-process hash**: collect image digest/version/SHA,
  feature presence, effective retention source/value, concrete
  `SlidingWindowSpec`/`SlidingWindowMLASpec`/`MambaSpec` versus full-attention
  groups, `scheduler_block_size`, tier type, hash algorithm, and safe seed
  compatibility status. Apply the release-line matrix; never infer eligibility
  from an architecture name, and never treat `PYTHONHASHSEED` as isolation.
- **New provider docs**: compare new provider facts against current code, references, evals, and tests; recommend no change when the project already encodes the behavior.

## Rule Categories

`references/rules.json` holds the machine-readable AP-1 through AP-14 inventory.
AP-9b is the isolation/trust boundary; AP-14 is technical hash compatibility
inside an already authorized sharing group. Turn rules into findings with this
priority taxonomy:

| Priority | Category | Examples |
|---|---|---|
| P0 | Provider correctness | usage fields, thresholds, cache activation, TTL/retention |
| P1 | Prefix stability | static-first ordering, no volatile early values, stable tools/schemas |
| P2 | Measurement | denominator status, cache ratio, writes vs reads, output share, TTFT |
| P3 | Architecture | RAG/CAG, plane separation, multi-tenant boundaries, routing locality |
| P4 | Reporting | file-line findings, before/after layout, ROI assumptions, validation |

## Severity

### Applicability Before Severity

Assign severity only after the Project Context Gate and Applicability Gate. A real anti-pattern in a cold, sparse, single-run, output-bound, or non-cacheable route is not automatically high severity.

- **Critical**: confirmed metric drop or miss on a large shared prefix, expensive model, high traffic, long agent trajectory, or multi-replica production path.
- **High**: likely cache killer in a hot path, or evidence shows meaningful cache/cost/TTFT impact but metrics are incomplete.
- **Medium**: pattern can fragment cache but impact depends on traffic shape.
- **Low**: defensive cleanup, documentation, or monitoring improvement.

If hotness, prefix length, cadence, or cost impact is unknown, prefer `medium` or `needs validation` and state what would escalate or lower severity.

## Report Format

Default to terse findings first, preferring the evidence-bearing format:
`file:line | severity | provider/engine | issue | cache impact | fix | validation`.
For full handoff reports, load `references/report-template.md`.

## Agent-First Quality Bar

Before finalizing:
- Answer the decision asked for: change needed, no change, or evidence missing.
- Prefer wrapper/router references over generic provider references when both signals exist, and make no exact provider claim without the reference and Freshness Gate.
- Distinguish plane, cache miss, write-without-read, uneconomic hit, decode-bound latency, rate-limit pressure, and privacy-driven isolation.
- Include falsifiable validation: prefix fingerprints, usage fields, route/replica metrics, or cost/latency split.
- Do not propose cache controls, cache keys, or routing hints when the Not worth caching contract applies.

## Verification

Do not claim a fix works until one holds:
- Prefix fixes: the rendered cacheable prefix fingerprint is unchanged across users, timestamps, and queries.
- Provider fixes: repeated calls show cache-read/cached-token fields increasing per the provider reference.
- Routing fixes: repeated prefix families land on the intended route and metrics improve by route.
- Self-hosted fixes: prefix cache hit and KV block pressure metrics improve under a representative workload.

Recommend a CI/smoke check that renders representative prompts and fails when the cacheable prefix changes unexpectedly.

## Advisory Questions

With no codebase, ask only what is still missing: provider or engine; cache
planes in scope; audit type (cost/migration, prompt/code, agent, deployment,
observability/CI); available artifacts (request code, rendered prompts, usage
logs, deployment config, dashboards, evals); median/p95 input, static-prefix,
and output tokens plus agent steps; visible cache usage fields; replica and
gateway count; tool/schema stability across steps; history handling; whether
cache keys, salts, or routing hints are per-user or shared by prefix family;
and what changed before the hit rate or TTFT regressed.
