# Amazon Bedrock Prompt Cache Reference

Last reviewed: 2026-08-11. Verify official Bedrock and model-provider docs before exact claims about Converse vs InvokeModel syntax, supported models, token minimums, checkpoint limits, TTL, cross-region inference, pricing, or usage fields.

Official source: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html

## Mechanics

Bedrock prompt caching uses provider/model-specific cache points such as `cachePoint`. The native Converse response uses lower-camel usage fields: `inputTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`, and `outputTokens`. Some service metrics/wrappers expose PascalCase equivalents. Treat cache reads and writes as **additive** to `inputTokens` for total-input/cost accounting.

Model contracts differ: Anthropic uses cache-point blocks, Nova has its own cache-point/TTL rules, and OpenAI GPT-5.6 caching is exposed through the Bedrock `bedrock-mantle` route. Identify the model family before prescribing request syntax.

## Audit Checklist

- Detect `bedrock-runtime`, `ConverseCommand`, `InvokeModelCommand`, `boto3.client("bedrock-runtime")`, `cachePoint`, and both lower-camel/PascalCase cache usage fields.
- Inspect `system`, `messages`, tools, and document blocks before the cache point. Dynamic user-specific intro before `cachePoint` can force writes without reads.
- Confirm model-family support, token minimum, checkpoint count, and valid cache-point locations.
- Check cross-region inference and routed region/model; region changes can break locality or support.
- Keep tools and schemas stable across repeated requests.
- Distinguish write/create tokens from read tokens; writes alone do not prove savings.

## Diagnostics

Ask for request body, model ID, region, Converse/InvokeModel surface, `CacheReadInputTokens`, `CacheWriteInputTokens`, `CacheDetails`, rendered prefix pair, tool/schema hash, and route/region metadata. If writes are high and reads low, check dynamic content before checkpoint, route/region drift, TTL/cadence, unsupported surface, or tool changes.
