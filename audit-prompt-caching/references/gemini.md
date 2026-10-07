# Gemini Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12; only the Agent Platform cache isolation subsection was re-checked 2026-10-07 against the context caching overview (page updated 2026-10-06; observation date, not an introduction date).

Verify before exact claims:
- supported models for implicit and explicit caching
- minimum token counts by API surface/model
- TTL defaults and limits
- storage pricing for explicit caches
- usage metadata fields
- Vertex AI vs Gemini API differences
- whether implicit caching has a cost-saving guarantee for the selected model/API surface

Official sources:
- Gemini context caching (the generic URL now renders the Interactions variant by default): https://ai.google.dev/gemini-api/docs/caching
- Interactions caching: https://ai.google.dev/gemini-api/docs/interactions/caching
- Generate Content caching (labelled legacy): https://ai.google.dev/gemini-api/docs/generate-content/caching
- Gemini API docs: https://ai.google.dev/gemini-api/docs
- Interactions API schema: https://ai.google.dev/api/interactions-api
- Generate Content schema: https://ai.google.dev/api/generate-content
- Gemini Enterprise Agent Platform (formerly Vertex AI) context caching: https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/context-cache/context-cache-overview
- Agent Platform zero data retention and `cacheConfig`: https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/zero-data-retention
- Pricing: https://ai.google.dev/gemini-api/docs/pricing

## Stable Mechanics

Gemini has two relevant caching modes:

- **Implicit caching**: automatic for qualifying Gemini models, with no guaranteed savings unless the provider reports a hit.
- **Explicit context caching**: create and reuse a cache object with a TTL and a more predictable cost-saving surface.

Use explicit caching when the application repeatedly uses a large stable context and needs deterministic cache reuse. Use implicit caching as an optimization, not a guarantee. Cached content is still part of the effective prompt prefix; put large shared content early.

The Gemini **Interactions API** supports implicit caching only; the docs state explicit cache objects are not supported there. Continue an interaction with `previous_interaction_id` when that API is used; it is a conversation-continuity handle, not an explicit cache object ID, and it carries only conversation history (tools, system instruction, and generation config must be resent). It requires the default `store=true`; a `store=false` deployment cannot use it, so its history-reuse path is gone. Stored interactions are retained 55 days on the paid tier and 1 day on the free tier. A normal response reports `usage.total_input_tokens`, `usage.total_cached_tokens`, and `usage.total_output_tokens`; the final streaming event reports the same totals at `metadata.total_usage`. These totals use inclusive accounting.

Minimum cacheable sizes are model- and surface-specific: on the Gemini API, Gemini 3.x models need 4,096 tokens and Gemini 2.5 models 2,048; on the Agent Platform the Gemini 3 family needs 4,096 but implicit caching on Gemini 3.7 Flash, 3.8 Flash, and 3.1 Pro Preview needs 6,144. Verify the current table before calling a prompt "long enough".

## Provider Checks

### Implicit Cache Expectations

Do not assume 100% hit rate for identical-looking prompts. Check docs and usage metadata, then measure real traffic. If implicit caching does not hit, first verify prompt length, shared-prefix placement, request cadence, model support, and whether the beginning of the prompt is truly stable.

### Explicit Cache Lifecycle

When using explicit caches, verify:
- cache object creation
- TTL
- cache name/ID reuse
- cleanup of stale cache objects
- storage pricing
- whether cached content is treated as a prefix to the prompt

### Gemini API Vs Agent Platform (Vertex AI)

Thresholds, regions, pricing, and supported models differ. The Agent Platform states a 90% discount for implicit and explicit hits on Gemini 2.5+ (75% on 2.0), stores explicit caches in the request region, has no maximum TTL, defaults to 60 minutes, and offers a project-level kill switch (`projects/{id}/cacheConfig` with `disableCache: true`, applied to all regions). The Gemini API pricing page shows cached input at about 10% of input for Gemini 3.x with model-specific storage prices that change on 2027-01-01 for the 3.6-3.8 Flash line, and some Flash-Lite models list caching as not available there while the Agent Platform supports them. Identify the exact surface before recommending changes.

### Agent Platform Cache Isolation

