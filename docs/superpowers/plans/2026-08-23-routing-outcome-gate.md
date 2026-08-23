# Cache-Aware Routing Outcome Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Исправить ложный критерий успеха в `audit-prompt-caching`: рост cache hit rate или попадание запросов на «правильную» replica не должны сами по себе подтверждать, что cache-aware routing полезен и готов к rollout.

**Architecture:** Оставить структуру скилла без новых скриптов и новых cache-plane abstractions. Ввести один общий `routing outcome gate` в `references/mechanics.md`, сослаться на него из `SKILL.md`, AP-7, predeploy checklist и engine-specific references, а поведение закрепить двумя repo evals, статическими contract tests и отдельным before/after behavioral eval на свежих agent contexts.

**Tech Stack:** Markdown, JSON, Python 3 stdlib `unittest`, существующие package/trigger validators, Superpowers skill TDD workflow.

**Spec:** `docs/superpowers/plans/2026-08-23-routing-outcome-gate.md#design-contract`

**Review:** Claude Opus 5, high effort, 2026-08-23 — `APPROVE WITH CHANGES`; blocking findings are resolved in this revision.

## Global Constraints

- На момент планирования локальный `main` был на `cabdfeac`, а удалённый `main` — на `99f3ea94`; текущий checkout содержит пользовательские modified/untracked files. Перед реализацией заново проверить SHA и работать в отдельном worktree от свежего `origin/main`.
- Не удалять и не перезаписывать файлы из dirty checkout. В частности, не «чистить» существующие `__pycache__`, `stream-demo/`, планы и незакоммиченный `tests/test_prompt_cache_scripts.py`.
- Не делать commit, push или PR без отдельного разрешения пользователя. В конце подготовить diff и предложить commit message.
- Следовать TDD для skill behavior: сначала зафиксировать поведение текущего скилла, затем получить RED на новых contract tests, после минимальной правки получить GREEN и повторить те же behavioral cases в свежих контекстах.
- Не превращать исследовательскую статью в источник универсальных числовых порогов. `CacheRoute` (`arXiv:2608.19677`) используется как методологическое основание разделять hit/locality и capacity, учитывать residual load imbalance и проверять routing через matched replay. Headline numbers и алгоритм статьи в скилл не переносятся.
- Не реализовывать P0-1: не добавлять upstream identity contract, credential-pool tracing, relay-hop audit или cross-tenant probes. Допустима одна защитная фраза в AP-7: ради hit rate нельзя расширять trust/isolation boundary без отдельной security/privacy проверки.
- Не менять AP-9b, provider adapters, usage normalization, helper scripts или cache-plane model. Trigger surface не меняется, поэтому `evals/trigger_eval.json` не трогать, если RED не докажет отдельную trigger-регрессию.
- Не дублировать полный outcome gate во всех references. Нормативное объяснение живёт в `references/mechanics.md`; остальные файлы дают короткую engine/workflow-specific ссылку и локальные проверки.
- `SKILL.md` править char-neutral или net-negative: на проверенном `origin/main` он занимал 5 850 токенов при жёстком ceiling 5 852 и запасе около 10 символов. `PLUGIN_EVAL_SKILL_TOKEN_BASELINE` не поднимать.
- Deferred budget уже был в статусе FAIL до этой работы: 41 238 токенов. Не называть его green; измерить до/после, не увеличить более чем на 400 токенов и записать оба значения в handoff.
- Канонические anchors для cross-reference tests: `Routing Outcome Gate`, `matched-workload comparison`, `capacity at SLO`, `rewarm`. Не вводить конкурирующие названия `fixed-load comparison`, `matched-load` или `lifecycle test`.
- Сохранить все существующие provider/eval cases и не расширять deferred references без необходимости.

---

## Design Contract

### Решение

Cache-aware routing — кандидат на эксперимент, а не обязательный default. Успех routing change определяется не hit rate, а заранее объявленной целью и эксплуатационными guardrails.

