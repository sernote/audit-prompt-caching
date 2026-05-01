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


def lint(payload):
    findings = [
        item
        for item in (
            lint_volatile_prefix(payload),
            lint_tool_order(payload),
            lint_dynamic_schema(payload),
        )
        if item
    ]
    clean_checks = []
    found_rule_ids = {item["rule_id"] for item in findings}
    for rule_id in ("AP-1", "AP-2"):
        if rule_id not in found_rule_ids:
            clean_checks.append(rule_id)
    return {
        "status": "findings" if findings else "ok",
        "findings": findings,
        "clean_checks": clean_checks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Lint a JSON LLM request payload for prompt-cache layout issues."
    )
    parser.add_argument("path", help="JSON request payload")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.path).read_text())
    result = lint(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
