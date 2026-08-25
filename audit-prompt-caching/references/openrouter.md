# OpenRouter Prompt Cache Reference

Last reviewed: 2026-08-25. OpenRouter is a router, not one provider. Confirm the request surface, account policy, actual provider/model, and retained wire evidence before interpreting cache fields or changing routing.

Official sources:
- Prompt caching: https://openrouter.ai/docs/guides/best-practices/prompt-caching
- Provider routing: https://openrouter.ai/docs/guides/routing/provider-selection
- Response caching: https://openrouter.ai/docs/guides/features/response-caching
- Router metadata: https://openrouter.ai/docs/guides/features/router-metadata
- ZDR: https://openrouter.ai/docs/guides/features/zdr

## Mechanics

Apply the shared Cache Plane Gate in `SKILL.md` and `references/mechanics.md`: provider/model names do not identify whether evidence is provider prompt cache, OpenRouter `gateway_response`, engine KV, or semantic response cache.

Locate the integration and final request shape:

```bash
rg -n "openrouter|OPENROUTER_API_KEY|openrouter.ai/api/v1|@openrouter/sdk|OpenRouter|openrouter/auto" .
```

Search separately for OpenRouter controls and continuity handles; confirm matches as OpenRouter settings, not another framework’s flags or application-local identifiers:

```bash
rg -l -i "x-openrouter-cache|x-openrouter-(experimental-)?metadata|cache_enabled|cache_ttl_seconds|session_id|x-session-id|prompt_cache_key" .
```

Inspect `model`, `models`, `provider`, `plugins`, `messages`, `cache_control`, message transforms, account provider preferences, `zdr`, `data_collection`, and context compression. Record control/handle kind and HMAC-SHA256 or another keyed hash, never raw prompt/session values. compressed and uncompressed prompts are different cache inputs.

## Sticky Provider Routing

Source: https://openrouter.ai/docs/guides/best-practices/prompt-caching; Chat API: https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion; Responses API: https://openrouter.ai/docs/api/api-reference/responses/create-a-response.

OpenRouter documents sticky affinity expiring after 10 minutes of inactivity; successful requests reset it. The page says an error does not update “the cache”; read that narrowly as sticky-affinity state, not provider prompt-cache eviction. Sticky locality is not provider cache-hit evidence.

Body `session_id` takes precedence over `x-session-id`; the value is limited to 256 characters. Only when both are absent can `prompt_cache_key` be used. This is an audit synthesis, not a quoted provider enumeration: `session_id → x-session-id → prompt_cache_key → opening-message identity`. `metadata.session_id` is generic metadata, not a routing handle, and is excluded.

With `session_id`, sticky routing can activate after any successful request before cache usage is observed; without it, activation is described after a cache hit. The cache-read pricing condition applies. Unresolved: verify per model/provider; no rollout.

Scope is account × model × conversation. For Chat/Responses, header-only `x-session-id` is treated as the documented `session_id` channel; verify this inference on audited traffic. For non-chat embeddings, reranking, speech-to-text, text-to-speech, image-generation, and video-generation, the value is grouping only, sticky routing does not apply, and these endpoints accept only this header channel. Different conversations may use different providers without proving a defect.

Without a handle, OpenRouter derives opening identity from the first system/developer message and first non-system message. A stable measured anchor is a measured pilot, not a universal fix; changing `prompt_cache_key` also repartitions sticky affinity. An existing `prompt_cache_key` can provide session-pinned routing without a new rollout, but its timing relative to the no-session default is unresolved.

Unavailable sticky providers can fall back to the next-best provider; an error may permit rerouting because it does not update sticky state. Treat transitions as route evidence, not a prompt-cache miss. Auto/Pareto router models may reuse a resolved model only while it remains in the current candidate set: this is not a guarantee or hard pin. The docs say manual `provider.order` disables automatic sticky routing. Keep order, fallback, `allow_fallbacks`, `provider.only`, `provider.ignore`, sorting, and `openrouter/auto` as diagnostic dimensions through the Routing Outcome Gate, not as a routing-change recommendation.

