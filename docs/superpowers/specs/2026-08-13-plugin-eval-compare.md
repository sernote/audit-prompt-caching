# Plugin Eval Comparison: audit-prompt-caching

## At a Glance
- Score delta: +14
- Grade: F -> D
- Risk: high -> high
- Budget delta (trigger/invoke/deferred): -35 / -2 / +3498

## Why It Matters
- Score delta: +14.
- Grade moved from F to D.
- Risk moved from high to high.
- 1 failure were resolved.

## Fix First
- No new failures were introduced.

## Recommended Next Step
- Continue from the improved baseline
- Why: The comparison is trending in the right direction, so the next move is to keep the workflow tight and repeatable.
- Chat request: "What should I run next?"
- Local command: `plugin-eval start ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --request 'What should I run next?' --format markdown`

## Details
<details>
<summary>Resolved failures</summary>

- trigger_cost_tokens-budget-high
</details>
<details>
<summary>New failures</summary>

- No new failures.
</details>
