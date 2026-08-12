#!/usr/bin/env python3
"""Render a prompt-cache audit report from usage logs and findings."""

import argparse
import json
import math
import sys
from pathlib import Path

import analyze_usage_logs


SEVERITIES = {"critical", "high", "medium", "low"}
DEFAULT_MEASUREMENT_CHANGE = "unknown"
DEFAULT_PROMPT_BEHAVIOR_CHANGE = "unknown"
DEFAULT_PROVIDER_ROUTING_CHANGE = "unknown"
DEFAULT_CONFIDENCE = "low"
DEFAULT_DO_FIRST = "analyze usage logs and validate prefix stability"
DEFAULT_DO_NOT_DO_YET = "make provider/routing changes without telemetry"
CACHE_PLANES = (
    "gateway_response",
    "provider_prompt",
    "engine_kv",
    "external_kv",
    "semantic_response",
)
CLINIC_DIMENSIONS = (
    "applicability",
    "evidence_quality",
    "prefix_stability",
    "usage_accounting",
    "routing_locality",
    "economics",
    "isolation",
)
CLINIC_STATUSES = ("pass", "warning", "fail", "unknown", "not_applicable")
DEFAULT_CLINIC_STATUS = "unknown"
NON_DECISION_GRADE_DENOMINATORS = ("invalid", "ambiguous")


def canonical_cache_planes(planes):
    """Deduplicate selected planes and return them in canonical order."""
    selected = set(planes or ())
    return [plane for plane in CACHE_PLANES if plane in selected]


def resolve_usage_accounting(status, denominator_status):
    """Derive usage_accounting from the measured usage denominator status."""
    if denominator_status not in NON_DECISION_GRADE_DENOMINATORS:
        return status
    if status == "pass":
        raise ValueError(
            "usage_accounting cannot be pass while the usage denominator_status is "
            f"{denominator_status}"
        )
    if status == DEFAULT_CLINIC_STATUS:
        return "fail" if denominator_status == "invalid" else "warning"
    return status


def build_clinic_summary(args, usage):
    summary = {
        dimension: getattr(args, dimension) for dimension in CLINIC_DIMENSIONS
    }
    summary["usage_accounting"] = resolve_usage_accounting(
        summary["usage_accounting"], usage.get("denominator_status")
    )
    return summary


def parse_finding(text):
    parts = [part.strip() for part in text.split("|")]
    finding = {
        "raw": text,
        "source": None,
        "rule_id": None,
        "severity": "low",
        "provider": None,
        "issue": text,
        "evidence": "",
        "evidence_type": "",
        "confidence": "",
        "impact_condition": "",
        "cache_impact": "",
        "safe_first_action": "",
        "fix": "",
        "validation": "",
        "do_not_do_yet": "",
    }
    if len(parts) >= 13 and parts[1].lower() in SEVERITIES:
        if parts[0].startswith("AP-"):
            finding["rule_id"] = parts[0]
        else:
            finding["source"] = parts[0]
        finding.update(
            {
                "severity": parts[1].lower(),
                "provider": parts[2],
                "issue": parts[3],
                "evidence": parts[4],
                "evidence_type": parts[5],
                "confidence": parts[6],
                "impact_condition": parts[7],
                "cache_impact": parts[8],
                "safe_first_action": parts[9],
                "fix": parts[10],
                "validation": parts[11],
                "do_not_do_yet": parts[12],
            }
        )
        return finding
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


def has_extended_fields(finding):
    return any(
        finding.get(key)
        for key in (
            "evidence",
            "evidence_type",
            "confidence",
            "impact_condition",
            "safe_first_action",
            "do_not_do_yet",
        )
    )


def load_usage(path):
    records = analyze_usage_logs.read_records(Path(path))
    return analyze_usage_logs.summarize(records)


