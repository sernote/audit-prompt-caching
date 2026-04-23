# Audit Prompt Caching Skill

`audit-prompt-caching` is a Codex/agent skill for auditing LLM prompt and prefix cache behavior: cache misses, `cached_tokens=0`, TTFT regressions, OpenRouter/provider-routing issues, agent tool-routing costs, provider migration risk, and vLLM/SGLang deployment issues.

The skill is based on a Habr article series about prompt-cache economics, common anti-patterns, and dynamic tools in agent loops.

## Who It Is For

- AI engineers debugging prompt-cache misses or long TTFT
- backend engineers building LLM request paths
- agent developers working with tools, MCP, compaction, or coding assistants
- platform/SRE engineers running vLLM, SGLang, or multi-replica inference
- teams comparing providers or estimating effective LLM cost

## What It Audits

- Stable prompt prefix layout
- Volatile data in system prompts and early messages
- Non-deterministic tool/schema serialization
- Dynamic tool sets inside agent loops
- History truncation, compaction, and summarization
- Cache-aware routing for managed and self-hosted inference
- OpenRouter sticky routing, provider fallback, and cache read/write fields
- KV-cache budget, eviction, and deployment config
- Provider-specific usage fields and docs freshness

## Install Or Share

The portable skill folder is:

```text
audit-prompt-caching/
```

Copy that folder into the target agent's skills directory. Keep the folder name aligned with the `name` field in `audit-prompt-caching/SKILL.md`.

## Example Prompts

```text
Use $audit-prompt-caching to audit this OpenAI app. cached_tokens stays at 0 even though the system prompt is 8k tokens.
```

```text
Use $audit-prompt-caching to review our coding agent. We started selecting only 5 tools per step and total cost went up.
```

```text
Use $audit-prompt-caching to inspect this vLLM deployment. TTFT spiked after scaling from 1 to 4 pods.
```

```text
Use $audit-prompt-caching to audit our OpenRouter app. cache_write_tokens appears, but cached_tokens stays zero after we added provider.order and openrouter/auto.
```

```text
Use $audit-prompt-caching to compare Anthropic and OpenAI for this RAG workload using static tokens, output tokens, hit rate, and migration risk.
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
    agent-tools.md
    sglang.md
    vllm.md
    deepseek.md
    economics.md
    gemini.md
    predeploy-checklist.md
    qwen.md
    yandexgpt.md
    zai.md
    use-cases.md
  evals/
    evals.json
    trigger_eval.json
```

## Validation

Validate the skill package with the Anthropic/Codex skill validator when available:

```bash
python3 quick_validate.py audit-prompt-caching
```

The repository also includes JSON eval prompts:

- `audit-prompt-caching/evals/evals.json`: behavioral audit scenarios
- `audit-prompt-caching/evals/trigger_eval.json`: should-trigger and should-not-trigger queries

These evals are a starting point. A full proof cycle should still compare baseline agent behavior against behavior with the skill enabled.

## Freshness Policy

Provider cache behavior changes. The skill treats bundled provider references as heuristics and instructs the agent to verify official docs before exact claims about pricing, TTL, model support, field names, cache-control semantics, or routing hints.
