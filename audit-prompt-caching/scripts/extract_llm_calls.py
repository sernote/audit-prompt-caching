#!/usr/bin/env python3
"""Find likely LLM provider calls and cache-related signals in a repository."""

import argparse
import json
import os
import re
import sys
from pathlib import Path


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}

SOURCE_SUFFIXES = {
    ".cjs",
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".service",
    ".sh",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

SOURCE_FILENAMES = {
    "Dockerfile",
    "Containerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "Makefile",
}

PROVIDER_PATTERNS = {
    "openai": [
        r"\bfrom\s+openai\s+import\b",
        r"\bimport\s+openai\b",
        r"\bresponses\.create\s*\(",
        r"\bchat\.completions\.create\s*\(",
        r"\bprompt_cache_key\b",
        r"\bprompt_cache_retention\b",
    ],
    "anthropic": [
        r"\banthropic\b",
        r"\bAnthropic\s*\(",
        r"\bmessages\.create\s*\(",
        r"\bcache_control\b",
    ],
    "bedrock": [
        r"\bbedrock-runtime\b",
        r"\bBedrockRuntime\b",
        r"\bclient\.converse\b",
        r"\binvoke_model\b",
        r"\bcachePoint\b",
        r"\bCache(Read|Write)InputTokens\b",
    ],
    "openrouter": [
        r"\bopenrouter\b",
        r"\bopenrouter\.ai/api/v1\b",
        r"\bOPENROUTER_API_KEY\b",
        r"\bopenrouter/auto\b",
    ],
    "vllm": [
        r"\bvllm\b",
        r"(^|[^A-Za-z0-9_])--enable-prefix-caching($|[^A-Za-z0-9_-])",
        r"(^|[^A-Za-z0-9_])--enable-kv-cache-events($|[^A-Za-z0-9_-])",
        r"(^|[^A-Za-z0-9_])--prefix-cache-retention-interval($|[^A-Za-z0-9_-])",
        r"\bprefix_cache_retention_interval\b",
        r"\bVLLM_PREFIX_CACHE_RETENTION_INTERVAL\b",
        r"(^|[^A-Za-z0-9_])--prefix-caching-hash-algo($|[^A-Za-z0-9_-])",
        r"\bprefix_caching_hash_algo\b",
        r"\b(enable_kv_cache_events|kv_cache_events)\b",
        r"\b(kv_transfer_config|kv_connector|LMCacheConnector)\b",
        r"\bAsyncLLMEngine\b",
    ],
    "sglang": [
        r"\bsglang\b",
        r"\bRadixAttention\b",
        r"(^|[^A-Za-z0-9_])--disable-radix-cache($|[^A-Za-z0-9_-])",
        r"\bHiCache\b",
        r"\b(enable_hierarchical_cache|hicache_storage_backend)\b",
        r"\b(disaggregation_mode|pd_disaggregation)\b",
    ],
    "gemini": [
        r"\bgoogle\.genai\b",
        r"\bgoogle\.generativeai\b",
        r"\bCachedContent\b",
    ],
    "deepseek": [
        r"\bdeepseek\b",
        r"\bapi\.deepseek\.com\b",
        r"\bprompt_cache_hit_tokens\b",
    ],
    "qwen": [
        r"\bdashscope\b",
        r"\bqwen\b",
        r"\bbailian\b",
    ],
}


VLLM_SIGNAL_LABELS = {
    r"\bvllm\b": "vllm",
    r"(^|[^A-Za-z0-9_])--enable-prefix-caching($|[^A-Za-z0-9_-])": "--enable-prefix-caching",
    r"(^|[^A-Za-z0-9_])--enable-kv-cache-events($|[^A-Za-z0-9_-])": "--enable-kv-cache-events",
    r"(^|[^A-Za-z0-9_])--prefix-cache-retention-interval($|[^A-Za-z0-9_-])": "--prefix-cache-retention-interval",
    r"\bprefix_cache_retention_interval\b": "prefix_cache_retention_interval",
    r"\bVLLM_PREFIX_CACHE_RETENTION_INTERVAL\b": "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
    r"(^|[^A-Za-z0-9_])--prefix-caching-hash-algo($|[^A-Za-z0-9_-])": "--prefix-caching-hash-algo",
    r"\bprefix_caching_hash_algo\b": "prefix_caching_hash_algo",
    r"\b(enable_kv_cache_events|kv_cache_events)\b": "kv_cache_events",
    r"\b(kv_transfer_config|kv_connector|LMCacheConnector)\b": "kv_transfer_config",
    r"\bAsyncLLMEngine\b": "AsyncLLMEngine",
}


# Keep the syntax matcher generic and bounded.  Credential semantics are
# classified in Python below, so adding a new casing or separator does not
# require another overlapping keyword regex.  The key component bound also
# keeps the scanner's worst-case work linear on arbitrary source lines.
IDENTIFIER_KEY_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9_])
    (?:(?:"(?P<double_key>[A-Za-z0-9][A-Za-z0-9_-]{0,127})")
      |(?:'(?P<single_key>[A-Za-z0-9][A-Za-z0-9_-]{0,127})')
      |(?P<plain_key>[A-Za-z0-9][A-Za-z0-9_-]{0,127}))
    \s*[:=]\s*
    """,
    re.VERBOSE,
)
OPTION_KEY_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9_])--(?P<option>[A-Za-z0-9][A-Za-z0-9_-]{0,127})
    (?:(?:=\s*)|(?:\s+))
    """,
    re.VERBOSE,
)
CURL_USER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:-u|--user)(?:(?:=\s*)|(?:\s+))"
)

