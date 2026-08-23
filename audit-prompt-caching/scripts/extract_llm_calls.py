#!/usr/bin/env python3
"""Find provider/cache signals while always eliding source snippets.

Findings retain a stable path, line, provider, pattern, and signal contract;
the compatibility ``text`` field is always ``[SOURCE_SNIPPET_ELIDED]`` and the
sole supported source-snippet policy is ``elided``. Paths are emitted verbatim
as locators; use the reported path and line for authorized local inspection
instead of relying on copied source text. Only closed-vocabulary vLLM values
are emitted; bare boolean flags resolve to ``true`` and unknown values to
``unspecified``.
"""

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
        r"\bCacheReadInputTokens\b",
        r"\bCacheWriteInputTokens\b",
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
        r"\benable_prefix_caching\b",
        r"\bVLLM_ENABLE_PREFIX_CACHING\b",
        r"\benable_kv_cache_events\b",
        r"\bkv_cache_events\b",
        r"\bVLLM_ENABLE_KV_CACHE_EVENTS\b",
        r"\bVLLM_KV_CACHE_EVENTS\b",
        r"\bVLLM_PREFIX_CACHING_HASH_ALGO\b",
        r"\bkv_transfer_config\b",
        r"\bkv_connector\b",
        r"\bLMCacheConnector\b",
        r"\bAsyncLLMEngine\b",
    ],
    "sglang": [
        r"\bsglang\b",
        r"\bRadixAttention\b",
        r"(^|[^A-Za-z0-9_])--disable-radix-cache($|[^A-Za-z0-9_-])",
        r"\bHiCache\b",
        r"\benable_hierarchical_cache\b",
        r"\bhicache_storage_backend\b",
        r"\bdisaggregation_mode\b",
        r"\bpd_disaggregation\b",
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


SIGNAL_LABELS = {
    # OpenAI
    r"\bfrom\s+openai\s+import\b": "from_openai_import",
    r"\bimport\s+openai\b": "import_openai",
    r"\bresponses\.create\s*\(": "responses_create",
    r"\bchat\.completions\.create\s*\(": "chat_completions_create",
    r"\bprompt_cache_key\b": "prompt_cache_key",
    r"\bprompt_cache_retention\b": "prompt_cache_retention",
    # Anthropic
    r"\banthropic\b": "anthropic",
    r"\bAnthropic\s*\(": "Anthropic",
    r"\bmessages\.create\s*\(": "messages_create",
    r"\bcache_control\b": "cache_control",
    # Bedrock
    r"\bbedrock-runtime\b": "bedrock-runtime",
    r"\bBedrockRuntime\b": "BedrockRuntime",
    r"\bclient\.converse\b": "client_converse",
    r"\binvoke_model\b": "invoke_model",
    r"\bcachePoint\b": "cachePoint",
    r"\bCacheReadInputTokens\b": "CacheReadInputTokens",
    r"\bCacheWriteInputTokens\b": "CacheWriteInputTokens",
    # OpenRouter
    r"\bopenrouter\b": "openrouter",
    r"\bopenrouter\.ai/api/v1\b": "openrouter_api",
    r"\bOPENROUTER_API_KEY\b": "OPENROUTER_API_KEY",
    r"\bopenrouter/auto\b": "openrouter_auto",
    # vLLM
    r"\bvllm\b": "vllm",
    r"(^|[^A-Za-z0-9_])--enable-prefix-caching($|[^A-Za-z0-9_-])": "--enable-prefix-caching",
    r"(^|[^A-Za-z0-9_])--enable-kv-cache-events($|[^A-Za-z0-9_-])": "--enable-kv-cache-events",
    r"(^|[^A-Za-z0-9_])--prefix-cache-retention-interval($|[^A-Za-z0-9_-])": "--prefix-cache-retention-interval",
    r"\bprefix_cache_retention_interval\b": "prefix_cache_retention_interval",
    r"\bVLLM_PREFIX_CACHE_RETENTION_INTERVAL\b": "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
    r"(^|[^A-Za-z0-9_])--prefix-caching-hash-algo($|[^A-Za-z0-9_-])": "--prefix-caching-hash-algo",
    r"\bprefix_caching_hash_algo\b": "prefix_caching_hash_algo",
    r"\benable_prefix_caching\b": "--enable-prefix-caching",
    r"\bVLLM_ENABLE_PREFIX_CACHING\b": "--enable-prefix-caching",
    r"\benable_kv_cache_events\b": "--enable-kv-cache-events",
    r"\bkv_cache_events\b": "kv_cache_events",
    r"\bVLLM_ENABLE_KV_CACHE_EVENTS\b": "--enable-kv-cache-events",
    r"\bVLLM_KV_CACHE_EVENTS\b": "kv_cache_events",
    r"\bVLLM_PREFIX_CACHING_HASH_ALGO\b": "prefix_caching_hash_algo",
    r"\bkv_transfer_config\b": "kv_transfer_config",
    r"\bkv_connector\b": "kv_connector",
    r"\bLMCacheConnector\b": "LMCacheConnector",
    r"\bAsyncLLMEngine\b": "AsyncLLMEngine",
    # SGLang
    r"\bsglang\b": "sglang",
    r"\bRadixAttention\b": "RadixAttention",
    r"(^|[^A-Za-z0-9_])--disable-radix-cache($|[^A-Za-z0-9_-])": "--disable-radix-cache",
    r"\bHiCache\b": "HiCache",
    r"\benable_hierarchical_cache\b": "enable_hierarchical_cache",
    r"\bhicache_storage_backend\b": "hicache_storage_backend",
    r"\bdisaggregation_mode\b": "disaggregation_mode",
    r"\bpd_disaggregation\b": "pd_disaggregation",
    # Gemini, DeepSeek, and Qwen
    r"\bgoogle\.genai\b": "google_genai",
    r"\bgoogle\.generativeai\b": "google_generativeai",
    r"\bCachedContent\b": "CachedContent",
    r"\bdeepseek\b": "deepseek",
    r"\bapi\.deepseek\.com\b": "deepseek_api",
    r"\bprompt_cache_hit_tokens\b": "prompt_cache_hit_tokens",
    r"\bdashscope\b": "dashscope",
    r"\bqwen\b": "qwen",
    r"\bbailian\b": "bailian",
}

VLLM_SIGNAL_LABELS = {
    pattern: SIGNAL_LABELS[pattern]
    for pattern in PROVIDER_PATTERNS["vllm"]
}

LEGACY_PATTERN_ALIASES = {
    r"\bCacheReadInputTokens\b": r"\bCache(Read|Write)InputTokens\b",
    r"\bCacheWriteInputTokens\b": r"\bCache(Read|Write)InputTokens\b",
    r"\benable_kv_cache_events\b": r"\b(enable_kv_cache_events|kv_cache_events)\b",
    r"\bkv_cache_events\b": r"\b(enable_kv_cache_events|kv_cache_events)\b",
    r"\bkv_transfer_config\b": r"\b(kv_transfer_config|kv_connector|LMCacheConnector)\b",
    r"\bkv_connector\b": r"\b(kv_transfer_config|kv_connector|LMCacheConnector)\b",
    r"\bLMCacheConnector\b": r"\b(kv_transfer_config|kv_connector|LMCacheConnector)\b",
    r"\benable_hierarchical_cache\b": r"\b(enable_hierarchical_cache|hicache_storage_backend)\b",
    r"\bhicache_storage_backend\b": r"\b(enable_hierarchical_cache|hicache_storage_backend)\b",
    r"\bdisaggregation_mode\b": r"\b(disaggregation_mode|pd_disaggregation)\b",
    r"\bpd_disaggregation\b": r"\b(disaggregation_mode|pd_disaggregation)\b",
}

SOURCE_SNIPPET_POLICY = "elided"
SOURCE_SNIPPET_TEXT = "[SOURCE_SNIPPET_ELIDED]"
SIGNAL_VALUE_UNSPECIFIED = "unspecified"
VLLM_BOOLEAN_VALUES = frozenset({"true", "false", "1", "0"})
VLLM_HASH_VALUES = frozenset(
    {"builtin", "sha256", "sha256_cbor", "xxhash", "xxhash_cbor"}
)
VLLM_RETENTION_VALUE_PATTERN = re.compile(r"\A\d{1,9}\Z")
COMMENTED_LINE_PATTERN = re.compile(r"\A\s*(?:#|//|;|--\s)")
VLLM_SIGNAL_VALUE_ALIASES = {
    "--enable-prefix-caching": (
        "--enable-prefix-caching",
        "enable_prefix_caching",
        "VLLM_ENABLE_PREFIX_CACHING",
    ),
    "--enable-kv-cache-events": (
        "--enable-kv-cache-events",
        "enable_kv_cache_events",
        "kv_cache_events",
        "VLLM_ENABLE_KV_CACHE_EVENTS",
        "VLLM_KV_CACHE_EVENTS",
    ),
    "kv_cache_events": (
        "--enable-kv-cache-events",
        "enable_kv_cache_events",
        "kv_cache_events",
        "VLLM_ENABLE_KV_CACHE_EVENTS",
        "VLLM_KV_CACHE_EVENTS",
    ),
    "--prefix-caching-hash-algo": (
        "--prefix-caching-hash-algo",
        "prefix_caching_hash_algo",
        "VLLM_PREFIX_CACHING_HASH_ALGO",
    ),
    "prefix_caching_hash_algo": (
        "--prefix-caching-hash-algo",
        "prefix_caching_hash_algo",
        "VLLM_PREFIX_CACHING_HASH_ALGO",
    ),
    "--prefix-cache-retention-interval": (
        "--prefix-cache-retention-interval",
        "prefix_cache_retention_interval",
        "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
    ),
    "prefix_cache_retention_interval": (
        "--prefix-cache-retention-interval",
        "prefix_cache_retention_interval",
        "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
    ),
    "VLLM_PREFIX_CACHE_RETENTION_INTERVAL": (
        "--prefix-cache-retention-interval",
        "prefix_cache_retention_interval",
        "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
    ),
}


def _consume_allowlisted_flag_value(line, aliases, vocabulary, numeric=False):
    """Resolve a narrowly allow-listed setting without returning source text."""
    for alias in aliases:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(alias)}(?![A-Za-z0-9_-])"
        )
        match = pattern.search(line)
        if match is None:
            continue
        index = match.end()
        while index < len(line) and line[index].isspace():
            index += 1
        has_separator = index < len(line) and line[index] in ":="
        if has_separator:
            index += 1
            while index < len(line) and line[index].isspace():
                index += 1
        elif index >= len(line) or line[index] in "#;,)}]" or line[index] == "-":
            return "true" if not numeric else SIGNAL_VALUE_UNSPECIFIED
        if index >= len(line) or line[index] in "#;,)}]":
            return "true" if not numeric else SIGNAL_VALUE_UNSPECIFIED

        quote = line[index] if line[index] in {'"', "'"} else ""
        if quote:
            index += 1
            value_start = index
            while index < len(line) and line[index] != quote:
                index += 1
            candidate = line[value_start:index]
        else:
            value_start = index
            while index < len(line) and not line[index].isspace() and line[index] not in ",;)}]":
                index += 1
            candidate = line[value_start:index]
        candidate = candidate.lower()
        if candidate in vocabulary:
            return candidate
        if numeric and VLLM_RETENTION_VALUE_PATTERN.fullmatch(candidate):
            return candidate
        return SIGNAL_VALUE_UNSPECIFIED
    return SIGNAL_VALUE_UNSPECIFIED


