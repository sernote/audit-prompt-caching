# Response Cache

Last reviewed: 2026-08-25.

## Response-Cache Evidence Details

Source: https://openrouter.ai/docs/guides/features/response-caching

### Controls

`gateway_response` is off by default; request controls or a preset enable it. Enablers: `X-OpenRouter-Cache: true` (when the preset does not configure caching); preset `cache_enabled: true`. Disablers, in precedence order: preset `cache_enabled: false` (not overridable by any header), then request `X-OpenRouter-Cache: false` (overrides a preset-enabled cache). Passive; no traffic change.

`X-OpenRouter-Cache-TTL` is dual-role: request TTL uses `1–86400` seconds (clamps out-of-range); response reports remaining HIT/full MISS TTL and overrides preset `cache_ttl_seconds`. `X-OpenRouter-Cache-Clear` is an active refresh control: when enabled it deletes and repopulates the entry; it has no effect when caching is disabled. never send or recommend it in a passive audit; it is not proof of enablement. Checklist non-forwarding of Clear is fail-closed defence-in-depth, not an enablement claim.

### Timing

Retain `X-OpenRouter-Cache-Status` (`HIT`/`MISS`; corroborate MISS with request/preset), `X-OpenRouter-Cache-Age` (HIT-only), `X-OpenRouter-Cache-TTL` (remaining HIT/full MISS TTL; request control), and `X-OpenRouter-Cache-Source-Id` (HIT-only populating ID).

Only `200 OK` responses cache; errors, rate-limit responses, and partial results never do. A HIT precedes provider call: not provider prompt-cache activity and cannot warm provider cache. concurrent requests can both MISS and bill; entries can evict before TTL expiry; neither proves disabled. HIT/sticky reset undocumented; verify per account.

### Boundary

Identity: API key + model + endpoint type + streaming mode + normalized body SHA-256; end-user identity is not a separate header dimension. Whitespace normalized; JSON property order and explicit-vs-omitted fields change the key. HTTP-Referer, X-Title, and provider headers excluded. body fields such as user, session_id, and metadata partition the cache. Replay requires matching key/dimensions/body; backend-assigned authenticated fields can partition it. A client-controlled handle is not an isolation boundary without authenticated-state validation at assignment site; forwarded, transformed, hashed, or concatenated derivations remain unresolved/AP-9b.

### Usage

A HIT returns zeroed billable usage and does not call the provider. Partition before prompt-cache ratios, denominator, latency/TTFT, cost/ROI, or warm-up analysis. Zero fields: Chat Completions/Responses `prompt_tokens`, `completion_tokens`, `total_tokens`; embeddings `prompt_tokens`, `total_tokens`; Anthropic Messages `input_tokens`, `output_tokens`.

all-zero usage alone is not proof of a response-cache HIT: errors, empty records, endpoint differences, or missing telemetry yield zeroes. Require status/source or verified endpoint evidence. Body-only/streamed logs without headers need `response_cache_source_id`; otherwise unresolved.

A zero-input HIT makes analyzer row/aggregate `denominator_status` ambiguous until partitioned; token-weighted may remain unchanged. Malformed nonzero cache details are not a HIT contract; unpartitioned aggregates describe provider-reached, not end-to-end requests.

### ZDR/replay

Account-level ZDR disables OpenRouter response caching. Per-request `provider.zdr` constrains provider candidates; an enabled gateway cache can retain a response. Provider in-memory caching is separate: ZDR describes in-memory prompt caching as not retaining data, so ZDR is not proof that provider implicit prompt caching is forbidden. It may remove cache-capable routes. Do not merge planes.

TTL parsing: out-of-range clamps, non-numeric uses preset/default, trailing text/decimals truncate. HIT replays stored response verbatim despite `temperature`. Body-only identical output corroborates, not proves, without status/source. Router metadata is absent on HIT; absence is not a HIT detector; use headers/source.