VALUE_STOP_CHARS = frozenset('"\'`,;)}]')
STRUCTURAL_VALUE_STOP_CHARS = frozenset(",;)}]")
SCHEME_NAMES = frozenset({"basic", "bearer", "token"})
CAMEL_BOUNDARY_PATTERN = re.compile(r"([a-z0-9])([A-Z])")
ACRONYM_BOUNDARY_PATTERN = re.compile(r"([A-Z]+)([A-Z][a-z])")
IDENTIFIER_WORD_PATTERN = re.compile(r"[A-Za-z0-9]+")
SCHEME_PREFIX_PATTERN = re.compile(
    r"^(?P<scheme>Bearer|Basic|Token)\s+(?P<credential>\S+)$",
    re.IGNORECASE,
)
PLURAL_STEMS = {
    "authorizations": "authorization",
    "credentials": "credential",
    "keys": "key",
    "passwords": "password",
    "salts": "salt",
    "secrets": "secret",
    "seeds": "seed",
    "tokens": "token",
}
SENSITIVE_QUALIFIERS = frozenset(
    {"access", "api", "auth", "bearer", "hf", "hub", "pat", "refresh", "service", "session", "vault"}
)


def split_identifier_words(identifier):
    """Split snake/kebab/mixed-case keys into lowercase semantic words."""
    expanded = CAMEL_BOUNDARY_PATTERN.sub(r"\1_\2", identifier)
    expanded = ACRONYM_BOUNDARY_PATTERN.sub(r"\1_\2", expanded)
    words = []
    for word in IDENTIFIER_WORD_PATTERN.findall(expanded):
        words.append(PLURAL_STEMS.get(word.lower(), word.lower()))
    return words


def is_sensitive_key(identifier):
    """Classify a parsed key without treating ordinary token counts as secrets."""
    words = split_identifier_words(identifier)
    word_set = set(words)
    if not words:
        return False
    compact_identifier = re.sub(r"[^a-z0-9]", "", identifier.lower())
    if "salt" in compact_identifier or "seed" in compact_identifier:
        return True
    if word_set.intersection({"salt", "seed", "secret", "password", "credential"}):
        return True
    if "authorization" in word_set:
        return True
    if "key" in word_set and word_set.intersection({"access", "api", "private"}):
        return True
    return "token" in word_set and bool(word_set.intersection(SENSITIVE_QUALIFIERS))


def _key_from_match(match):
    return (
        match.groupdict().get("double_key")
        or match.groupdict().get("single_key")
        or match.groupdict().get("plain_key")
        or match.groupdict().get("option")
    )


def _consume_token(text, start):
    index = start
    while index < len(text) and not text[index].isspace() and text[index] not in VALUE_STOP_CHARS:
        index += 1
    return index


def _scheme_name(value):
    match = SCHEME_PREFIX_PATTERN.match(value)
    return match.group("scheme") if match else None


