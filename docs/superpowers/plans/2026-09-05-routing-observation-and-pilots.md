# Routing observation and first external pilots

**Goal:** Make the next audit reproducible from obtainable inputs and prepare a
usable first-pilot packet. Website implementation is already assigned to its
existing thread; do not duplicate it here.

**Base:** `54f333fd06fafc7a8428aab7242682548c5891af` on draft PR #21.
This continuation uses the isolated `codex/cache-pilot-evidence` branch.
The original checkout and the first PR remain intact.

## 1. Establish available evidence

- [x] Search bounded local project artifacts for correlated standalone
  vllm-router/worker/client exports. Report field coverage and gaps without
  publishing private records or treating aggregate metrics as traces.
- [x] Inspect pinned router source and reproduce its observation boundary in
  an isolated loopback-only lab if the available runtime permits. Pin the
  router commit and use controlled mock HTTP workers with synthetic inputs.
  This exercises a real router and fake workers; it is not vLLM inference,
  a production trace, a KV benchmark or a policy performance comparison.
- [x] Keep native observations, injected instrumentation, synthetic worker
  values and inferred joins distinct. Do not synthesize an upstream attempt ID
  from row order, timestamps or a client request number.

## 2. Deliver a reusable technical result

- [x] Record exact commands, versions, inputs, observed fields and supported
  conclusions. If a correlated export exists, run the analyzer and retain the
  mapping evidence. If native fields are absent, provide an exact export or
  instrumentation contract with evidence for the missing links.
- [x] Prefer a small reproducible lab or example over a heuristic native-log
  parser. Keep any new repository helpers stdlib-only; use RED/GREEN for their
  behavior changes. Network activity, if a lab helper is needed, is explicit
  and restricted to local test endpoints outside the installed skill.
- [x] Independently review the technical contract and the resulting code or
  reproduction. Preserve the Routing Outcome Gate and explicit unknowns.

## 3. Make the first pilot possible

- [x] Add a short participant guide: choose a real task, pin the skill version,
  supply minimum artifacts, run the audit, verify a result, and return feedback.
  Include prompt/config and normalized-routing paths, plus the valid outcomes
  of no change, missing evidence, and incomplete audit.
- [x] Add an operator protocol and an empty results ledger with definitions
  for invited, started, completed useful audit, time-to-result, independent
  repeat use, and missing repeat opportunity. Do not enter fake participants.
- [x] Prepare invitation and follow-up drafts for five voluntary pilots. No
  external messages or posts are sent in this task. The learning targets are
  three completed useful audits and two independent repeats when a relevant
  next task occurs; these are not observed results or a market estimate.
- [x] Connect the Habr draft's practical section to the actual available
  package/version without claiming that synthetic examples prove production
  performance. Keep the article independently useful.

## 4. Verify and deliver

- [x] Verify affected behavior, package and link integrity, command examples,
  and whitespace. Run existing suite if code or package integration changes.
- [x] Run spec review, then quality review; resolve actionable findings.
- [x] Commit and prepare a separate draft PR stacked on #21, making the
  dependency and supported conclusions explicit. Do not merge or publish
  articles implicitly.
- [x] Update the durable editorial execution record with actual results,
  unavailable evidence and the next concrete input needed for real pilots.

## Decisions and observed progress

- No correlated local production export was found in the bounded discovery.
  The deliverable is an exact capture contract plus a controlled observation
  lab; no parser invents missing attempt identity.
- Built unmodified upstream router `1d10e71` with its locked dependencies,
  Rust 1.94.1, debug profile and two build jobs. Real loopback runs used one
  synthetic HTTP worker, no GPU, no OTel and disabled retries.
- A nonempty repeated chat prompt produced policy input 0/0. Source inspection
  found that the pinned regular HTTP chat path supplies a session ID or empty
  string, not message text. Added a scoped vLLM/routing reference correction
  and manual behavioral scenario 33; other endpoints/versions remain separate.
- Three HTTP200 responses yielded three circuit-breaker successes; only two
  included intended stream terminal markers. This is an observation-boundary
  reproduction, not a GPU benchmark or a claim of a circuit-breaker defect.
- Inherited `RUST_LOG=warn` suppressed debug logs in the first run. The next
  run explicitly set `RUST_LOG=vllm_router_rs=debug` and preserved policy logs.
- Pilot spec and quality reviews passed after fixes to denominators, partial
  finding verification, command errors, fail-closed version pinning and the
  distinction between local helpers and configured agent data processing.
- Updated the private Habr/router drafts and research notes; sent the API-path
  and stream-boundary corrections to the existing website thread. Articles
  and pilot invitations have not been published or sent externally.

## Measured package budget

The existing guard requires remeasurement for new guidance rather than removing
established provider behavior. The first full run reached 212 tests and failed
only that guard: 60,163 estimated deferred tokens exceeded the prior 59,427.
The corrected ceiling is exactly the measured 240,650 characters / 60,163
`ceil(chars / 4)` estimate. The increase is 2,943 characters: 1,309 for the pinned
API-path reference, 531 for the export interpretation boundary, and 1,103 for
behavioral scenario 33. This estimate includes eval/script source; it is not
actual model token usage or all context loaded during every audit.

The trigger ceiling remains 147 and SKILL.md remains 25,573 characters / 6,394
estimated tokens. The pilot packet, loopback helper, offline tests and raw lab
records are outside the installed skill. Ruling: accept the measured increase
of 736 estimated deferred tokens to prevent a source-confirmed API-path error;
leave other provider references and the Routing Outcome Gate intact.

## Final local verification

- Full discovery: **213 tests passed** after the measured ceiling update and
  persistence-failure fix; the lab has **8 focused offline tests**, with RED
  observed before its implementation and its error-path correction.
- Skill package validation and the **31-record trigger dataset** passed. The
  latter is dataset validation, not a measured agent trigger success rate.
- Python syntax (including the external lab), shell recipe syntax, 24 relative
  Markdown links and staged whitespace passed. The raw Prometheus snapshot's
  native final blank line has one exact-path `.gitattributes` exception.
- Final real loopback run exited 0 with `stream_complete=[true,true,false]`;
  all three HTTP statuses were 200. Five preserved raw artifacts match the run
  byte-for-byte and their documented SHA-256 values.
- A fresh agent used a separate installed package and the supplied artifacts,
  without reading the expected answer/evals. It identified the API-path cause
  of 0/0, rejected a shared session ID as KV proof, identified the incomplete
  stream and kept engine/cache performance unknown. This is one behavioral
  check, not a population-level evaluation.
- Technical spec review passed after a regression reproduced and fixed an
  erroneous successful manifest on metrics-write failure. Pilot spec and
  quality reviews passed; final whole-branch quality review: **APPROVE**.

## Delivery

Implementation commit: `8c1b18c00d482df68b78a1bb3af3fe7c296971fa`.
Draft [PR #22](https://github.com/sernote/audit-prompt-caching/pull/22) targets
`codex/cache-first-audit` and remains dependent on draft #21. The pilot guide
and operator schema pin the tested implementation commit; main is unchanged.
The final documentation commit only advances those pins and records completion.

The author's local editorial execution record links to the PR, lab artifacts
and pilot guide and distinguishes this completed preparation from external pilot
results, publication or a comparative GPU benchmark. No pilot invitations or
Habr/Telegram posts were sent. CI status must be read for the final PR head.
