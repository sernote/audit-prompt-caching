# Amazon Bedrock Prompt Cache Reference

Last reviewed: 2026-09-12. Verify official Bedrock and model-provider docs before exact claims about Converse vs InvokeModel syntax, supported models, token minimums, checkpoint limits, TTL, cross-region inference, pricing, or usage fields.

Official sources: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html ;
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html ;
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CachePointBlock.html ;
model cards under https://docs.aws.amazon.com/bedrock/latest/userguide/ (per-model caching rows).

## Mechanics

Bedrock documents two cache types: **implicit** (best-effort, no request markers) and **explicit** (`cachePoint` on Converse, `cache_control` on InvokeModel and the Anthropic Messages route). Support for each varies by model and API, and model cards carry separate implicit/explicit rows. A request with no `cachePoint` does not prove that no caching happens.

The native Converse response uses lower-camel usage fields: `inputTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`, `outputTokens`, plus `cacheDetails` (a list of `{inputTokens, ttl}` write breakdowns per TTL, 1h before 5m, empty when nothing was written). Some service metrics/wrappers expose PascalCase equivalents. `inputTokens` covers only non-cached input, so treat reads and writes as **additive** to it for total-input/cost accounting.

Model contracts differ:
- Anthropic Claude: `cachePoint: {"type": "default", "ttl": "5m" | "1h"}` in `tools`, `system`, and `messages`; up to 4 checkpoints; longer-TTL points must precede shorter ones. The minimum is evaluated on cumulative tokens across `tools` -> `system` -> `messages`, and changing `tools` invalidates the later sections. Minimums are model-tiered (512 for the Claude 5 Opus/Fable/Mythos tier, 1,024 or 4,096 for others at the last review); Bedrock also looks back about 20 content blocks from a breakpoint for a hit. 1h TTL is unavailable on the oldest supported Claude models.
- Amazon Nova: implicit caching for all text prompts plus explicit `cachePoint` in `system` and `messages` only (no `tools`), 5m TTL, about 1K minimum, 4 checkpoints, and a documented 20K-token cap on cacheable content.
- OpenAI GPT-5.6 and later (including GPT-6): caching only via the Responses API, on both `bedrock-runtime` (`/openai/v1`, cross-region `us.`/`global.` profiles only) and `bedrock-mantle`. `prompt_cache_breakpoint`/`prompt_cache_options` follow the OpenAI contract with a 30m TTL, 1,024 minimum, 4 checkpoints, and paid writes (about 1.25x input) with reads at about 0.1x; the usage object is OpenAI-shaped (`usage.input_tokens_details.cached_tokens` and `cache_write_tokens`) and **inclusive**, so do not apply the Converse additive rule there. GPT-5.5 and older are implicit-only with free writes; GPT-OSS models list no caching.

AWS now recommends `bedrock-runtime` for new OpenAI- and Anthropic-compatible workloads (`/anthropic` and `/openai/v1` routes); `bedrock-mantle` remains supported. Identify the model family and endpoint before prescribing request syntax.

## Audit Checklist

- Detect `bedrock-runtime`, `bedrock-mantle`, `ConverseCommand`, `InvokeModelCommand`, `boto3.client("bedrock-runtime")`, `cachePoint`, `cacheDetails`, and both lower-camel/PascalCase cache usage fields; classify each usage object as Converse-additive or OpenAI-inclusive before computing a ratio.
- Inspect `system`, `messages`, tools, and document blocks before the cache point. Dynamic user-specific intro before `cachePoint` can force writes without reads.
- Confirm model-family support, token minimum, checkpoint count, and valid cache-point locations.
- Check cross-region inference and routed region/model; AWS says high demand "may lead to increased cache writes", and newer Claude 5.x and all OpenAI models on `bedrock-runtime` are cross-region-profile-only, so route drift is the default. CloudTrail `additionalEventData.inferenceRegion` identifies the serving region.
- Confirm on-demand inference: prompt caching is not supported for batch inference.
- Keep tools and schemas stable across repeated requests.
- Distinguish write/create tokens from read tokens; writes alone do not prove savings.

## Diagnostics

Ask for request body, model ID, endpoint (`bedrock-runtime` vs `bedrock-mantle`), region, Converse/InvokeModel/Responses/Messages surface, `cacheReadInputTokens`, `cacheWriteInputTokens`, `cacheDetails` (or OpenAI-shaped `cached_tokens`/`cache_write_tokens`), rendered prefix pair, tool/schema hash, and route/region metadata. If writes are high and reads low, check dynamic content before checkpoint, a `tools` change invalidating `system`/`messages`, TTL ordering, route/region drift, TTL/cadence, unsupported surface, or tool changes.