def _consume_value(text, start, allow_equals=False):
    """Return a bounded source value span, including a complete scheme value."""
    index = start
    while index < len(text) and text[index].isspace():
        index += 1
    if allow_equals and index < len(text) and text[index] == "=":
        index += 1
        while index < len(text) and text[index].isspace():
            index += 1
    if index >= len(text) or text[index] in STRUCTURAL_VALUE_STOP_CHARS:
        return None

    quote = text[index] if text[index] in {'"', "'"} else ""
    if quote:
        value_start = index
        index += 1
        while index < len(text):
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == quote:
                value_end = index + 1
                inner = text[value_start + 1 : index]
                return value_start, value_end, quote, _scheme_name(inner)
            index += 1
        inner = text[value_start + 1 :]
        return value_start, len(text), quote, _scheme_name(inner)

    value_start = index
    first_end = _consume_token(text, index)
    if first_end == value_start:
        return None
    first = text[value_start:first_end]
    if first.lower() in SCHEME_NAMES:
        second_start = first_end
        while second_start < len(text) and text[second_start].isspace():
            second_start += 1
        second_end = _consume_token(text, second_start)
        if second_end > second_start:
            return value_start, second_end, "", first
    return value_start, first_end, "", None


def _redacted_value(text, value_info):
    value_start, value_end, quote, scheme = value_info
    raw_value = text[value_start:value_end]
    closing_quote = quote if quote and raw_value.endswith(quote) else ""
    if quote:
        if scheme:
            return f"{quote}{scheme} [REDACTED_SECRET]{closing_quote}"
        return f"{quote}[REDACTED_SECRET]{closing_quote}"
    if scheme:
        return f"{scheme} [REDACTED_SECRET]"
    return "[REDACTED_SECRET]"


def redact_sensitive_text(text):
    """Redact classified assignment, option, header, and curl credential values."""
    events = []
    for match in IDENTIFIER_KEY_PATTERN.finditer(text):
        events.append((match.start(), match.end(), "assignment", _key_from_match(match)))
    for match in OPTION_KEY_PATTERN.finditer(text):
        events.append((match.start(), match.end(), "option", _key_from_match(match)))
    for match in CURL_USER_PATTERN.finditer(text):
        events.append((match.start(), match.end(), "curl-user", None))
    events.sort(
        key=lambda event: (
            event[0],
            {"curl-user": 0, "option": 1, "assignment": 2}[event[2]],
            -(event[1] - event[0]),
        )
    )

    output = []
    cursor = 0
    for start, end, kind, key in events:
        if start < cursor:
            continue
        sensitive = kind == "curl-user" or is_sensitive_key(key or "")
        value_info = _consume_value(text, end, allow_equals=kind == "option")
        if value_info is None:
            output.append(text[cursor:end])
            cursor = end
            continue
        value_start, value_end, _, _ = value_info
        if sensitive:
            output.append(text[cursor:value_start])
            output.append(_redacted_value(text, value_info))
            cursor = value_end
        else:
            output.append(text[cursor:end])
            cursor = end
    output.append(text[cursor:])
    return "".join(output)


def should_scan(path):
    if path.name.startswith(".env"):
        return False
    return path.is_file() and (
        path.suffix.lower() in SOURCE_SUFFIXES or path.name in SOURCE_FILENAMES
    )


def iter_files(root):
    root = Path(root)
    if any(part.startswith(".env") or part in SKIP_DIRS for part in root.parts):
        return
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIRS and not dirname.startswith(".env")
        )
        current_path = Path(current)
        for filename in sorted(filenames):
            path = current_path / filename
            if should_scan(path):
                yield path


def find_matches(root):
    findings = []
    providers = {provider: 0 for provider in PROVIDER_PATTERNS}
    files_scanned = 0
    for path in iter_files(root):
        files_scanned += 1
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for provider, patterns in PROVIDER_PATTERNS.items():
                matched_patterns = [
                    pattern
                    for pattern in patterns
                    if re.search(pattern, line, flags=re.IGNORECASE)
                ]
                if not matched_patterns:
                    continue
                providers[provider] += 1
                finding = {
                    "path": str(path.relative_to(root)),
                    "line": lineno,
                    "provider": provider,
                    "pattern": matched_patterns[0],
                    "text": redact_sensitive_text(line.strip()[:200]),
                }
                if provider == "vllm":
                    finding["signals"] = list(
                        dict.fromkeys(
                            VLLM_SIGNAL_LABELS.get(pattern, pattern)
                            for pattern in matched_patterns
                        )
                    )
                findings.append(finding)
    providers = {name: count for name, count in providers.items() if count}
    return {
        "root": str(root),
        "files_scanned": files_scanned,
        "matches": len(findings),
        "providers": providers,
        "findings": findings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Find likely LLM provider calls in a repository."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    print(json.dumps(find_matches(root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
