# Quick Operational Playbook

Last reviewed: 2026-05-25.

Use this reference when the user needs a fast, practical path through a prompt-cache incident or design review. It complements the deeper provider references; do not use it to bypass provider-specific source checks.

## First Decision

Classify the request before recommending changes:

| Symptom | First check | Usually load next |
|---|---|---|
| low cache hit rate | repeated prefix length, first divergent prefix byte/token, cache read/write fields | provider reference plus `references/observability.md` |
| high bill with good hit rate | output-token share, dynamic input, write premium, traffic cadence | `references/economics.md` |
| migration regressed cache | source/target cache semantics, prefix order, thresholds, usage fields | both provider references |
| wrapper or gateway ambiguity | actual routed provider/model, transformed request body, cache fields | router or wrapper reference before generic provider docs |
| TTL or retention question | repeat cadence, write/read ratio, storage or write premium | provider reference and official docs |

For every path, decide whether caching is applicable before optimizing. A route that is short, rare, mostly unique, dominated by output/tool latency, or constrained by isolation policy may need measurement or a different optimization instead.

## Stable Prefix Layout

The durable shape is:

```text
stable tools and schemas
stable system/developer instructions
stable examples or reusable documents
append-only conversation anchor
late dynamic user, tenant, request, time, trace, and tool-result data
```

Exact provider serialization differs, but the audit question is the same: what bytes or token IDs are identical at the beginning of the requests that should reuse cache? Dynamic values before that shared prefix split the cache family.

Keep these rules explicit:

- Sort tool definitions and schema keys when local code controls serialization.
- Put request IDs, timestamps, `cwd`, live `git status`, user profile facts, trace IDs, and A/B labels after the stable prefix or in supported metadata.
- Version prompt families intentionally; do not let invisible middleware create dozens of unplanned prompt versions.
- For provider wrapper calls, inspect the final provider-visible payload before trusting visible app-level prompt text.

## Multi-Turn And Sliding Breakpoints

For append-only chat or agent loops, old turns stay in place and new turns append at the end:

```text
turn 1: stable prefix + user_1
turn 2: stable prefix + user_1 + assistant_1 + user_2
turn 3: stable prefix + user_1 + assistant_1 + user_2 + assistant_2 + user_3
```

This can support sliding cache reuse when the earlier prefix is not rewritten. If compaction rewrites early turns, the cache family changes. Prefer raw history while it fits, then compact bulky tool results, and use lossy summaries only after the stable anchor is protected.

Provider-specific notes to verify in official docs before exact advice:

- Anthropic: top-level automatic caching can move the breakpoint forward in multi-turn conversations, while explicit block-level breakpoints are better when a stable prefix is followed by a varying suffix.
- Anthropic: explicit breakpoints are limited and the lookback window can miss old writes in long block-heavy conversations; add stable breakpoints before they are needed.
- OpenAI: prompt caching is automatic for eligible long prompts; `prompt_cache_key` is a routing hint, not a privacy boundary or prefix-stability fix.
- Gemini: implicit caching is automatic on supported models, while explicit cached content has its own lifecycle and billing surface.
- vLLM/SGLang: visible text is not enough; tokenizer, chat template, adapter, multimodal hashes, routing, and KV capacity can decide reuse.

## What To Do First

For a production incident:

1. Capture one hot prompt family and two representative consecutive requests.
2. Log provider cache read/write fields, total input, output, TTFT or prefill latency, final latency, route/model/region, and prompt/tool/schema hashes.
3. Compare rendered prefix bytes or token IDs before changing prompts.
4. Check whether cache writes happen without later reads, reads happen but costs stay high, or no cache fields appear at all.
5. Make the smallest reversible change: measurement first, then layout, then routing or provider settings.

Do not start by adding cache controls everywhere, pinning a provider, forcing a longer TTL, or broadening cross-tenant reuse. Those can be correct only after the applicable route, trust boundary, cadence, and provider semantics are known.

## Official Source Checks

Provider facts change. Verify exact model names, thresholds, field names, TTL/retention options, storage/write premiums, and privacy posture from official docs before final advice:

- OpenAI prompt caching: https://developers.openai.com/api/docs/guides/prompt-caching
- Anthropic prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Gemini context caching: https://ai.google.dev/gemini-api/docs/caching
- vLLM prefix caching: https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html