def _signal_value(signal, line):
    aliases = VLLM_SIGNAL_VALUE_ALIASES.get(signal)
    if aliases is None:
        return SIGNAL_VALUE_UNSPECIFIED
    if signal in {
        "--enable-prefix-caching",
        "--enable-kv-cache-events",
        "kv_cache_events",
    }:
        return _consume_allowlisted_flag_value(line, aliases, VLLM_BOOLEAN_VALUES)
    if signal in {"--prefix-caching-hash-algo", "prefix_caching_hash_algo"}:
        return _consume_allowlisted_flag_value(line, aliases, VLLM_HASH_VALUES)
    return _consume_allowlisted_flag_value(line, aliases, frozenset(), numeric=True)


def should_scan(path):
    if path.name.startswith(".env"):
        return False
    return path.is_file() and (
        path.suffix.lower() in SOURCE_SUFFIXES or path.name in SOURCE_FILENAMES
    )


def iter_files(root):
    root = Path(root)
    if root.name.startswith(".env") or root.name in SKIP_DIRS:
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
                signals = list(
                    dict.fromkeys(SIGNAL_LABELS[pattern] for pattern in matched_patterns)
                )
                finding = {
                    "path": str(path.relative_to(root)),
                    "line": lineno,
                    "provider": provider,
                    "pattern": LEGACY_PATTERN_ALIASES.get(
                        matched_patterns[0], matched_patterns[0]
                    ),
                    "text": SOURCE_SNIPPET_TEXT,
                    "signals": signals,
                    "commented": bool(COMMENTED_LINE_PATTERN.match(line)),
                    "signal_values": {
                        signal: _signal_value(signal, line) for signal in signals
                    },
                }
                findings.append(finding)
    providers = {name: count for name, count in providers.items() if count}
    return {
        "root": str(root),
        "files_scanned": files_scanned,
        "matches": len(findings),
        "providers": providers,
        "findings": findings,
        "source_snippet_policy": SOURCE_SNIPPET_POLICY,
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
