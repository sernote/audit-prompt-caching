# Usage Surface Adapters — Design

## Goal

Make `analyze_usage_logs.py` normalize current Gemini Interactions responses and
streaming completion events without mixing them with Gemini Generate Content
usage fields, while keeping provider accounting explicit and testable.

## Scope

- Introduce small, dependency-free adapters for Bedrock, Gemini Interactions,
  Gemini Generate Content, and unknown wrappers.
- Give each adapter one responsibility: recognize its wire shape, select its
  usage envelope, and emit canonical token fields plus accounting semantics.
- Preserve the existing CLI and its canonical JSON/JSONL output contract.
- Add fixtures-in-tests for normal Interactions responses, no-hit responses,
  streaming `metadata.total_usage`, legacy Generate Content, and Bedrock
  metric/usage envelopes.

## Non-goals

- Do not split the one-file CLI into packages or introduce framework
  dependencies.
- Do not infer cache semantics from arbitrary wrapper fields.
- Do not change provider prices, cache policy, or report presentation.

## Architecture

`normalize_record` remains the application core. It asks the first matching
surface adapter for a canonical row and applies generic aggregation afterward.
Adapters own provider wire contracts only; generic accounting owns totals,
ratios, warnings, and output serialization.

```text
raw log record
  -> ordered surface adapters (matches + usage envelope + canonical row)
  -> generic inclusive/additive accounting
  -> summary or normalized JSONL
```

Adapter order is deliberate: explicit provider labels win; then structurally
unique Bedrock and Gemini Interactions forms; then legacy Gemini Generate
Content; finally unknown-wrapper fallback. A zero value is still a field
presence signal, so cache misses are not confused with unsupported shapes.

## Error Handling

Unknown wrappers retain the existing `AMBIGUOUS_ACCOUNTING_SEMANTICS` warning.
Recognized provider surfaces with a valid no-hit response report zeros without
that warning. Malformed or absent usage fields continue to normalize to zero
without crashing the CLI.

## Verification

- TDD: each new fixture fails against the old mixed-field implementation.
- Full script unit suite, package validation, trigger eval, Python compilation,
  whitespace check, and clean worktree verification.
