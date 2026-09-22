# Cache Audit Evidence Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add traceable usage-field provenance, trustworthy denominator status, explicit cache planes, and a no-score Cache Clinic Summary without breaking existing analyzer/report consumers.

**Architecture:** Preserve the existing small hexagonal boundary. Provider adapters are anti-corruption layers that return canonical token values plus raw-field paths and accounting semantics. `normalize_record` validates and aggregates those values into a provider-neutral event contract. `render_audit_report.py` is a presentation adapter that consumes only the canonical summary and explicit CLI conclusions. No provider-specific logic belongs in the renderer, and no new parallel normalizer is introduced.

**Tech Stack:** Python 3.10+ standard library, `unittest`, JSON/JSONL fixtures, Markdown skill/reference files, plugin-eval 0.1.2.

---

## Task 1: Add provenance and denominator status to normalized usage

**Files:**

- Modify: `tests/test_prompt_cache_scripts.py:187-620`
- Modify: `audit-prompt-caching/scripts/analyze_usage_logs.py:59-588`
- Modify: `fixtures/expected/usage_summary_openai.json`

### Step 1: Write failing analyzer contract tests

Add focused tests that assert:

```python
self.assertEqual(event["schema_version"], 1)
self.assertEqual(
    event["source_fields"],
    {
        "input_tokens": "usage.input_tokens",
        "cached_tokens": "usage.input_tokens_details.cached_tokens",
        "cache_read_input_tokens": None,
        "cache_creation_input_tokens": None,
        "cache_write_tokens": None,
        "output_tokens": "usage.output_tokens",
    },
)
self.assertEqual(event["denominator_status"], "valid")
```

Cover these surfaces with their actual paths:

- OpenAI Responses and Chat inclusive usage;
- Anthropic additive usage;
- Bedrock `metrics.InputTokens` and Converse `usage.inputTokens`;
- Gemini Interactions stream `metadata.total_usage.*` and Generate Content `usageMetadata.*`;
- unknown recursive wrapper fields, both ambiguous by default and valid after `--accounting-mode`;
- an inclusive contradiction producing `denominator_status: invalid`;
- aggregate precedence `invalid > ambiguous > valid` and empty-input ambiguity.

Update the exact expected OpenAI summary fixture to include aggregate `denominator_status` only after the behavior exists.

### Step 2: Run the focused tests and witness RED

Run:

```bash
python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_analyze_usage_logs_can_emit_normalized_jsonl_events \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_analyze_usage_logs_marks_wrapper_accounting_ambiguous \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_analyze_usage_logs_warns_when_openai_breakdown_exceeds_input
```

Expected: FAIL because `schema_version`, `source_fields`, and `denominator_status` are absent.

### Step 3: Implement path-aware extraction at the provider boundary

Add small helpers rather than expanding `normalize_record`:

```python
CANONICAL_USAGE_FIELDS = (
    "input_tokens",
    "cached_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cache_write_tokens",
    "output_tokens",
)


def extracted_value(value, names, prefix):
    for name in names:
        if isinstance(value, dict) and name in value:
            return number(value[name]), ".".join((*prefix, name))
    return 0, None
```

Each adapter extraction must return both canonical values and exactly six source-path entries. Preserve the actual envelope chosen by `first_usage_envelope`; do not reconstruct a guessed path after extraction. Extend recursive unknown extraction with path-aware walking.

Avoid raw-record retention and do not include values in `source_fields`.

### Step 4: Implement denominator validation and aggregate precedence

Use a dedicated helper with a narrow contract:

```python
def denominator_status(row, semantics):
    if semantics == "ambiguous":
        return "ambiguous"
    if semantics == "inclusive" and any(
        row[field] > row["input_tokens"]
        for field in (
            "cached_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "cache_write_tokens",
        )
    ):
        return "invalid"
    return "valid"
```

Preserve `OPENAI_CACHE_BREAKDOWN_EXCEEDS_INPUT` for backward compatibility. Use a provider-neutral stable warning for an impossible inclusive breakdown on other adapters. Add `schema_version` only to normalized events, not to the aggregate summary.

Aggregate status with a constant precedence map; no records means `ambiguous`.

### Step 5: Run analyzer tests and witness GREEN

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: all tests pass.

### Step 6: Commit

