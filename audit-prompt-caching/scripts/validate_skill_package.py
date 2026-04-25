#!/usr/bin/env python3
"""Validate the audit-prompt-caching skill package structure."""

import argparse
import json
import re
import sys
from pathlib import Path


REFERENCE_PATTERN = re.compile(r"`((?:references|scripts|evals)/[^`\s]+)`")


def parse_frontmatter(text):
    if not text.startswith("---\n"):
        return {}, "SKILL.md must start with YAML frontmatter"
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return {}, "SKILL.md frontmatter is not closed"
    data = {}
    current_key = None
    for raw_line in parts[1].splitlines():
        if not raw_line.strip():
            continue
        if raw_line.startswith(" ") and current_key:
            data[current_key] += " " + raw_line.strip()
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        current_key = key.strip()
        data[current_key] = value.strip().strip('"')
    return data, None


def validate_json(path, errors):
    try:
        json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")


def validate_python(path, errors):
    try:
        compile(path.read_text(), str(path), "exec")
    except (OSError, SyntaxError) as exc:
        errors.append(f"{path}: invalid Python: {exc}")


def validate(skill_dir):
    skill_dir = Path(skill_dir)
    errors = []
    warnings = []
    checks = {}

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append("missing SKILL.md")
        return {"status": "error", "checks": checks, "errors": errors, "warnings": warnings}

    skill_text = skill_md.read_text()
    metadata, frontmatter_error = parse_frontmatter(skill_text)
    if frontmatter_error:
        errors.append(frontmatter_error)
    for key in ("name", "description"):
        if not metadata.get(key):
            errors.append(f"SKILL.md missing frontmatter key: {key}")
    checks["SKILL.md"] = "ok" if not frontmatter_error else "error"

    before = len(errors)
    for rel_path in sorted(set(REFERENCE_PATTERN.findall(skill_text))):
        path = skill_dir / rel_path
        if not path.exists():
            errors.append(f"referenced file does not exist: {rel_path}")
    checks["references"] = "error" if len(errors) > before else "ok"

    eval_dir = skill_dir / "evals"
    if eval_dir.exists():
        before = len(errors)
        for path in sorted(eval_dir.glob("*.json")):
            validate_json(path, errors)
        checks["evals"] = "error" if len(errors) > before else "ok"
    else:
        warnings.append("missing evals directory")

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        before = len(errors)
        for path in sorted(scripts_dir.glob("*.py")):
            validate_python(path, errors)
        checks["scripts"] = "error" if len(errors) > before else "ok"
    else:
        warnings.append("missing scripts directory")

    return {
        "status": "error" if errors else "ok",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate a Codex skill package.")
    parser.add_argument("skill_dir", nargs="?", default="audit-prompt-caching")
    args = parser.parse_args(argv)
    result = validate(Path(args.skill_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
