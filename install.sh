#!/usr/bin/env bash
set -euo pipefail

SKILL_NAME="audit-prompt-caching"
DEFAULT_REPO="https://github.com/sernote/audit-prompt-caching.git"
DEFAULT_REF="main"

agent="codex"
custom_dir=""
source_dir=""
repo_url="$DEFAULT_REPO"
repo_ref="$DEFAULT_REF"
force=0
tmp_dir=""

usage() {
  cat <<'EOF'
Install the audit-prompt-caching skill.

Usage:
  install.sh [options]

Examples:
  curl -fsSL https://raw.githubusercontent.com/sernote/audit-prompt-caching/main/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/sernote/audit-prompt-caching/main/install.sh | bash -s -- --agent claude
  bash install.sh --source-dir . --dir /tmp/skills --force

Options:
  --agent codex      Install to ~/.codex/skills/audit-prompt-caching (default)
  --agent claude     Install to ~/.claude/skills/audit-prompt-caching
  --agent both       Install to both default skill directories
  --dir PATH         Install under a custom skills directory
  --source-dir PATH  Copy from a local repository checkout or skill directory
  --repo URL         Git repository URL to clone
  --ref REF          Git branch or tag to clone
  --force            Replace an existing audit-prompt-caching install
  --help             Show this help
EOF
}

die() {
  printf 'install.sh: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$tmp_dir" && -d "$tmp_dir" ]]; then
    rm -rf "$tmp_dir"
  fi
}
trap cleanup EXIT

expand_path() {
  local path="$1"
  case "$path" in
    "~")
      printf '%s\n' "$HOME"
      ;;
    "~/"*)
      printf '%s/%s\n' "$HOME" "${path#~/}"
      ;;
    *)
      printf '%s\n' "$path"
      ;;
  esac
}

resolve_skill_dir() {
  local root="$1"

  if [[ -f "$root/SKILL.md" && -d "$root/references" && -d "$root/scripts" && -d "$root/evals" ]]; then
    printf '%s\n' "$root"
    return 0
  fi

  if [[ -f "$root/$SKILL_NAME/SKILL.md" && -d "$root/$SKILL_NAME/references" && -d "$root/$SKILL_NAME/scripts" && -d "$root/$SKILL_NAME/evals" ]]; then
    printf '%s\n' "$root/$SKILL_NAME"
    return 0
  fi

  die "could not find $SKILL_NAME package under $root"
}

validate_install() {
  local target="$1"

  [[ -f "$target/SKILL.md" ]] || die "installed package is missing SKILL.md"
  [[ -d "$target/references" ]] || die "installed package is missing references/"
  [[ -d "$target/scripts" ]] || die "installed package is missing scripts/"
  [[ -d "$target/evals" ]] || die "installed package is missing evals/"
}

install_one() {
  local parent="$1"
  local source_skill_dir="$2"
  local target="$parent/$SKILL_NAME"

  case "$target" in
    */audit-prompt-caching)
      ;;
    *)
      die "refusing to install to unexpected target: $target"
      ;;
  esac

  mkdir -p "$parent"

  if [[ -e "$target" ]]; then
    if [[ "$force" -ne 1 ]]; then
      die "$target already exists; rerun with --force to replace it"
    fi
    rm -rf "$target"
  fi

  cp -R "$source_skill_dir" "$target"
  validate_install "$target"
  printf 'Installed %s to %s\n' "$SKILL_NAME" "$target"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent)
      [[ $# -ge 2 ]] || die "--agent requires a value"
      agent="$2"
      case "$agent" in
        codex|claude|both)
          ;;
        *)
          die "--agent must be codex, claude, or both"
          ;;
      esac
      shift 2
      ;;
    --dir)
      [[ $# -ge 2 ]] || die "--dir requires a value"
      custom_dir="$(expand_path "$2")"
      shift 2
      ;;
    --source-dir)
      [[ $# -ge 2 ]] || die "--source-dir requires a value"
      source_dir="$(expand_path "$2")"
      shift 2
      ;;
    --repo)
      [[ $# -ge 2 ]] || die "--repo requires a value"
      repo_url="$2"
      shift 2
      ;;
    --ref)
      [[ $# -ge 2 ]] || die "--ref requires a value"
      repo_ref="$2"
      shift 2
      ;;
    --force)
      force=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

if [[ -n "$source_dir" ]]; then
  source_skill_dir="$(resolve_skill_dir "$source_dir")"
else
  command -v git >/dev/null 2>&1 || die "git is required; install git or use --source-dir from a local checkout"
  tmp_dir="$(mktemp -d)"
  git clone --depth 1 --branch "$repo_ref" "$repo_url" "$tmp_dir/repo" >/dev/null
  source_skill_dir="$(resolve_skill_dir "$tmp_dir/repo")"
fi

if [[ -n "$custom_dir" ]]; then
  install_one "$custom_dir" "$source_skill_dir"
else
  case "$agent" in
    codex)
      install_one "${CODEX_HOME:-$HOME/.codex}/skills" "$source_skill_dir"
      ;;
    claude)
      install_one "${CLAUDE_HOME:-$HOME/.claude}/skills" "$source_skill_dir"
      ;;
    both)
      install_one "${CODEX_HOME:-$HOME/.codex}/skills" "$source_skill_dir"
      install_one "${CLAUDE_HOME:-$HOME/.claude}/skills" "$source_skill_dir"
      ;;
  esac
fi

printf '\nRestart your agent session, then ask: Use $%s to audit my LLM cache behavior.\n' "$SKILL_NAME"
