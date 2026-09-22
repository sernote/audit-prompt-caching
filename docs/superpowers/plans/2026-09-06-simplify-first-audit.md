# Simplify the first real audit

> **For agentic workers:** Use superpowers:executing-plans for this approved correction.

**Goal:** Give readers a direct project-audit path and optional feedback, while
retaining the verified router observations from PR #22.

**Architecture:** One short guide links to the existing feedback issue template.
Advanced routing capture stays in technical documentation. The optional router
lab leads with its findings and recorded artifacts. Script behavior is unchanged.

**Tech stack:** Markdown, existing Python stdlib helpers, GitHub issue template.

## Approved scope and baseline

The user approved simplifying the pilot package after reviewing its unnecessary
process and the missing real-world input for the normalized analyzer. Participant
quotas, ledgers and operator/recruitment protocols are not product requirements.

Main is `622677ae476c64d875663faf53a93353ab17a5e7` (PR #21). PR #22 was merged
later into `codex/cache-first-audit`, at `f416efec82180edb49d1deb604ba4cfec49c607b`,
and is not in main. Port the useful files explicitly and open a PR against main.
Keep the original dirty checkout and the historical PR branches intact.

The carried-over package budget is 240,650 deferred characters / 60,163
`ceil(chars / 4)` estimated tokens. Its 736-token increase over main covers the
pinned API-path guidance and behavioral scenario 33. Accept that previously
measured increase; the main skill remains at 6,394 estimated tokens. This cleanup
does not change the installed package relative to #22. The test comment points
here because #22's superseded pilot plan is not included.

## Steps

- [x] Carry over the unchanged router lab, recorded artifacts, API-path
  references, behavioral scenario and matching existing tests/budget from #22.
  Do not carry over `docs/pilots/` or its implementation plan.
- [x] Add `docs/first-audit.md`: install through the existing README, run the
  skill on one real project task, verify the result, optionally use the existing
  `.github/ISSUE_TEMPLATE/audit-result.md`. No enrollment, quota or result ledger.
- [x] Move #22's technical capture guidance to `docs/routing-capture.md`, remove
  pilot dependencies, and keep it an optional reference for advanced routing
  investigations. Position the normalized analyzer as experimental until a
  real export exercises the complete path.
- [x] Update the root README and lab README: project audit first, advanced
  routing later; recorded findings before native-build instructions. Repair
  all local links and avoid temporary PR-version installation instructions.
- [ ] Correct the local editorial handoff, article links and roadmap so they
  use the simplified entry point and do not require participant quotas before
  publication. Notify the existing website task using public links only.
- [x] Verify all 213 existing tests, package and trigger-dataset validation,
  Markdown links, raw artifact hashes, unchanged script behavior and whitespace.
  No new tests are needed for this documentation-only correction.
- [x] Get an independent review of the final changes. Delivery is a draft PR
  targeting current main; its published diff and CI status must be checked.

## Acceptance

The first-use path requires only installation and a real project task. Feedback
is optional. The final diff contains no pilot enrollment, ledger, recruitment
protocol or numerical adoption gate. Technical limits remain explicit: mock
worker timings are not inference results and normalized exports require real
identity mappings. Publication of articles is separate from repository changes.

## Verification before delivery

All 213 tests passed in 20.788 seconds. Package and 31-record trigger-dataset
validation passed; the latter does not execute agent behavior. All 23 relative
Markdown links resolve and all five recorded artifact hashes match. Installed
package, probe and raw artifacts match #22 byte-for-byte; the changed budget
comment leaves the test AST identical. Independent final review approved the
candidate after the budget comment was pointed to this plan.
