# Amazon Bedrock Prompt Cache Reference

Verify official Bedrock and model-provider docs before exact claims about Converse vs InvokeModel syntax, supported models, token minimums, checkpoint limits, TTL, cross-region inference, pricing, or usage fields.

## Mechanics

Bedrock prompt caching uses provider/model-specific cache points such as `cachePoint`. Usage often appears as `CacheReadInputTokens`, `CacheWriteInputTokens`, and `CacheDetails` in service metrics or response metadata. Treat Bedrock as its own provider surface even when the underlying model family resembles Anthropic or another API.

## Audit Checklist

- Detect `bedrock-runtime`, `ConverseCommand`, `InvokeModelCommand`, `boto3.client("bedrock-runtime")`, `cachePoint`, `CacheReadInputTokens`, and `CacheWriteInputTokens`.
- Inspect `system`, `messages`, tools, and document blocks before the cache point. Dynamic user-specific intro before `cachePoint` can force writes without reads.
- Confirm model-family support, token minimum, checkpoint count, and valid cache-point locations.
- Check cross-region inference and routed region/model; region changes can break locality or support.
- Keep tools and schemas stable across repeated requests.
- Distinguish write/create tokens from read tokens; writes alone do not prove savings.

## Diagnostics

Ask for request body, model ID, region, Converse/InvokeModel surface, `CacheReadInputTokens`, `CacheWriteInputTokens`, `CacheDetails`, rendered prefix pair, tool/schema hash, and route/region metadata. If writes are high and reads low, check dynamic content before checkpoint, route/region drift, TTL/cadence, unsupported surface, or tool changes.
