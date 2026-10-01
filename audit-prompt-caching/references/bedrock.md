# Amazon Bedrock Prompt Cache Reference

Last reviewed: 2026-09-12; only the GPT-6.1 Sol exception was reviewed 2026-10-01. Verify official Bedrock and model-provider docs before exact claims about Converse vs InvokeModel syntax, supported models, token minimums, checkpoint limits, TTL, cross-region inference, pricing, or usage fields.

Official sources: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html ;
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html ;
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CachePointBlock.html ;
model cards under https://docs.aws.amazon.com/bedrock/latest/userguide/ (per-model caching rows).
Current OpenAI model list: https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards-openai.html .

## Mechanics

Bedrock documents two cache types: **implicit** (best-effort, no request markers) and **explicit** (`cachePoint` on Converse, `cache_control` on InvokeModel and the Anthropic Messages route). Support for each varies by model and API, and model cards carry separate implicit/explicit rows. A request with no `cachePoint` does not prove that no caching happens.

The native Converse response uses lower-camel usage fields: `inputTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`, `outputTokens`, plus `cacheDetails` (a list of `{inputTokens, ttl}` write breakdowns per TTL, 1h before 5m, empty when nothing was written). Some service metrics/wrappers expose PascalCase equivalents. `inputTokens` covers only non-cached input, so treat reads and writes as **additive** to it for total-input/cost accounting.

Model contracts differ:
- Anthropic Claude: `cachePoint: {"type": "default", "ttl": "5m" | "1h"}` in `tools`, `system`, and `messages`; up to 4 checkpoints; longer-TTL points must precede shorter ones. The minimum is evaluated on cumulative tokens across `tools` -> `system` -> `messages`, and changing `tools` invalidates the later sections. Minimums are model-tiered (512 for the Claude 5 Opus/Fable/Mythos tier, 1,024 or 4,096 for others at the last review); Bedrock also looks back about 20 content blocks from a breakpoint for a hit. 1h TTL is unavailable on the oldest supported Claude models.
- Amazon Nova: implicit caching for all text prompts plus explicit `cachePoint` in `system` and `messages` only (no `tools`), 5m TTL, about 1K minimum, 4 checkpoints, and a documented 20K-token cap on cacheable content.
- Listed OpenAI GPT-5.6 models and GPT-6 Astra: caching only via the Responses API, on both `bedrock-runtime` (`/openai/v1`, cross-region `us.`/`global.` profiles only) and `bedrock-mantle`. `prompt_cache_breakpoint`/`prompt_cache_options` follow the OpenAI contract with a 30m TTL, 1,024 minimum, 4 checkpoints, and paid writes (about 1.25x input) with reads at about 0.1x; the usage object is OpenAI-shaped (`usage.input_tokens_details.cached_tokens` and `cache_write_tokens`) and **inclusive**, so do not apply the Converse additive rule there. GPT-5.5 and older are implicit-only with free writes; GPT-OSS models list no caching. As of 2026-09-22, AWS's model cards list GPT-6 Astra but not GPT-6 Sol; verify the exact model ID before applying this contract to a new GPT-6 route.
- OpenAI GPT-6.1 Sol ([model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-sol.html), added 2026-09-29) is an exact-model exception that does **not** follow the GPT-5.6/Astra contract above:
  - Explicit prompt caching is unsupported on every listed API (`bedrock-mantle` Responses and Chat Completions; `bedrock-runtime` Responses, Chat Completions, Converse, and Invoke). Do not prescribe `prompt_cache_breakpoint`, `prompt_cache_options`, `cachePoint`, or any other cache marker for this model.
  - The card does not establish implicit caching, TTL, token minimum, or cache usage fields/accounting; treat all of them as unknown and do not import direct OpenAI or Astra defaults.
  - Routes: Mantle `openai.gpt-6.1-sol` at exactly `https://bedrock-mantle.us-east-1.api.aws/openai/v1` (`us-east-1` only); Runtime `us.openai.gpt-6.1-sol` (US geographic profile only). There is no direct in-Region Runtime invocation and no `global.` profile.
  - Standard tier only (Priority, Flex, and Reserved are unsupported). Published USD per 1M input / cache write / cache read / output tokens: `2.20 / 2.75 / 0.11 / 11.00` when input is <=272K tokens; `4.40 / 5.50 / 0.22 / 16.50` applied to the full request when input exceeds 272K. These Mantle IAD and US CRIS rates already include the published 10% premium; the card's global base-rate rows are price references and do not imply a global route.
  - AWS states the cache pricing dimensions do not change feature support. Price columns alone establish neither whether caching occurs, nor which usage fields appear, nor ROI; require raw per-route cache usage reconciled with billing before claiming savings.

AWS now recommends `bedrock-runtime` for new OpenAI- and Anthropic-compatible workloads (`/anthropic` and `/openai/v1` routes); `bedrock-mantle` remains supported. Identify the model family and endpoint before prescribing request syntax.

## Audit Checklist

- Detect `bedrock-runtime`, `bedrock-mantle`, `ConverseCommand`, `InvokeModelCommand`, `boto3.client("bedrock-runtime")`, `cachePoint`, `cacheDetails`, and both lower-camel/PascalCase cache usage fields; classify each usage object as Converse-additive or OpenAI-inclusive before computing a ratio. Classify GPT-6.1 Sol usage as ambiguous until its raw per-route usage and accounting are verified.
- Inspect `system`, `messages`, tools, and document blocks before the cache point. Dynamic user-specific intro before `cachePoint` can force writes without reads.
- Confirm model-family support, token minimum, checkpoint count, and valid cache-point locations.
- Check cross-region inference and routed region/model; AWS says high demand "may lead to increased cache writes", and newer Claude 5.x and all OpenAI models on `bedrock-runtime` are cross-region-profile-only, so route drift is the default. CloudTrail `additionalEventData.inferenceRegion` identifies the serving region.
- Confirm on-demand inference: prompt caching is not supported for batch inference.
- Keep tools and schemas stable across repeated requests.
- Distinguish write/create tokens from read tokens; writes alone do not prove savings.

## Diagnostics

Ask for request body, model ID, endpoint (`bedrock-runtime` vs `bedrock-mantle`), region, Converse/InvokeModel/Responses/Messages surface, `cacheReadInputTokens`, `cacheWriteInputTokens`, `cacheDetails` (or OpenAI-shaped `cached_tokens`/`cache_write_tokens`), rendered prefix pair, tool/schema hash, and route/region metadata. If writes are high and reads low, check dynamic content before checkpoint, a `tools` change invalidating `system`/`messages`, TTL ordering, route/region drift, TTL/cadence, unsupported surface, or tool changes. For GPT-6.1 Sol, ask for the raw unmodified usage object instead of assuming either field shape; missing cache fields do not prove implicit caching is absent, and skip checkpoint diagnostics because explicit caching is unsupported.
