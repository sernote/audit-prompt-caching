# LLM Cache Audit Skill

[![CI](https://github.com/sernote/audit-prompt-caching/actions/workflows/ci.yml/badge.svg)](https://github.com/sernote/audit-prompt-caching/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Stdlib only](https://img.shields.io/badge/scripts-stdlib--only-green)
![Codex skill](https://img.shields.io/badge/Codex-skill-compatible-black)

`audit-prompt-caching` finds where repeated LLM requests stop sharing a stable
prefix, then checks whether provider semantics, routing, or self-hosted KV
behavior support a cache change at all.

## Quick Start

Install the skill:

```bash
npx skills add https://github.com/sernote/audit-prompt-caching --skill audit-prompt-caching
```

Try the first local audit:

```bash
git clone --depth 1 https://github.com/sernote/audit-prompt-caching.git
cd audit-prompt-caching
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json \
  examples/first-audit/before-a.txt examples/first-audit/before-b.txt
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json \
  examples/first-audit/after-a.txt examples/first-audit/after-b.txt
```

The example keeps the same task instructions and request context, but moves the
changing timestamp and ticket details after the stable instructions. The
measured common UTF-8 prefix grows from `43` to `254` bytes. Both commands exit
with status `1` because the complete requests still differ by design. See the
[first-audit walkthrough](examples/first-audit/README.md) for the exact output
and limits of this measurement.

## Audit Hero Shot

```text
+------------------------------------------------------------+
| LLM CACHE AUDIT                                            |
+------------------------------------------------------------+
| Before: 43 stable UTF-8 bytes                              |
| After:  254 stable UTF-8 bytes                             |
| Change: stable task instructions moved before context      |
| Evidence: local rendered text comparison                   |
| Next: check provider eligibility and real usage telemetry  |
+------------------------------------------------------------+
```

To audit your own project, start a new Codex session in its repository and ask:

```text
Use $audit-prompt-caching to audit this project for prompt-cache misses. Start with the request-building code and configuration. Check prefix layout, tools and schemas, history changes, provider or router settings, and deployment cache locality. Tell me when no change is justified and what evidence would be needed before claiming cache hits or savings.
```

Code and configuration are enough to begin; production logs are optional
supporting evidence. A justified "no change needed" result is valid.
The short [real-project guide](docs/first-audit.md) covers checking a finding
and sharing optional feedback.

Project background and longer examples are on the
[project page](https://notevskii.tech/projects/audit-prompt-caching/). Updates
and field notes are in the public [Telegram channel](https://t.me/sergeinotevskii).

## Why This Exists

LLM cache reuse can fail silently. A timestamp in the system prompt, shuffled
tool schemas, or a changed first user message can make repeated requests
diverge early. A managed-router fallback or a new self-hosted replica can send
byte-identical requests to a route or worker without reusable cache state.

This skill gives agents a cache-specific audit path: inspect prefix stability,
provider semantics, cache telemetry, routing locality, KV pressure, and whether
caching is the right lever for the workload.

## Synthetic Usage Demo

The bundled usage fixture is synthetic data for exercising the reporting
helpers. It is separate from the first prefix-stability audit above and does
not describe a live provider workload.

From the same repository root used in Quick Start, run its arithmetic:

```bash
python3 audit-prompt-caching/scripts/analyze_usage_logs.py \
  fixtures/openai/repeated_prefix_usage.jsonl
```

Render a report from the same fixture:

```bash
python3 audit-prompt-caching/scripts/render_audit_report.py \
  --usage-log fixtures/openai/repeated_prefix_usage.jsonl \
  --provider openai \
  --engine "Responses API" \
  --finding "fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | synthetic cold-start record | the first fixture record has zero cached tokens by construction | treat it as demo input rather than a defect | use real repeated-call telemetry for conclusions"
```

Lint known-good rendered request fixtures:

```bash
python3 audit-prompt-caching/scripts/layout_linter.py \
  fixtures/layout/good_openai_request.json
python3 audit-prompt-caching/scripts/layout_linter.py \
  fixtures/layout/good_openai_responses_request.json
```

`layout_linter.py` accepts Chat-style `messages` payloads and Responses-style
`input` payloads when checking for volatile early content, unstable tool order,
and dynamic schema fields.

## Synthetic Fixture Signal

These values are computed only from the bundled synthetic records. They verify
the helper's arithmetic; they are not evidence about production cache behavior.

| Signal | Value |
|---|---:|
| Records reviewed | 3 |
| Input tokens | 15,600 |
| Cached tokens | 9,300 |
| Cache hit ratio | 59.62% |
| Output share | 7.17% |

The following is a separate synthetic ROI calculation for 1,000 requests with
9k static input tokens, 300 dynamic input tokens, 2k output tokens, 71% cache
hit rate, and explicit sample prices:

```text
Total cost: $34.60 -> $23.10
Total savings: 33.24%
Input savings: 61.84%
```

The usage fixture and ROI scenario are arithmetic demonstrations, not a
production guarantee. Validate real outcomes with the provider's usage fields,
billing export, route evidence, and latency measurements.

## Experimental Routing Evidence Helper

For an advanced self-hosted investigation, this optional helper joins an
existing normalized export. There is no bundled native-log adapter, and the
complete capture-to-analysis path still needs validation on a real deployment.
Start a project audit from code and configuration using the guide above.

To explore the helper's output, try the synthetic export from the repository root:

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py \
  fixtures/routing/slow-with-reuse.jsonl --attempt-ttft-limit-ms 500
```

The helper joins decisions and outcomes by run, request and attempt. It keeps
missing evidence visible and can identify actual reuse alongside a client TTFT
violation. That observation does not establish what caused the delay.

It accepts the documented [normalized JSONL export](audit-prompt-caching/references/routing-evidence.md),
not native vllm-router logs. The limit applies to one attempt, not a percentile
SLO or a policy rollout decision. Predictions retain their own target worker;
they are not assumed to describe the selected worker. See the
[routing fixtures](fixtures/routing/README.md) for the supported examples.

The [routing capture reference](docs/routing-capture.md) describes the evidence
needed when a real investigation requires matching router decisions to worker
and client outcomes. The [router observation example](examples/router-observation/README.md)
shows two verified API/metric pitfalls, with recorded artifacts and optional
instructions to reproduce them using a synthetic HTTP worker.

## Cache Flow

```mermaid
flowchart LR
  A["stable tools / schemas"] --> B["stable system / developer instructions"]
  B --> C["few-shot examples / static docs"]
  C --> D["append-only conversation anchor"]
  D --> E["late dynamic user data"]
  A --> H["prefix + tool + schema hash"]
  H --> I["provider cache read/write fields"]
  I --> J["TTFT / cost / route metrics"]
```

## Positioning

This project is a static audit skill plus dependency-free local scripts. It complements runtime observability and gateway tools rather than replacing them.

| Project | Primary job | Static cache-path audit | Portable agent skill | Stdlib-only local scripts |
|---|---|---:|---:|---:|
| `audit-prompt-caching` | Cross-provider prompt/prefix/KV cache audit | yes | yes | yes |
| [ussumant/cache-audit](https://github.com/ussumant/cache-audit) | Claude Code cache-rules skill | Claude-focused | Claude Code-focused | single skill |
| [Helicone](https://github.com/Helicone/helicone) | LLM observability and gateway | runtime-oriented | no | no |
| [Langfuse](https://github.com/langfuse/langfuse) | LLM observability, evals, prompt management | runtime-oriented | no | no |
| [LiteLLM](https://github.com/BerriAI/litellm) | LLM gateway/proxy | runtime/gateway-oriented | no | no |

## Who It Is For

- AI engineers debugging prompt-cache misses or long TTFT.
- Backend engineers building LLM request paths.
- Agent developers working with tools, MCP, compaction, or coding assistants.
- Platform/SRE engineers running vLLM, SGLang, or multi-replica inference.
- Teams comparing providers or estimating effective LLM cost.

## What It Audits

- Prompt-cache applicability before recommending changes.
- Stable prompt prefix layout.
- Volatile data in system prompts and early messages.
- Non-deterministic tool/schema serialization.
- Dynamic tool sets inside agent loops.
- History truncation, compaction, and summarization.
- Cache-aware routing for managed and self-hosted inference.
- OpenRouter sticky routing, provider fallback, and cache read/write fields.
- Amazon Bedrock cache checkpoints and read/write fields.
- Prefill vs decode latency and output-token cost share.
- KV-cache budget, eviction, and deployment config.
- Provider-specific usage fields and docs freshness.
- ROI assumptions across static, dynamic, and output tokens.
- CI/smoke-test readiness for stable prefix drift.

## Primary Workflow: Audit A Project

The main use case is an agent working inside a project repository. The skill should first inspect source code and configuration, then use logs or rendered payloads as evidence when they are available.

The agent should start with project artifacts such as:

- prompt builders, prompt templates, and request renderers
- provider SDK calls and cache-control parameters
- tool registries, JSON schemas, structured-output definitions, and serialization code
- conversation history, compaction, truncation, and agent-loop logic
- environment config, feature flags, router/gateway config, and provider selection
- Docker Compose, Kubernetes, Helm, vLLM, SGLang, or other inference deployment files

Usage logs, billing exports, rendered JSON request payloads, prefix hashes, traces, and latency data are supporting evidence. They help confirm symptoms, compare before/after prefixes, calculate cache read/write ratios, and estimate ROI, but they are not the primary entry point for the skill.

## Bundled Scripts

The skill includes small dependency-free helpers for repeatable audits:

```bash
python3 audit-prompt-caching/scripts/extract_llm_calls.py .
python3 audit-prompt-caching/scripts/layout_linter.py path/to/rendered_request.json
python3 audit-prompt-caching/scripts/prefix_stability_check.py before.json after.json
python3 audit-prompt-caching/scripts/analyze_usage_logs.py usage.jsonl
python3 audit-prompt-caching/scripts/analyze_usage_logs.py --jsonl-normalized usage.jsonl
python3 audit-prompt-caching/scripts/analyze_routing_logs.py routing.jsonl --attempt-ttft-limit-ms 500
python3 audit-prompt-caching/scripts/estimate_cache_roi.py \
  --static-tokens 9000 \
  --dynamic-tokens 300 \
  --output-tokens 2000 \
  --requests 100 \
  --hit-rate 0.8 \
  --input-price-per-mtok 2.0 \
  --cached-input-price-per-mtok 0.2 \
  --output-price-per-mtok 8.0
python3 audit-prompt-caching/scripts/render_audit_report.py \
  --usage-log path/to/usage.jsonl \
  --provider openai \
  --engine "Responses API" \
  --cache-plane gateway_response \
  --cache-plane provider_prompt \
  --evidence-quality warning \
  --usage-accounting warning \
  --prefix-stability fail \
  --finding "src/llm/request.py:42 | high | openai | dynamic timestamp in system prompt | timestamp changes the cacheable prefix on every call | move volatile metadata after the stable prefix | compare rendered request bytes across repeated calls"
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

`extract_llm_calls.py` is a lexical locator only: snippets are always elided.
It can match comments, dead code, or overridden configuration; it never
resolves active/effective values or source precedence. Open each reported
`path:line` and verify the resolved runtime configuration during Deployment
Audit. Paths remain verbatim.

`layout_linter.py` accepts rendered Chat-style `messages` payloads and
Responses-style `input` payloads.

`analyze_routing_logs.py` is experimental and requires the
[normalized export contract](audit-prompt-caching/references/routing-evidence.md).
It does not accept ordinary router logs directly.

`render_audit_report.py` takes `--cache-plane` once per plane in scope
(`gateway_response`, `provider_prompt`, `engine_kv`, `external_kv`,
`semantic_response`) and one status per Cache Clinic dimension, such as
`--evidence-quality` or `--usage-accounting`. Unset dimensions stay `unknown`,
and the report emits no aggregate score across them. When the normalized usage
denominator is `ambiguous` or `invalid`, the rendered cache hit ratio and both
cost lines (`Cost impact:` and the priced-scenario `Assessment:`) are qualified
as non-decision-grade and cannot support a savings claim.

`render_audit_report.py --accounting-mode inclusive|additive` resolves wrapper
usage logs whose cache-token accounting is only known externally, the same way
`analyze_usage_logs.py --accounting-mode` does. It cannot rescue an inclusive
contradiction: a denominator that stays `invalid` still rejects
`--usage-accounting pass`.

`prefix_stability_check.py` compares raw bytes by default so JSON key-order drift is visible. Use `--canonical-json` only when sorted-key normalization is intentional.

Provider usage metadata and billing exports remain authoritative; these scripts are audit aids.

## Evidence Artifacts

Fixtures are not required for a real audit. They are bundled demo and regression-test data that show expected file shapes without needing a production project or production logs.

When evidence is needed, point the scripts at exported artifacts from the user's system:

```bash
python3 audit-prompt-caching/scripts/analyze_usage_logs.py path/to/real_usage.jsonl
python3 audit-prompt-caching/scripts/layout_linter.py path/to/rendered_request.json
python3 audit-prompt-caching/scripts/prefix_stability_check.py request_a.json request_b.json
```

Good real inputs are:

- provider usage logs or billing exports with cache read/write fields
- one or more rendered JSON request payloads from the hot path, such as Chat-style `messages` or Responses-style `input`
- normalized per-step agent logs with model, route, prefix hash, tools hash, token usage, and latency
- deployment or router config when cache locality or self-hosted KV reuse is part of the issue

The skill does not capture live traffic by itself. Export or redact representative records first when telemetry evidence is needed. Keep bundled fixtures for demos, tests, and examples of the expected schema.

## Example Prompts

Use these as pressure scenarios, not generic smoke tests.

OpenAI-compatible wrapper ambiguity:

```text
Use $audit-prompt-caching to review this app. It imports the OpenAI SDK, but base_url points to https://openrouter.ai/api/v1. We added prompt_cache_key, provider.order, and openrouter/auto; cache_write_tokens appears, but cached_tokens stays zero. Decide whether this is an OpenAI issue or a router/cache-locality issue.
```

Claude automatic caching writes every request:

```text
Use $audit-prompt-caching to audit our Claude layout. We added top-level cache_control to an 18k-token policy prompt, then append timestamp and user question as the final content block. usage.cache_creation_input_tokens increments every request, but cache_read_input_tokens stays zero.
```

Bedrock Converse cross-region cachePoint:

```text
Use $audit-prompt-caching to review this Bedrock Converse request. cachePoint is placed after a user-specific intro, tools differ by route, CacheWriteInputTokens is high, CacheReadInputTokens is near zero, and some traffic uses cross-region inference.
```

MCP tool registry drift:

```text
Use $audit-prompt-caching to audit our coding agent. The MCP tool registry is queried every step, tool order changes with plugin load timing, read-only mode removes write tools, and compaction rewrites the first user turn. Costs rose even though each step sends fewer tools.
```

vLLM/SGLang multi-replica KV:

```text
Use $audit-prompt-caching to inspect this self-hosted deployment. vLLM/SGLang replicas sit behind a generic gateway, p99 prompt length is 12k, max_model_len is 128k, prefix hashes look stable, but TTFT spikes after scaling and prefix-cache metrics vary by replica.
```

High cached tokens, low savings:

```text
Use $audit-prompt-caching to explain why this workload still costs too much. cached_tokens is high and TTFT improved, but responses average 4k output tokens, tool calls add seconds, TPM errors did not improve, and finance wants to know whether prompt caching is the wrong lever.
```

## Structure

```text
audit-prompt-caching/
  SKILL.md
  agents/openai.yaml
  references/
    openai.md
    openrouter.md
    azure-openai.md
    anthropic.md
    bedrock.md
    agent-tools.md
    sglang.md
    vllm.md
    deepseek.md
    economics.md
    gemini.md
    mechanics.md
    routing-evidence.md
    predeploy-checklist.md
    report-template.md
    qwen.md
    yandexgpt.md
    zai.md
    use-cases.md
  scripts/
    analyze_usage_logs.py
    analyze_routing_logs.py
    estimate_cache_roi.py
    extract_llm_calls.py
    layout_linter.py
    prefix_stability_check.py
    render_audit_report.py
    validate_skill_package.py
    run_trigger_eval.py
  evals/
    evals.json
    trigger_eval.json
fixtures/
  layout/
  openai/
  anthropic/
  bedrock/
  openrouter/
  vllm/
  routing/
  expected/
```

## Validation

Validate the skill package with the bundled validator:

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

The repository also includes JSON eval prompts:

- `audit-prompt-caching/evals/evals.json`: behavioral audit scenarios.
- `audit-prompt-caching/evals/trigger_eval.json`: should-trigger and should-not-trigger queries.

Run the local script/package tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

These evals are a starting point. A full proof cycle should still compare baseline agent behavior against behavior with the skill enabled.

## First-Audit Feedback

After trying the skill on a project, [share an audit result](https://github.com/sernote/audit-prompt-caching/issues/new?template=audit-result.md).
A useful finding, a justified no-change result, missing evidence or an incomplete
audit all help improve the first-use path. The template asks for a small
shareable example and optional discovery source; nothing is collected
automatically.

## Project Quality Gates

CI runs the unittest suite, package validator, trigger eval, Python syntax compile, whitespace check, and generated-bytecode guard. Keep new scripts stdlib-only and add fixture-backed tests for behavior changes.

## Freshness Policy

Provider cache behavior changes. The skill treats bundled provider references as heuristics and instructs the agent to verify official docs before exact claims about pricing, TTL, model support, field names, cache-control semantics, or routing hints.

## License

MIT. See `LICENSE`.
