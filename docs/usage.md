# Commands and audit scenarios

Start with the [first-project guide](first-audit.md) if you want an agent to
audit your code. This page collects optional local commands and detailed
diagnostic scenarios.

All Python commands below run from this repository's root and require
Python 3.10+ with no third-party packages. Clone the repository first if needed:

```bash
git clone --depth 1 https://github.com/sernote/audit-prompt-caching.git
cd audit-prompt-caching
```

## Bundled scripts

| Helper | Input and purpose |
|---|---|
| `extract_llm_calls.py` | Source/config directory → candidate call sites and settings to inspect |
| `layout_linter.py` | Rendered request JSON → known prefix-layout risks |
| `prefix_stability_check.py` | Two rendered requests → first difference and common prefix |
| `analyze_usage_logs.py` | Exported usage JSONL → cache accounting and normalized events |
| `estimate_cache_roi.py` | Explicit workload and price assumptions → estimated cost impact |
| `render_audit_report.py` | Usage plus supplied findings/statuses → an audit report |
| `analyze_routing_logs.py` | Normalized routing JSONL → linked decisions/outcomes; experimental |

Locate potential LLM calls in your project:

```bash
python3 audit-prompt-caching/scripts/extract_llm_calls.py path/to/project
```

This is a lexical locator only: snippets are always elided, but paths remain
visible. Matches may come from comments, dead code, or overridden configuration.
It never resolves active/effective values or source precedence. Open each
reported `path:line`, follow the active request path, and verify the resolved
runtime configuration.

Check a rendered payload or compare two requests:

```bash
python3 audit-prompt-caching/scripts/layout_linter.py path/to/rendered_request.json
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json \
  path/to/request_a.json path/to/request_b.json
```

The linter accepts Chat-style `messages` and Responses-style `input`. It checks
volatile early content, tool ordering, dynamic schema fields, GPT-5.6/GPT-6
Astra cache controls, and mid-conversation effort changes (`configuration_update`
items and Claude per-message `output_config.effort`). Existing examples:

```bash
python3 audit-prompt-caching/scripts/layout_linter.py \
  fixtures/layout/good_openai_request.json
python3 audit-prompt-caching/scripts/layout_linter.py \
  fixtures/layout/good_openai_responses_request.json
```

Effort examples live in `fixtures/layout/*effort_request.json`. The prefix
checker compares raw bytes by default so JSON key-order drift remains visible.
Use `--canonical-json` only when sorted-key normalization is intentional.
It returns exit `1` when the complete inputs differ, including a useful pair
with a long stable prefix. See the [prefix walkthrough](../examples/first-audit/README.md).

Analyze exported usage, or inspect the normalized records:

```bash
python3 audit-prompt-caching/scripts/analyze_usage_logs.py path/to/usage.jsonl
python3 audit-prompt-caching/scripts/analyze_usage_logs.py --jsonl-normalized \
  path/to/usage.jsonl
```

### Reporting and accounting

The renderer combines usage analysis with findings and statuses supplied by
the caller. For example, after inspecting the request path:

```bash
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
```

This is a command template: replace the paths, API label, planes and finding
with evidence from the actual project. The sample file/line is illustrative.

Pass `--cache-plane` once per layer in scope: `gateway_response`,
`provider_prompt`, `engine_kv`, `external_kv`, or `semantic_response`.
Use the [report dimensions](../audit-prompt-caching/references/report-template.md)
to record applicability, evidence, prefix stability, accounting, routing,
economics and isolation. Unset dimensions default to `unknown`; the renderer
derives `warning` or `fail` for usage accounting when its denominator is
ambiguous or invalid. The report emits no aggregate score.

If normalized usage has an `ambiguous` or `invalid` denominator, the hit ratio
and cost conclusions are marked as unsuitable for a savings decision
(`non-decision-grade`).
`--accounting-mode inclusive|additive`, supported by both the usage analyzer
and renderer, resolves wrapper semantics known from external evidence. It
cannot repair contradictory input: an `invalid` denominator still rejects
`--usage-accounting pass`.

Provider usage and billing exports remain authoritative. Missing cache fields
must remain unknown; an explicit zero is a different observation. See
[observability and accounting](../audit-prompt-caching/references/observability.md).

## Synthetic usage and ROI

The bundled usage fixture exercises the reporting helpers with synthetic data.
It is separate from the prefix-layout example and represents no live workload.

```bash
python3 audit-prompt-caching/scripts/analyze_usage_logs.py \
  fixtures/openai/repeated_prefix_usage.jsonl
```

| Signal | Fixture value |
|---|---:|
| Records reviewed | 3 |
| Input tokens | 15,600 |
| Cached tokens | 9,300 |
| Cache hit ratio | 59.62% |
| Output share | 7.17% |

Render the same fixture with a supplied explanatory finding:

```bash
python3 audit-prompt-caching/scripts/render_audit_report.py \
  --usage-log fixtures/openai/repeated_prefix_usage.jsonl \
  --provider openai \
  --engine "Responses API" \
  --finding "fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | synthetic cold-start record | the first fixture record has zero cached tokens by construction | treat it as demo input rather than a defect | use real repeated-call telemetry for conclusions"
```

The following is a separate cost model: 1,000 requests, 9,000 static input
tokens, 300 dynamic input tokens, 2,000 output tokens and a 71% assumed cache
hit rate. Prices are illustrative inputs, not a provider price quote.