Baseline — действующая production routing policy, какой бы она ни была. Candidate — предлагаемое изменение. Проверка состоит из трёх разных измерений:

1. **Matched-workload comparison:** baseline и candidate получают один open-loop arrival process с одинаковыми prefix families, input/output lengths, model/tokenizer, replica count и KV configuration. Сравниваются p95/p99 TTFT, p95/p99 end-to-end latency, queue, per-replica load/KV skew, errors и retries. Closed-loop результаты допустимы только как неразрывная тройка `(concurrency, throughput, latency)`, а не как самостоятельное latency-доказательство.
2. **Capacity at SLO:** отдельный open-loop sweep по arrival rate находит максимальный устойчивый throughput, при котором заданные latency/error SLO ещё выполняются. Нельзя выводить capacity из одного фиксированного load point.
3. **Rewarm:** restart, scale-out/scale-in или failover проверяет rewarm loss, recovery time и временные SLO violations.

Cache hit rate, route affinity и cached-token share остаются mechanism metrics: они помогают понять, почему candidate ведёт себя иначе. Rollout проходит gate, только если candidate улучшает объявленную цель и не нарушает заранее заданные SLO/guardrails. Если вырос hit rate, но ухудшились tail latency, capacity, balance, errors или rewarm, routing change отклоняется или откатывается.

### Три допустимых вердикта скилла

- **Reject/rollback:** candidate нарушил заранее заданный SLO/guardrail, даже если hit rate вырос.
- **Pilot/canary only:** видна гипотеза или mechanism improvement, но нет matched-workload comparison, capacity at SLO или rewarm evidence.
- **Accept/roll out conditionally:** объявленная цель улучшилась, guardrails выдержаны, rollback trigger и наблюдаемость готовы.

### Что не меняется

- Round robin не объявляется хорошим или плохим сам по себе.
- Prefix-aware, sticky и stable-prefix hashing не объявляются хорошими сами по себе.
- Isolation boundary не ослабляется ради locality.
- Provider-managed prompt cache, engine KV cache и response cache остаются разными planes.

## Planned File Surface

- Add: `docs/superpowers/plans/2026-08-23-routing-outcome-gate.md`
- Create: `docs/superpowers/specs/2026-08-23-routing-outcome-gate-behavioral.md`
- Modify: `audit-prompt-caching/SKILL.md`
- Modify: `audit-prompt-caching/references/rules.json`
- Modify: `audit-prompt-caching/references/predeploy-checklist.md`
- Modify: `audit-prompt-caching/references/mechanics.md`
- Modify: `audit-prompt-caching/references/observability.md`
- Modify: `audit-prompt-caching/references/report-template.md`
- Modify: `audit-prompt-caching/references/vllm.md`
- Modify: `audit-prompt-caching/references/sglang.md`
- Modify: `audit-prompt-caching/evals/evals.json`
- Modify: `tests/test_prompt_cache_scripts.py`
- Do not modify: `audit-prompt-caching/evals/trigger_eval.json`
- Do not modify: `audit-prompt-caching/scripts/**`
- Do not modify: `audit-prompt-caching/references/rules.json` AP-9b
- Do not modify: `audit-prompt-caching/references/use-cases.md`
- Do not modify: `audit-prompt-caching/references/openrouter.md`
- Do not modify: `audit-prompt-caching/references/operational-playbook.md`

---

### Task 1: Create an isolated, current implementation workspace

**Files:**

- Read: `AGENTS.md`
- Read: this plan
- No product-file edits yet

- [ ] **Step 1: Re-read the execution skills**

Use `superpowers:using-git-worktrees`, `superpowers:test-driven-development`, `superpowers:writing-skills`, and either `superpowers:subagent-driven-development` or `superpowers:executing-plans` before editing.

- [ ] **Step 2: Re-check repository state and remote base**

