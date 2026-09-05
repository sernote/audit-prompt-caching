# Prompt-cache audit pilot

This pilot uses one real prompt-cache task from your current work. A bundled
demo can help you learn the command, but it does not count as a pilot result.
The pilot operator does not need your source code, logs, prompts or configuration.
The Python helpers run locally without network access. An agent-led audit follows
your configured agent's data-processing settings; use inputs appropriate for that
setup. Only share a redacted excerpt with the operator if you choose to.

## 1. Pin the pilot version

This pilot uses draft [PR #22](https://github.com/sernote/audit-prompt-caching/pull/22),
stacked on [PR #21](https://github.com/sernote/audit-prompt-caching/pull/21), rather
than stable `main`. The tested commit includes the first-audit example, normalized
routing analyzer and pinned router API-path guidance.

The SHA pins the skill code; use this current PR guide for the pilot protocol.

```bash
git clone https://github.com/sernote/audit-prompt-caching.git audit-prompt-caching-pilot &&
cd audit-prompt-caching-pilot &&
git checkout --detach 8c1b18c00d482df68b78a1bb3af3fe7c296971fa &&
test "$(git rev-parse HEAD)" = "8c1b18c00d482df68b78a1bb3af3fe7c296971fa" &&
bash install.sh --source-dir . --agent codex
```

The installer stops if the skill is already installed. Review or back up that
copy before deciding whether to rerun the same command with `--force`; do not
replace an existing installation blindly. Restart the agent session after an
install.

Stable `main` remains suitable for an agent-led project audit, but do not use
the first-audit example or `analyze_routing_logs.py` commands below unless the
files are present in your checkout. This guide intentionally depends on the
pinned draft commit.

## 2. Choose one real path

### Prompt or configuration path

Choose a real repeated LLM request, cache miss, cost concern, or long-TTFT
question. The minimum input is a local project checkout containing the request
builder or prompt template and its relevant provider, gateway, or deployment
configuration. Two representative rendered prompts or request JSON files are
helpful, but optional.

From the pinned skill checkout, locate likely request paths:

```bash
python3 audit-prompt-caching/scripts/extract_llm_calls.py /path/to/your/project
```

If you have a rendered request JSON, inspect its layout:

```bash
python3 audit-prompt-caching/scripts/layout_linter.py /path/to/request.json
```

If you have two representative renders from the same path, compare their raw
prefix first:

```bash
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json \
  /path/to/render-a.json /path/to/render-b.json
```

Use `--canonical-json` only when sorted-key normalization is intentionally part
of the request contract. Exit code `1` plus a valid comparison JSON report can
mean the complete inputs differ. Exit code `1` can also accompany an input or
command error, such as a missing file. Check that stdout contains valid JSON
with `stable`, `stable_prefix_bytes`, and `first_difference`, and inspect stderr
for an error or traceback before interpreting the result. The bundled
[first-audit walkthrough](../../examples/first-audit/README.md) demonstrates
this boundary.

Start an agent session in the project under audit and use:

```text
Use $audit-prompt-caching to audit this real project task. Start with the code and configuration that build and route the repeated LLM request. If available, inspect these two representative rendered requests: /path/to/render-a.json and /path/to/render-b.json. Give me an evidence-backed finding, a justified no-change result, or the next concrete measurement needed. Do not claim provider cache reuse, KV reuse, latency improvement, or savings without the corresponding telemetry.
```

### Normalized-routing path

Choose this path only if you already have a small normalized JSONL export that
follows the [routing evidence contract](../../audit-prompt-caching/references/routing-evidence.md).
The minimum useful rows preserve genuine `run_id`, `request_id`, and
`attempt_id` values and pair the selected model, pool, worker, and provenance
across a decision and outcome. Missing optional measurements remain `null` or
absent; do not turn unknown values into zero or infer attempt IDs from timing.

From the pinned checkout, run:

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py \
  /path/to/routing.jsonl
```

If the system has an explicit per-attempt client TTFT target, add it:

```bash
python3 audit-prompt-caching/scripts/analyze_routing_logs.py \
  /path/to/routing.jsonl --attempt-ttft-limit-ms 500
```

Replace `500` with the declared target; omit the option when no target exists.
This analyzer does not parse native vllm-router logs. It does not collect GPU
data, reconstruct KV events, or prove policy performance. A valid report can
show incomplete joins or unknown measurements and still exit successfully.

Use this agent prompt:

```text
Use $audit-prompt-caching to audit /path/to/routing.jsonl against the normalized routing-evidence contract. Keep decisions, outcomes, retries or other attempts, prediction targets, selected workers, and unknown fields separate. State what the export proves, what remains unknown, and the next concrete observation needed. Do not infer causality, cost, capacity, percentile SLOs, deployment approval, or GPU behavior from this file.
```

## 3. Verify the result

Stop when the audit reaches one honest outcome:

- **Useful finding:** it points to specific evidence, states the impact
  condition, proposes a safe action, and names a check that could disprove it.
- **Useful no-change:** it names the inspected scope and explains why a prompt,
  provider, or routing change is not justified.
- **Concrete next measurement:** evidence is insufficient, but the audit names
  one obtainable artifact or observation and explains what decision it would
  unlock.
- **Incomplete audit:** the available evidence supports none of the above.
  Record the gap without guessing. This is a legitimate pilot outcome, though
  it is not counted as a useful completion.

Provider cache fields, real request traces, billing data, or matched routing
outcomes are needed for claims about hits, savings, latency, or policy effects.
Local byte stability and normalized joins are narrower evidence.

## 4. Optional feedback

You may return only this small summary; files and private repository access are
not required:

```text
Participant ID: P___
Audit ID: A___
Path: prompt/config or normalized routing
Outcome: useful finding / useful no-change / concrete next measurement / incomplete
Approximate time to first result:
Help needed: none / install / artifact choice / interpretation
One useful or confusing point:
```

Do not include API keys, credentials, raw private prompts, customer data, full
logs, or a private repository. Share a short redacted excerpt only when it is
safe and necessary.
