# First audit: move changing context later

This example checks one narrow property before any provider or routing change:
how much of two rendered prompts is byte-for-byte identical from the start.

The `before` prompts put a changing timestamp, ticket ID, and customer message
before the reusable task instructions. The `after` prompts contain exactly the
same information, reordered so the task instructions come first:

```text
before: request context (changes) -> task instructions (stable)
after:  task instructions (stable) -> request context (changes)
```

The files are plain ASCII text so the reported UTF-8 byte offset is easy to
inspect. They represent rendered prompts, not a provider's JSON request format.

## Run it

From the repository root, compare the two `before` renders:

```bash
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json examples/first-audit/before-a.txt examples/first-audit/before-b.txt
```

Observed output:

```json
{
  "stable": false,
  "stable_prefix_bytes": 43,
  "first_difference": {
    "byte_offset": 43,
    "near": "",
    "first_char": "5:00Z\nTicket: SUP-1042\nCustomer message:",
    "second_char": "8:00Z\nTicket: SUP-1047\nCustomer message:"
  }
}
```

Now compare the two reordered `after` renders:

```bash
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json examples/first-audit/after-a.txt examples/first-audit/after-b.txt
```

Observed output:

```json
{
  "stable": false,
  "stable_prefix_bytes": 254,
  "first_difference": {
    "byte_offset": 254,
    "near": "",
    "first_char": "5:00Z\nTicket: SUP-1042\nCustomer message:",
    "second_char": "8:00Z\nTicket: SUP-1047\nCustomer message:"
  }
}
```

Both commands intentionally exit with status `1`. The script returns nonzero
whenever the complete inputs differ, and the request context must differ for
this test. The useful result is that the identical leading region grows from
`43` to `254` UTF-8 bytes while every instruction and context field is kept.

## What this result means

It establishes only that the two local text files share a longer raw-byte
prefix after reordering. `stable_prefix_bytes` is not a token count, a provider
eligibility check, proof of a provider cache read, proof of self-hosted KV
reuse, or a measurement of latency, billing, or savings. These commands do not
call a provider API.

A real cache audit must also check the provider or engine's current cache
requirements, the exact serialized request path, repeat cadence, routing and
replica locality, cache telemetry, output cost, and workload safety boundaries.

## Apply it to your project

1. Render two representative requests from the same hot path while varying
   normal runtime context such as time, user input, or request identity.
2. Save the exact text or serialization your application sends. Compare it in
   raw mode first; use `--canonical-json` only when sorted-key normalization is
   an intentional part of the request contract.
3. Run the helper against those two files and inspect the first difference.
4. Audit the code that constructs the request before changing cache controls,
   keys, or routing.

For example:

```bash
python3 audit-prompt-caching/scripts/prefix_stability_check.py --json path/to/render-a.txt path/to/render-b.txt
```

Then ask the installed skill to follow the result through your codebase:

```text
Use $audit-prompt-caching to audit this project. Start with the code and configuration that build and route LLM requests. I have two representative rendered prompts at path/to/render-a.txt and path/to/render-b.txt. Explain the first prefix divergence, check whether a change is justified, and list the telemetry needed before claiming provider cache reuse, KV reuse, latency improvement, or savings.
```

Rendered prompts and usage logs help confirm behavior, but they are not required
to begin. The skill can audit prompt builders, tool and schema construction,
history handling, provider calls, router settings, and deployment configuration
directly. If the layout is already stable or caching is not useful for the
workload, "no change needed" is a successful audit outcome when the evidence is
stated.
