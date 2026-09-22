# Audit a real project

Choose one question from your current work: repeated cache misses, a changed
prompt or tool set, or unexplained prefill latency. Start with the code and
configuration that build and route those requests. Rendered payloads and usage
logs can help when you already have them.

## Run the audit

[Install the skill](../README.md#quick-start), then start a new agent session in
the project you want to audit. Use inputs appropriate for your agent's configured
data-processing settings.

```text
Use $audit-prompt-caching to audit this project's repeated LLM requests. Start with the request-building code and configuration. Check the prompt prefix, tools, history and relevant provider or router behavior. Show the evidence for each finding and how I can verify it. If no change is justified, explain why; if evidence is missing, name the next concrete check. Do not claim cache hits, latency improvements or savings without measurements.
```

Add the specific symptom and relevant paths to that request. The agent can use
the bundled helpers as needed; running every script is not a prerequisite.
The optional [prefix-layout example](../examples/first-audit/README.md) shows
what a local byte comparison can establish.

## Check one conclusion

Follow a finding back to the active request path and its cited code or
configuration. Verify the proposed change with representative inputs; use
provider or engine telemetry before claiming cache reuse, speed or savings.
A supported no-change conclusion can also resolve the original question.

When evidence is missing, check whether the proposed observation is obtainable
and would answer your question. Record the unresolved point rather than treating
the suggestion itself as proof that the problem is solved.

## Optional feedback

Use the existing [audit feedback form](https://github.com/sernote/audit-prompt-caching/issues/new?template=audit-result.md)
to share what you checked, what helped or confused you, and whether you could
verify the result. Approximate time and help needed are optional. Keep credentials
and private project contents out of the public issue.
