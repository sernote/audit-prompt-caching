# Contributing

This repository keeps `audit-prompt-caching` portable: scripts must stay dependency-free and Python stdlib-only unless a change explicitly documents why an external dependency is worth the portability cost.

## Change Checklist

- Add or update tests before changing script behavior.
- Keep provider-specific rules in the relevant `references/*.md` file.
- Use `fixtures/` for redacted reproducible examples.
- Curated guides, examples, and fixtures intended for users are repository deliverables, including their required logs and snapshots. Keep ephemeral agent working materials (plans, design drafts, journals, review and eval reports, execution logs, and source snapshots) in an artifact directory outside every checkout of this repository; do not commit them.
- Run the full local verification suite before submitting changes:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
git diff --check
```

Remove generated `__pycache__` directories and `*.pyc` files before committing.
