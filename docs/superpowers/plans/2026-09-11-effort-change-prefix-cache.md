# Effort changes without prefix-cache loss (Claude Fable 5.1, GPT-6 Astra)

Date: 2026-09-11

Both providers now document a way to change reasoning/effort mid-conversation
without restarting the prefix cache. The skill previously treated any effort
change as undocumented and only covered GPT-5.6 cache controls.

Verified sources (2026-09-11):

- Anthropic prompt caching, effort, thinking, mid-conversation system messages,
  and "What's new in Claude Fable 5.1" pages on platform.claude.com.
- OpenAI: `developers.openai.com` was unreachable from this environment. The
  GPT-6 Astra guide text was read from the copy vendored in the openai/codex
  repository (`upgrading-to-gpt-6-astra.md`) and the `openai-python` SDK types
  (`ResponseConfigurationUpdateItemParam`, `PromptCacheOptions`, `Reasoning`).
  Prices and long-context thresholds for Astra come only from third-party
  pages and are therefore recorded as unverified.

## 1. Linter

Files: `audit-prompt-caching/scripts/layout_linter.py`, `tests/test_prompt_cache_scripts.py`.

- Extend the direct explicit-cache model set with `gpt-6` and `gpt-6-astra`;
  `cache_policy.model_support` reports the matched family.
- Add `lint_effort_continuity` (rule `AP-15`):
  - OpenAI `configuration_update` input items on a model that is not GPT-6
    Astra, or together with `reasoning.mode: "pro"`, or carrying anything
    other than `reasoning.effort`.
  - Anthropic `role: "system"` messages carrying `output_config` on a model
    without per-message effort.
- Emit an `effort_policy` block with request-level effort and per-message
  effort item counts so audits can correlate with usage telemetry.

TDD: failing tests first, then minimal implementation.

## 2. Fixtures

`fixtures/layout/good_openai_astra_effort_request.json`,
`fixtures/layout/bad_openai_astra_effort_request.json`,
`fixtures/layout/good_anthropic_effort_request.json`,
`fixtures/layout/bad_anthropic_effort_request.json`.

## 3. Rules and references

- `references/rules.json`: add `AP-15` (effort/reasoning continuity).
- `references/anthropic.md`: Claude 5 family snapshot (512-token minimum,
  0.025x cache reads on Fable 5.1/Mythos 5.1, per-message effort beta,
  turn-scoped system messages, mid-conversation tool changes, thinking block
  binding, invalidation table).
- `references/openai.md`: GPT-6 Astra snapshot (`configuration_update`,
  pro-mode rejection, `prompt_cache_options.comparison_response_id`, SDK
  lookback statement, unverified pricing).
- `references/agent-tools.md`: effort changes as cache-relevant state.
- `scripts/extract_llm_calls.py`: lexical signals for `configuration_update`,
  `output_config`, and the per-message effort beta header.

## 4. Skill surface

`SKILL.md` triggers, playbook entry for mid-conversation effort changes,
rule inventory AP-1..AP-15, linter description. Add trigger and behavior evals.

## 5. Budgets

The frontmatter description is frozen at its measured 147-token ceiling and
every phrase in it is test-anchored, so the new triggers live in the body only.
Remeasured after this change: SKILL.md 6676 estimated tokens (was 6394),
deferred corpus 65570 (was 60163). Both constants are updated in
`tests/test_prompt_cache_scripts.py` with this plan as the reference.

## 6. Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
git diff --check
```