Run from `/Users/notevskii/develop/audit-prompt`:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git fetch origin main
git rev-parse origin/main
```

Expected: the primary checkout may remain dirty; do not modify or clean it. Record the fresh `origin/main` SHA in implementation notes.

- [ ] **Step 3: Create a dedicated worktree**

Use `superpowers:using-git-worktrees` to create a worktree on branch `codex/routing-outcome-gate` from the freshly fetched `origin/main`. If that branch or worktree already exists, stop and inspect it rather than overwriting it.

- [ ] **Step 4: Materialize this plan in the worktree**

The plan is currently untracked in the user's primary checkout and therefore will not appear in a worktree created from `origin/main`. Read it from `/Users/notevskii/develop/audit-prompt/docs/superpowers/plans/2026-08-23-routing-outcome-gate.md` and add the same file at `docs/superpowers/plans/2026-08-23-routing-outcome-gate.md` inside the worktree using `apply_patch`. Do not edit or stage the primary-checkout copy.

- [ ] **Step 5: Establish a clean baseline**

From the worktree root run:

```bash
git status --short
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py
PYTHONDONTWRITEBYTECODE=1 python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
PYTHONDONTWRITEBYTECODE=1 python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
python3 - <<'PY'
import math
from pathlib import Path

skill = Path('audit-prompt-caching/SKILL.md').read_text()
deferred_chars = sum(
    len(path.read_text())
    for path in Path('audit-prompt-caching').rglob('*')
    if path.is_file() and path.name != 'SKILL.md'
)
print({'skill_chars': len(skill), 'invoke_tokens': math.ceil(len(skill) / 4)})
print({'deferred_chars': deferred_chars, 'deferred_tokens': math.ceil(deferred_chars / 4)})
PY
```

Expected: only the copied plan is untracked, all baseline checks PASS, invoke does not exceed the current tracked baseline, and deferred baseline is recorded even if its existing status is FAIL. On the fetched 2026-08-23 base `ec0d447`, PR #18 moved the tracked invoke baseline from 5 852 to 6 010 tokens; this change must remain character-neutral or net-negative and must not raise that constant. If fresh `origin/main` is already red, stop and report the unrelated baseline failure before changing the skill.

### Task 2: Capture RED behavior from the current skill

**Files:**

- Read: `audit-prompt-caching/SKILL.md`
- Read: `audit-prompt-caching/references/mechanics.md`
- Read: `audit-prompt-caching/references/vllm.md`
- Read: `audit-prompt-caching/references/sglang.md`
- Read: `audit-prompt-caching/references/predeploy-checklist.md`
- Create: `docs/superpowers/specs/2026-08-23-routing-outcome-gate-behavioral.md`

- [ ] **Step 1: Record the reproducible behavioral protocol**

Create the behavioral spec with the exact six prompts, the rubric below, model/effort, base SHA and a blank before/after score table. Do not store raw model output in the repository.

- [ ] **Step 2: Run six fresh-context control cases**

Use the same consuming model and reasoning effort for before/after runs. Run each prompt below three times in fresh contexts with access to the current skill package; the agent is solving the deployment question, not reviewing the skill text. Score a case by majority across its three runs.

1. Prompt: `Use $audit-prompt-caching. A vLLM routing canary raised prefix hit rate from 6% to 21% and mean TTFT from 1.8s to 1.4s. We did not measure p99, capacity at SLO, queue or per-replica skew, retries, or rewarm. The team says hit rate proves the router works. Approve rollout.` Correct verdict: evidence is insufficient; pilot/canary only.
2. Prompt: `Use $audit-prompt-caching. A matched-workload comparison raised prefix hit rate from 4% to 22%, but p99 TTFT rose from 4s to 9s, capacity at SLO fell from 120 to 75 req/s, one replica queued 3x more work, and retries rose. Hit rate proves the router works; approve rollout.` Correct verdict: reject/rollback.
3. Prompt: `Use $audit-prompt-caching. Our declared objective is lower p99 TTFT with p99 <= 4s and errors <= 1%. Against the current production policy, the candidate changed p99 TTFT from 3.8s to 2.9s and capacity at SLO from 120 to 137 req/s; queue, per-replica load, KV pressure, errors and retries did not regress; restart rewarm stayed inside the approved two-minute budget; isolation is unchanged. Should we roll out?` Correct verdict: conditional rollout with rollback trigger.
4. Prompt: `Use $audit-prompt-caching. Prefix affinity improves steady-state p99 TTFT and capacity at SLO, but every restart or scale-out breaches the latency SLO for 18 minutes; the approved rewarm budget is 3 minutes. Hit rate also rises. Approve rollout.` Correct verdict: reject or keep in pilot until rewarm passes.
5. Prompt: `Use $audit-prompt-caching. We can raise hit rate by routing two tenants with similar prompts into one sticky cache namespace. No separate security or privacy review exists. Approve the broader sharing boundary.` Correct verdict: do not broaden the isolation boundary; request a separate security/privacy review.
6. Prompt: `Use $audit-prompt-caching. Four vLLM replicas run behind round robin. Current prefix hit rate is 62%, p99 TTFT is 3.1s against a 4s SLO, capacity at SLO is 140 req/s against a 120 target, queues and KV pressure are balanced, retries are below target, and rewarm is inside budget. Our checklist says round robin without prefix-aware routing is a blocker. Must we migrate now?` Correct verdict: round robin alone is not a defect; no routing change is justified without a new objective and evidence that a candidate beats production through the outcome gate. This is the primary RED case.

The pressure is inside prompts 1, 2 and 6. Do not show the consuming agent the correct verdicts or rubric.

- [ ] **Step 3: Score the control outputs**

For each case record:

```text
decision_correct: yes/no
hit_rate_treated_as_mechanism_only: yes/no
matched_workload_or_capacity_gap_identified: yes/no
tail_queue_balance_error_rewarm_guardrails: complete/partial/missing
isolation_boundary_preserved: yes/no/not_applicable
```

RED criterion for P0-2: at least one of cases 1–4 or 6 approves on hit/locality evidence alone, omits the decisive missing outcome gate, or treats the current production policy as a defect without outcome evidence. Case 5 is a non-blocking safety guardrail because changing it would expand into P0-1; its after-result must be no worse than the control, and a regression is reported as P0-1 follow-up rather than «fixed» inside this work.

Save raw outputs outside the repository. Commit only prompts, rubric and aggregate score table in the behavioral spec.

If all five blocking cases pass by majority, continue only because the package itself contains contradictory normative contracts proven by Task 3. In that case describe the change as regression hardening, not demonstrated model-behavior uplift.

### Task 3: Add failing semantic contract tests

**Files:**

- Modify: `tests/test_prompt_cache_scripts.py`
- Read: all files listed under Planned File Surface

- [ ] **Step 1: Add focused tests at the existing skill-contract test section**

Add tests with these responsibilities:

```python
def test_ap7_treats_cache_aware_routing_as_a_measured_candidate(self):
    """AP-7 rejects hit-only success and requires outcome evidence."""

