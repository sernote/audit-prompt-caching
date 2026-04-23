# Prompt Cache Audit Use Cases

Use this reference when the user asks how the skill applies in practice, when a codebase has many artifact types, or when the audit scope is unclear.

## Cost And Migration

Load `references/economics.md`.

Typical users:
- AI platform lead choosing providers or models
- AI engineer estimating production cost
- FinOps or backend lead investigating an LLM bill
- team migrating between managed APIs or to self-hosted inference

Symptoms:
- price-list comparison does not match the bill
- cache hit rate is high but total cost stays high
- provider migration changed cache behavior
- static prompt is large, output share is unknown, or traffic is bursty

Inspect:
- API usage responses and billing exports
- `cached_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, output tokens
- estimates for static tokens, dynamic tokens, output tokens, hit rate, TTL, write premium
- prompt layout before and after migration
- provider references, verified against official docs before exact claims

## Managed Router And OpenRouter

Load `references/openrouter.md`. If the symptom is financial, also load `references/economics.md`.

Typical users:
- AI engineer using OpenRouter as an OpenAI-compatible gateway
- backend engineer configuring model/provider fallback
- platform lead balancing cache locality, price, latency, and privacy policy
- agent developer using `openrouter/auto` or multiple model fallbacks

Symptoms:
- OpenRouter shows cache writes but few cache reads
- provider or model fallback changes cache hit rate
- `provider.order`, `provider.only`, `provider.ignore`, ZDR, or account provider settings were added
- `openrouter/auto` or `models` routing makes repeated prompts land on different model/provider routes
- `cache_control` works direct-to-provider but behaves differently through OpenRouter

Inspect:
- OpenRouter base URL, SDK, request body, and model slug
- `provider` routing object, account provider preferences, fallback policy
- `messages`, especially first system/developer and first non-system message
- `cache_control` placement and provider-specific compatibility
- `plugins`, especially context compression
- `cached_tokens`, `cache_write_tokens`, cache discount, response model/provider metadata

## Prompt And Request Code

Usually start from `SKILL.md` anti-patterns. For release gates or incidents, also load `references/predeploy-checklist.md`.

Typical users:
- backend engineer building LLM requests
- prompt engineer maintaining templates
- SDK/integration engineer
- release engineer reviewing prompt-affecting changes

Symptoms:
- `cached_tokens` stays zero on repeated calls
- hit rate dropped after SDK, template, or schema change
- request looks the same to humans but not to the provider
- structured output or tool definitions are large

Inspect:
- prompt builders and template files
- canonical render functions and whitespace normalization
- SDK client calls and request wrappers
- tool registry and tool serialization
- `response_format`, JSON schema, Pydantic/dataclass serialization
- multimodal input representation, image detail, signed URLs

## Agent And Coding Assistant

Load `references/agent-tools.md`.

Typical users:
- agent developer
- coding-assistant developer
- AI engineer designing tool routing
- MCP/tooling engineer
- framework engineer owning compaction or summarization

Symptoms:
- the agent got more expensive after selecting fewer tools
- `tools_count` or `prefix_hash` changes on every step
- Plan/debug/read-only modes swap the system prompt or tool list
- long trajectories have rising TTFT or repeated prefill
- compaction rewrites early messages

Inspect:
- agent loop and per-step request construction
- dynamic tool retrieval, semantic routing, allowed tools, tool search, deferred loading
- MCP registry and tool descriptions
- subagent/tool bundle routing
- history truncation, tool-result compaction, summarization
- per-step `cached_tokens`/cache-read fields, `prefix_hash`, `tools_count`, tool-name hash

## Deployment And Self-Hosted Inference

Load `references/predeploy-checklist.md` and the relevant engine/provider reference.

Typical users:
- platform/SRE engineer running vLLM, SGLang, or Qwen self-hosted
- inference engineer tuning KV cache capacity
- team scaling from one model replica to many

Symptoms:
- stable prompts still miss after scaling replicas
- TTFT spikes after changing replica count or gateway routing
- KV cache evicts hot prefixes
- `max_model_len` is much larger than real p99 input length
- identical workloads behave differently by pod or route

Inspect:
- `docker-compose.yml`, `Dockerfile`, Helm values
- Kubernetes `Deployment`, `Service`, `Ingress`, HPA, gateway, service mesh config
- vLLM/SGLang engine arguments such as prefix caching, max model length, GPU memory utilization, tensor/pipeline parallel settings
- load balancer routing policy, sticky routing, prefix-aware routing, consistent hashing
- KV block pressure, eviction metrics, prefix-cache hit/query metrics, TTFT by route
- tokenizer and chat template stability for self-hosted models
- cache salt, cache namespace, and user/tenant isolation policy

## Observability And CI

Load `references/predeploy-checklist.md`.

Typical users:
- observability engineer
- QA engineer
- release engineer
- platform owner adding cache guardrails

Symptoms:
- cache regressions are noticed only after the bill or latency alert
- release changed prompt behavior without an explicit prompt diff
- no dashboard separates cacheable traffic from unique traffic
- no test protects the stable prefix

Inspect or add:
- rendered prompt snapshots for representative routes
- prefix fingerprint for `system + tools + stable early messages`
- tool/schema hash and prompt version dimensions
- cache ratio, cache writes vs reads, TTFT/prefill latency, output-token cost share
- deploy, SDK, model, prompt version, route, replica, region dimensions
- CI smoke test that fails when the cacheable prefix changes unexpectedly

## Article-Derived Scenario Map

- Economics article: cost comparison, provider migration, effective cost, output share, TTL/write premium, hidden migration tax.
- Anti-patterns article: volatile prefix data, template drift, schema/tool serialization, append-only history, routing, parallel fan-out, cache lifetime.
- Agents article: dynamic tool selection, stable tool bundles, masking/allowed tools/tool search/deferred loading, compaction, per-step diagnostics.

## Triage Shortcut

If the user gives only one symptom:
- Cost increased: start with usage fields and output share, then prompt stability.
- `cached_tokens=0`: start with prompt prefix and tool/schema stability.
- Agent got expensive: start with dynamic tools and history mutation.
- TTFT after scaling: start with routing and KV-cache capacity.
- vLLM/SGLang config: start with deployment files, replica routing, `max_model_len`, and KV metrics.
- OpenRouter cache miss: start with provider sticky routing, first-message identity, fallback/model routing, and cache read/write usage fields.
