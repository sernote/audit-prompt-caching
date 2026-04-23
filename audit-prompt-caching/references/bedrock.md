# Amazon Bedrock Prompt Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

Verify before exact claims:
- supported models, regions, and API surfaces
- minimum tokens per cache checkpoint
- maximum cache checkpoints per request
- fields that accept cache checkpoints for the selected model
- TTL support and pricing by model
- Converse vs InvokeModel request syntax
- usage field casing in the selected SDK/log source
- cross-region inference and prompt-management behavior

Official sources:
- Prompt caching: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- Converse API: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- Inference parameters and response fields: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters.html
- Pricing: https://aws.amazon.com/bedrock/pricing/

## Stable Mechanics

Amazon Bedrock prompt caching is controlled through cache checkpoints or model-family cache controls on supported API surfaces. Cache checkpoints mark the contiguous prompt prefix that should be cached. The prompt prefix before a checkpoint must remain stable between requests.

Request syntax depends on the API and model family:
- Converse API uses `cachePoint` objects in supported `system`, `messages`, or `tools` locations.
- InvokeModel request bodies use model-specific syntax. For Anthropic Claude on Bedrock, this can look like `cache_control`.
- Bedrock prompt management and the console playground can add more automatic cache-management behavior; verify the exact surface before diagnosing.

Do not assume direct Anthropic or direct OpenAI cache semantics apply unchanged through Bedrock. Bedrock has its own supported model matrix, regions, checkpoint limits, TTL behavior, pricing, cache-management options, and usage fields.

## Provider Checks

### Detect Bedrock Before Direct Providers

Search:

```bash
rg -n "bedrock-runtime|BedrockRuntime|bedrockRuntime|boto3.client\\([\"']bedrock-runtime|client\\.converse|converse_stream|InvokeModelCommand|ConverseCommand|invoke_model|cachePoint|CacheReadInputTokens|CacheWriteInputTokens|CacheDetails" .
```

If Bedrock is present, load this reference before `anthropic.md` or other model-family references. Load the underlying model-family reference only for prompt-layout details that still apply.

### Checkpoint Placement

Inspect whether checkpoints sit after reusable static content and before per-request content.

Common mistakes:
- placing `cachePoint` after dynamic user/session data
- adding checkpoints before the model-specific minimum token count
- changing tool definitions or system content before a checkpoint
- assuming every field supports checkpoints for every model
- exceeding the model-specific maximum number of checkpoints

### Converse Vs InvokeModel

Confirm the exact API surface:
- `converse` / `converse_stream`
- `invoke_model` / `invoke_model_with_response_stream`
- Bedrock prompt management
- console playground

Do not mix request-body examples across surfaces. A `cachePoint` example for Converse may not be valid for a raw model body passed to InvokeModel.

### TTL And Traffic Cadence

Compare TTL support with the workload cadence. Sparse repeats can create cache writes without enough reads. If long TTL is used, verify support and pricing for the selected model before recommending it.

When multiple TTLs are mixed, verify current Bedrock ordering constraints in the official docs before changing checkpoint order.

### Cross-Region Inference

If cross-region inference is enabled and cache writes rose unexpectedly, check whether routing behavior changed. Treat this as a route/cache-domain issue and measure cache read/write fields by model, region, and inference profile when available.

### Simplified Cache Management

For Claude models on Bedrock, check whether simplified cache management is enabled or expected. If it is, verify how far it searches back from the breakpoint and whether the static content layout fits that behavior.

## Diagnostics

Inspect raw provider usage, not only total input tokens.

Fields to look for:
- `CacheReadInputTokens`
- `CacheWriteInputTokens`
- `CacheDetails`
- SDK-specific lower/camel-case variants
- model ID, region, inference profile, API surface

If writes exist but reads stay low:
- prefix before checkpoint changed
- checkpoint is below the model-specific token minimum
- TTL expired before reuse
- route/region/inference profile changed
- unsupported model/region/API surface
- checkpoint placed in an unsupported field
- too many checkpoints or wrong checkpoint order
- dynamic tools/system/messages appear before checkpoint

## Monitoring

Track:
- cache read tokens
- cache write tokens
- checkpoint count and checkpoint field
- TTL choice
- model ID, region, inference profile, API surface
- prompt version, tool hash, schema hash
- TTFT and output tokens
- cache writes without later reads
