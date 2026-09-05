# Five-participant pilot protocol

## Purpose and limits

Invite up to five people to try the pinned draft on a naturally occurring,
real prompt-cache task. Participation is voluntary. The proposed learning
targets are:

- three people with a useful first real audit;
- two people with an independent repeat, counted only after a suitable later
  task occurs.

These are operating targets, not measured results, forecasts, conversion
rates, or market estimates. Keep unavailable values unknown. Do not recruit a
replacement solely to make a denominator look better.

## Low-burden flow

1. Assign a stable pseudonymous participant ID (`P001` through `P005`) and send
   one invitation draft from [messages.md](messages.md).
2. Give an accepted participant the [participant guide](README.md). A demo is
   optional; the pilot starts only on their own real project task.
3. Let the participant choose the prompt/config path or, when they already have
   a conforming export, the normalized-routing path. Never ask them to upload a
   full private repository, secrets, raw customer prompts, or unrestricted
   logs.
4. Record milestones in a private copy of
   [participants.csv](participants.csv) and each real audit in a private copy
   of [audits.csv](audits.csv). Use ISO 8601 timestamps with an explicit offset
   when known.
5. Offer help only when requested. After the first result, wait for a suitable
   later task before asking whether an unassisted repeat occurred.

Keep filled ledgers private unless each participant explicitly agrees to the
specific fields being shared. The repository contains headers only.

## Ledger schema

Use `P001` through `P005` for `participant_id` and sequential IDs such as
`A001` for `audit_id`. Keep the mapping from a participant ID to a person
outside the repository. Do not put names, repository URLs, prompt text, or raw
logs in either ledger.

`participants.csv` has one row per invitee:

| Column | Value |
|---|---|
| `participant_id` | Stable pseudonymous ID. |
| `invited_at`, `accepted_at`, `first_real_task_at`, `repeat_opportunity_at` | ISO 8601 timestamp with offset, or empty when absent or unknown. |
| `first_audit_id` | The participant's first real audit ID, or empty before a start. Demo audit IDs never go here. |
| `help_level` | Highest help used on the first real audit: `none`, `install`, `artifact_choice`, `interpretation`, `multiple`, or empty before a start. |
| `repeat_opportunity_status` | `observed`, `not_observed`, or `unknown`; use `observed` only with a corresponding timestamp. |
| `independent_repeat_audit_id` | A later real audit with `repeat_type=independent`, started after the recorded repeat opportunity; otherwise empty. |
| `notes` | Optional short, non-identifying operational note. |

`audits.csv` has one row per demo or real audit:

| Column | Value |
|---|---|
| `audit_id`, `participant_id` | Stable audit ID and matching participant ID. |
| `task_context` | `demo` or `real`. |
| `audit_path` | `prompt_config` or `normalized_routing`. |
| `project_scope_alias` | Non-identifying label such as `support_agent`; never a private URL. |
| `skill_ref` | Exact tested commit, expected to be `8c1b18c00d482df68b78a1bb3af3fe7c296971fa` for this pilot. |
| `started_at`, `result_at` | ISO 8601 timestamp with offset, or empty when unknown or no result exists. |
| `outcome` | One value from the outcome list below, or empty while in progress. |
| `useful_completion` | `yes`, `no`, or empty while in progress. |
| `artifacts_available` | Small category list such as `code_config`, `rendered_requests`, `normalized_jsonl`, or `none`; no paths or content. |
| `help_level` | `none`, `install`, `artifact_choice`, `interpretation`, or `multiple`. |
| `next_measurement` | Short non-sensitive description, `none`, or `unknown`. |
| `finding_review_coverage` | `all`, `some`, `none`, or `not_applicable`; `some` and `all` both mean at least one actionable finding was actually checked. |
| `contradicted_actionable_finding` | `yes` when at least one reviewed actionable finding was contradicted; `no` when at least one was reviewed and none of that reviewed subset was contradicted; `unknown` when findings exist but none were reviewed; `not_applicable` when the audit has no actionable finding. |
| `repeat_type` | `first`, `independent`, `assisted`, or `not_applicable` for a demo. |
| `notes` | Optional short, non-identifying operational note. |

## Definitions and denominators

