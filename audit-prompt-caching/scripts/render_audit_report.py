#!/usr/bin/env python3
"""Render a prompt-cache audit report from usage logs and findings."""

import argparse
import json
import sys
from pathlib import Path

import analyze_usage_logs


SEVERITIES = {"critical", "high", "medium", "low"}


def parse_finding(text):
    parts = [part.strip() for part in text.split("|")]
    finding = {
        "raw": text,
        "source": None,
        "rule_id": None,
        "severity": "low",
        "provider": None,
        "issue": text,
        "cache_impact": "",
        "fix": "",
        "validation": "",
    }
    if len(parts) >= 7 and parts[1].lower() in SEVERITIES:
        if parts[0].startswith("AP-"):
            finding["rule_id"] = parts[0]
        else:
            finding["source"] = parts[0]
        finding.update(
            {
                "severity": parts[1].lower(),
                "provider": parts[2],
                "issue": parts[3],
                "cache_impact": parts[4],
                "fix": parts[5],
                "validation": parts[6],
            }
        )
    return finding


def load_usage(path):
    records = analyze_usage_logs.read_records(Path(path))
    return analyze_usage_logs.summarize(records)


def build_report(args):
    usage = load_usage(args.usage_log)
    findings = [parse_finding(finding) for finding in args.finding]
    return {
        "provider": args.provider,
        "engine": args.engine,
        "usage": usage,
        "findings": findings,
        "expected_impact": expected_impact(usage),
    }


def expected_impact(usage):
    hit_ratio = usage.get("cache_hit_ratio", 0)
    if hit_ratio:
        return (
            f"Observed cache benefit on {hit_ratio:.4f} of input tokens. "
            "Validate TTFT and total cost separately before claiming savings."
        )
    return (
        "No cache benefit tokens observed. Validate prefix stability, provider "
        "support, routing, and cache read/write telemetry."
    )


def render_markdown(report):
    usage = report["usage"]
    lines = [
        "# Prompt Cache Audit",
        "",
        "## Executive Summary",
        "",
        f"- Provider/engine: {report['provider']}",
        f"- Engine/API surface: {report['engine']}",
        f"- Records reviewed: {usage['records']}",
        f"- Cache hit ratio: {usage['cache_hit_ratio']}",
        f"- Output share: {usage['output_share']}",
        "",
        "## Findings",
        "",
    ]
    if report["findings"]:
        for finding in report["findings"]:
            location = finding["source"] or finding["rule_id"] or "advisory"
            lines.append(
                " | ".join(
                    [
                        location,
                        finding["severity"],
                        finding["provider"] or report["provider"],
                        finding["issue"],
                        finding["cache_impact"],
                        finding["fix"],
                        finding["validation"],
                    ]
                )
            )
    else:
        lines.append("No findings supplied.")
    lines.extend(
        [
            "",
            "## Expected Impact",
            "",
            report["expected_impact"],
            "",
            "## Validation Plan",
            "",
            "1. Re-run usage analysis on repeated requests.",
            "2. Compare cache-read/cached-token fields with TTFT and total cost.",
            "3. Confirm prefix/tool/schema hashes stay stable across warm calls.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Render a prompt-cache audit report from usage logs."
    )
    parser.add_argument("--usage-log", required=True, help="JSON, JSONL, or CSV usage log")
    parser.add_argument("--provider", default="unknown")
    parser.add_argument("--engine", default="unknown")
    parser.add_argument(
        "--finding",
        action="append",
        default=[],
        help="Finding in file:line | severity | provider | issue | impact | fix | validation format",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
