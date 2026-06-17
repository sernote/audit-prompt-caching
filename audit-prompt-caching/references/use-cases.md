# Prompt Cache Audit Use Cases

Use this reference when scope is unclear or the repo has many LLM artifact types.

## Cost And Migration

Load `references/economics.md` plus provider references. Inspect billing exports, usage fields, static/dynamic/output token estimates, prompt layout before/after migration, TTL/write premium, and cache hit rate. Symptoms: bill mismatch, high hit rate with low savings, provider migration changed cache behavior.

## Managed Router And OpenRouter

Load `references/openrouter.md`; add `references/economics.md` when financial. Inspect OpenRouter base URL, `provider` routing object, fallback policy, `openrouter/auto`, first message identity, `cache_control`, `cached_tokens`, `cache_write_tokens`, routed provider/model, plugins, ZDR, and provider filters.

## Prompt And Request Code

Start from `references/rules.json`. Inspect prompt builders, SDK calls, canonical render functions, tool registries, `response_format`, JSON schema serialization, Bedrock `cachePoint`, and multimodal representation. Symptoms: `cached_tokens=0`, schema/tool drift, or prompt text looks identical to humans but not the provider.

## Agent And Coding Assistant

Load `references/agent-tools.md`. Inspect agent loop, dynamic tool retrieval, MCP registry, mode switching, history truncation, tool-result compaction, summarization, per-step `cached_tokens` / cache-read fields, `prefix_hash`, `tools_count`, tool-name hash, output tokens, and compaction events.

## Deployment And Self-Hosted Inference

Load `references/predeploy-checklist.md` and engine reference. Inspect Docker Compose, Dockerfile, Helm, Kubernetes Service/Ingress/HPA, gateway, service mesh, vLLM/SGLang flags, load balancer policy, KV pressure, cache salt, tokenizer/chat-template stability, and route/replica cache metrics. Symptoms: TTFT after scaling, stable prompts missing across pods, KV eviction.

## Observability And CI

Load `references/observability.md`. Add rendered prompt snapshots, prefix fingerprint for `system + tools + stable early messages`, tool/schema hash, prompt version, cache read/write fields, TTFT/prefill, output-token share, first/final token timestamps, deploy/model/route/replica dimensions, and a CI smoke test that fails when stable prefixes change.

## Triage Shortcut

- Cost increased: usage fields and output share, then prompt stability.
- `cached_tokens=0`: prefix and tool/schema stability.
- Agent got expensive: dynamic tools and history mutation.
- TTFT after scaling: routing and KV capacity.
- Cache hit but latency high: separate TTFT/prefill from decode/output/tool time.
- vLLM/SGLang config: deployment files, routing, `max_model_len`, KV metrics.
- OpenRouter cache miss: sticky routing, first-message identity, fallback/model routing, read/write usage.
