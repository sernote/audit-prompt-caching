# Provider prefix-cache refresh (September 2026)

> **For agentic workers:** Use superpowers:executing-plans for this approved refresh.

**Goal:** Re-verify every supported non-OpenAI/Anthropic provider reference
against official docs as of 2026-09-12, encode changed prefix-cache behavior,
refresh the OpenRouter router reference, and add the most-used OpenRouter model
vendors that the skill did not cover yet.

**Architecture:** One commit per provider so each delta is reviewable on its
own. References carry the facts; `extract_llm_calls.py` gains detection
signals only where a new provider or endpoint needs it; `analyze_usage_logs.py`
gains an adapter only when a usage shape is not already normalized. Evals and
tests lock in the new anchors. Package token ceilings are remeasured per commit
rather than compressing established guidance.

**Tech stack:** Markdown references, Python stdlib scripts, unittest.

## Steps

- [ ] z.ai: model list, preserved-thinking (`clear_thinking`) cache coupling,
  endpoint defaults, Coding Plan routing/credits, cached-input pricing shape.
- [ ] Azure OpenAI: GPT-5.6+ `prompt_cache_options`/`prompt_cache_breakpoint`,
  `cache_write_tokens`, paid writes, `prompt_cache_retention` for pre-5.6,
  `prompt_cache_key` rate cap, PTU-M limits, canonical Foundry URLs.
- [ ] Bedrock: implicit vs explicit taxonomy, `cacheDetails`, cumulative
  tools->system->messages minimum, 512-token Claude 5.x tier, Nova limits,
  OpenAI Responses inclusive accounting on `bedrock-runtime`/`bedrock-mantle`.
- [ ] Qwen/DashScope: message-level breakpoints for Qwen3.5+, explicit/implicit
  exclusivity, 20-content-block gap miss, Responses `input_tokens_details`
  and `cache_type`, non-standard Qwen3.8 pricing, regional workspace URLs.
- [ ] DeepSeek, Gemini, YandexGPT: apply verified deltas or record "no change".
- [ ] OpenRouter: apply verified deltas and refresh per-provider caching table.
- [ ] New vendors from OpenRouter usage rankings: reference, detection signals,
  usage adapter where the wire shape is new, evals, tests.
- [ ] Remeasure `PLUGIN_EVAL_DEFERRED_TOKEN_CEILING` and SKILL baseline; run
  the full verification commands from `AGENTS.md`.

## Acceptance

Every touched reference has `Last reviewed: 2026-09-12`, cites the official
source used, and marks unverified facts as such. Tests, package validation, and
trigger eval pass after each commit.
