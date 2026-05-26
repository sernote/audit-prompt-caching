# Vercel AI SDK Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-05-26.

Verify before exact claims:
- which API endpoint the `@ai-sdk/openai` factory selects in the installed major version (`openai(model)` vs `openai.chat(model)` vs `openai.responses(model)`)
- `providerOptions` shape for the installed `@ai-sdk/anthropic`, `@ai-sdk/openai`, `@ai-sdk/amazon-bedrock`, `@ai-sdk/google` versions
- whether `experimental_providerMetadata` is still accepted, deprecated, or removed
- telemetry field path on `result.usage` and `result.providerMetadata` for the installed major version
- `convertToModelMessages` / `convertToCoreMessages` behavior for `providerOptions` carry-over
- `experimental_prepareStep` and `stopWhen` signatures and the open status of issue #14170

Official sources:
- AI SDK Core: https://ai-sdk.dev/docs/ai-sdk-core
- Anthropic provider: https://ai-sdk.dev/providers/ai-sdk-providers/anthropic
- OpenAI provider: https://ai-sdk.dev/providers/ai-sdk-providers/openai
- Bedrock provider: https://ai-sdk.dev/providers/ai-sdk-providers/amazon-bedrock
- Google provider: https://ai-sdk.dev/providers/ai-sdk-providers/google-generative-ai
- Issue #14170 (prepareStep busts cache): https://github.com/vercel/ai/issues/14170
- Issue #15185 (tool-result providerOptions dropped pre-v6): https://github.com/vercel/ai/issues/15185

## Stable Mechanics

Vercel AI SDK is a client wrapper, not a model provider. Cache semantics come from the underlying provider; the SDK's contribution is where it places provider-specific directives on the wire and how it surfaces cache telemetry to the caller. Both can change across `ai` and `@ai-sdk/<provider>` major versions; pin the installed versions before reading the rest of this reference.

Provider-cache mechanics for the underlying API live in `references/anthropic.md`, `references/openai.md`, `references/bedrock.md`, and `references/gemini.md`. This reference covers only the wrapper layer.

## Provider Checks

### Detect Vercel AI SDK Before Generic Provider

`@ai-sdk/openai` and `@ai-sdk/anthropic` look like the direct provider SDKs but route through `ai`. The wire body and telemetry fields can differ from the direct-SDK case. Load this reference first, then the provider reference for wire mechanics.

```bash
rg -n "@ai-sdk/|from ['\"]ai['\"]|providerOptions|experimental_providerMetadata|convertToModelMessages|convertToCoreMessages|experimental_prepareStep|stopWhen|streamText|generateText|generateObject|streamObject" .
```

Pin the major versions before recommending field names:

```bash
node -p "require('./node_modules/ai/package.json').version"
node -p "require('./node_modules/@ai-sdk/anthropic/package.json').version"
node -p "require('./node_modules/@ai-sdk/openai/package.json').version"
```

### OpenAI Default Factory Changed Endpoint Between v4 And v5

For identical caller code, the default `openai(modelId)` factory targets different REST endpoints in different majors:

| Stack | Factory used | Endpoint |
|---|---|---|
| v4 default | `openai('gpt-4o-mini')` | `POST /v1/chat/completions` |
| v5 default | `openai('gpt-4o-mini')` | `POST /v1/responses` |
| explicit | `openai.chat('gpt-4o-mini')` | `POST /v1/chat/completions` |
| explicit | `openai.responses('gpt-4o-mini')` | `POST /v1/responses` |

OpenAI's prefix-cache lookup on the Responses API does not engage on its own — it requires `prompt_cache_key`. On Chat Completions the lookup is automatic. After a v4 → v5 upgrade without code changes, OpenAI `cached_tokens` typically drops to zero because the default endpoint moved to Responses while `promptCacheKey` was not set.

Audit grep:

```bash
rg -n "openai\(['\"]|openai\.chat\(|openai\.responses\(|promptCacheKey|promptCacheRetention" .
```

Safe first action when telemetry shows OpenAI `cached_tokens == 0` after a v5 upgrade: add `providerOptions: { openai: { promptCacheKey: '<route-name>' } }` to the call. Per-user keys destroy cross-user reuse; prefer route- or prompt-family-level keys.

### Anthropic cacheControl Placement Depends On The Field Shape

Where the SDK puts `cache_control` on the wire depends on which surface carries `providerOptions`:

| Source code shape | v4 wire | v5 wire |
|---|---|---|
| `system: 'string'`, no `providerOptions` | no `cache_control` | no `cache_control` |
| `system: 'string'` + top-level `providerOptions.anthropic.cacheControl` | no `cache_control` (silently dropped) | `cache_control` at top level of the request body (not on a block) |
| `messages: [{ role: 'system', content: '...', providerOptions: { anthropic: { cacheControl: {...} } } }]` | on the system block | on the system block |
| `messages: [{ role: 'user', content: [{ type: 'text', text, providerOptions: {...} }, ...] }]` | on the text part | on the text part |
| `tool({ ..., experimental_providerMetadata: { anthropic: { cacheControl: {...} } } })` | no `cache_control` (silently dropped) | n/a |
| `tool({ ..., providerOptions: { anthropic: { cacheControl: {...} } } })` | n/a in v4 typings | on the tool definition |

The v5 top-level placement for the `system: 'string'` case is not in the public Anthropic API spec. Anthropic currently accepts it. The canonical pattern (`messages[]` with `providerOptions` on the specific block) is the only form portable across SDK versions and across providers. Audit recommendation:

- accept `system: 'string' + cacheControl` only when telemetry on the installed versions confirms it works
- recommend rewriting to `messages[]` with a system-role message for any load-bearing breakpoint

Audit grep:

```bash
rg -n "system\s*:\s*['\"\\\\]|providerOptions|experimental_providerMetadata|cacheControl|cache_control" .
```

### convertToModelMessages Does Not Carry providerOptions

`UIMessage[]` (what `useChat` produces on the client) has no `providerOptions` slot. `convertToModelMessages(messages)` on the server transforms to `ModelMessage[]` but does not invent `providerOptions` that did not exist on the input. Re-attach `cacheControl` on the server after conversion, not in the client component.

### Tool-Result providerOptions Was Dropped Pre-v6

Fixed in `ai@6.x`. On older majors `providerOptions` on a tool-result message is silently absent from the wire. If a codebase caches tool results and `cache_write_tokens` stays zero on tool-result-heavy prompts, upgrade `ai` before further tuning. See https://github.com/vercel/ai/issues/15185.

### experimental_prepareStep Busts The Cache When activeTools Changes

Any `prepareStep` that returns a different `tools` set or `activeTools` on different steps rewrites the cacheable prefix and forces full prefill on the next step. Open at time of review: https://github.com/vercel/ai/issues/14170.

```bash
rg -n "experimental_prepareStep|prepareStep|activeTools|stopWhen|isStepCount" .
```

Architectural mitigation only: keep the full tool list constant across steps and rely on the model's selection, or use the underlying provider's allowed-tools mechanism (when exposed by the SDK) instead of mutating `tools`. Sort tools by name regardless.

### 1h TTL Telemetry Has A Per-Bucket Breakdown

`{ type: 'ephemeral', ttl: '1h' }` reaches the Anthropic wire on both v4 and v5. The response carries a per-TTL breakdown alongside the legacy total:

```json
"usage": {
  "cache_creation_input_tokens": 2213,
  "cache_read_input_tokens": 0,
  "cache_creation": {
    "ephemeral_5m_input_tokens": 0,
    "ephemeral_1h_input_tokens": 2213
  }
}
```

Cost dashboards that separate 5m vs 1h write spend must read `cache_creation.ephemeral_{5m,1h}_input_tokens`, not the summed `cache_creation_input_tokens`.

### generateObject Schema Serialization

`generateObject` + Zod produces byte-stable wire payloads across calls when the schema is module-level and unchanged. Risks to watch in code review:

- Zod schemas constructed inside the request handler with inline `.describe()` strings that depend on runtime values
- per-request additions to `response_format` such as `request_id`, tenant, or timestamps
- changes to schema field order between calls

If any are present, treat the structured-output schema as a dynamic block in the cacheable prefix.

### streamText / streamObject

`cache_control` is preserved through the streaming path. Cache fields surface after the stream completes; await the promise-shaped accessors:

```ts
const stream = streamText({ model, messages });
for await (const _ of stream.textStream) { /* discard or render */ }
const usage = await stream.usage;
const providerMetadata = await stream.providerMetadata;
```

For raw SSE bodies, parse `event: message_delta` / `event: message_stop` chunks to recover `usage` — the response body in network logs is event-stream, not JSON.

## Diagnostics

Pin the SDK surface to read the right field:

```ts
// v5+ (ai >= 5)
result.usage.inputTokenDetails?.cacheReadTokens
result.usage.inputTokenDetails?.cacheWriteTokens
result.providerMetadata?.anthropic?.cacheReadInputTokens
result.providerMetadata?.anthropic?.cacheCreationInputTokens
result.providerMetadata?.openai?.cachedPromptTokens

// v4 (ai 4.x) — deprecated names
result.usage.cachedInputTokens
result.providerMetadata?.anthropic?.cacheCreationInputTokens
```

The v5 `inputTokenDetails` path and the provider-namespaced fields can both be present and equal. Pick one as the source of truth in dashboards; do not double-count.

When the SDK report disagrees with provider raw usage, the raw wire body is authoritative. Capture it by wrapping `fetch`:

```ts
const logging = (input, init) => {
  // log JSON.parse(init.body) and the parsed response usage
  return fetch(input, init);
};
const anthropic = createAnthropic({ apiKey, fetch: logging });
```

This is the fastest way to see whether `cache_control` actually appears in the body and where it landed (top level vs system block vs tool vs content part).

Symptom → first check:

- `cached_tokens == 0` with OpenAI v5 default factory: confirm endpoint is `/v1/responses` and that `promptCacheKey` is set
- both `cache_creation_input_tokens` and `cache_read_input_tokens` zero on Anthropic: confirm `cache_control` is on the wire at all
- cache write but no read: directive landed at top level (v5 quirk) but the cached prefix bytes differ from earlier calls, or TTL expired, or a different route served call 2
- generateObject regression after schema rewrite: compare the serialized JSON Schema in the wire body between two calls

## Monitoring

Track per route family:
- `ai` and `@ai-sdk/<provider>` package versions and major
- chosen API factory (`openai(...)`, `openai.chat(...)`, `openai.responses(...)`, equivalents for other providers)
- presence of `cache_control` / `prompt_cache_key` in the captured wire body
- wire location of `cache_control` (top level vs system block vs tool vs content part)
- raw provider `cache_read_input_tokens` / `cache_creation_input_tokens` / `cached_tokens` per request
- SDK-surface `inputTokenDetails.cacheReadTokens` / `providerMetadata.<p>.cachedPromptTokens` and any divergence from raw
- ratio of raw cache read tokens to raw input tokens by route
- `experimental_prepareStep` / `stopWhen` presence and `tools_count` per step