The Agent Platform documents that Google Cloud isolates cached data by project number and never shares cached content across projects. That is the provider boundary only. Within one project, the docs make the application responsible for scoping cached agent outputs and prompt context to each execution context and, for background agents and multi-tenant proxies, aligning context-caching boundaries with end-user permission boundaries so an agent cannot reuse cached credentials or context across users. Project isolation does not demonstrate application safety.

Review passively from supplied code, configuration, or redacted traces:
- how each explicit cache name (`cachedContents` resource) or cached agent context is keyed, what its final complete contents include, and whether user-specific content maps to its execution context, end user, and permission scope
- whether the lookup path authorizes the caller before attaching a cache name, especially in shared background workers and proxies
- whether cached agent outputs, tool results, or credentials land in a cache reused across users

Private content, a different username on a cache attachment, or a missing authorization check is not by itself a confirmed finding. Report a confirmed application isolation finding only when supplied code, configuration, or redacted traces establish that a cache attachment violated a specific user, execution-context, or permission boundary: the recipient's applicable authorization scope excludes some material in the cache, or an established execution-context policy forbids that reuse. Judge authorization against the final complete cache contents (every document, agent output, tool result, or credential in it), not a cache key or label. When no specific boundary violation is established and the cache contents, the cache-name-to-user/permission mapping, the authorization check, or the recipient's applicable permission or authorization scope is not visible, report an unresolved isolation question and the evidence needed, not a demonstrated leak. So if the contents, a cross-user attachment, and a lookup with no authorization check are visible but neither the recipient's scope nor an applicable execution-context policy is, report the missing check as a known control gap and the access violation as unresolved, not as a confirmed unauthorized attachment or leak. When that evidence confirms every recipient is authorized for the entire cached context within an approved execution and permission boundary, including current delegated access, different users alone are not a finding. Disclosure of cached content in model outputs is a separate claim and stays unproven unless supplied outputs show it. Static context that every authorized caller may see is not a leak by itself, and this boundary does not require a project per user. Healthy hit rate or latency does not waive the review. Do not request credentials or run cross-user probes. This statement covers Agent Platform Gemini context caching; do not extend it to the Gemini Developer API (including Gemini Developer API Interactions) or Claude on the Agent Platform without their own source. Agent Platform Interactions is unverified against this overview: claim neither caching support, absence, nor isolation there from it.

### Large Stable Documents

If the same document/context is sent repeatedly, prefer explicit context caching after verifying it is supported for the model and region.

## Diagnostics

Usage field names vary by SDK/API surface. Check current docs. For Interactions, interpret `total_cached_tokens` as a subset of `total_input_tokens` (inclusive accounting), not as an additive input total. For a streamed Interaction, read the final `metadata.total_usage` envelope rather than a per-event delta.

For Generate Content, typical checks are:

```python
usage = response.usage_metadata
cached = getattr(usage, "cached_content_token_count", None)
prompt = getattr(usage, "prompt_token_count", None)
```

SDK naming can differ. Also check camelCase forms such as `cachedContentTokenCount` if the SDK returns dict-like metadata. Do not substitute Generate Content's `promptTokenCount` / `candidatesTokenCount` for Interactions' `totalInputTokens` / `totalOutputTokens`.

For Interactions, inspect `total_input_tokens` / `totalInputTokens`, `total_cached_tokens` / `totalCachedTokens`, `total_output_tokens` / `totalOutputTokens`, and `previous_interaction_id` rather than looking only for explicit-cache fields.

For OpenAI-compatible routes, check whether `usage.prompt_tokens_details.cached_tokens` is exposed.

If `cached` is zero for repeated large contexts:
- request is below current minimum token count for the model/API surface
- shared content is not at the beginning
- requests are too far apart for implicit reuse
- explicit cache name/ID is not reused
- cache TTL expired or cache object was deleted
- API surface or region differs from the one that created the cache
- Agent Platform project has `cacheConfig.disableCache: true`
- Interactions request used `store=false`, so `previous_interaction_id` history reuse is unavailable
- last turn ends on a model role, which newer models reject

## Monitoring

Track:
- cached token count
- prompt token count
- cache object ID/name
- TTL and expiration
- storage cost for explicit caches
- cache hit behavior by model and region
- request cadence for implicit caching

Alert on zero cached tokens for repeated large contexts, and on stale explicit caches that keep incurring storage cost.