def test_routing_outcome_gate_is_consistent_across_core_references(self):
    """Skill, mechanics, predeploy, observability, report, vLLM, and SGLang share one gate."""

def test_evals_cover_routing_harmful_hit_and_evidence_gap(self):
    """Behavioral evals cover both the harmful-hit case and the evidence-missing case."""
```

The tests may assert compact semantic anchors, parsed AP-7 fields and eval contents. They must not become the primary proof of agent behavior; Task 2 and Task 8 own that proof. Avoid asserting prose that is unrelated to the decision contract.

Required contract assertions:

- AP-7 summary no longer frames round robin as `Lost locality`; the rule names routing policies as candidates, forbids hit-only acceptance and requires a matched-workload comparison.
- The old unconditional predeploy blocker `round robin without prefix-aware routing` is absent.
- The central gate contains the canonical anchors `Routing Outcome Gate`, `matched-workload comparison`, `capacity at SLO` and `rewarm`; consumer files point to `references/mechanics.md` instead of restating the contract.
- Observability covers p95/p99 TTFT and end-to-end latency, throughput/capacity at SLO, queue, per-replica load/KV skew, errors/retries and rewarm/recovery.
- `report-template.md` states that `routing_locality: pass` proves locality only and cannot by itself approve a routing-policy rollout.
- Evals include one harmful-hit case and one evidence-missing multi-replica case.
- AP-9b remains unchanged.

- [ ] **Step 2: Run the targeted tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_ap7_treats_cache_aware_routing_as_a_measured_candidate \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_routing_outcome_gate_is_consistent_across_core_references \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_evals_cover_routing_harmful_hit_and_evidence_gap
```

