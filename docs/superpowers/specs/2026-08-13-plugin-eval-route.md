# Plugin Eval Start Here: audit-prompt-caching

## At a Glance
- Recommended path: Evaluate Skill
- Benchmark config present: no
- Usage log present: no
- Quick local entrypoint: `plugin-eval start ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --request 'Evaluate this skill against the draft cache audit evidence contract: provider field provenance, denominator validity, explicit cache planes, and a no-score clinic summary.' --format markdown`
- First local command: `plugin-eval analyze ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown`

## Why It Matters
- Start with a natural chat request, then let plugin-eval show the exact local command sequence behind it.
- Plugin Eval routed "Evaluate this skill against the draft cache audit evidence contract: provider field provenance, denominator validity, explicit cache planes, and a no-score clinic summary." to Evaluate Skill because it asks for the overall evaluation report or prioritized findings from it.

## Fix First
- Start with the recommended path before branching into secondary workflows.

## Recommended Next Step
- Evaluate Skill
- Why: Plugin Eval routed "Evaluate this skill against the draft cache audit evidence contract: provider field provenance, denominator validity, explicit cache planes, and a no-score clinic summary." to Evaluate Skill because it asks for the overall evaluation report or prioritized findings from it.
- Chat request: "Evaluate this skill against the draft cache audit evidence contract: provider field provenance, denominator validity, explicit cache planes, and a no-score clinic summary."
- Local command: `plugin-eval analyze ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown`

## Details
<details>
<summary>Full local sequence</summary>

- plugin-eval analyze ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown
</details>
<details>
<summary>Other chat requests</summary>

- Full Skill Analysis: "Give me a full analysis of this skill, including benchmark setup." -> plugin-eval analyze ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown
- Evaluate Skill: "Evaluate this skill." -> plugin-eval analyze ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown
- Explain Token Budget: "Explain the token budget for this skill." -> plugin-eval explain-budget ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown
- Measure Real Token Usage: "Measure the real token usage of this skill." -> plugin-eval init-benchmark ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching
- Benchmark With Starter Scenarios: "Help me benchmark this skill." -> plugin-eval init-benchmark ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching
- Start Here: "What should I run next?" -> plugin-eval analyze ~/.config/superpowers/worktrees/audit-prompt/cache-audit-report-contract/audit-prompt-caching --format markdown
</details>