## Cross-Provider Prompt-Cache Marker Translation

Source: https://openrouter.ai/docs/guides/best-practices/prompt-caching; Responses API: https://openrouter.ai/docs/api/api-reference/responses/create-a-response; Chat API: https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion; message transforms: https://openrouter.ai/docs/guides/features/message-transforms.

OpenRouter translates some markers, but TTL is not translated. An Anthropic block `cache_control` can become `prompt_cache_breakpoint` toward a supporting OpenAI model; a `prompt_cache_breakpoint` can become a default five-minute `cache_control` toward Anthropic or Google. `cache_control.ttl` is dropped toward OpenAI and `prompt_cache_options` is OpenAI-only. These are evidence boundaries, not marker-placement advice.

Under the prompt-caching page’s `Anthropic Claude` heading, top-level automatic `cache_control` covers the listed Anthropic, Google Vertex AI, Azure, Amazon Bedrock, and Claude Platform on AWS routes, including a trailing Bedrock breakpoint where required. Explicit per-block `cache_control` is separately described across Anthropic-compatible providers including Bedrock and Vertex. Do not read the top-level list as every marker form or as OpenAI-routed support.

Anthropic per-block `cache_control` inside Responses `input` is not exposed through the Responses API. OpenAI `prompt_cache_breakpoint` carries no TTL, while current OpenAI examples show request-root `prompt_cache_options` with `ttl` for Responses and Chat. Thus per-block TTL requires a surface exposing `cache_control`; do not infer that every Responses TTL request must move APIs.

For Responses toward the documented OpenAI route, inspect `usage.input_tokens_details`; for Chat inspect `usage.prompt_tokens_details`. `cached_tokens` are reads and `cache_write_tokens` writes where exposed. OpenRouter does not document inclusive versus additive totals: verify inclusivity per model/provider before accepting `valid`; `valid` is necessary but not sufficient on a route.

Usage is automatic in the response/final streaming message. Deprecated `usage: { include: true }` and `stream_options: { include_usage: true }` switches have no effect. Therefore missing fields are not automatically failures: `cache_write_tokens` is documented only for explicit caching and cache-write pricing. The raw OpenRouter shape may select the analyzer’s OpenAI/inclusive adapter and provisional `provider: "openai"`/`denominator_status: valid`; that is an analyzer artifact, not routed attribution. A wrapper-labelled `provider: "openrouter"` remains ambiguous until accounting semantics are verified. Do not transfer direct-provider OpenAI layout checks without final provider-visible evidence.

Message transforms document a context length default for context compression. Record `openrouter_metadata.pipeline[].context_compression` and compare compressed and uncompressed prompts: compressed and uncompressed prompts are different cache inputs. This is passive diagnosis; do not disable a production plugin. Batch cross-references this TTL non-translation rule, so a documented one-hour Anthropic strategy is not a cross-provider guarantee.

## OpenRouter Response-Cache Confounder

Source: https://openrouter.ai/docs/guides/features/response-caching. Bounded details: [`references/openrouter-response-cache.md`](references/openrouter-response-cache.md).

The `gateway_response` cache is separate from provider prompt caching. Inspect existing controls and evidence passively; partition response-cache HITs before prompt-cache ratios, latency/TTFT, cost/ROI, or provider warm-up. A response-cache header is not provider `cached_tokens`, and a gateway HIT cannot warm provider cache. Enabling, tuning, clearing, or warming this plane is out of scope.

## Route/Provider/Model Attribution

Source: https://openrouter.ai/docs/guides/features/router-metadata and https://openrouter.ai/docs/api/api-reference/generations/get-request-%26-usage-metadata-for-a-generation; usage accounting: https://openrouter.ai/docs/cookbook/administration/usage-accounting.