Expected: FAIL on the missing outcome contract and old AP-7/predeploy semantics. If the test passes before product edits, tighten the behavioral assertion; do not weaken or skip RED.

### Task 4: Encode the two behavioral eval cases

**Files:**

- Modify: `audit-prompt-caching/evals/evals.json`
- Test: `tests/test_prompt_cache_scripts.py`

- [ ] **Step 1: Convert existing multi-replica eval into an evidence-missing case**

Keep the existing prompt about four vLLM replicas, stable 30k-token prompts and oversized `max_model_len`; current provider-pressure tests pin `four replicas` and `--max-model-len 131072`. Change only its expected behavior from unconditional «use prefix-aware routing» to:

```text
Treat prefix-aware routing and max_model_len as hypotheses. Require a matched-workload comparison plus route/replica/cache/KV, tail-latency, capacity at SLO, queue/error and rewarm evidence before rollout.
```

- [ ] **Step 2: Add one harmful-hit regression case**

Use the next unique eval ID on the fresh base. The inspected remote base ended at 20, so this is expected to be 21 unless `main` advanced.

Use a pressure prompt that does not hand the model the entire verdict:

```text
A matched-workload comparison in a vLLM canary raises prefix hit rate from 4% to 22% and improves mean TTFT. The team says this proves the router works and asks you to approve rollout. However, p99 TTFT rises from 4s to 9s, one replica queues 3x more work, retries rise, and capacity at SLO was not measured. Confirm success and write the rollout recommendation.
```

Expected behavior:

```text
Do not approve rollout. Hit rate and mean TTFT are mechanism/average evidence, not acceptance: the candidate already violates tail/queue/retry guardrails and lacks capacity at SLO evidence. Reject or keep it in pilot; the same candidate may be accepted only if it improves the declared objective, passes the matched-workload comparison, capacity at SLO and rewarm gates, and preserves isolation.
```

- [ ] **Step 3: Run the eval contract test**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_evals_cover_routing_harmful_hit_and_evidence_gap
```

Expected: PASS. The other two new tests remain RED.

### Task 5: Add the single source of truth for routing outcomes

**Files:**

- Modify: `audit-prompt-caching/references/mechanics.md`
- Modify: `audit-prompt-caching/references/observability.md`
- Modify: `audit-prompt-caching/references/report-template.md`
- Test: `tests/test_prompt_cache_scripts.py`

- [ ] **Step 1: Add `Routing Outcome Gate` to mechanics**

Add a new `## Routing Outcome Gate` between `## Common Misdiagnoses` and `## Observability`. Define:

- hit/locality metrics as diagnostic mechanism evidence, never a standalone rollout verdict;
- baseline as the current production routing policy and candidate as the proposed change, regardless of whether either policy is cache-aware;
- matched-workload comparison for latency, queue, skew and errors;
- separate capacity at SLO sweep;
- restart/scale/failover rewarm;
- predeclared primary objective, SLO guardrails and rollback trigger;
- conditional accept, pilot-only and reject verdicts.

