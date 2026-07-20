#!/usr/bin/env python3
"""Lint JSON LLM request payloads for prompt-cache layout anti-patterns."""

import argparse
import json
import re
import sys
from pathlib import Path


VOLATILE_RE = re.compile(
    r"(today|timestamp|datetime|request[_ -]?id|trace[_ -]?id|run[_ -]?id|"
    r"session[_ -]?id|user[_ -]?id|tenant|company|\b20\d\d-\d\d-\d\d\b|"
    r"\breq_[A-Za-z0-9_-]+\b)",
    re.IGNORECASE,
)
DYNAMIC_SCHEMA_KEYS = {
    "requestid",
    "request_id",
    "traceid",
    "trace_id",
    "runid",
    "run_id",
    "timestamp",
    "datetime",
    "tenant",
    "userid",
    "user_id",
}
STABLE_HINT_RE = re.compile(
    r"(stable|reusable|policy|few-shot|examples|shared|static)",
    re.IGNORECASE,
)
GPT56_MODELS = {"gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
SUPPORTED_CACHE_BLOCKS = {
    "chat": {"text", "image_url", "input_audio", "file", "refusal"},
    "responses": {"input_text", "input_image", "input_file"},
}


def finding(rule_id, severity, category, issue, evidence, fix, validation):
    return {
        "rule_id": rule_id,
        "severity": severity,
        "category": category,
        "issue": issue,
        "evidence": evidence,
        "fix": fix,
        "validation": validation,
    }


def serialized_text(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def message_text(message):
    content = message.get("content", "")
    return serialized_text(content)


def input_text(input_item):
    if isinstance(input_item, dict) and "content" in input_item:
        return serialized_text(input_item["content"])
    return serialized_text(input_item)


def ordered_prompt_segments(payload):
    segments = []
    instructions = payload.get("instructions")
    if instructions is not None:
        segments.append(("instructions", serialized_text(instructions)))

    messages = payload.get("messages", [])
    if isinstance(messages, list):
        for index, message in enumerate(messages):
            if isinstance(message, dict):
                segments.append((f"messages[{index}]", message_text(message)))

    input_value = payload.get("input")
    if isinstance(input_value, list):
        for index, item in enumerate(input_value):
            segments.append((f"input[{index}]", input_text(item)))
    elif input_value is not None:
        segments.append(("input", input_text(input_value)))

    return segments


def lint_volatile_prefix(payload):
    segments = ordered_prompt_segments(payload)
    if not segments:
        return None
    volatile_index = None
    stable_index = None
    volatile_label = ""
    volatile_evidence = ""
    for index, (label, text) in enumerate(segments):
        if volatile_index is None and VOLATILE_RE.search(text):
            volatile_index = index
            volatile_label = label
            volatile_evidence = text[:160]
        if stable_index is None and STABLE_HINT_RE.search(text):
            stable_index = index
    if volatile_index is not None and (
        stable_index is None or volatile_index <= stable_index
    ):
        return finding(
            "AP-1",
            "high",
            "prefix-stability",
            "volatile data appears before reusable prompt content",
            f"{volatile_label} contains {volatile_evidence!r}",
            "move request/user/time metadata after the stable cacheable prefix",
            "render multiple requests and confirm the cacheable prefix hash is stable",
        )
    return None


def tool_name(tool):
    if not isinstance(tool, dict):
        return ""
    function = tool.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    name = tool.get("name")
    return name if isinstance(name, str) else ""


def lint_tool_order(payload):
    tools = payload.get("tools", [])
    if not isinstance(tools, list) or len(tools) < 2:
        return None
    names = [name for name in (tool_name(tool) for tool in tools) if name]
    if len(names) >= 2 and names != sorted(names):
        return finding(
            "AP-2",
            "high",
            "tool-schema-stability",
            "tool definitions are not sorted by stable name",
            f"tools order is {names}",
            "sort tool definitions by function/name before rendering requests",
            "compare rendered request bytes across repeated calls",
        )
    return None


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def lint_dynamic_schema(payload):
    response_format = payload.get("response_format")
    if response_format is None:
        return None
    for obj in walk(response_format):
        for key, value in obj.items():
            normalized = key.replace("-", "_").lower()
            value_text = value if isinstance(value, str) else ""
            if normalized in DYNAMIC_SCHEMA_KEYS or VOLATILE_RE.search(value_text):
                return finding(
                    "AP-2",
                    "high",
                    "tool-schema-stability",
                    "structured-output schema contains dynamic request metadata",
                    f"response_format key/value {key!r}: {value_text!r}",
                    "keep request IDs, timestamps, and trace values out of cacheable schemas",
                    "render schemas for repeated calls and confirm byte stability",
                )
    return None


def direct_gpt56(payload):
    model = payload.get("model")
    return model in GPT56_MODELS


def api_surface(payload):
    has_messages = "messages" in payload
    has_input = "input" in payload
    if has_messages == has_input:
        return "ambiguous"
    return "chat" if has_messages else "responses"


def marker_locations(value, path="$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key == "prompt_cache_breakpoint":
                yield child_path, child
            yield from marker_locations(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from marker_locations(child, f"{path}[{index}]")


def supported_content_blocks(payload, surface):
    root = "messages" if surface == "chat" else "input"
    items = payload.get(root)
    if not isinstance(items, list):
        return
    for item_index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("content"), list):
            continue
        for content_index, block in enumerate(item["content"]):
            if isinstance(block, dict):
                path = f"$.{root}[{item_index}].content[{content_index}]"
                yield path, block


def cache_issue(message, path, fix, severity="high"):
    return finding(
        "AP-11",
        severity,
        "explicit-cache-policy",
        message,
        path,
        fix,
        "re-run the linter and then verify cache read/write telemetry",
    )


def lint_gpt56_cache_policy(payload):
    surface = api_surface(payload)
    policy = {
        "model_support": "gpt-5.6" if direct_gpt56(payload) else "unknown",
        "api_surface": surface,
        "mode": None,
        "ttl": None,
        "explicit_breakpoints": 0,
        "validated": False,
        "valid": None,
    }
    if not direct_gpt56(payload):
        return policy, []

    policy["validated"] = True
    findings = []
    if surface == "ambiguous":
        findings.append(
            cache_issue(
                "GPT-5.6 request must contain exactly one of messages or input",
                "$",
                "use one supported OpenAI API prompt surface",
            )
        )

    options = payload.get("prompt_cache_options", {})
    if not isinstance(options, dict):
        findings.append(
            cache_issue(
                "prompt_cache_options must be an object",
                "prompt_cache_options",
                "send an object with optional mode and ttl fields",
            )
        )
    else:
        mode = options.get("mode", "implicit")
        ttl = options.get("ttl", "30m")
        policy["mode"] = mode
        policy["ttl"] = ttl
        if mode not in ("implicit", "explicit"):
            findings.append(
                cache_issue(
                    "prompt_cache_options.mode must be implicit or explicit",
                    "prompt_cache_options.mode",
                    "set mode to implicit or explicit",
                )
            )
        if ttl != "30m":
            findings.append(
                cache_issue(
                    "prompt_cache_options.ttl must be 30m",
                    "prompt_cache_options.ttl",
                    "set ttl to 30m for this GPT-5.6 contract snapshot",
                )
            )

    if "prompt_cache_retention" in payload:
        findings.append(
            cache_issue(
                "prompt_cache_retention is deprecated for GPT-5.6",
                "prompt_cache_retention",
                "use prompt_cache_options instead",
                severity="medium",
            )
        )

    markers = list(marker_locations(payload))
    block_by_marker_path = {}
    if surface in SUPPORTED_CACHE_BLOCKS:
        for block_path, block in supported_content_blocks(payload, surface):
            if "prompt_cache_breakpoint" in block:
                block_by_marker_path[f"{block_path}.prompt_cache_breakpoint"] = block

    valid_markers = 0
    for path, value in markers:
        block = block_by_marker_path.get(path)
        if block is None:
            findings.append(
                cache_issue(
                    "prompt_cache_breakpoint must be on a supported content block",
                    path,
                    "move the marker onto a Chat or Responses content block",
                )
            )
            continue
        if block.get("type") not in SUPPORTED_CACHE_BLOCKS[surface]:
            findings.append(
                cache_issue(
                    "prompt_cache_breakpoint uses an unsupported content block type",
                    path,
                    "attach the marker to a supported prompt input block",
                )
            )
            continue
        if value != {"mode": "explicit"}:
            findings.append(
                cache_issue(
                    'prompt_cache_breakpoint must be exactly {"mode":"explicit"}',
                    path,
                    "use the documented explicit marker value",
                )
            )
            continue
        valid_markers += 1

    if policy["mode"] == "explicit" and not markers:
        findings.append(
            cache_issue(
                "explicit mode has no valid prompt_cache_breakpoint, so cache writes are disabled",
                "prompt_cache_options.mode",
                "add a breakpoint or use implicit mode when automatic writes are intended",
                severity="medium",
            )
        )

    policy["explicit_breakpoints"] = valid_markers
    policy["valid"] = not findings
    return policy, findings


def lint(payload):
    if not isinstance(payload, dict):
        raise ValueError("request payload must be a JSON object")
    cache_policy, cache_findings = lint_gpt56_cache_policy(payload)
    findings = [
        item
        for item in (
            lint_volatile_prefix(payload),
            lint_tool_order(payload),
            lint_dynamic_schema(payload),
        )
        if item
    ]
    findings.extend(cache_findings)
    clean_checks = []
    found_rule_ids = {item["rule_id"] for item in findings}
    for rule_id in ("AP-1", "AP-2"):
        if rule_id not in found_rule_ids:
            clean_checks.append(rule_id)
    if cache_policy["validated"] and cache_policy["valid"]:
        clean_checks.append("AP-11")
    return {
        "status": "findings" if findings else "ok",
        "findings": findings,
        "clean_checks": clean_checks,
        "cache_policy": cache_policy,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lint a JSON LLM request payload for prompt-cache layout issues."
    )
    parser.add_argument("path", help="JSON request payload")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.path).read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"invalid request JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("invalid request JSON: root must be an object", file=sys.stderr)
        return 2
    result = lint(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
