# Amazon Bedrock Prompt Cache Reference

Last reviewed: 2026-09-12; only the GPT-6.1 Sol entry was re-checked 2026-10-06 against the undated prompt-caching page and model card (observation date, not a release date). Verify official Bedrock and model-provider docs before exact claims about Converse vs InvokeModel syntax, supported models, token minimums, checkpoint limits, TTL, cross-region inference, pricing, or usage fields.

Official sources: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html ;
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_TokenUsage.html ;
https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_CachePointBlock.html ;
model cards under https://docs.aws.amazon.com/bedrock/latest/userguide/ (per-model caching rows).
Current OpenAI model list: https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards-openai.html .

## Mechanics

Bedrock documents two cache types: **implicit** (best-effort, no request markers) and **explicit** (`cachePoint` on Converse, `cache_control` on InvokeModel and the Anthropic Messages route). Support for each varies by model and API, and model cards carry separate implicit/explicit rows. A request with no `cachePoint` does not prove that no caching happens.

The native Converse response uses lower-camel usage fields: `inputTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens`, `outputTokens`, plus `cacheDetails` (a list of `{inputTokens, ttl}` write breakdowns per TTL, 1h before 5m, empty when nothing was written). Some service metrics/wrappers expose PascalCase equivalents. `inputTokens` covers only non-cached input, so treat reads and writes as **additive** to it for total-input/cost accounting.

Model contracts differ:
- Anthropic Claude: `cachePoint: {"type": "default", "ttl": "5m" | "1h"}` in `tools`, `system`, and `messages`; up to 4 checkpoints; longer-TTL points must precede shorter ones. The minimum is evaluated on cumulative tokens across `tools` -> `system` -> `messages`, and changing `tools` invalidates the later sections. Minimums are model-tiered (512 for the Claude 5 Opus/Fable/Mythos tier, 1,024 or 4,096 for others at the last review); Bedrock also looks back about 20 content blocks from a breakpoint for a hit. 1h TTL is unavailable on the oldest supported Claude models.
- Amazon Nova: implicit caching for all text prompts plus explicit `cachePoint` in `system` and `messages` only (no `tools`), 5m TTL, about 1K minimum, 4 checkpoints, and a documented 20K-token cap on cacheable content.
- Listed OpenAI GPT-5.6 models and GPT-6 Astra: caching only via the Responses API, on both `bedrock-runtime` (`/openai/v1`, cross-region `us.`/`global.` profiles only) and `bedrock-mantle`. `prompt_cache_breakpoint`/`prompt_cache_options` follow the OpenAI contract with a 30m TTL, 1,024 minimum, 4 checkpoints, and paid writes (about 1.25x input) with reads at about 0.1x; the usage object is OpenAI-shaped (`usage.input_tokens_details.cached_tokens` and `cache_write_tokens`) and **inclusive**, so do not apply the Converse additive rule there. GPT-5.5 and older are implicit-only with free writes; GPT-OSS models list no caching. As of 2026-09-22, AWS's model cards list GPT-6 Astra but not GPT-6 Sol; verify the exact model ID before applying this contract to a new GPT-6 route.
- OpenAI GPT-6.1 Sol ([model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-sol.html)) has its own exact-model surface and placement contract; do not copy the GPT-5.6/Astra lists above:
  - `bedrock-runtime`: implicit caching on Responses, Chat Completions, InvokeModel, and Converse; explicit caching on Responses, Chat Completions, and InvokeModel. Converse is implicit-only for this model: flag a native `cachePoint` as unsupported and audit prefix stability instead. `bedrock-mantle` (`/openai/v1`): implicit and explicit on Responses and Chat Completions.
  - Explicit: set `prompt_cache_options.mode` to `explicit` (the default `implicit` mode also adds an automatic latest-message breakpoint; `explicit` with no breakpoint does not cache) and `prompt_cache_options.ttl` to `30m`, the only supported TTL and the default, so flag any other value. AWS separately says cached prefixes stay reusable for at least 30 minutes, so `30m` is minimum retention, not an exact eviction deadline: a longer gap is a possible-miss risk that proves neither zero reads nor per-request billable writes; check raw reads/writes and actual retention/cadence before a cold-start or cost claim. Add `"prompt_cache_breakpoint": {"mode": "explicit"}` to an `input_text` block in Responses or a `text` content part in Chat Completions and InvokeModel; GPT-5.6's `input_image`/`input_file` placement is not listed for Sol.
  - The cumulative prefix before a breakpoint must reach 1,024 tokens. Multiple explicit breakpoints are allowed, and AWS states each request can create up to four cache writes; keep that wording rather than inventing a breakpoint-count rule.
  - Routes: Mantle `openai.gpt-6.1-sol` at exactly `https://bedrock-mantle.us-east-1.api.aws/openai/v1` (`us-east-1` only); Runtime only through `us.openai.gpt-6.1-sol` (US geographic) or `global.openai.gpt-6.1-sol` (global) profiles, with no direct in-Region Runtime invocation. Treat Mantle and each profile as distinct routing identities: segment telemetry per route and treat switching between them as route drift. Standard tier only (Priority, Flex, and Reserved are unsupported).
  - Documented support verifies none of: the usage fields each route/API returns, additive vs inclusive accounting, observed hits, savings, or production behavior. Missing fields prove neither absence nor presence of hits.
  - For ROI use `references/economics.md` verified rates scoped to exact provider, model/version, region, currency, endpoint/deployment, tier, source, and date; without them report the token mix and formula only.