| Measure | Operational definition | Denominator or calculation |
|---|---|---|
| Invited | The invitation was actually delivered to one distinct person. Drafting does not count. | Count of distinct `participant_id` values with `invited_at`. Maximum five for this pilot. |
| Accepted | The invitee explicitly opted in to try the pilot. Silence and polite interest do not count. | Acceptance rate = distinct accepted participants / distinct invited participants. |
| Started | The participant applied the skill or a pinned helper to their own current project task and supplied the minimum local input. A bundled demo does not count. | Start rate = distinct participants whose `first_audit_id` points to a started real audit / distinct accepted participants. |
| First-use useful completion | The participant's first real audit produced an evidence-backed useful finding, a justified no-change result, or one concrete obtainable next measurement tied to a decision. | First-use useful-completion rate = distinct participants whose `first_audit_id` has `useful_completion=yes` / distinct participants with a started first real audit. Target count: 3 people. |
| Incomplete first audit | The first real audit could not reach any useful-completion outcome. Preserve the reason as missing evidence, command failure, scope mismatch, or unknown. | Incomplete first-audit rate = distinct participants whose `first_audit_id` has `useful_completion=no` / distinct participants with a started first real audit. Never reclassify it to meet the target. |
| Time to result | Wall-clock time from `started_at` to the first useful-completion result on each participant's `first_audit_id`. | Median and range among first-use useful completions with both timestamps; report the count with known timing. Do not treat missing timestamps as zero. |
| Help | Human assistance on the first real audit after acceptance, classified as `none`, `install`, `artifact_choice`, `interpretation`, or `multiple`. Documentation alone is `none`. | Report counts by class across distinct participants with a started first real audit. |
| Repeat opportunity | After a participant's first real audit, a later real task occurs where the skill is applicable and the participant can reasonably use it. A scheduled demo or manufactured task is not an opportunity. | Count distinct participants with `repeat_opportunity_status=observed` and `repeat_opportunity_at`. Use `not_observed` when no later task has occurred and `unknown` when follow-up cannot establish whether one occurred. |
| Independent repeat | On a repeat opportunity, the participant starts another real audit without live operator help or a direct prompt to run it for that task. A later factual check-in may discover it. | Independent-repeat rate = distinct participants with a qualifying `independent_repeat_audit_id` / distinct participants with a repeat opportunity. Target count: 2 people, only if opportunities occur. |

For each rate, report both numerator and denominator. If a denominator is zero,
report `not available`, not `0%`. Count additional real audits separately by
`repeat_type`; never add them to the first-use funnel or count more than one
repeat opportunity or independent repeat per participant.

## Outcomes and review

Use exactly one `outcome` per audit:

- `useful_finding`
- `useful_no_change`
- `concrete_next_measurement`
- `incomplete_missing_evidence`
- `incomplete_command_failure`
- `incomplete_scope_mismatch`
- `incomplete_unknown`

The first three set `useful_completion=yes`; the others set it to `no`.
No-change remains a positive result when the inspected scope and evidence are
clear. Insufficient evidence remains visible even when it lowers completion.

Classify `task_context=demo` for bundled examples and `task_context=real` only
for the participant's own current task. Demo rows may be recorded for support
diagnosis, but exclude them from started, completion, timing, false-positive,
and repeat measures.

An actionable finding is contradicted when the authoritative request path,
provider usage record, or observed routing outcome shows that the reported
defect does not exist in the active path. This is different from an unverified
finding, a low-impact issue, a no-change result, or an incomplete audit.

The ledger supports an **audit-level false-positive incidence**, not a
finding-level rate:

```text
distinct first real audits with contradicted_actionable_finding=yes
-----------------------------------------------------------------
distinct first real audits with finding_review_coverage=some or all
```

Report the numerator and denominator. `finding_review_coverage=some` preserves
mixed or partial verification: `contradicted_actionable_finding=no` then means
only that none of the reviewed subset was contradicted. It does not validate
the unreviewed findings or the audit as a whole. Exclude audits with `none` or
`not_applicable` coverage from both sides of this measure.

## Closeout readout

At the end, report distinct-participant counts for invited, accepted, first
real audits started, first-use useful completions by outcome, incomplete first
audits by reason, and help class. Report additional audits separately. Report
time-to-result only for known first-audit pairs. Report distinct people with
repeat opportunities separately from distinct people with independent repeats.
Add a short qualitative list of recurring friction, but do not identify
participants or publish their artifacts.
