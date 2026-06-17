# Vercel AI SDK Prefix Cache Reference

Last reviewed: 2026-05-26. Verify installed `ai` and `@ai-sdk/<provider>` majors before exact claims about endpoints, `providerOptions`, telemetry fields, `experimental_providerMetadata`, `convertToModelMessages`, `experimental_prepareStep`, or `stopWhen`.

Official sources:
- AI SDK Core: https://ai-sdk.dev/docs/ai-sdk-core
- Anthropic provider: https://ai-sdk.dev/providers/ai-sdk-providers/anthropic
- OpenAI provider: https://ai-sdk.dev/providers/ai-sdk-providers/openai
- Bedrock provider: https://ai-sdk.dev/providers/ai-sdk-providers/amazon-bedrock
- Google provider: https://ai-sdk.dev/providers/ai-sdk-providers/google-generative-ai
- Issue #14170: https://github.com/vercel/ai/issues/14170
- Issue #15185: https://github.com/vercel/ai/issues/15185

## Mechanics

Vercel AI SDK is a wrapper. Provider cache semantics come from the underlying API; the SDK affects which endpoint is used, where provider-specific directives land on the wire, and how cache telemetry surfaces.

Detect it before direct-provider advice:

```bash
rg -n "@ai-sdk/|from ['\"]ai['\"]|providerOptions|experimental_providerMetadata|convertToModelMessages|convertToCoreMessages|experimental_prepareStep|stopWhen|streamText|generateText|generateObject|streamObject" .
```

Pin versions with `node -p "require('./node_modules/ai/package.json').version"` and the relevant provider package versions.

## Audit Checklist

- OpenAI endpoint can differ by major/version and factory. Check whether `openai(model)`, `openai.chat(model)`, or `openai.responses(model)` is used before reading `cached_tokens`.
- If OpenAI Responses is used and cache reads are zero, check whether `promptCacheKey` is set at route/prompt-family granularity; avoid per-user keys for shared content.
- Anthropic `cacheControl` placement depends on field shape. Portable form is `messages[]` or content parts with `providerOptions` on the exact block; top-level call-site shortcuts must be verified in telemetry.
- `convertToModelMessages` does not invent provider options absent from UI messages; reattach cache control server-side after conversion.
- Tool-result `providerOptions` were dropped before `ai@6`; upgrade before tuning tool-result caching. See issue #15185.
- `experimental_prepareStep` or `prepareStep` that changes `tools` or `activeTools` rewrites the cacheable prefix. See issue #14170.
- `generateObject` schema construction is cache-safe only when schema text is module-level and stable; dynamic `.describe()`, request IDs, tenant fields, or timestamps make schemas volatile.
- `streamText` / `streamObject` expose cache fields after stream completion; await usage/provider metadata.

## Diagnostics

Relevant v5 paths include:

```ts
result.usage.inputTokenDetails?.cacheReadTokens
result.usage.inputTokenDetails?.cacheWriteTokens
result.providerMetadata?.anthropic?.cacheReadInputTokens
result.providerMetadata?.anthropic?.cacheCreationInputTokens
result.providerMetadata?.openai?.cachedPromptTokens
```

When SDK fields disagree with raw provider usage, raw wire response is authoritative. Wrap `fetch` to log request body and parsed response usage, especially to confirm `cache_control` location and whether OpenAI calls Chat Completions or Responses.

Track package versions, selected factory, wire `cache_control` / `prompt_cache_key`, cache-control location, raw provider cache fields, SDK cache fields, and `tools_count` per step.
