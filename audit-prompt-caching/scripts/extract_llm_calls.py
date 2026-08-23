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


# Keep identifier components bounded.  The previous ``[A-Z0-9_-]*`` prefix
# could retry every possible split of a long non-match, making extraction
# quadratic.  A credential name can still have up to 64 bounded components on
# either side of its sensitive component, which covers deployment identifiers
# without permitting an unbounded regex search.
SENSITIVE_NAME_COMPONENT = r"[A-Z0-9]{1,64}"
SENSITIVE_NAME_PREFIX = rf"(?:{SENSITIVE_NAME_COMPONENT}[_-]){{0,64}}"
SENSITIVE_NAME_TRAILING = rf"(?:[_-]{SENSITIVE_NAME_COMPONENT}){{0,64}}"
SENSITIVE_NAME_CORE = (
    r"(?:PYTHONHASHSEED|"
    r"API[_-]?KEY|API[_-]?TOKENS?|"
    r"ACCESS[_-]?KEY|PRIVATE[_-]?KEY|"
    r"SALT|SEED|TOKEN(?:S)?|SECRET(?:S)?|PASSWORD(?:S)?|CREDENTIAL(?:S)?)"
)
SENSITIVE_ASSIGNMENT_NAME = (
    rf"{SENSITIVE_NAME_PREFIX}{SENSITIVE_NAME_CORE}{SENSITIVE_NAME_TRAILING}"
)
SENSITIVE_OPTION_NAME = SENSITIVE_ASSIGNMENT_NAME

# These are ordinary request/usage fields, not credentials.  The matcher
# deliberately recognizes TOKEN as a bounded component so names such as
# API_TOKENS are covered, then leaves these well-known non-secret fields alone.
NON_CREDENTIAL_NAMES = {
    "INPUT_TOKENS",
    "MAX_TOKENS",
    "OUTPUT_TOKENS",
    "TOKEN_COUNT",
}


SENSITIVE_ASSIGNMENT_PATTERNS = (
    re.compile(
        rf'''(?ix)(?P<prefix>(?<![A-Za-z0-9_])["']?(?P<name>{SENSITIVE_ASSIGNMENT_NAME})["']?\]?\s*[:=]\s*)(?P<quote>")(?P<value>(?:\\.|[^"\\])*)"'''
    ),
    re.compile(
        rf"""(?ix)(?P<prefix>(?<![A-Za-z0-9_])["']?(?P<name>{SENSITIVE_ASSIGNMENT_NAME})["']?\]?\s*[:=]\s*)(?P<quote>')(?P<value>(?:\\.|[^'\\])*)'"""
    ),
    re.compile(
        rf'''(?ix)(?P<prefix>(?<![A-Za-z0-9_])["']?(?P<name>{SENSITIVE_ASSIGNMENT_NAME})["']?\]?\s*[:=]\s*)(?P<value>[^\s"'`,;]+)'''
    ),
    re.compile(
        rf'''(?ix)(?P<prefix>(?<![A-Za-z0-9_])--(?P<option>{SENSITIVE_OPTION_NAME})\s+)(?P<quote>")(?P<value>(?:\\.|[^"\\])*)"'''
    ),
    re.compile(
        rf"""(?ix)(?P<prefix>(?<![A-Za-z0-9_])--(?P<option>{SENSITIVE_OPTION_NAME})\s+)(?P<quote>')(?P<value>(?:\\.|[^'\\])*)'"""
    ),
    re.compile(
        rf'''(?ix)(?P<prefix>(?<![A-Za-z0-9_])--(?P<option>{SENSITIVE_OPTION_NAME})\s+)(?P<value>[^\s"'`,;]+)'''
    ),
)

AUTHORIZATION_HEADER_PATTERN = re.compile(
    r'''(?ix)(?P<prefix>(?<![A-Za-z0-9_])["']?authorization["']?\s*:\s*["']?(?:bearer|basic)\s+)(?P<value>[^\s"'`,;]+)'''
)


def redact_sensitive_text(text):
    """Redact sensitive assignment/option values before emitting snippets."""
    for pattern in SENSITIVE_ASSIGNMENT_PATTERNS:
        def replace_assignment(match):
            candidate = match.groupdict().get("name") or match.groupdict().get("option")
            normalized = candidate.upper().replace("-", "_") if candidate else ""
            if normalized in NON_CREDENTIAL_NAMES:
                return match.group(0)
            quote = match.groupdict().get("quote", "")
            return (
                f"{match.group('prefix')}"
                f"{quote}[REDACTED_SECRET]{quote}"
            )

        text = pattern.sub(replace_assignment, text)
    text = AUTHORIZATION_HEADER_PATTERN.sub(
        lambda match: f"{match.group('prefix')}[REDACTED_SECRET]",
        text,
    )
    return text


def should_scan(path):
    if path.name.startswith(".env"):
        return False
    return path.is_file() and (
        path.suffix.lower() in SOURCE_SUFFIXES or path.name in SOURCE_FILENAMES
    )


def iter_files(root):
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