```bash
git add audit-prompt-caching/scripts/analyze_usage_logs.py tests/test_prompt_cache_scripts.py fixtures/expected/usage_summary_openai.json
git commit -m "feat: add usage evidence provenance"
```

## Task 2: Add cache planes and a no-score clinic report

**Files:**

- Modify: `tests/test_prompt_cache_scripts.py:736-990`
- Modify: `audit-prompt-caching/scripts/render_audit_report.py:1-337`
- Modify: `fixtures/expected/report_openai.md`

### Step 1: Write failing report contract tests

Add JSON and Markdown tests for:

```python
result = run_script(
    "render_audit_report.py",
    "--usage-log", usage_path,
    "--cache-plane", "engine_kv",
    "--cache-plane", "provider_prompt",
    "--cache-plane", "provider_prompt",
    "--applicability", "pass",
    "--evidence-quality", "warning",
    "--prefix-stability", "fail",
    "--usage-accounting", "pass",
    "--json",
)
```

Assert canonical, deduplicated plane order and all seven dimensions. Assert Markdown includes `## Cache Clinic Summary`, renders `unknown` dimensions, and contains no `score`, `rank`, or grade field. Add CLI rejection tests for an invalid status and for `usage_accounting: pass` with ambiguous or invalid denominator evidence.

Add a test that an ambiguous/invalid denominator makes `expected_impact` explicitly non-decision-grade instead of reporting the hit ratio as confirmed savings evidence.

### Step 2: Run focused report tests and witness RED

Run:

```bash
python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_render_audit_report_outputs_markdown_from_usage_fixture \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_render_audit_report_outputs_json_from_usage_fixture
```

Expected: FAIL on missing CLI arguments and report fields.

### Step 3: Implement provider-neutral report helpers

Define constants and small helpers:

```python
CACHE_PLANES = (
    "gateway_response",
    "provider_prompt",
    "engine_kv",
    "external_kv",
    "semantic_response",
)
CLINIC_DIMENSIONS = (
    "applicability",
    "evidence_quality",
    "prefix_stability",
    "usage_accounting",
    "routing_locality",
    "economics",
    "isolation",
)
CLINIC_STATUSES = ("pass", "warning", "fail", "unknown", "not_applicable")
```

- Canonicalize planes by filtering `CACHE_PLANES`, not by preserving arbitrary CLI order.
- Initialize every clinic dimension to `unknown`.
- If denominator is `invalid` and usage accounting is unknown, resolve it to `fail`.
- If denominator is `ambiguous` and usage accounting is unknown, resolve it to `warning`.
- Reject an explicit `pass` for ambiguous or invalid evidence with `ValueError` so `argparse` exits 2.
- Do not derive any other clinic dimension.

Do not import provider names or inspect raw records in the renderer.

### Step 4: Render the new sections without an aggregate score

Add `cache_planes` and `clinic_summary` to JSON. In Markdown, render cache planes and all seven dimensions before findings. Render `Cache planes: unknown` when the list is empty.

Update `expected_impact` so ambiguous or invalid denominators block decision-grade hit-rate wording even when a numeric ratio exists.

### Step 5: Run report tests and witness GREEN

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: all tests pass.

### Step 6: Commit

```bash
git add audit-prompt-caching/scripts/render_audit_report.py tests/test_prompt_cache_scripts.py fixtures/expected/report_openai.md
git commit -m "feat: add cache clinic report contract"
```

## Task 3: Rewrite the skill contract with progressive disclosure

**Files:**

- Modify: `tests/test_prompt_cache_scripts.py:1560-1945`
- Modify: `audit-prompt-caching/evals/evals.json`
- Modify: `audit-prompt-caching/SKILL.md:1-309`
- Modify: `audit-prompt-caching/references/observability.md`
- Modify: `audit-prompt-caching/references/report-template.md`
- Modify: `README.md`

### Step 1: Write failing pressure-scenario tests

Add repository tests that require the combined skill, references, and evals to contain:

- all five cache planes and the instruction to identify in-scope planes;
- `schema_version`, `source_fields`, and `denominator_status` contract terms;
- the seven clinic dimensions and the explicit prohibition on an aggregate score;
- a stable-prefix plan based on rendered payload evidence, not assumed provider serialization;
- passive isolation reporting and no unauthorized active cross-tenant probes.

