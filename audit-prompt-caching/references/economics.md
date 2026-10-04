# Prompt Cache Economics

Use this reference for cost, migration, or "high hit rate but no savings" questions. Verify current provider pricing, cache discounts, storage/write premiums, TTLs, and model support from official docs before exact math.

## Variables

- `S`: static cacheable input tokens.
- `D`: dynamic uncached input tokens.
- `O`: output tokens.
- `h`: cache hit rate on `S`.
- `Pw`: full price per cache-write token when provider charges for creation; if a source quotes only a premium over input, use `Pi` plus that premium.
- `Pr`: cache-read/cached-token price.
- `Pi`: uncached input price.
- `Po`: output price.

Input baseline: `(S + D) * Pi`. With cache: `(1-h) * S * Pi + h * S * Pr + D * Pi`, plus `Pw - Pi` per miss token actually written and `O * Po` output cost.

For GPT-5.6+ OpenAI and Claude, use measured `ordinary_input * Pi + write * Pw + read * Pr + output * Po`, where `ordinary_input` excludes write and read tokens, so each write is charged once at full `Pw`. OpenAI's `input_tokens` includes reads/writes; Claude's excludes them. Without usage, the ROI helper accepts assumed `--cache-write-rate` and `--cache-write-input-price-per-mtok`.

## Verified Rate Inputs

A real audit records primary rates scoped to provider, exact model/version, region, currency, deployment type, and service tier, with the source URL or billing export identity, retrieval/observation date, and effective date; an unknown effective or publication date stays unknown. Verify ordinary input, cached-read, full write, and output prices, plus storage/TTL fees where actually charged. A model family, shared API usage fields, or an older model's rates do not establish another model's ratios. With missing or unverified rates, report the token mix and formula but no numeric ROI verdict; bundled multipliers are not defaults. Clearly hypothetical inputs support conditional arithmetic labeled as such, never a current price claim. A price entry proves no availability, region eligibility, endpoint support, minimum tokens, TTL/retention, context threshold, or release date.

References track billing mechanics (paid writes, storage/TTL fees, usage accounting) and invalid generalized rules, not price lists; a rate change alone does not justify a new model-specific exception.

## Cache Write Break-Even

For equivalent tokens either written or read, let `R` be the read fraction, `w = Pw/Pi`, `r = Pr/Pi`. Cache saves input cost when `(1-R)*w + R*r < 1`, which for `w > r` is `R > (w-1)/(w-r)`; equality is neutral. This excludes output, uncached suffixes, and capacity effects; separately verified storage/TTL fees can make this threshold incomplete.

Historical illustrative configurations from earlier reviews, not current rate, TTL, or support defaults:

| Cache policy | Write multiplier | Read multiplier | Minimum read fraction to save input cost |
| --- | ---: | ---: | ---: |
| GPT-5.6+ OpenAI (most models), 30m | 1.25× | 0.10× | Above 21.7% |
| GPT-6.1 Sol OpenAI, 30m | 1.25× | 0.05× | Above 20.8% |
| Claude Opus 5.5, 5m | 1.25× | 0.05× | Above 20.8% |
| Claude Opus 5.5, 1h | 2× | 0.05× | Above 51.3% |

Percentages are rounded; for a borderline read fraction, compare it with the exact `(w-1)/(w-r)` value.

These are theoretical token fractions, not observed hit rates. Earlier OpenAI writes already paid ordinary input; for paid-write models take `w` from the verified full write price. Compare 1h TTL's higher write cost with measured reads.

## Checklist

- Separate cache write/create tokens from read/hit tokens.
- Calculate output-token share before changing prompt layout or model.
- Check traffic cadence against TTL/retention; sparse traffic may write repeatedly and read rarely.
- Include migration risk: new provider threshold, prefix ordering, usage fields, routing, TTL, and write premium.
- Compare by prompt family, not blended global averages.
- When pricing is unverified, name the missing rate scope and withhold a numeric ROI verdict.

## Useful Conclusions

- High hit rate with low savings usually means output/decode/tool cost dominates.
- A cache write premium can make low reuse more expensive than no caching.
- Per-user isolation can be correct but should be reported as expected efficiency loss.
- Provider migration can create a hidden migration tax when a once-stable static document moves after dynamic user content.
