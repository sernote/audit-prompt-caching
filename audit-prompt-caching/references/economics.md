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
