#!/usr/bin/env python3
"""Compare serialized prompts or request payloads and report prefix stability."""

import argparse
import difflib
import json
import sys
from pathlib import Path


def load_payload(path, canonical_json=False):
    text = Path(path).read_text()
    if not canonical_json:
        return text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


def first_difference(a, b):
    limit = min(len(a), len(b))
    for index in range(limit):
        if a[index] != b[index]:
            return index
    if len(a) != len(b):
        return limit
    return None


def json_pointer_for_difference(path, byte_index):
    try:
        data = json.loads(Path(path).read_text())
    except json.JSONDecodeError:
        return ""
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
    decoder = json.JSONDecoder()

    # Lightweight breadcrumb: find the nearest preceding JSON key in the
    # canonical text. This is enough to orient a prompt-cache audit finding.
    prefix = canonical[:byte_index]
    matches = list(reversed(prefix.split('"')))
    for idx in range(1, len(matches), 2):
        candidate = matches[idx]
        if candidate and candidate not in "{}[],: ":
            return candidate
    try:
        decoder.raw_decode(canonical)
    except json.JSONDecodeError:
        return ""
    return ""


def unified_context(a, b, names):
    return "\n".join(
        difflib.unified_diff(
            a.splitlines(),
            b.splitlines(),
            fromfile=names[0],
            tofile=names[1],
            n=3,
            lineterm="",
        )
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare two rendered prompts or JSON request payloads."
    )
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON only. Default is a human-readable report.",
    )
    parser.add_argument(
        "--canonical-json",
        action="store_true",
        help="Parse JSON and compare sorted-key canonical form instead of raw bytes.",
    )
    args = parser.parse_args(argv)

    first_text = load_payload(args.first, args.canonical_json)
    second_text = load_payload(args.second, args.canonical_json)
    index = first_difference(first_text, second_text)

    if index is None:
        report = {
            "stable": True,
            "stable_prefix_bytes": len(first_text.encode()),
            "first_difference": None,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    location = json_pointer_for_difference(args.first, index)
    report = {
        "stable": False,
        "stable_prefix_bytes": len(first_text[:index].encode()),
        "first_difference": {
            "byte_offset": index,
            "near": location,
            "first_char": first_text[index : index + 40],
            "second_char": second_text[index : index + 40],
        },
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print()
        print(unified_context(first_text, second_text, (args.first, args.second)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
