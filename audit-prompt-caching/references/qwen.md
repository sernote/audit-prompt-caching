# Qwen / DashScope Prefix Cache Reference

## Documentation Freshness

Last reviewed: 2026-04-24.

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

## Stable Mechanics

Qwen can mean:

- managed DashScope / Alibaba Cloud Model Studio API
- OpenAI-compatible DashScope endpoints
- self-hosted open-weight Qwen models on vLLM/SGLang/Transformers

Always identify which one is in use.

DashScope docs describe both explicit and implicit context caching for supported models. Self-hosted Qwen follows the inference engine's cache behavior, so use the vLLM/SGLang reference for those deployments.

## Provider Checks

### Managed DashScope

Check whether the model and region support context caching. Verify whether the project uses explicit `cache_control` style caching or implicit caching.

For OpenAI-compatible responses, inspect `usage.prompt_tokens_details.cached_tokens` when present. For explicit-cache examples, also inspect `cache_creation_input_tokens` so the audit can distinguish cache writes from cache reads.

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

For Anthropic-compatible routes, check `usage.cache_read_input_tokens` and `usage.cache_creation_input_tokens`.

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
