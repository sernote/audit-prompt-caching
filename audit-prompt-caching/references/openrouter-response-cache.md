# OpenRouter Response-Cache Evidence Details

Last reviewed: 2026-08-25. Bounded diagnostic detail only; this is not an enablement or optimization guide.

## Response-Cache Evidence Details

Source: https://openrouter.ai/docs/guides/features/response-caching

### Plane and controls

OpenRouter response caching is the separate `gateway_response` plane. It is off when neither a request control nor a preset enables it. `X-OpenRouter-Cache: true|false` participates in the control; a preset `cache_enabled` can enable it, `cache_enabled: false` cannot be overridden by the header, and request `X-OpenRouter-Cache: false` can disable a preset-enabled cache. Inspect existing controls passively; do not change production traffic.

`X-OpenRouter-Cache-TTL` is dual-role: on a request it asks for a custom seconds TTL in the documented `1–86400` range, with out-of-range values clamped; on a response it reports remaining TTL on a HIT and full effective TTL on a MISS. It can override preset `cache_ttl_seconds`. Do not copy a volatile default value into this reference. `X-OpenRouter-Cache-Clear` is an active refresh control, has no effect unless caching is enabled, and is not proof that the plane was enabled.

### Evidence and timing

Retain these headers when possible:

| Evidence | Boundary |
| --- | --- |
| `X-OpenRouter-Cache-Status` | `HIT`/`MISS` evidence for the gateway plane; corroborate MISS with request/preset enablement. |
| `X-OpenRouter-Cache-Age` | HIT-only age. |
| `X-OpenRouter-Cache-TTL` | Remaining TTL on HIT; full TTL on MISS; also a request control. |
| `X-OpenRouter-Cache-Source-Id` | HIT-only populating-generation ID. |

Only successful `200 OK` responses are cached. A HIT is served before any provider call, so it is not provider prompt-cache activity and cannot warm provider cache. Identical concurrent requests can both MISS and be billed independently; entries can be evicted before TTL expiry under memory pressure. Neither behavior proves the plane is disabled. The docs do not state whether a HIT resets sticky inactivity; verify that per account before attributing a later provider switch to sticky failure.

### Key and tenant boundary

Identity includes API key, model, endpoint type, streaming mode, and normalized request-body SHA-256. Extra whitespace is normalized away; JSON property order and explicit-versus-omitted optional fields can produce different keys. `HTTP-Referer`, `X-Title`, and provider-specific headers are excluded. The cache is scoped to an API key, so different keys do not share it even under one account/organization. A body-identical request from another tenant can replay when the same API key and all key dimensions match; review this conditional boundary against the existing `isolation` clinic and AP-9b trust boundary. Do not infer provider attribution from a replay.

### Usage partition

A HIT returns zeroed billable usage and does not call the provider. Partition it before prompt-cache ratios, denominator, latency/TTFT, cost/ROI, or warm-up analysis. Endpoint-specific zero fields are:

- Chat Completions/Responses: `prompt_tokens`, `completion_tokens`, `total_tokens`;
- embeddings: `prompt_tokens`, `total_tokens`;
- Anthropic Messages: `input_tokens`, `output_tokens`.

all-zero usage alone is not proof of a response-cache HIT: errors, empty records, endpoint differences, and missing telemetry also produce zeroes. Require status/source evidence or a verified endpoint contract. For body-only/streamed logs without headers, use generation `response_cache_source_id`; otherwise report unresolved.

A zero-input HIT makes the analyzer row and aggregate `denominator_status` ambiguous until partitioned. A numeric token-weighted result may remain unchanged only after that caveat is handled. Nonzero cache details in a malformed record are not a HIT contract; without partitioning, the aggregate describes provider-reached rather than end-to-end requests.

### ZDR, parsing, replay

Account-level ZDR separately disables OpenRouter response caching. Per-request `provider.zdr` does not change response-cache eligibility, so an enabled gateway cache can retain a response while ZDR constrains provider candidates. Provider in-memory prompt caching is a separate ZDR fact; do not merge it with gateway retention.

TTL parsing is evidence-sensitive: out-of-range values clamp, non-numeric values fall back to preset/default, trailing non-numeric text is truncated, and decimal values truncate. A HIT replays the stored response verbatim, even when `temperature` would otherwise vary output. Identical body-only output can corroborate, not prove, a HIT without status/source evidence. Router metadata is absent on a HIT; absence is not a HIT detector, so use cache headers or source ID. A HIT generation is historical replay attribution, not a provider request trace.
