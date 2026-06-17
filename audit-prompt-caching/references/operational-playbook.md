# Quick Operational Playbook

Last reviewed: 2026-05-25. Use for fast triage; do not bypass provider-specific source checks.

## First Decision

| Symptom | First check | Usually load next |
|---|---|---|
| low cache hit rate | prefix length, first divergence, read/write fields | provider ref + `references/observability.md` |
| high bill with good hit rate | output share, write premium, cadence | `references/economics.md` |
| migration regression | source/target cache semantics, layout, fields | both provider refs |
| provider wrapper ambiguity | actual routed provider/model and transformed body | wrapper ref before generic provider |
| TTL or retention question | cadence, write/read ratio, TTL/price | provider ref |

## Stable Prefix Layout

```text
stable tools and schemas
stable system/developer instructions
stable examples or reusable documents
append-only conversation anchor
late dynamic user, tenant, request, time, trace, and tool-result data
```

Sort tools/schema keys; put request IDs, timestamps, `cwd`, live `git status`, tenant/user facts, trace IDs, and A/B labels after the stable prefix or in supported metadata. For provider wrappers, inspect the final provider-visible payload.

## Multi-Turn And Sliding

Append-only growth can support sliding reuse:

```text
stable prefix + user_1
stable prefix + user_1 + assistant_1 + user_2
```

Compaction rewrites can change the cache family. Prefer raw history, then compact bulky tool results, then summarize only after preserving the stable anchor. Provider details such as Anthropic automatic breakpoints, 20-block lookback, OpenAI `prompt_cache_key`, Gemini cached content, and vLLM/SGLang tokenization must be verified in official docs.

## What To Do First

1. Capture one hot prompt family and two consecutive rendered requests.
2. Log provider cache read/write fields, input/output tokens, TTFT or prefill, final latency, route/model/region, prompt/tool/schema hashes.
3. Compare rendered prefix bytes before changing prompts.
4. Determine write-without-read, read-with-low-savings, or no cache fields.
5. Make the smallest reversible change: measurement, then layout, then routing/provider settings.

Official docs: OpenAI prompt caching, Anthropic prompt caching, Gemini context caching, and vLLM prefix caching.