When already retained, `X-OpenRouter-Metadata: enabled` exposes `openrouter_metadata.requested` (requested slug/alias), `strategy`, selected `openrouter_metadata.endpoints.available[].selected`, and optional `attempts[]`/`pipeline[]`, including `context_compression`. Do not add the header in a passive audit. Absent optional arrays are not telemetry defects; a failed request has no selected endpoint.

Response-cache HITs omit `openrouter_metadata`: metadata presence rules out a HIT, but metadata absence is not a HIT detector. Use cache status/source evidence. `openrouter_metadata.attempt: 0` with no selected endpoint means no provider was reached; absent metadata can also mean a missing/disabled/invalid header, error, auth/rate-limit, or validation path.

Retain `X-Generation-Id` and distinguish it from `X-OpenRouter-Cache-Source-Id`. A HIT has its own replay generation; the source ID names the populating generation. Read-only fallback is `GET /api/v1/generation?id=<generation-id>` against the auditee’s records. Inspect available `provider_name`, `model`, `router`, `session_id`, `preset_id`, `cache_discount`, `native_tokens_cached`, `response_cache_source_id`, `total_cost`, `is_byok`, and `upstream_inference_cost`. This is historical attribution, not a provider request trace.

The prompt-caching page describes signed `cache_discount` signs for reads/writes; generation exposes the field but not that convention. Split reads from writes. `upstream_inference_cost` is BYOK-only per usage accounting. Native-token inclusivity is unresolved: never mix `native_tokens_cached` with normalized ratios. Hash raw `session_id` values.

## Batch and Warm-Up Semantics

Source: https://openrouter.ai/docs/batch-quickstart and https://openrouter.ai/docs/guides/best-practices/prompt-caching; model variants: https://openrouter.ai/docs/llms.txt.

The prompt-caching page names an Anthropic `:batch` request path. The `llms.txt` index lists model variants but not `:batch` as a model variant; it is not a model variant, so the path surface is unresolved. Separately, the docs’ `Anthropic Claude` → `Caching in the Batch API` wording is Batch API scope; no Batch API `session_id` grouping or sticky-for-Batch behavior is documented.

Use a conservative no-cross-line-visibility caveat. The docs describe one-hour explicit breakpoints for the Claude family and successive shared-prefix reuse; do not generalize that TTL to every provider/route. Retain Batch generation IDs and privacy/retention caveats. A response-cache HIT cannot warm provider prompt cache because it is served before any provider.

## Audit Checklist

- Establish endpoint, requested variant, account policy, and actual provider/model.
- Capture final body/headers, provider controls, fallback/order/filters, transforms, continuity handles, and keyed fingerprints; never log raw prompts/secrets.
- Separate provider fields from `gateway_response`, engine KV, and semantic-response evidence with the Cache Plane Gate.
- For sticky/marker evidence, record handles, opening/prefix hashes, timing, transitions, provider-visible form, usage path, accounting semantics, and verification per model/provider; missing fields are unresolved.
- For response cache, retain headers, HIT/MISS/source evidence, generation IDs, and zero-usage shape; partition HITs before analysis.
- Apply ZDR/data_collection and provider allow/ignore lists as applicability filters; ZDR is not proof that in-memory provider caching is forbidden.
- Use the Routing Outcome Gate and `references/mechanics.md`; this reference does not recommend pins, fallback changes, a new `session_id` rollout, cache-control placement, response-cache enablement, or warm-up.

## Diagnostics

Ask for raw request/response shape, endpoint, requested/routed model/provider, keyed continuity hashes, settings, `cached_tokens`, `cache_write_tokens`, endpoint totals, cache headers, `X-Generation-Id`, source ID, and privacy policy. Record observed, inferred, and unresolved facts.

If writes exist but reads stay low, check opening drift, fallback/candidate changes, unsupported provider behavior, marker translation/ignoring, context compression, response-cache HIT partitioning, and expiry/eviction. Verify per model/provider; do not confuse provider-reached with gateway-served records.

This reference is an audit aid, not evidence of provider support, TTL retention, route selection, or accounting, and not a guarantee. Provider-value freshness is review-verified against the linked sources; production controls and routing changes are out of scope.