Add at least three eval pressure scenarios:

1. gateway response cache success but provider prompt-cache miss — must separate planes;
2. high numeric hit ratio from an unknown wrapper — must mark denominator/evidence ambiguous and avoid a savings claim;
3. incomplete audit evidence — must show unknown clinic dimensions and no aggregate score.

Add a frontmatter budget test that calls plugin-eval only in the final verification, not in every unittest. The unittest should instead assert the description is concise and preserves the positive/negative trigger phrases already protected by existing tests.

### Step 2: Run the new tests and witness RED

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
```

Expected: FAIL because the cache-plane, evidence-contract, and clinic-summary instructions are absent.

### Step 3: Make the smallest skill rewrite

Shorten the frontmatter description to at most 139 plugin-eval estimated tokens while preserving current trigger behavior.

In `SKILL.md`:

- add one compact cache-plane gate near applicability;
- add provenance/denominator evidence to the usage-analysis script description and quality bar;
- add the Cache Clinic Summary to output contracts;
- remove or consolidate repeated wording so invocation tokens do not exceed the 5,852-token baseline.

Put the detailed canonical event fields in `references/observability.md` and the detailed plane/status rendering contract in `references/report-template.md`. Do not add a new reference file.

Update README examples to demonstrate explicit `--cache-plane` and clinic status use without claiming an aggregate score.

### Step 4: Run package behavior checks and witness GREEN

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
```

Expected: all tests pass; package and trigger eval report `status: ok`.

### Step 5: Commit

```bash
git add audit-prompt-caching/SKILL.md audit-prompt-caching/references/observability.md audit-prompt-caching/references/report-template.md audit-prompt-caching/evals/evals.json README.md tests/test_prompt_cache_scripts.py
git commit -m "docs: define cache audit evidence workflow"
```

## Task 4: Compare static evaluation and complete verification

**Files:**

- Modify if needed: implementation files from Tasks 1-3
- Generate: `docs/superpowers/specs/2026-08-13-plugin-eval-after.json`
- Generate: `docs/superpowers/specs/2026-08-13-plugin-eval-after.md`
- Generate: `docs/superpowers/specs/2026-08-13-plugin-eval-compare.md`

### Step 1: Run plugin-eval after implementation

Run:

```bash
node /Users/notevskii/.codex/plugins/cache/openai-curated-remote/plugin-eval/0.1.2/scripts/plugin-eval.js \
  analyze audit-prompt-caching --format json \
  --output docs/superpowers/specs/2026-08-13-plugin-eval-after.json
node /Users/notevskii/.codex/plugins/cache/openai-curated-remote/plugin-eval/0.1.2/scripts/plugin-eval.js \
  analyze audit-prompt-caching --format markdown \
  --output docs/superpowers/specs/2026-08-13-plugin-eval-after.md
node /Users/notevskii/.codex/plugins/cache/openai-curated-remote/plugin-eval/0.1.2/scripts/plugin-eval.js \
  compare docs/superpowers/specs/2026-08-13-plugin-eval-before.json \
  docs/superpowers/specs/2026-08-13-plugin-eval-after.json \
  --format markdown \
  --output docs/superpowers/specs/2026-08-13-plugin-eval-compare.md
```

Expected: trigger estimate leaves the excessive band; invoked-skill estimate does not exceed 5,852 tokens. Any deferred-token increase is reported rather than hidden. The package-local test warning may remain and must be labeled as a layout heuristic, not a real missing-test defect.

### Step 2: Run full fresh verification

Run:

```bash
python3 -m unittest tests/test_prompt_cache_scripts.py
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'), *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
git diff --check
find . -name __pycache__ -type d -prune -exec rm -rf {} +
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```

Expected: all commands pass; the final `find` prints nothing.

### Step 3: Review the final branch

Perform two independent reviews against the design spec:

1. spec compliance — every acceptance criterion implemented, no out-of-scope active integration;
2. code quality — backward compatibility, provider math, source-path accuracy, CLI failure behavior, and complexity.

Fix all critical and important findings with a new RED/GREEN test before claiming completion.

### Step 4: Commit durable review artifacts

```bash
git add docs/superpowers/specs docs/superpowers/plans/2026-08-13-cache-audit-report-contract.md
git commit -m "docs: record cache audit contract evaluation"
```
