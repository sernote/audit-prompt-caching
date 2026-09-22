# Amazon Bedrock Prompt Cache Reference

Verify official Bedrock and model-provider docs before exact claims about Converse vs InvokeModel syntax, supported models, token minimums, checkpoint limits, TTL, cross-region inference, pricing, or usage fields.

## Mechanics

Bedrock prompt caching uses provider/model-specific controls. Converse-style integrations can use `cachePoint`, with `CacheReadInputTokens`, `CacheWriteInputTokens`, and `CacheDetails` in service metrics or response metadata. The OpenAI-compatible `bedrock-mantle` Responses endpoint instead uses the OpenAI-shaped controls described below. Treat Bedrock as its own provider surface even when the underlying model family resembles Anthropic or another API.

## OpenAI GPT-5.6 on Bedrock Mantle

AWS documents `openai.gpt-5.6-sol`, Terra, and Luna through its OpenAI-compatible Responses endpoint, with implicit caching by default. For explicit caching, add `prompt_cache_breakpoint: {"mode": "explicit"}` to a supported input content block and send `extra_body={"prompt_cache_options": {"mode": "explicit", "ttl": "30m"}}` through the OpenAI SDK. Read `response.usage.input_tokens_details.cached_tokens` and `cache_write_tokens`; both are included in `usage.input_tokens`. Do not add those counts to the input total as with Anthropic usage. AWS's example uses a stable `prompt_cache_key`; verify routing semantics on this endpoint separately from OpenAI's native GPT-5.6+ guidance.

Source: https://aws.amazon.com/blogs/machine-learning/introducing-explicit-prompt-caching-for-openai-gpt-5-6-models-on-amazon-bedrock/ (published 2026-07-30). Do not infer that a newer OpenAI model is available on Bedrock until AWS lists it.

## Audit Checklist

- Detect `bedrock-runtime`, `ConverseCommand`, `InvokeModelCommand`, `boto3.client("bedrock-runtime")`, `cachePoint`, `CacheReadInputTokens`, and `CacheWriteInputTokens`.
- Inspect `system`, `messages`, tools, and document blocks before the cache point. Dynamic user-specific intro before `cachePoint` can force writes without reads.
- Confirm model-family support, token minimum, checkpoint count, and valid cache-point locations.
- Check cross-region inference and routed region/model; region changes can break locality or support.
- Keep tools and schemas stable across repeated requests.
- Distinguish write/create tokens from read tokens; writes alone do not prove savings.

## Diagnostics

Ask for request body, model ID, region, Converse/InvokeModel surface, `CacheReadInputTokens`, `CacheWriteInputTokens`, `CacheDetails`, rendered prefix pair, tool/schema hash, and route/region metadata. If writes are high and reads low, check dynamic content before checkpoint, route/region drift, TTL/cadence, unsupported surface, or tool changes.