```bash
python3 audit-prompt-caching/scripts/estimate_cache_roi.py \
  --static-tokens 9000 \
  --dynamic-tokens 300 \
  --output-tokens 2000 \
  --requests 1000 \
  --hit-rate 0.71 \
  --input-price-per-mtok 2.0 \
  --cached-input-price-per-mtok 0.2 \
  --output-price-per-mtok 8.0
```

Rounded calculation:

```text
Total cost: $34.60 -> $23.10
Total savings: 33.24%
Input savings: 61.84%
```

Neither the fixture nor the cost model demonstrates production savings.
Validate actual outcomes with provider usage, billing, route evidence and
latency measurements.

## Experimental routing evidence helper

The routing helper joins an existing normalized export by run, request and
attempt. It has no bundled native-log adapter; the complete capture-to-analysis
path still needs validation on a real deployment.

Try the synthetic example:

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py \
  fixtures/routing/slow-with-reuse.jsonl --attempt-ttft-limit-ms 500
```

It can show actual reuse alongside a client TTFT violation while preserving
missing evidence. That combination does not establish the cause of the delay.
The limit is for one attempt, not a percentile SLO or policy rollout decision.
Predictions retain their target worker, which may differ from the chosen worker.

- [Normalized JSONL contract](../audit-prompt-caching/references/routing-evidence.md)
- [Supported routing fixtures](../fixtures/routing/README.md)
- [Real-deployment capture requirements](routing-capture.md)
- [Recorded router observations](../examples/router-observation/recorded/2026-09-05/README.md)
- [Optional router/mock-worker reproduction](../examples/router-observation/README.md)

The recorded example uses standalone vllm-router and a synthetic HTTP worker.
It verifies API and metric boundaries without a GPU; it is not a KV benchmark
or comparison of routing policies.

## Evidence artifacts

For a real project, useful inputs include:

- Prompt builders, tool registries, schemas, history/compaction logic and active
  provider or deployment configuration.
- Representative rendered requests: Chat-style `messages`, Responses-style
  `input`, or the serialization actually sent by the application.
- Provider usage or billing exports with cache read/write fields.
- Per-step agent records with model, route, prefix/tool hashes, usage and latency.
- Worker and router observations when locality or self-hosted KV is in scope.

Fixtures demonstrate input shapes and exercise the helpers; they are not a
prerequisite for an audit. The skill does not capture live traffic by itself.
Export and redact representative records when telemetry is needed, using inputs
appropriate for your agent's configured data-processing settings.

Use this skill alongside existing gateway and observability tools. Related
projects include [LiteLLM](https://github.com/BerriAI/litellm),
[Langfuse](https://github.com/langfuse/langfuse),
[Helicone](https://github.com/Helicone/helicone) and the
[cache-audit skill](https://github.com/ussumant/cache-audit).
Their presence alone does not establish which cache layer or request path a
record describes; check the exported evidence.

## Example prompts

These use Codex's `$audit-prompt-caching` invocation. In another agent, ask it
to use the installed `audit-prompt-caching` skill by name. Add your actual paths
and symptom to the relevant scenario.

### OpenAI-compatible wrapper ambiguity

```text
Use $audit-prompt-caching to review this app. It imports the OpenAI SDK,
but base_url points to https://openrouter.ai/api/v1. We added
prompt_cache_key, provider.order, and openrouter/auto; cache_write_tokens
appears, but cached_tokens stays zero. Identify the actual provider and
routing path before diagnosing the cache behavior.
```

### Claude automatic caching writes every request

```text
Use $audit-prompt-caching to audit our Claude layout. We added top-level
cache_control to an 18k-token policy prompt, then append timestamp and
user question as the final content block. usage.cache_creation_input_tokens
increments every request, but cache_read_input_tokens stays zero.
```

### Bedrock Converse cross-region cachePoint

```text
Use $audit-prompt-caching to review this Bedrock Converse request.
cachePoint is placed after a user-specific intro, tools differ by route,
CacheWriteInputTokens is high, CacheReadInputTokens is near zero,
and some traffic uses cross-region inference.
```

### MCP tool registry drift

```text
Use $audit-prompt-caching to audit our coding agent. The MCP tool registry
is queried every step, tool order changes with plugin load timing,
read-only mode removes write tools, and compaction rewrites the first
user turn. Costs rose even though each step sends fewer tools.
```

### vLLM/SGLang multi-replica KV

```text
Use $audit-prompt-caching to inspect this self-hosted deployment.
vLLM/SGLang replicas sit behind a generic gateway, p99 prompt length
is 12k, max_model_len is 128k, prefix hashes look stable, but TTFT
spikes after scaling and prefix-cache metrics vary by replica.
```

### High cached tokens, low savings

```text
Use $audit-prompt-caching to explain why this workload still costs too
much. cached_tokens is high and TTFT improved, but responses average
4k output tokens, tool calls add seconds, TPM errors did not improve,
and finance wants to know whether prompt caching is the wrong lever.
```

## Validation

Run the repository checks:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
git diff --check
```

The [behavioral scenarios](../audit-prompt-caching/evals/evals.json) describe
expected audit behavior. The [trigger dataset](../audit-prompt-caching/evals/trigger_eval.json)
contains should-trigger and should-not-trigger queries. `run_trigger_eval.py`
checks that dataset's structure; it does not run an agent or measure trigger
accuracy. Agent evaluations need a separate baseline-versus-skill comparison.

CI also checks Python syntax and generated bytecode. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for the change workflow. The package keeps
its responsibilities in [SKILL.md](../audit-prompt-caching/SKILL.md),
[references](../audit-prompt-caching/references),
[scripts](../audit-prompt-caching/scripts) and [evals](../audit-prompt-caching/evals).
