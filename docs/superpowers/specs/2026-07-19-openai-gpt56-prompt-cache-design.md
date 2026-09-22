# OpenAI GPT-5.6 prompt-cache support

Date: 2026-07-19

## Purpose

Update the portable audit skill for the current direct OpenAI prompt-caching
contract without turning the package into a provider simulator.

The implementation must help an auditor answer four questions:

1. Is a GPT-5.6 request using valid cache controls and marker placement?
2. Are OpenAI cache-read and cache-write usage fields counted without inflating
   input tokens?
3. Can paid cache writes make the route more expensive?
4. Does the report distinguish observed cache telemetry from priced ROI?

## Source of truth

Implementation decisions come from the official OpenAI prompt-caching guide and
model pages verified on 2026-07-19:

- https://developers.openai.com/api/docs/guides/prompt-caching
- https://developers.openai.com/api/docs/models/all

Provider responses and billing exports remain authoritative for usage and cost.

## Current contract to represent

For recognized direct GPT-5.6 request shapes:

- Request-wide cache policy is configured through `prompt_cache_options`.
- `mode` is `implicit` or `explicit`; omitted mode means `implicit`.
- The supported TTL in this skill snapshot is `30m`.
- Explicit write boundaries use
  `{"prompt_cache_breakpoint":{"mode":"explicit"}}` on supported prompt content
  blocks.
- OpenAI creates at most four new cache writes per request. Marker count is not
  treated as an API-validity limit because older markers can still be read.
- `prompt_cache_retention` belongs to the older automatic-cache contract and
  must not be recommended for GPT-5.6.
- `usage.*_tokens_details.cached_tokens` and
  `usage.*_tokens_details.cache_write_tokens` are breakdowns of the endpoint
  input total. They are not extra input tokens.
- Cache writes can have a distinct caller-supplied price. The skill must not
  hard-code current model pricing.

The guide's read-boundary wording is not encoded as a hard validation limit.
Unknown models and provider wrappers remain unknown instead of inheriting direct
OpenAI behavior.

## Minimal design

### Request linting

Extend `layout_linter.py` only for the current direct GPT-5.6 family aliases
(`gpt-5.6`, `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`).

The linter validates:

- exactly one prompt-bearing API surface: `messages` or `input`;
- `prompt_cache_options` object, mode, and TTL;
- explicit marker value and placement on supported content blocks;
- explicit mode with no marker as a cache-disabled audit finding, not an API
  syntax claim;
- marker shape and placement, without confusing write slots with a marker cap;
- deprecated `prompt_cache_retention`.

Output adds a compact `cache_policy` object and AP-11 findings. It does not
materialize provider cache keys or predict whether OpenAI will reuse a prefix.

### Prefix comparison

Keep `prefix_stability_check.py` as the existing whole-input raw/canonical
comparison helper. It is useful evidence, but it does not claim explicit
breakpoint reuse. The skill documentation must state this limitation.

### Usage accounting

`analyze_usage_logs.py` dispatches exact known shapes:

- OpenAI Responses and Chat: inclusive input accounting;
- Anthropic and Bedrock: additive read/write accounting;
- wrappers or unknown providers: preserve reported totals, mark accounting
  ambiguous, and require `--accounting-mode` for an additive interpretation.

Normalized output adds:

- `cache_write_tokens`;
- `cache_write_total_tokens`;
- `cache_benefit_tokens`;
- `accounting_semantics`;
- machine-readable warnings.

Warnings are nonfatal. OpenAI cache fields individually larger than endpoint
input produce `OPENAI_CACHE_BREAKDOWN_EXCEEDS_INPUT`.

### ROI

`estimate_cache_roi.py` partitions static input into mutually exclusive read,
write, and ordinary shares:

```text
read = static * requests * hit_rate
write = static * requests * cache_write_rate
ordinary = static * requests - read - write
```

All values must be finite and nonnegative, requests positive, rates in
`[0,1]`, and their sum no greater than one. A nonzero write rate requires an
explicit write price. Existing zero-write invocations retain their results.

### Report

`render_audit_report.py`:

- shows read volume, write volume, write/read ratio, and usage warnings;
- says cost is unknown without pricing;
- optionally accepts ROI JSON produced by the bundled estimator;
- validates provenance, required finite fields, and basic cost consistency;
- classifies priced results as savings, increased cost, or neutral.

This is a local reporting contract, not a security boundary or a general
accounting interchange format.

## Explicit non-goals

- A catalog of every OpenAI model.
- Structural/LCS simulation of provider breakpoint reuse.
- Reimplementation of the OpenAI tokenizer or cache-key algorithm.
- Exhaustive defense against artificial huge-number and floating-point inputs.
- Hard-coded model prices.
- Provider attribution from normalized wrapper fields alone.
- Changing legacy automatic-cache guidance for non-GPT-5.6 models.

## Compatibility

- Existing script commands remain valid.
- Existing zero-write ROI output remains numerically compatible.
- Existing usage fields remain present; new fields are additive.
- Unknown providers are reported conservatively.
- Malformed CLI input exits nonzero without a successful report.

## Verification

The test suite covers the public contract:

- valid and invalid GPT-5.6 cache controls and markers;
- direct OpenAI inclusive accounting;
- Anthropic/Bedrock additive accounting;
- ambiguous wrapper behavior and explicit override;
- paid-write ROI, invalid domains, and negative outcome;
- unpriced and priced reports plus warning rendering;
- legacy tests, package validation, trigger evals, syntax, and whitespace.