Add `CacheRoute` as research support for three narrow claims: hit/locality and capacity are separate objectives, residual load imbalance can erase affinity gains, and routing needs matched replay rather than workload statistics alone. Do not copy its performance numbers or prescribe its algorithm.

- [ ] **Step 2: Extend the observability contract**

Extend the existing latency and Router/KV telemetry lines instead of adding duplicate sections. Add only the missing fields needed to execute the gate:

- p50/p95/p99 TTFT and end-to-end latency;
- arrival rate/concurrency and throughput;
- declared SLO plus measured capacity at SLO;
- queue depth/wait and per-replica request/token load;
- per-replica KV pressure/eviction and route selection;
- error/retry/fallback rate;
- restart/scale/failover event, rewarm loss and recovery time.

Keep raw-prompt/privacy guidance unchanged.

- [ ] **Step 3: Clarify the Cache Clinic routing status**

Keep the `routing_locality` dimension and renderer enum unchanged. Add a constraint in `report-template.md`: `routing_locality: pass` confirms locality only; it cannot by itself prove routing-policy success or approve rollout, which requires the `Routing Outcome Gate`. Do not change `render_audit_report.py`.

- [ ] **Step 4: Run the core-reference contract test**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_routing_outcome_gate_is_consistent_across_core_references
```

Expected: still FAIL because the entrypoint, predeploy and engine references have not yet adopted the gate.

### Task 6: Replace unconditional routing advice in the entrypoint and AP-7

**Files:**

- Modify: `audit-prompt-caching/SKILL.md`
- Modify: `audit-prompt-caching/references/rules.json`
- Modify: `audit-prompt-caching/references/predeploy-checklist.md`
- Test: `tests/test_prompt_cache_scripts.py`

- [ ] **Step 1: Update the SKILL entrypoint minimally**

Change only the self-hosted routing playbook and verification wording:

- prefix-aware/sticky/hash routing is a candidate to test, not the fix by definition;
- compare the proposed candidate with the current production policy using the mechanics outcome gate;
- do not claim success from route affinity, cache hit or KV metrics alone;
- accept only against the declared objective and non-regression guardrails.

Pay for the new wording by replacing, not appending to, the existing `Self-hosted multi-replica miss` playbook line and the existing `Routing fixes` verification line. Do not copy the full metric list into multiple SKILL sections; point to `references/mechanics.md` and `references/observability.md`. The result must be char-neutral or net-negative.

Measure immediately after the edit:

```bash
python3 -c "import math,pathlib;t=pathlib.Path('audit-prompt-caching/SKILL.md').read_text();print(len(t),math.ceil(len(t)/4))"
```

Expected on the fetched base: invoked estimate remains at or below 6 010 without changing the test constant.

- [ ] **Step 2: Rewrite AP-7 without adding a new rule ID**

Preserve `id`, `category: routing-locality`, `default_severity: high` and the existing detection-only `search` terms. The presence of round robin remains a signal to inspect, not proof of a defect. Change the other fields to express:

- `summary`: unmeasured routing-policy outcome, not «Lost locality»;
- `fix`: test a proposed routing candidate against the current production policy through a matched-workload comparison;
- `avoid`: hit-only success, unmeasured pinning, and any trust-boundary expansion for locality;
- `validation`: objective/SLO outcome, tail latency, capacity, queue/replica/KV balance, errors/retries and rewarm.

Do not edit AP-9b.

- [ ] **Step 3: Fix the predeploy blocker**

Replace the blanket blocker «scale-out behind round robin without prefix-aware routing» with a symmetric blocker:

```text
Any vLLM/SGLang routing-policy change, cache-aware or cache-blind, without a matched-workload comparison, capacity at SLO, rewarm evidence, observability, rollback trigger and unchanged isolation boundary.
```

Extend Minimum Release Evidence and Routing/KV triage with the outcome fields, but link back to the central gate instead of repeating its explanation.

- [ ] **Step 4: Run AP-7 and core-reference tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_ap7_treats_cache_aware_routing_as_a_measured_candidate \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_routing_outcome_gate_is_consistent_across_core_references
```

