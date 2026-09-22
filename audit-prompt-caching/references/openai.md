# OpenAI Prefix Cache Reference

Last reviewed: 2026-09-22. Verify model support, prices, thresholds, API fields, and retention again before making exact operational claims.

Official sources:
- GPT-6 Sol model: https://developers.openai.com/api/docs/models/gpt-6-sol
- Prompt caching and model differences: https://developers.openai.com/api/docs/guides/prompt-caching
- Prompt cache diagnostics: https://developers.openai.com/api/docs/guides/prompt-caching/diagnostics
- Reasoning configuration updates: https://developers.openai.com/api/docs/guides/reasoning
- Pricing: https://openai.com/api/pricing/

## Generation Boundary

OpenAI caches a rendered prompt prefix, including model-side instructions, tools, developer instructions, and conversation history. A matching visible string alone does not prove a matching rendered prefix. A prefix hash contributes to routing, but cache state lives on individual machines; region, expiry, and load still affect whether an exact prefix is found. Extended cache state can use GPU-local storage under the documented data-retention posture.

| Behavior | GPT-5.6 and later, including `gpt-6-sol` | Earlier models |
| --- | --- | --- |
| Minimum cacheable prefix | 1,024 visible input tokens; hidden OpenAI tokens do not count | Model- and request-dependent |
| Breakpoints | Implicit by default; explicit on supported Responses content blocks | Implicit only |
| Cache write | 1.25× ordinary input price; reported as `cache_write_tokens` | No separate cache-write charge |
| Cache read | 0.1× ordinary input price | Check model's cached-input price |
| Lifetime setting | `prompt_cache_options.ttl`; only `"30m"` is documented, and it is the default | `prompt_cache_retention`: `"24h"` for `gpt-5.5`/Pro; `"in_memory"` or `"24h"` on supported older models |
| `prompt_cache_key` | Optional for separate customer/user cache accounting and probing isolation; not needed to optimize routing | Stable key helps route a prefix to the same cache; it does not guarantee a hit |
| `cached_tokens` | Exact eligible boundary, excluding hidden tokens | May be rounded down to a multiple of 128 |

For earlier models, a hot key/prefix can overflow locality; the guide discusses about 15 requests per minute per key as a planning envelope. GPT-5.6+ handles cache routing automatically, so do not prescribe a key as the default fix for a miss. Cache entries do not cross organization or regional processing boundaries. Check Zero Data Retention and Regional Inference settings for the actual model and organization before proposing a retention change.

## Breakpoints and Agent Context

- In `prompt_cache_options: {"mode": "explicit"}`, mark the last reusable `input_text` block with `prompt_cache_breakpoint: {"mode": "explicit"}`. Without a marker, explicit-only mode creates no cache writes. Content after the last marker is ordinarily billed as uncached input rather than written to cache.
- Top-level `instructions` cannot carry an explicit breakpoint. Put reusable developer instructions in an `input_text` block inside a developer message when a marker is needed.
- Implicit mode writes at the latest eligible user message, last tool response in a consecutive tool-response group, or end of the initial consecutive developer-message block. Explicit markers can coexist with implicit mode. A request can create up to four writes; the implicit breakpoint consumes one of those slots.
- Keep stable instructions, examples, tools, schemas, images, and documents before volatile user/request data. A tool/schema/order, `text.format`, `parallel_tool_calls`, `text.verbosity`, request-level `reasoning.effort`, or compaction change can alter the rendered prefix.
- For supported GPT-6 single-agent Responses conversations, append a `configuration_update` input item to change effort while leaving request-level `reasoning.effort` unchanged. Preserve the update in conversation history; changing the request-level setting can rewrite the earlier prefix. This control is not universal across API modes.
- Keep `tools` definitions stable. Use `tool_choice: "none"` or `allowed_tools` to change callability, tool search with `defer_loading`, or a developer-role `additional_tools` input item for append-only additions where supported. Do not assume changing the top-level `tools` array preserves the cache.
- On supported GPT-5.6+ Responses requests, `prompt_cache_options.prewarm: true` writes the known prefix without generating output. The write is billed normally; send the real request after it completes and measure reuse before scheduling warm-ups.

## Usage, Cost, and Diagnostics

Responses usage on GPT-5.6+ includes `usage.input_tokens_details.cached_tokens` and `cache_write_tokens` when available. Both are **parts of** `usage.input_tokens`, not additive fields. Compute ordinary input as `input_tokens - cached_tokens - cache_write_tokens`; price the three categories separately. For `gpt-6-sol`, the model page currently lists $2 ordinary input, $0.20 cache read, and $2.50 cache write per million tokens. Keep model prices outside reusable calculations and recheck before quoting them.

Chat Completions uses `usage.prompt_tokens` and `usage.prompt_tokens_details.cached_tokens`; check that surface's raw response before assuming new write fields or breakpoint controls propagate through a wrapper. Cached input still counts toward TPM rate limits.

For GPT-5.6+ supported Responses requests, `prompt_cache_options.comparison_response_id` requests `prompt_cache_diagnostics` against a recent completed response from the same organization. It does not load the earlier conversation or change cache behavior. A diagnostic `cache_hit` says no mismatch was found against that comparison; actual reused tokens and billing come from `usage`. Reasons such as `tools_changed` help localize misses. The Prompt Caching Dashboard gives aggregate trends; compare token totals, not averages of per-request hit percentages.

If `cached_tokens == 0`, check the model/API surface, minimum visible prefix length, breakpoint mode/placement, prefix/tool/schema drift, region, cadence, and routed machine. If writes are high but reads stay low, inspect the dynamic suffix, reuse cadence, and routing before adding keys or prewarming. If reads are high but savings are low, check output-token share, cache-write cost, decode latency, and external tool time.
