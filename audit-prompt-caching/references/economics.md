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

Input-only baseline: `(S + D) * Pi`.
With cache: `(1-h) * S * Pi + h * S * Pr + D * Pi`, plus write/storage premiums when applicable.
Total cost must add `O * Po`; output often dominates after good input caching.

For GPT-5.6+ OpenAI and Claude, writes are a separate billing category. When actual usage fields exist, prefer `ordinary_input * Pi + cache_write * Pw + cache_read * Pr + output * Po` over a hit-rate approximation. OpenAI's `input_tokens` includes read and write tokens; Anthropic's `input_tokens` excludes them. The bundled ROI estimator accepts total `--cache-write-tokens` and `--cache-write-price-per-mtok` so a 1.25× or 2× write price is included without guessing the number of writes from a hit rate.

## Cache Write Break-Even

For a stream of otherwise equivalent input tokens that are either written or read from cache, let `R` be the read fraction, `w = Pw/Pi`, and `r = Pr/Pi`. The cached stream beats ordinary input only when `w*(1-R) + r*R < 1`, or `R > (w-1)/(w-r)`. This excludes output, uncached suffixes, capacity effects, and setup work; use measured token categories for a real workload.

| Cache policy | Write multiplier | Read multiplier | Minimum read fraction to save input cost |
| --- | ---: | ---: | ---: |
| GPT-5.6+ OpenAI, 30m | 1.25× | 0.10× | Above 21.7% |
| Claude Opus 5.5, 5m | 1.25× | 0.05× | Above 20.8% |
| Claude Opus 5.5, 1h | 2× | 0.05× | Above 51.3% |

These thresholds are derived from the documented multipliers, not observed cache-hit rates. A cold write still pays for input on earlier OpenAI models; the GPT-5.6+ change is the **additional 25% write premium**. Longer TTL can improve reuse, but its higher write price must be weighed against the actual read fraction.

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