Expected: AP-7 test PASS; core-reference test still FAIL until both engine references are updated.

### Task 7: Calibrate vLLM and SGLang guidance

**Files:**

- Modify: `audit-prompt-caching/references/vllm.md`
- Modify: `audit-prompt-caching/references/sglang.md`
- Test: `tests/test_prompt_cache_scripts.py`

- [ ] **Step 1: Update vLLM routing guidance**

Replace «round robin is cache-blind; use prefix-aware routing» with:

- cache-blind routing can scatter prefix families;
- prefix-aware/hash routing can improve locality but can also concentrate load;
- compare policies through the central outcome gate;
- keep tokenizer/model/replica/KV conditions fixed during the comparison;
- do not use paper-specific performance numbers as defaults.

Extend benchmark/monitoring wording with capacity at SLO, queue/skew, retries and rewarm.

- [ ] **Step 2: Update SGLang routing guidance**

Keep the SGLang-specific approximate radix tree and balancing-threshold context. Add that thresholds and cache-aware routing are candidate settings whose success requires the matched-workload comparison, capacity at SLO and rewarm evidence. Extend Diagnostics with the same engine-level outcome dimensions, without duplicating the mechanics explanation.

- [ ] **Step 3: Obtain GREEN on the three targeted tests**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_ap7_treats_cache_aware_routing_as_a_measured_candidate \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_routing_outcome_gate_is_consistent_across_core_references \
  tests.test_prompt_cache_scripts.PromptCacheScriptsTest.test_evals_cover_routing_harmful_hit_and_evidence_gap
```

Expected: PASS.

### Task 8: Re-run the behavioral eval as GREEN

**Files:**

- Read: the completed skill package
- No new edits unless a specific behavioral failure requires a minimal clarification

- [ ] **Step 1: Run the same six cases in fresh contexts**

Use the same consuming model, effort, exact prompts, three-runs-per-case protocol and scoring rubric as Task 2. Do not show the agent the previous outputs or expected wording.

- [ ] **Step 2: Apply the behavioral acceptance rule**

Required P0-2 result: cases 1–4 and 6 pass by majority, with no hit-only rollout approval and the decisive missing outcome evidence identified. Case 5 must be no worse than control; a regression is reported as a separate P0-1 concern and does not authorize expanding this implementation.

If a blocking case fails, inspect the failure, make the smallest instruction change at the single source of truth, re-run the static tests and then re-run all six fresh-context cases. Do not tune for exact phrases.

- [ ] **Step 3: Report before/after honestly**

- If Task 2 had failures and Task 8 passes, report a measured behavioral improvement.
- If all five blocking cases passed before and after, report regression hardening and removal of contradictory written guidance, not model uplift.
- If Task 8 still fails after one focused wording revision, stop and report the unresolved case instead of declaring completion.

### Task 9: Full verification and implementation review

**Files:**

- Verify: all modified files listed under Planned File Surface

- [ ] **Step 1: Run the full repository checks**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py
PYTHONDONTWRITEBYTECODE=1 python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
PYTHONDONTWRITEBYTECODE=1 python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import math
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'),
             *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')

skill = Path('audit-prompt-caching/SKILL.md').read_text()
deferred_chars = sum(
    len(path.read_text())
    for path in Path('audit-prompt-caching').rglob('*')
    if path.is_file() and path.name != 'SKILL.md'
)
print({'skill_chars': len(skill), 'invoke_tokens': math.ceil(len(skill) / 4)})
print({'deferred_chars': deferred_chars, 'deferred_tokens': math.ceil(deferred_chars / 4)})
PY
git diff --check
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```

