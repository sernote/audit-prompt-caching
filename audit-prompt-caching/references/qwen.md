# Qwen / DashScope Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-09-12.

Verify before exact claims:
- supported Qwen/DashScope models by region
- explicit vs implicit context cache support
- TTL and pricing for explicit context cache
- usage field names for OpenAI-compatible and native APIs
- whether snapshot/latest models are supported
- tool/MCP API behavior

Official sources:
- DashScope / Alibaba Cloud Model Studio context cache: https://help.aliyun.com/zh/model-studio/context-cache
- Model Studio docs: https://help.aliyun.com/zh/model-studio/
- Qwen docs: https://qwen.readthedocs.io/
- Qwen vLLM deployment: https://qwen.readthedocs.io/en/stable/deployment/vllm.html
- Responses API: https://help.aliyun.com/en/model-studio/qwen-api-via-openai-responses
- Context cache: https://help.aliyun.com/en/model-studio/context-cache
- Explicit cache best practice: https://help.aliyun.com/en/model-studio/explicit-cache-best-practice
- Anthropic-compatible Messages API: https://www.alibabacloud.com/help/en/model-studio/anthropic-api-messages
- Model pricing: https://help.aliyun.com/en/model-studio/model-pricing

## Stable Mechanics

Qwen can mean:

- managed DashScope / Alibaba Cloud Model Studio API
- OpenAI-compatible DashScope endpoints
- self-hosted open-weight Qwen models on vLLM/SGLang/Transformers

Always identify which one is in use.

DashScope docs describe both explicit and implicit context caching for supported models, and the two are mutually exclusive per request: a request carrying `cache_control` uses only explicit caching. Both need at least 1,024 cacheable tokens (explicit TTL 5 minutes, reset on hit; implicit TTL unspecified and implicit cannot be disabled). Snapshot models such as `qwen3.8-max-0902` and third-party models (DeepSeek, Kimi, GLM) are listed with explicit cache support per region. Self-hosted Qwen follows the inference engine's cache behavior, so use the vLLM/SGLang reference for those deployments.

Explicit breakpoints on Qwen3.5+ are **message-level**: several `cache_control` markers inside one message's content array do not create separate breakpoints, multiple system messages merge into one segment, and `tools` are cached as part of the system message and cannot carry `cache_control`. Up to 4 markers per request. Older Qwen models support content-level breakpoints. A hit is also lost when the gap between the last content block and an existing cached block exceeds about 20 content blocks.

For the documented DashScope Responses flow, enable session cache with `x-dashscope-session-cache: enable` (default `disable`) and continue with `previous_response_id`; a response `id` stays valid for 7 days and the cache engages once the cumulative context exceeds 1,024 tokens. Any character change in the system or user prompt, including whitespace, resets `cached_tokens` to 0. This is distinct from a generic prefix hash: preserve the response lineage only within the intended conversation and do not log raw IDs. Responses usage reports the total as `usage.input_tokens` and may expose both `input_tokens_details.cached_tokens` and `prompt_tokens_details.cached_tokens`, plus `prompt_tokens_details.cache_creation_input_tokens` with a nested `cache_creation.cache_type` fixed to `ephemeral`; do not assume OpenAI field names are complete for Qwen.

## Provider Checks

### Managed DashScope

Check whether the model and region support context caching. Verify whether the project uses explicit `cache_control` style caching or implicit caching.

For OpenAI-compatible responses, inspect `usage.prompt_tokens_details.cached_tokens` when present. For explicit-cache examples, also inspect `cache_creation_input_tokens` so the audit can distinguish cache writes from cache reads. The FAQ says `input_tokens` may exceed `cached_tokens + cache_creation_input_tokens` by a few backend-appended tokens (typically 10 or fewer), so a ratio slightly below 1.0 on a full hit is normal, not a leak.

Pricing is not uniform: the standard rates are explicit creation 125%, explicit hit 10%, implicit hit 20% of the input price, but qwen3.8-max, qwen3.8-flash, and qwen3.8-2.4t-a95b (and some third-party models) use different cached rates, and Singapore list prices differ from Beijing/US. Read the model's own pricing row before estimating savings.

Regional OpenAI-compatible and Anthropic-compatible base URLs are now workspace-scoped (`https://{WorkspaceId}.{region}.maas.aliyuncs.com/compatible-mode/v1` and `/apps/anthropic`), with legacy `dashscope.aliyuncs.com`, `coding.dashscope.aliyuncs.com` (Coding Plan), and Token Plan hosts still documented. Caches are isolated per account and per model, so a host, workspace, or model switch is a cold start.

### Self-Hosted Qwen

Use engine-specific checks:
- vLLM/SGLang prefix caching
- `max_model_len`
- KV cache budget
- tokenizer/chat template stability
- YaRN/RoPE scaling only when the workload needs long context

### Region And Model Names

DashScope model support varies by region and by deployment scope. Do not give model support advice without checking current docs.

## Diagnostics

For DashScope OpenAI-compatible responses:

```python
total = response.usage.prompt_tokens
details = response.usage.prompt_tokens_details
cached = getattr(details, "cached_tokens", 0)
created = getattr(details, "cache_creation_input_tokens", 0)
ratio = cached / total if total else 0
```

For native DashScope APIs, `prompt_tokens_details` may be exposed as a mapping:

```python
details = response.usage.get("prompt_tokens_details", {})
cached = details.get("cached_tokens", 0)
created = details.get("cache_creation_input_tokens", 0)
```

For Anthropic-compatible routes, check `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens`; they are reported separately from `input_tokens` (additive), and on streams the full set arrives in `message_delta`, not `message_start`. The Messages page says `cache_control` may sit on tool-use blocks while the best-practice page says markers cannot target tools; treat tool-level breakpoints as unverified until a wire capture shows a write.

The bundled `analyze_usage_logs.py` reads `prompt_tokens_details.cache_creation_input_tokens` inside the OpenAI-shaped adapter as inclusive; label the record `provider: anthropic` when the Anthropic-compatible route is used so the additive adapter applies.

If `created > 0` and `cached == 0` across repeated calls, the cache is being written but not reused; check prefix stability, TTL, route/model support, and region-specific response fields.

For self-hosted Qwen, use vLLM/SGLang metrics.

## Monitoring

Track:
- cached tokens by model/region/route
- explicit cache creation vs read tokens when available
- `cache_creation_input_tokens`, `cached_tokens`, `cache_read_input_tokens` by compatibility route
- model name and region
- prompt/tool/schema hash
- engine KV metrics for self-hosted deployments

Alert on cache drops after region/model switch, SDK migration, chat template change, or engine upgrade.
