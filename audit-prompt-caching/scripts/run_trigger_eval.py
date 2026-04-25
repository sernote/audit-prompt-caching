#!/usr/bin/env python3
"""Summarize trigger eval coverage for the audit-prompt-caching skill."""

import argparse
import json
import sys
from pathlib import Path


def load_cases(skill_dir):
    path = Path(skill_dir) / "evals" / "trigger_eval.json"
    try:
        data = json.loads(path.read_text())
    except OSError as exc:
        return [], [f"{path}: cannot read trigger evals: {exc}"]
    except json.JSONDecodeError as exc:
        return [], [f"{path}: invalid JSON: {exc}"]

    if not isinstance(data, list):
        return [], [f"{path}: expected a JSON list"]

    errors = []
    cases = []
    for index, item in enumerate(data):
        label = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: expected object")
            continue
        query = item.get("query")
        should_trigger = item.get("should_trigger")
        if not isinstance(query, str) or not query.strip():
            errors.append(f"{label}: missing non-empty query")
        if not isinstance(should_trigger, bool):
            errors.append(f"{label}: missing boolean should_trigger")
        if isinstance(query, str) and isinstance(should_trigger, bool):
            cases.append({"query": query, "should_trigger": should_trigger})
    return cases, errors


def summarize(skill_dir):
    cases, errors = load_cases(skill_dir)
    positive = sum(1 for case in cases if case["should_trigger"])
    negative = sum(1 for case in cases if not case["should_trigger"])

    if not cases:
        errors.append("trigger evals contain no valid cases")
    if positive == 0:
        errors.append("trigger evals contain no positive should_trigger cases")
    if negative == 0:
        errors.append("trigger evals contain no negative should_trigger cases")

    return {
        "status": "error" if errors else "ok",
        "cases": len(cases),
        "positive_cases": positive,
        "negative_cases": negative,
        "errors": errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize trigger eval coverage.")
    parser.add_argument("skill_dir", nargs="?", default="audit-prompt-caching")
    args = parser.parse_args(argv)

    result = summarize(Path(args.skill_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