def load_roi(path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("ROI JSON must be an object")
    if data.get("producer") != "estimate_cache_roi.py":
        raise ValueError("ROI JSON producer must be estimate_cache_roi.py")
    if data.get("schema_version") != 1:
        raise ValueError("ROI JSON schema_version must be 1")
    if not isinstance(data.get("pricing"), dict):
        raise ValueError("ROI JSON pricing must be an object")
    required_numbers = (
        "cache_read_input_cost",
        "cache_write_input_cost",
        "total_baseline_cost",
        "total_with_cache_cost",
        "total_savings",
    )
    for field in required_numbers:
        value = data.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"ROI JSON {field} must be a finite number")
    expected_savings = data["total_baseline_cost"] - data["total_with_cache_cost"]
    if not math.isclose(
        expected_savings,
        data["total_savings"],
        rel_tol=1e-6,
        abs_tol=2e-6,
    ):
        raise ValueError("ROI JSON total cost fields are inconsistent")
    return data


def cost_assessment(roi):
    if roi is None:
        return "unknown (no pricing supplied)"
    savings = roi["total_savings"]
    if savings > 0:
        return f"savings of ${savings:.6f}"
    if savings < 0:
        return f"increased cost by ${abs(savings):.6f}"
    return "neutral in the priced scenario"


def build_report(args):
    usage = load_usage(args.usage_log)
    roi = load_roi(args.roi_json) if args.roi_json else None
    findings = [parse_finding(finding) for finding in args.finding]
    return {
        "provider": args.provider,
        "engine": args.engine,
        "measurement_change": args.measurement_change,
        "prompt_behavior_change": args.prompt_behavior_change,
        "provider_routing_change": args.provider_routing_change,
        "cache_planes": canonical_cache_planes(args.cache_plane),
        "clinic_summary": build_clinic_summary(args, usage),
        "confidence": args.confidence,
        "do_first": args.do_first,
        "do_not_do_yet": args.do_not_do_yet,
        "usage": usage,
        "roi": roi,
        "cost_assessment": cost_assessment(roi),
        "findings": findings,
        "expected_impact": expected_impact(usage, roi),
    }


def denominator_caveat(usage):
    status = usage.get("denominator_status")
    if status not in NON_DECISION_GRADE_DENOMINATORS:
        return None
    return (
        f"Usage denominator status is {status}, so the observed cache hit ratio "
        "is non-decision-grade and must not support a savings claim. "
        "Fix usage accounting before estimating impact."
    )


def rendered_cache_hit_ratio(usage):
    ratio = usage.get("cache_hit_ratio", 0)
    status = usage.get("denominator_status")
    if status in NON_DECISION_GRADE_DENOMINATORS:
        return f"{ratio} (non-decision-grade; denominator {status})"
    return str(ratio)


