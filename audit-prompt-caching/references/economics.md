# Prompt Cache Economics

Use this reference for cost, migration, or "high hit rate but no savings" questions. Verify current provider pricing, cache discounts, storage/write premiums, TTLs, and model support from official docs before exact math.

## Variables

- `S`: static cacheable input tokens.
- `D`: dynamic uncached input tokens.
- `O`: output tokens.
- `h`: cache hit rate on `S`.
- `Pw`: cache-write price or premium when provider charges for creation.
- `Pr`: cache-read/cached-token price.
- `Pi`: uncached input price.
- `Po`: output price.

Input baseline: `(S + D) * Pi`. With cache: `(1-h) * S * Pi + h * S * Pr + D * Pi`, plus write premiums and `O * Po` output cost.

For GPT-5.6+ OpenAI and Claude, use measured `ordinary_input * Pi + write * Pw + read * Pr + output * Po`. OpenAI's `input_tokens` includes reads/writes; Claude's excludes them. Without usage, the ROI helper accepts assumed `--cache-write-rate` and `--cache-write-input-price-per-mtok`.

## Cache Write Break-Even

For equivalent tokens either written or read, let `R` be the read fraction, `w = Pw/Pi`, `r = Pr/Pi`. Cache saves input cost when `R > (w-1)/(w-r)`. This excludes output, uncached suffixes, and capacity effects.

| Cache policy | Write multiplier | Read multiplier | Minimum read fraction to save input cost |
| --- | ---: | ---: | ---: |
| GPT-5.6+ OpenAI, 30m | 1.25× | 0.10× | Above 21.7% |
| Claude Opus 5.5, 5m | 1.25× | 0.05× | Above 20.8% |
| Claude Opus 5.5, 1h | 2× | 0.05× | Above 51.3% |

These are theoretical token fractions, not observed hit rates. Earlier OpenAI writes already paid ordinary input; GPT-5.6+ adds a 25% premium. Compare 1h TTL's higher write cost with measured reads.

## Checklist

- Separate cache write/create tokens from read/hit tokens.
- Calculate output-token share before changing prompt layout or model.
- Check traffic cadence against TTL/retention; sparse traffic may write repeatedly and read rarely.
- Include migration risk: new provider threshold, prefix ordering, usage fields, routing, TTL, and write premium.
- Compare by prompt family, not blended global averages.
- State assumptions when pricing is unverified.

## Useful Conclusions

- High hit rate with low savings usually means output/decode/tool cost dominates.
- A cache write premium can make low reuse more expensive than no caching.
- Per-user isolation can be correct but should be reported as expected efficiency loss.
- Provider migration can create a hidden migration tax when a once-stable static document moves after dynamic user content.
