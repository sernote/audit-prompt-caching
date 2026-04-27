# Audit Prompt Caching Skill

`audit-prompt-caching` is a portable agent skill for auditing LLM prompt and prefix cache behavior: cache misses, `cached_tokens=0`, TTFT regressions, OpenRouter routing issues, Bedrock cache checkpoints, agent tool-routing costs, provider migration risk, and vLLM/SGLang deployment issues.

The skill is based on a Habr article series about prompt-cache economics, common anti-patterns, and dynamic tools in agent loops.

## Who It Is For

- AI engineers debugging prompt-cache misses or long TTFT
- backend engineers building LLM request paths
- agent developers working with tools, MCP, compaction, or coding assistants
- platform/SRE engineers running vLLM, SGLang, or multi-replica inference
- teams comparing providers or estimating effective LLM cost

## What It Audits

- Prompt-cache applicability before recommending changes
- Stable prompt prefix layout
- Volatile data in system prompts and early messages
- Non-deterministic tool/schema serialization
- Dynamic tool sets inside agent loops
- History truncation, compaction, and summarization
- Cache-aware routing for managed and self-hosted inference
- OpenRouter sticky routing, provider fallback, and cache read/write fields
- Amazon Bedrock cache checkpoints and read/write fields
- Prefill vs decode latency and output-token cost share
- KV-cache budget, eviction, and deployment config
- Provider-specific usage fields and docs freshness
- ROI assumptions across static, dynamic, and output tokens
- CI/smoke-test readiness for stable prefix drift

## Install Or Share

The portable skill folder is:

```text
audit-prompt-caching/
```

Copy that folder into the target agent's skills directory. Keep the folder name aligned with the `name` field in `audit-prompt-caching/SKILL.md`.

## Works With

This package is authored as a Codex skill, but the folder is intentionally portable: `SKILL.md` is the entry point, `references/` holds selectively loaded context, and `scripts/` are dependency-free helpers. Manual `$audit-prompt-caching` invocation is optional; the frontmatter description and trigger evals are designed for natural prompts such as `cached_tokens у меня нулевой`.

### Codex

Install:

```bash
mkdir -p ~/.codex/skills
cp -R audit-prompt-caching ~/.codex/skills/audit-prompt-caching
```

Restart Codex so it reloads installed skills. Natural trigger: `cached_tokens у меня нулевой, хотя system prompt повторяется`.

### Claude Code

Install by copying the portable folder into the local skills directory used by your Claude Code setup, preserving the folder name:

```bash
cp -R audit-prompt-caching <claude-code-skills-dir>/audit-prompt-caching
```

If your setup uses project-local instructions instead of a global skills directory, reference `audit-prompt-caching/SKILL.md` from the project instructions and keep `references/` plus `scripts/` next to it.

### Cursor

Use the skill as a project-local rule pack: copy `audit-prompt-caching/` into the repository and point Cursor rules or agent instructions at `audit-prompt-caching/SKILL.md`. Keep the folder layout intact so references and scripts resolve by relative path.

### Continue

Use the skill as reusable agent context: copy `audit-prompt-caching/` into a shared prompts/rules directory and include `audit-prompt-caching/SKILL.md` in the Continue assistant configuration. Keep `references/` and `scripts/` available beside the skill file.

## Example Prompts

```text
cached_tokens у меня нулевой, хотя system prompt на 8k токенов повторяется в каждом OpenAI Responses API request.
```

```text
Our coding agent started selecting only 5 tools per step, and total cost went up instead of down.
```

```text
TTFT spiked after scaling vLLM from 1 to 4 pods; prefix cache hit rate collapsed.
```

```text
OpenRouter shows cache_write_tokens, but cached_tokens stays zero after we added provider.order and openrouter/auto.
```

```text
Bedrock Converse has high CacheWriteInputTokens but low CacheReadInputTokens.
```

```text
Compare Anthropic and OpenAI for this RAG workload using static tokens, output tokens, hit rate, and migration risk.
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
    predeploy-checklist.md
    report-template.md
    qwen.md
    yandexgpt.md
    zai.md
    use-cases.md
  scripts/
    analyze_usage_logs.py
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
  openai/
  anthropic/
  bedrock/
  openrouter/
  vllm/
  expected/
```

## Bundled Scripts

The skill includes small dependency-free helpers for repeatable audits:

```bash
python3 audit-prompt-caching/scripts/extract_llm_calls.py .
python3 audit-prompt-caching/scripts/layout_linter.py fixtures/layout/good_openai_request.json
python3 audit-prompt-caching/scripts/prefix_stability_check.py before.json after.json
python3 audit-prompt-caching/scripts/analyze_usage_logs.py usage.jsonl
python3 audit-prompt-caching/scripts/analyze_usage_logs.py --jsonl-normalized usage.jsonl
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
  --usage-log fixtures/openai/repeated_prefix_usage.jsonl \
  --provider openai \
  --engine "Responses API" \
  --finding "fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | cold request has zero cached tokens | first request pays full prefill | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase"
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

`prefix_stability_check.py` compares raw bytes by default so JSON key-order drift is visible. Use `--canonical-json` only when sorted-key normalization is intentional.

Provider usage metadata and billing exports remain authoritative; these scripts are audit aids.

## Five-Minute Demo

Run the bundled fixture pack to see the audit loop without production logs:

```bash
python3 audit-prompt-caching/scripts/analyze_usage_logs.py \
  fixtures/openai/repeated_prefix_usage.jsonl

python3 audit-prompt-caching/scripts/analyze_usage_logs.py \
  --jsonl-normalized \
  fixtures/openai/repeated_prefix_usage.jsonl

python3 audit-prompt-caching/scripts/render_audit_report.py \
  --usage-log fixtures/openai/repeated_prefix_usage.jsonl \
  --provider openai \
  --engine "Responses API" \
  --finding "fixtures/openai/repeated_prefix_usage.jsonl:1 | low | openai | cold request has zero cached tokens | first request pays full prefill | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase"

python3 audit-prompt-caching/scripts/layout_linter.py \
  fixtures/layout/good_openai_request.json
```

Compare the rendered Markdown with `fixtures/expected/report_openai.md` for the expected report shape.

## Validation

Validate the skill package with the bundled validator:

```bash
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

The repository also includes JSON eval prompts:

- `audit-prompt-caching/evals/evals.json`: behavioral audit scenarios
- `audit-prompt-caching/evals/trigger_eval.json`: should-trigger and should-not-trigger queries

Run the local script/package tests:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

These evals are a starting point. A full proof cycle should still compare baseline agent behavior against behavior with the skill enabled.

## Project Quality Gates

CI runs the unittest suite, package validator, trigger eval, Python syntax compile, whitespace check, and generated-bytecode guard. Keep new scripts stdlib-only and add fixture-backed tests for behavior changes.

## License

MIT. See `LICENSE`.

## Freshness Policy

Provider cache behavior changes. The skill treats bundled provider references as heuristics and instructs the agent to verify official docs before exact claims about pricing, TTL, model support, field names, cache-control semantics, or routing hints.