def expected_impact(usage, roi=None):
    clauses = []
    if roi is not None:
        if roi["total_savings"] > 0:
            clauses.append(
                f"The supplied pricing scenario estimates ${roi['total_savings']:.6f} "
                "in savings. Validate it against provider billing."
            )
        elif roi["total_savings"] < 0:
            clauses.append(
                f"The supplied pricing scenario estimates ${abs(roi['total_savings']):.6f} "
                "in increased cost. Reduce cache writes or confirm the workload still benefits."
            )
        else:
            clauses.append(
                "The supplied pricing scenario is cost-neutral. Validate provider billing."
            )

    caveat = denominator_caveat(usage)
    if caveat:
        clauses.append(caveat)
    elif roi is None:
        hit_ratio = usage.get("cache_hit_ratio", 0)
        if hit_ratio:
            clauses.append(
                f"Observed cache benefit on {hit_ratio:.4f} of input tokens. "
                "Validate TTFT and total cost separately before claiming savings."
            )
        else:
            clauses.append(
                "No cache benefit tokens observed. Validate prefix stability, provider "
                "support, routing, and cache read/write telemetry."
            )
    return " ".join(clauses)


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
        f"- Cache hit ratio: {rendered_cache_hit_ratio(usage)}",
        f"- Cache read tokens: {usage['cache_benefit_tokens']}",
        f"- Cache write tokens: {usage['cache_write_total_tokens']}",
        f"- Cache write/read ratio: {usage['cache_write_read_ratio']}",
        f"- Output share: {usage['output_share']}",
        f"- Cost impact: {report['cost_assessment']}",
        f"- Measurement change: {report['measurement_change']}",
        f"- Prompt behavior change: {report['prompt_behavior_change']}",
        f"- Provider/routing change: {report['provider_routing_change']}",
        f"- Confidence: {report['confidence']}",
        f"- Do first: {report['do_first']}",
        f"- Do not do yet: {report['do_not_do_yet']}",
        "",
        "## Cache Clinic Summary",
        "",
        "- Cache planes: "
        + (", ".join(report["cache_planes"]) if report["cache_planes"] else "unknown"),
    ]
    for dimension in CLINIC_DIMENSIONS:
        label = dimension.replace("_", " ").capitalize()
        lines.append(f"- {label}: {report['clinic_summary'][dimension]}")
    lines.extend(
        [
            f"- Usage denominator status: {usage['denominator_status']}",
            "",
            "## Findings",
            "",
        ]
    )
    if report["findings"]:
        for finding in report["findings"]:
            location = finding["source"] or finding["rule_id"] or "advisory"
            if has_extended_fields(finding):
                lines.append(
                    " | ".join(
                        [
                            location,
                            finding["severity"],
                            finding["provider"] or report["provider"],
                            finding["issue"],
                            finding["evidence"],
                            finding["evidence_type"],
                            finding["confidence"],
                            finding["impact_condition"],
                            finding["cache_impact"],
                            finding["safe_first_action"],
                            finding["fix"],
                            finding["validation"],
                            finding["do_not_do_yet"],
                        ]
                    )
                )
            else:
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

    if usage["warnings"]:
        lines.extend(["", "## Usage Warnings", ""])
        for warning in usage["warnings"]:
            lines.append(f"- {warning['code']}: {warning['message']}")

    if report["roi"] is not None:
        roi = report["roi"]
        lines.extend(
            [
                "",
                "## Priced Cache Scenario",
                "",
                f"- Baseline cost: ${roi['total_baseline_cost']:.6f}",
                f"- Cost with cache: ${roi['total_with_cache_cost']:.6f}",
                f"- Cache read cost: ${roi['cache_read_input_cost']:.6f}",
                f"- Cache write cost: ${roi['cache_write_input_cost']:.6f}",
                f"- Assessment: {report['cost_assessment']}",
            ]
        )
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
    parser.add_argument("--measurement-change", default=DEFAULT_MEASUREMENT_CHANGE)
    parser.add_argument("--prompt-behavior-change", default=DEFAULT_PROMPT_BEHAVIOR_CHANGE)
    parser.add_argument("--provider-routing-change", default=DEFAULT_PROVIDER_ROUTING_CHANGE)
    parser.add_argument(
        "--cache-plane",
        action="append",
        choices=list(CACHE_PLANES),
        default=[],
        help="Cache plane observed in the audited system; repeatable.",
    )
    for dimension in CLINIC_DIMENSIONS:
        parser.add_argument(
            f"--{dimension.replace('_', '-')}",
            choices=list(CLINIC_STATUSES),
            default=DEFAULT_CLINIC_STATUS,
            help=f"Cache clinic status for {dimension.replace('_', ' ')}.",
        )
    parser.add_argument("--confidence", default=DEFAULT_CONFIDENCE)
    parser.add_argument("--do-first", default=DEFAULT_DO_FIRST)
    parser.add_argument("--do-not-do-yet", default=DEFAULT_DO_NOT_DO_YET)
    parser.add_argument(
        "--roi-json",
        help="Optional JSON output from estimate_cache_roi.py.",
    )
    parser.add_argument(
        "--finding",
        action="append",
        default=[],
        help=(
            "Finding in the 7-field format "
            "source | severity | provider | issue | impact | fix | validation "
            "or the 13-field extended evidence format"
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    try:
        report = build_report(args)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
