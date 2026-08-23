# Vercel AI SDK Prefix Cache Reference

Last reviewed: 2026-08-23. Verify installed `ai` and `@ai-sdk/<provider>` majors before exact claims about endpoints, `providerOptions`, telemetry fields, `experimental_providerMetadata`, `convertToModelMessages`, `experimental_prepareStep`, or `stopWhen`.

Official sources:
- AI SDK Core: https://ai-sdk.dev/docs/ai-sdk-core
- Anthropic provider: https://ai-sdk.dev/providers/ai-sdk-providers/anthropic
- OpenAI provider: https://ai-sdk.dev/providers/ai-sdk-providers/openai
- Bedrock provider: https://ai-sdk.dev/providers/ai-sdk-providers/amazon-bedrock
- Google provider: https://ai-sdk.dev/providers/ai-sdk-providers/google-generative-ai
- Issue #14170: https://github.com/vercel/ai/issues/14170
- Issue #15185: https://github.com/vercel/ai/issues/15185
- Base `allowedTools` introduction (May 5, 2026): https://github.com/vercel/ai/commit/29e6ac6f1ffe0eaed2aa937c8a1657e90d3d8411
- `allowedTools` mapping fix: https://github.com/vercel/ai/commit/a062795bbe22ecc96a38d114bf8b8ea4af070914
- v6 backport: https://github.com/vercel/ai/pull/19051

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

## OpenAI Responses allowedTools

`allowedTools` is a Vercel wrapper option for the OpenAI Responses surface
(Responses-only). It is
not a general OpenAI-compatible feature. Keep a stable full `tools` catalog in
every request and change only the provider allow-list when the
endpoint, release line, model, and tool class pass the applicability and
economics gates. Changing `activeTools` removes entries from the request and
can rewrite the cacheable prefix; changing `activeTools` can be cheaper when a smaller catalog is better for a
cold or low-reuse route, so this is not a blanket ban on `activeTools`.

```ts
const result = await generateText({
  model: openai.responses('gpt-5.5'),
  tools: { weather, cityAttractions, search: openai.tools.webSearch() },
  providerOptions: {
    openai: {
      allowedTools: { toolNames: ['weather', 'search'], mode: 'auto' },
    },
  },
  prompt: 'What is the weather in San Francisco?',
});
```

`providerOptions.openai.allowedTools` accepts declared names in `toolNames`;
accepted modes are mode: `auto` and mode: `required`. It overrides request-level
`toolChoice`; `auto`
lets the model answer without a tool, while `required` requires a call to an
allowed tool. The allowedTools capability gate requires all of these facts:

1. the selected factory is `openai.responses(...)`, not Chat Completions;
2. the installed `ai` and `@ai-sdk/openai` versions are pinned in `package.json`
   and lockfile, and the release line contains the option;
3. the target model capability and concrete tool class support the requested semantics;
4. the final wire body and usage response confirm the mapping and route.

The chronology separates availability from corrected behavior: on May 5, 2026,
commit `29e6ac6` introduced the base Responses option; on Aug 18, 2026,
commit `a062795` corrected built-in/provider-defined/custom/MCP mapping, with
the v6 backport in `3.0.98` and the 4.x correction in `4.0.43`.

The availability gate and corrected-mapping gate are separate. The checked matrix is:

| `@ai-sdk/openai` line | Availability | Corrected provider-tool mapping |
| --- | --- | --- |
| `2.x` / AI SDK v5 | `allowedTools` is absent from the checked schema | not applicable; do not remove `activeTools` without another wire-tested mechanism |
| `3.x` / AI SDK v6 | available from `3.0.62` | corrected at `>=3.0.98` |
| `4.x` | available in the checked line | corrected at `>=4.0.43` |
| unknown line | verify lockfile, changelog, and wire fixture | do not transfer floors across majors |

The corrected Responses wire shape is `tool_choice: {type:
"allowed_tools", mode, tools: [...]}`. Derive entries from the declared tool;
do not turn every name into a function entry:

| Tool class | Entry in `allowed_tools.tools` |
| --- | --- |
| function | `{type: "function", name}` |
| custom | `{type: "custom", name}` |
| MCP | `{type: "mcp", server_label}` |
| supported built-in/provider-defined tool | `{type}` |

The provider option's `toolNames` uses the names declared in the SDK `tools`
object. A canonical provider name may also resolve for provider-defined tools.
If a declared name collides with another tool's provider name, the declared tool name has priority: the declared tool wins, and a warning is required. A provider name shared by several tools is
ambiguous and is removed from the allow-list with a warning. An unknown name
keeps the SDK's existing function-entry behavior but must produce a warning;
the provider may then reject the request.

`tool_search`, tools with `deferLoading`, and namespaced tools cannot be
represented in `allowed_tools`. The SDK removes them from the effective
allow-list and emits a warning. If removal leaves an empty allow-list, the
request fails with an error rather than becoming unrestricted. An MCP entry
allows the server as a whole using its `server_label` (server-level); per-tool MCP restriction
requires the MCP tool's own `allowedTools` mechanism.

For Azure, load `references/azure-openai.md` and record the endpoint,
deployment/model, and `api-version`. Verify that exact API version's Responses
tool_choice schema and final wire before using `allowed_tools`; do not claim
universal support.

The table describes direct OpenAI Responses wire capability. Do not transfer
Vercel SDK's name-resolution, warnings, drop, or error semantics to direct
OpenAI Responses, Azure Responses, Chat Completions, or an arbitrary
OpenAI-compatible wrapper without that surface's own schema and wire evidence.
For diagnosis record package versions,
factory, model/tool capability, `toolNames`, `mode`, final request body and
`tool_choice`, SDK warnings, HTTP status, raw provider usage, and stable
tools/prefix hashes. A stable wire prefix plus usage evidence confirms cache
impact; a narrower callable set alone does not.