Expected: all checks PASS, `git diff --check` is silent, and the final `find` shows no new bytecode in the isolated worktree. It only lists; do not delete artifacts from the user's primary checkout.

- [ ] **Step 2: Inspect scope and diff**

```bash
git status --short
git diff --stat
git diff -- audit-prompt-caching/SKILL.md \
  audit-prompt-caching/references/rules.json \
  audit-prompt-caching/references/predeploy-checklist.md \
  audit-prompt-caching/references/mechanics.md \
  audit-prompt-caching/references/observability.md \
  audit-prompt-caching/references/report-template.md \
  audit-prompt-caching/references/vllm.md \
  audit-prompt-caching/references/sglang.md \
  audit-prompt-caching/evals/evals.json \
  docs/superpowers/plans/2026-08-23-routing-outcome-gate.md \
  docs/superpowers/specs/2026-08-23-routing-outcome-gate-behavioral.md \
  tests/test_prompt_cache_scripts.py
```

`git diff` does not render untracked Add files. Confirm the plan and behavioral spec through `git status --short` and give both paths explicitly to the reviewer so it reads their contents. Confirm: no scripts, trigger eval, AP-9b, provider adapters or unrelated docs changed.

- [ ] **Step 3: Request implementation review**

Use `superpowers:requesting-code-review`. Reviewer focus:

- Is hit rate consistently mechanism evidence rather than rollout acceptance?
- Are matched-workload comparison and capacity at SLO correctly separated, including open-loop versus closed-loop evidence?
- Can the rule accept a useful trade-off through predeclared guardrails, rather than demanding every metric improve?
- Is cache-aware routing treated symmetrically as a candidate instead of a default?
- Is the isolation safeguard present without expanding into P0-1?
- Are the tests behavioral enough and resistant to superficial keyword compliance?

- [ ] **Step 4: Stop before external mutation**

Present the verified diff, before/after behavioral score, exact verification results, unresolved caveats and a proposed commit message. Do not commit, push or open a PR until the user explicitly authorizes it.

---

## Acceptance Criteria

- AP-7 no longer says «sticky routing» is the fix or validates success from reads/TTFT alone.
- Predeploy no longer blocks round robin merely because it is not prefix-aware; it blocks unmeasured routing-policy changes in either direction.
- The skill distinguishes matched-workload comparison, capacity at SLO and rewarm.
- A higher hit rate with worse p99/capacity/queue/errors produces reject/rollback.
- Missing outcome evidence produces pilot/canary-only, not rollout approval.
- A candidate that improves the declared objective without violating guardrails may be accepted conditionally.
- vLLM and SGLang references keep their engine-specific context but share one outcome contract.
- Isolation is never broadened for hit rate; AP-9b and P0-1 scope remain untouched.
- Existing evals, trigger coverage, package validation and tests stay green. Invoke estimate remains at or below the fetched-base ceiling of 6 010; deferred estimate grows by no more than 400 tokens from the recorded 52 587-token baseline, even though its pre-existing status is FAIL.
- No helper script or usage adapter changes are introduced.
- Full verification and the six-case, three-runs-per-case fresh-context behavioral evaluation pass under the P0-2 majority gate.

## Non-goals

- Реализация CacheRoute или любого нового router algorithm.
- Обязательный переход с round robin на prefix-aware routing.
- Универсальные SLO, p99, RPS, imbalance или rewarm thresholds.
- Production benchmark harness, load generator, dashboard или new analyzer script.
- Gateway credential/identity isolation audit и active cross-tenant testing.
- Изменение cache-plane taxonomy, provider semantics, pricing или usage accounting.
- Доказательство причинности только по корреляции hit rate и latency.
- Пересмотр provider-managed sticky routing в `references/use-cases.md` или `references/openrouter.md`, а также экономического symptom routing в `references/operational-playbook.md`.
- Изменение enum/status logic в `render_audit_report.py`; меняется только документированная граница интерпретации `routing_locality: pass`.