AWS now recommends `bedrock-runtime` for new OpenAI- and Anthropic-compatible workloads (`/anthropic` and `/openai/v1` routes); `bedrock-mantle` remains supported. Identify the model family and endpoint before prescribing request syntax.

## Audit Checklist

- Detect `bedrock-runtime`, `bedrock-mantle`, `ConverseCommand`, `InvokeModelCommand`, `boto3.client("bedrock-runtime")`, `cachePoint`, `cacheDetails`, and both lower-camel/PascalCase cache usage fields; classify each usage object as Converse-additive or OpenAI-inclusive before computing a ratio. Classify GPT-6.1 Sol usage as ambiguous until its raw per-route/API usage and accounting are verified.
- Inspect `system`, `messages`, tools, and document blocks before the cache point. Dynamic user-specific intro before `cachePoint` can force writes without reads.
- Confirm model-family support, token minimum, checkpoint count, and valid cache-point locations.
- Check cross-region inference and routed region/model; AWS says high demand "may lead to increased cache writes", and newer Claude 5.x and all OpenAI models on `bedrock-runtime` are cross-region-profile-only, so route drift is the default. CloudTrail `additionalEventData.inferenceRegion` identifies the serving region.
- Confirm on-demand inference: prompt caching is not supported for batch inference.
- Keep tools and schemas stable across repeated requests.
- Distinguish write/create tokens from read tokens; writes alone do not prove savings.

## Diagnostics

Ask for request body, model ID, endpoint (`bedrock-runtime` vs `bedrock-mantle`), region, Converse/InvokeModel/Responses/Messages surface, `cacheReadInputTokens`, `cacheWriteInputTokens`, `cacheDetails` (or OpenAI-shaped `cached_tokens`/`cache_write_tokens`), rendered prefix pair, tool/schema hash, and route/region metadata. If writes are high and reads low, check dynamic content before checkpoint, a `tools` change invalidating `system`/`messages`, TTL ordering, route/region drift, TTL/cadence, unsupported surface, or tool changes. For GPT-6.1 Sol, ask for the raw unmodified usage object per route/API instead of assuming either field shape. On its explicit surfaces, check mode, breakpoint block type, the cumulative 1,024 minimum, dynamic content before the breakpoint, and traffic gaps beyond the `30m` minimum retention as a possible miss, not certain eviction; on Converse, check implicit prefix stability and route without prescribing checkpoints.
