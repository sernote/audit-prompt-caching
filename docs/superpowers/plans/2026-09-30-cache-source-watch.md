# Daily Cache Source Watch

**Goal:** Add a maintainable source registry and a daily discovery, triage, and
dispatch workflow for `audit-prompt-caching`, with a small stdlib ledger that
makes coverage, dedupe, and reservations durable. See
`docs/superpowers/specs/2026-09-30-cache-source-watch-design.md`.

**Constraints:** No changes to `audit-prompt-caching/` (zero installed-skill
tokens). Stdlib only. TDD for the helper. No commit, push, PR, or automation
creation in this thread; the coordinator owns those. Deviation journal:
`docs/tmp/2026.09.30_cache-watch_deviations.md`.

## Tasks

- [x] Record the static plugin-eval baseline of the installed skill before changes.
- [x] Inventory the providers and projects the references cite; discover and
  verify primary URLs live (curl, falling back to web fetch), including
  release channels and feeds that actually return XML.
- [x] Write the tests in `tests/test_cache_watch.py` first and observe RED
  (the module does not exist yet):
  - windows: first run, cursor catch-up, overlap, capped catch-up with a
    single recorded gap, cadence (weekly not due), and a failed first run that
    keeps its original `pending_from` on later retries;
  - lease: second start refused while live; expiry marks the run abandoned; a
    wrong or expired token cannot record, triage, reserve, or dispatch;
  - checks: failed/partial keep the cursor; finish-run `partial` exits 2 with matching JSON;
  - snapshots: baseline, whitespace-only unchanged, changed with diff; a
    change staged in an abandoned run is still `changed` next run;
  - triage: incomplete `implement` gate refused; bare-URL alias refused; bound
    alias dedupe merges evidence; a second distinct change on the same URL is
    a new candidate; `duplicate_active` while work is live;
  - reservations: the active cap, the attempt cap, the uncertain path that blocks
    re-reservation, release, and failure followed by a retry;
  - PR lifecycle: a completed thread with an open PR still blocks duplicates
    and counts toward the cap; `closed_unmerged` requires re-triage; `merged`
    is separate from thread status;
  - concurrency: parallel processes reserving the same key yield one winner;
  - safety: a ledger inside a git work tree is refused; a failed atomic write keeps the old ledger;
  - registry: the real `sources.json` validates and every `affects` path exists.
- [x] Implement `maintenance/cache-watch/cache_watch.py` minimally to GREEN.
- [x] Write `sources.json` from the verified inventory.
- [x] Write `daily-run.md`, `child-thread.md`, `activation.example.json`, and `README.md`.
- [x] Add pointers in the repository `README.md` and `AGENTS.md` layout.
- [x] Smoke run the CLI against a temporary ledger: start, record, triage,
  reserve, mark uncertain, release, and finish. Create no thread.
- [x] Verification: unit tests, package validator, trigger eval, syntax,
  `git diff --check`, and bytecode cleanup.
- [x] Static plugin-eval after the change; report the delta separately from behavioral evidence.
- [x] Update the deviation journal and this plan with the results.

Later parent corrections (added as RED tests, then implemented): the
test-clock ledger mode, required snapshot or `--items`, required references
and a known source in the gate, `disabled` reporting, verbatim source dates,
`clientThreadId` refusal, JSON error envelopes, and `pr open`/`merged`
clearing `needs_decision`. See the deviation journal.

## Fix round 2026-09-30: final review findings 1-3

Source: `/tmp/cache-watch-final-review.txt`, findings 1-3 as validated by the
parent. Scope is only these three; bytecode cleanup is the parent's
pre-commit hygiene step, and failing sources stay enabled.

- [x] RED tests first (`tests/test_cache_watch.py`):
  - two different keys sharing one release or snapshot alias return
    `alias_conflict` (exit 3) and leave the first candidate's outcome, gate,
    aliases, evidence and dispatch untouched, also when it is reserved;
    the existing key still merges; change-scoped aliases (`@<binding>#<topic>`)
    create distinct candidates; an unresolved conflict is listed by
    `finish-run`; an empty `#` topic is refused;
  - update the two old tests that required silent merging of different keys;
  - backlog: failed, released and capacity-deferred `implement` candidates
    stay in `status.attention` after later runs advance every source; merged
    work is not listed; `attempts_exhausted` sets `needs_decision` and keeps
    the dispatch record and a history entry;
  - quoting: every `gh api` path containing `?` in `sources.json` extraction
    and in `daily-run.md` is quoted (registry validation plus a runbook check).
- [x] Implement minimally to GREEN in `cache_watch.py`.
- [x] Update `sources.json` extraction strings, `daily-run.md` (quoted
  commands, per-shell setup, alias conflict resolution before `finish-run`,
  daily backlog processing, known versus new failures in the summary), and
  the spec.
- [x] Correct deviation journal item 10 and append this round.
- [x] Verification commands from `AGENTS.md`.

## Results (2026-09-30)

- `python3 -m unittest discover -s tests -p 'test_*.py'`: 276 tests OK (36 in
  `test_cache_watch.py`). After the fix round: 281 tests OK (41 in
  `test_cache_watch.py`). The fix round's RED run had 41 tests with 4
  failures and 2 errors, all for the expected reasons.
- Package validator `ok`; trigger eval 40 cases (30 positive, 10 negative), no errors.
- Registry: 77 sources, 26 groups, all daily; 8 marked partial or unverified
  and still enabled. All 10 `gh api` paths are quoted, and `validate-registry`
  returns `valid`.
- Syntax compile OK, including `maintenance/cache-watch/cache_watch.py`;
  `git diff --check` clean. Bytecode left by the test runs (for example
  `audit-prompt-caching/scripts/__pycache__/`) is removed by the parent's
  pre-commit cleanup.
- Fix-round CLI smoke (a subprocess on a scratch test-clock ledger, real
  registry): a shared release alias under a second key returned
  `alias_conflict`, exit 3, `ok: false`. The first `implement` candidate stayed
  in `attention` as `dispatch backlog: none, attempt 0`.
- plugin-eval static analysis: 59/D before and after, budget delta +0/+0/+0
  (no skill files changed). Nothing here is behavioral evidence of daily
  operation; that is limited to the unit tests and one CLI smoke run.

## Exit codes (CLI contract)

`0` ok · `1` usage or validation error · `2` run finished `partial` ·
`3` duplicate or conflicting state · `4` limit reached (capacity or attempts) ·
`5` run lease held by another run, or invalid/expired · `6` ledger lock timeout. JSON on stdout always
carries `ok` and `status` consistent with the exit code.
