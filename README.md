# LLM Cache Audit Skill

[![CI](https://github.com/sernote/audit-prompt-caching/actions/workflows/ci.yml/badge.svg)](https://github.com/sernote/audit-prompt-caching/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Stdlib only](https://img.shields.io/badge/scripts-stdlib--only-green)

**Find what breaks LLM prompt caching in your project.**

`audit-prompt-caching` helps Codex, Claude Code, and compatible agents trace
cache misses through your request code, provider settings, and routing.

Start with code and configuration. Get findings with evidence and a verification
step; add exported payloads or telemetry when available.

[Get started](#quick-start) · [See an example](#see-a-prefix-fix) ·
[What it audits](#what-it-audits) · [Commands and scenarios](docs/usage.md)

## Quick Start

From the project you want to audit, install the skill for your agent
with the [skills CLI](https://skills.sh/docs/cli) (requires Node.js/npx):

```bash
npx skills add https://github.com/sernote/audit-prompt-caching --skill audit-prompt-caching
```

Start a new agent session in that project and ask:

```text
Use the audit-prompt-caching skill
to audit this project's LLM calls.
Start with code and configuration.
Show findings, evidence, and checks.
Explain when no change is justified
or what evidence is still missing.
```

Add your symptom and relevant paths. In Codex, you can also invoke the skill as
`$audit-prompt-caching`. The [first-project guide](docs/first-audit.md) explains
how to check one conclusion and share optional feedback.

<details>
<summary>Install without Node.js, or choose a custom directory</summary>

Use the bundled Bash installer from a local checkout:

```bash
git clone --depth 1 https://github.com/sernote/audit-prompt-caching.git
cd audit-prompt-caching
bash install.sh --source-dir . --agent codex
```

Use `--agent claude` for Claude Code, `--agent both` for both agents, or
`--dir path/to/skills` for a custom skills directory. Existing installations
are preserved unless you pass `--force` to replace them. See
`bash install.sh --help` for all options.

The local audit helpers need Python 3.10+ and use only the standard library.
The installer itself requires Bash; the command above also uses Git.

</details>

## See a prefix fix

In the bundled example, a changing timestamp and support-ticket context precede
the shared task instructions. Moving that context later preserves all the
information and gives repeated requests a longer identical beginning.

The change in block order:

```diff
- Request context (changes)
  Task instructions (shared)
+ Request context (changes)
```

| Compared request pair | Common UTF-8 prefix |
|---|---:|
| Before reordering | 43 bytes |
| After reordering | 254 bytes |

These are measured local text comparisons from a small synthetic example.
They show prefix stability; provider eligibility, cache hits, latency and
savings still require their own checks.

<details>
<summary>Reproduce the comparison with Python — no API key needed</summary>

Clone this repository, or use your existing checkout. Run from its root:

```bash
git clone --depth 1 https://github.com/sernote/audit-prompt-caching.git
cd audit-prompt-caching
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json \
  examples/first-audit/before-a.txt examples/first-audit/before-b.txt
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json \
  examples/first-audit/after-a.txt examples/first-audit/after-b.txt
```

Both comparisons intentionally return exit status `1`: the complete requests
still differ. Read `stable_prefix_bytes` in each result. The
[walkthrough](examples/first-audit/README.md) includes the exact output and
shows how to compare two renders from your own application.

</details>

## What you get

An audit connects its conclusion to the active request path and a verification
step. It can produce:

- **A finding with evidence:** where the prefix changes, usage is lost or
  miscounted, or routing/cache state needs attention; what to change and how to
  check the result.
- **A supported no-change result:** the layout is already appropriate, the
  workload rarely repeats, or output generation and tools dominate the cost.
- **A specific missing measurement:** the request, usage field, route or worker
  observation needed to resolve the question.

For a longer handoff, the [report format](audit-prompt-caching/references/report-template.md)
keeps applicability, evidence, prefix stability, accounting, routing, economics
and isolation separate. Unproven dimensions remain `unknown`.

## What It Audits

| Your question | What the audit inspects |
|---|---|
| Why do repeated prompts miss? | Request builders, early variable content, serialization and the first prefix divergence |
| Why did an agent become more expensive? | Tool/MCP registries, schemas, history, compaction and per-step configuration changes |
| Can I trust these cached-token numbers? | Actual provider/API path, raw usage fields, wrapper accounting and missing telemetry |
| Why is a warm request still slow? | Prefill vs. decode, client timings, route selection, queue/load signals and retries |
| Why did reuse drop after deployment or scaling? | vLLM/SGLang versions, effective configuration, replica locality, KV pressure, retention and offload |
| Is caching worth changing here? | Prefix length and repeat cadence, input/output costs, cache read/write prices and tenant boundaries |

The skill covers code reviews, agent loops, provider migrations and self-hosted
deployment audits. It can also guide an investigation without a repository.
See the [scenario prompts](docs/usage.md#example-prompts) for concrete starting
points.

## Provider and framework references

Provider-specific checks live in selectively loaded references:

- **APIs and gateways:** [OpenAI](audit-prompt-caching/references/openai.md),
  [Azure OpenAI](audit-prompt-caching/references/azure-openai.md),
  [Anthropic](audit-prompt-caching/references/anthropic.md),
  [Amazon Bedrock](audit-prompt-caching/references/bedrock.md),
  [Gemini](audit-prompt-caching/references/gemini.md),
  [OpenRouter](audit-prompt-caching/references/openrouter.md).
- **Agents and frameworks:** [tools, MCP and agent loops](audit-prompt-caching/references/agent-tools.md),
  [Vercel AI SDK](audit-prompt-caching/references/vercel-ai-sdk.md),
  [Mastra](audit-prompt-caching/references/mastra.md).
- **Self-hosted inference:** [vLLM](audit-prompt-caching/references/vllm.md),
  [SGLang](audit-prompt-caching/references/sglang.md),
  [routing evidence](audit-prompt-caching/references/routing-evidence.md).

<details>
<summary>More provider references</summary>

[DeepSeek](audit-prompt-caching/references/deepseek.md) ·
[Qwen](audit-prompt-caching/references/qwen.md) ·
[Moonshot](audit-prompt-caching/references/moonshot.md) ·
[MiniMax](audit-prompt-caching/references/minimax.md) ·
[Mistral](audit-prompt-caching/references/mistral.md) ·
[xAI](audit-prompt-caching/references/xai.md) ·
[YandexGPT](audit-prompt-caching/references/yandexgpt.md) ·
[Z.AI](audit-prompt-caching/references/zai.md) ·
[Tencent](audit-prompt-caching/references/tencent.md) ·
[Xiaomi](audit-prompt-caching/references/xiaomi.md)

</details>

The agent verifies current official documentation before exact claims about
model support, cache controls, TTL, pricing or usage fields. Bundled references
are a starting point for that check.

## Examples and local tools

| Start here | What it demonstrates |
|---|---|
| [Prefix-layout walkthrough](examples/first-audit/README.md) | Reorder a rendered prompt and inspect its first divergence |
| [Recorded vllm-router observations](examples/router-observation/recorded/2026-09-05/README.md) | A session-ID routing input and HTTP success that does not guarantee a complete stream; real router, synthetic worker, no GPU |
| [Usage and ROI examples](docs/usage.md#synthetic-usage-and-roi) | Run the helpers on synthetic records and explicit sample prices |
| [Script reference](docs/usage.md#bundled-scripts) | Locate calls, lint payloads, compare prefixes, analyze usage and render a report |
| [Routing capture guide](docs/routing-capture.md) | Collect evidence for a self-hosted routing investigation |

The scripts run locally with Python's standard library. The agent uses them as
needed; a first audit does not require running every helper.

The routing analyzer is **experimental**. It consumes a
[normalized JSONL export](audit-prompt-caching/references/routing-evidence.md)
and has no bundled native-router-log adapter. End-to-end capture and analysis
still need validation on a real deployment. Request/attempt joins and measured
worker/client outcomes are necessary before drawing routing conclusions.

## Working with evidence

Use the skill alongside your existing telemetry: request payloads, provider
usage, billing exports, traces and per-replica metrics. It does not capture live
traffic by itself. The [usage guide](docs/usage.md#evidence-artifacts) describes
useful inputs and how the helpers preserve uncertain accounting.

A gateway response-cache hit, a provider prompt-cache read and self-hosted KV
reuse are different observations. A stable local prefix alone establishes none
of them. Each finding should name the cache layer and the evidence behind it.

## Contributing and feedback

Tried it on a project? [Share an audit result](https://github.com/sernote/audit-prompt-caching/issues/new?template=audit-result.md):
what helped, what was unclear, or what evidence was missing. Feedback is optional;
keep credentials and private project contents out of public issues.

[CONTRIBUTING.md](CONTRIBUTING.md) covers tests, package validation and change
guidelines. The [validation notes](docs/usage.md#validation) distinguish script
tests, trigger-dataset checks and agent behavior evaluations.

Project background and longer explanations: [notevskii.tech](https://notevskii.tech/projects/audit-prompt-caching/).
Updates and engineering field notes: [Telegram](https://t.me/sergeinotevskii).

## License

[MIT](LICENSE).
