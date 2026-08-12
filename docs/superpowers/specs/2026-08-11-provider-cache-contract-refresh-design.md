# Provider Cache Contract Refresh — Design

## Goal

Bring the `audit-prompt-caching` skill in line with the cache contracts verified on 2026-08-11, without presenting provider-specific fields as interchangeable.

## Scope

- Normalize current Bedrock lower-camel response usage and Gemini Interactions cache-read usage.
- Refresh direct-provider references for Azure OpenAI, Bedrock, Gemini, Anthropic, OpenRouter, Qwen, DeepSeek, z.ai, vLLM, and SGLang.
- Extend provider detection and agent guidance for session/cache-routing handles, cache diagnostics, reasoning continuity, and multi-tier KV observability.
- Add behavioral tests for every parser or detector change, and trigger/eval coverage for new cache-audit paths.

## Non-goals

- Do not bake volatile prices or full model availability matrices into scripts.
- Do not add network dependencies or live-traffic collection.
- Do not turn prompt-cache guidance into response-cache guidance; OpenRouter response caching is only identified as a confounder.

## Architecture

The normalizer remains a provider-shape adapter. Bedrock lower-camel API payloads are classified as additive accounting, while Gemini Interactions cache reads remain inclusive and use `usage.total_cached_tokens` as the cache-read count. Unknown wrappers retain the existing ambiguous-accounting warning.

Provider references remain the authoritative semantic layer. Each update states surface boundaries, cache-read/write fields, routing/TTL constraints, and a safe validation action. Agent checks use opaque keyed hashes and handle kinds rather than raw session or cache-key values.

## Data Flow

```text
raw usage/request/config
  -> shape detection and normalization
  -> provider-aware accounting semantics
  -> provider reference and audit checks
  -> evidence-bearing report, telemetry, and CI guidance
```

## Verification

- Test-first unit coverage proves every newly recognized usage shape and detector signal.
- Full unittest suite, package validation, trigger evaluation, syntax compilation, and whitespace check pass.
- A final independent Claude review checks documentation claims against current official sources and the diff.
