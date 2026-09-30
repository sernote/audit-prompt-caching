# Cache Source Watch

Maintainer tooling that keeps `audit-prompt-caching` current. Once a day, a
coordinator agent checks the official sources behind the skill's references,
triages changes against a relevance gate, and dispatches bounded
implementation threads that end in a reviewable pull request.

This directory is not part of the installed skill and adds no skill prompt
tokens. Design: `docs/superpowers/specs/2026-09-30-cache-source-watch-design.md`.

| File | Purpose |
|---|---|
| `sources.json` | Curated registry: one monitored URL per entry, with priority, type, dating, cadence, affected references, cache relevance, extraction approach, and verification record |
| `daily-run.md` | Coordinator runbook for each heartbeat |
| `child-thread.md` | Brief for an implementation thread |
| `cache_watch.py` | Stdlib ledger CLI: run lease, per-source windows and cursors, snapshots, triage, reservations, lifecycle |
| `activation.example.json` | Shape of the local activation config (real values stay outside the repository) |

## Bootstrap and activation

Requirements: Python 3.10+ on a POSIX host (the ledger uses `fcntl` locks).

1. **Validate** the registry from a reviewed commit:
   `python3 maintenance/cache-watch/cache_watch.py validate-registry --registry maintenance/cache-watch/sources.json --repo-root .`
2. **Copy** `maintenance/cache-watch/` from that commit into a runtime directory
   keyed by commit (for example `<runtime-root>/<commit>/`). The schedule must
   not depend on a disposable worktree or an unmerged checkout.
3. **Create** the state directory outside every git checkout and initialize it:
   `python3 <runtime>/cache_watch.py init --ledger <state-dir>`. The CLI refuses
   a ledger inside a work tree. This production ledger always uses the real
   clock; `--now` works only on scratch ledgers created with
   `init --test-clock` (tests and smoke runs).
4. **Configure:** write the local activation config from
   `activation.example.json` next to the state, with real paths, repository,
   schedule, coordinator thread, and limits.
5. **Schedule** one daily heartbeat in the coordinator thread that follows
   `daily-run.md`.
6. **Baseline run.** The first run records snapshots of undated docs as
   `baseline` (not changes) and triages only dated entries inside the window.
   Changes to undated docs are detected from the second run on.

To upgrade, review and merge registry or runbook changes, copy the new commit
into a new runtime directory, and point the activation config at it. The
ledger is unaffected.

## Maintaining the registry

- Prefer contract docs and pricing pages for provider behavior, and
  release pages or changelogs for dated engine and SDK changes.
- Blogs and benchmarks are `discovery_only`. They lead to a contract
  source but never justify an implementation.
- Add a feed only after fetching it and seeing feed XML.
- Record how each URL was verified (`verified.on`, `method`, `result`). A
  source that currently fails verification stays listed with the observed
  failure, so the daily run reports it instead of skipping it silently.
- Every `affects` path must exist. `tests/test_cache_watch.py` validates the
  registry.
- Quote any `gh api` path containing `?` in `extraction`, for example
  `gh api 'repos/o/r/releases?per_page=30'`. Unquoted, zsh aborts with
  `no matches found`. `validate-registry` refuses the unquoted form.
