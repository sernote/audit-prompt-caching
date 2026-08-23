#!/usr/bin/env python3
"""Find provider/cache signals as lexical locators while eliding snippets.

Findings retain a stable path, line, provider, pattern, and signal contract;
snippets are always elided: the ``text`` field is always
``[SOURCE_SNIPPET_ELIDED]`` and the sole supported source-snippet policy is
``elided``. This scanner is a lexical locator only: a
line may match comments, dead code, or overridden configuration, and the
scanner never resolves active/effective values or source precedence. Paths are
emitted verbatim; open the reported path:line and verify the resolved runtime
configuration during Deployment Audit.
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
        r"(^|[^A-Za-z0-9_])--no-enable-prefix-caching($|[^A-Za-z0-9_-])",
        r"(^|[^A-Za-z0-9_])--enable-prefix-caching($|[^A-Za-z0-9_-])",
        r"(^|[^A-Za-z0-9_])--kv-events-config($|[^A-Za-z0-9_-])",
        r"(^|[^A-Za-z0-9_])--prefix-cache-retention-interval($|[^A-Za-z0-9_-])",
        r"\bprefix_cache_retention_interval\b",
        r"\bVLLM_PREFIX_CACHE_RETENTION_INTERVAL\b",
        r"(^|[^A-Za-z0-9_])--prefix-caching-hash-algo($|[^A-Za-z0-9_-])",
        r"\bprefix_caching_hash_algo\b",
        r"\benable_prefix_caching\b",
        r"\benable_kv_cache_events\b",
        r"\bkv_cache_events\b",
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
    r"(^|[^A-Za-z0-9_])--no-enable-prefix-caching($|[^A-Za-z0-9_-])": "--no-enable-prefix-caching",
    r"(^|[^A-Za-z0-9_])--enable-prefix-caching($|[^A-Za-z0-9_-])": "--enable-prefix-caching",
    r"(^|[^A-Za-z0-9_])--kv-events-config($|[^A-Za-z0-9_-])": "--kv-events-config",
    r"(^|[^A-Za-z0-9_])--prefix-cache-retention-interval($|[^A-Za-z0-9_-])": "--prefix-cache-retention-interval",
    r"\bprefix_cache_retention_interval\b": "prefix_cache_retention_interval",
    r"\bVLLM_PREFIX_CACHE_RETENTION_INTERVAL\b": "VLLM_PREFIX_CACHE_RETENTION_INTERVAL",
    r"(^|[^A-Za-z0-9_])--prefix-caching-hash-algo($|[^A-Za-z0-9_-])": "--prefix-caching-hash-algo",
    r"\bprefix_caching_hash_algo\b": "prefix_caching_hash_algo",
    r"\benable_prefix_caching\b": "enable_prefix_caching",
    r"\benable_kv_cache_events\b": "enable_kv_cache_events",
    r"\bkv_cache_events\b": "kv_cache_events",
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
