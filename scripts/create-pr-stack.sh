#!/usr/bin/env bash
# Create a full GitHub PR stack in one go (ready for review — never draft).
#
# Each step is one line: BRANCH|TITLE|BODY
#   - BRANCH must already exist on the remote
#   - Stack is linear: step N's branch must contain step N-1's tip
#   - PR 1 bases on --base (default: master)
#   - PR N bases on step N-1's BRANCH
#
# Usage (BODY is one field; use $'\n' for multi-line bodies with --step):
#   scripts/create-pr-stack.sh --base master \
#     --step 'cursor/m2|feat: M2 logging|## Summary'$'\n''- logs + rain' \
#     --step 'cursor/m3|feat: M3 analyzer|## Summary'$'\n''- weekly review'
#
#   scripts/create-pr-stack.sh --dry-run --base master \
#     --step 'b1|Title 1|Body one' \
#     --step 'b2|Title 2|Body two'
#
# Stdin form (one step per line; BODY must stay on the same line):
#   scripts/create-pr-stack.sh --base master <<'EOF'
#   cursor/m2|feat: M2 logging|## Summary - logs + rain
#   cursor/m3|feat: M3 analyzer|## Summary - weekly review
#   EOF
#
# After merging: merge bottom-up. Prefer deleting the merged head branch so
# GitHub retargets the next PR onto master. If the head is kept, run:
#   gh pr edit <next> --base master
# before merging the tip (otherwise the tip merges into a dead feature branch).

set -euo pipefail

BASE_REF="master"
REMOTE="origin"
DRY_RUN=0
REPO=""
STEPS=()

usage() {
  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base) BASE_REF="${2:?}"; shift 2 ;;
    --remote) REMOTE="${2:?}"; shift 2 ;;
    --repo) REPO="${2:?}"; shift 2 ;;
    --step) STEPS+=("${2:?}"); shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage 0 ;;
    *)
      echo "Unknown arg: $1" >&2
      usage 1
      ;;
  esac
done

if [[ ${#STEPS[@]} -eq 0 ]] && [[ ! -t 0 ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "${line// }" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    STEPS+=("$line")
  done
fi

if [[ ${#STEPS[@]} -eq 0 ]]; then
  echo "No steps given. Pass --step or pipe BRANCH|TITLE|BODY lines on stdin." >&2
  usage 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required" >&2
  exit 1
fi

GH_REPO_ARGS=()
if [[ -n "$REPO" ]]; then
  GH_REPO_ARGS=(--repo "$REPO")
fi

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

gh_cmd() {
  # Avoid unbound-variable errors when GH_REPO_ARGS is empty under `set -u`.
  if [[ ${#GH_REPO_ARGS[@]} -gt 0 ]]; then
    run gh "$@" "${GH_REPO_ARGS[@]}"
  else
    run gh "$@"
  fi
}

if [[ "$DRY_RUN" -eq 0 ]]; then
  git fetch "$REMOTE" "$BASE_REF" >/dev/null 2>&1 || true
fi

declare -a BRANCHES=()
declare -a TITLES=()
declare -a BODIES=()

for step in "${STEPS[@]}"; do
  if [[ "$step" != *"|"* ]]; then
    echo "Invalid step (need BRANCH|TITLE|BODY): $step" >&2
    exit 1
  fi
  branch="${step%%|*}"
  rest="${step#*|}"
  if [[ "$rest" != *"|"* ]]; then
    title="$rest"
    body=""
  else
    title="${rest%%|*}"
    body="${rest#*|}"
  fi
  branch="$(trim "$branch")"
  title="$(trim "$title")"
  if [[ -z "$branch" || -z "$title" ]]; then
    echo "Invalid step (need BRANCH|TITLE|BODY): $step" >&2
    exit 1
  fi
  BRANCHES+=("$branch")
  TITLES+=("$title")
  BODIES+=("$body")
done

n=${#BRANCHES[@]}

for ((i = 0; i < n; i++)); do
  b="${BRANCHES[$i]}"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    if ! git ls-remote --exit-code --heads "$REMOTE" "$b" >/dev/null 2>&1; then
      echo "Remote branch missing: $REMOTE/$b (push it first)" >&2
      exit 1
    fi
    git fetch "$REMOTE" "$b" >/dev/null 2>&1 || true
  fi
  if [[ "$i" -gt 0 && "$DRY_RUN" -eq 0 ]]; then
    prev="${BRANCHES[$i - 1]}"
    if ! git merge-base --is-ancestor "$REMOTE/$prev" "$REMOTE/$b" 2>/dev/null; then
      echo "Stack not linear: $prev is not an ancestor of $b" >&2
      echo "Each step branch must contain the previous step's tip." >&2
      exit 1
    fi
  fi
done

echo "Creating $n-PR stack (ready for review, not draft)"
echo "  base: $BASE_REF"
for ((i = 0; i < n; i++)); do
  parent="$BASE_REF"
  [[ "$i" -gt 0 ]] && parent="${BRANCHES[$i - 1]}"
  echo "  $((i + 1)). ${BRANCHES[$i]} -> $parent  --  ${TITLES[$i]}"
done
echo

CREATED_URLS=()

for ((i = 0; i < n; i++)); do
  branch="${BRANCHES[$i]}"
  title="${TITLES[$i]}"
  body="${BODIES[$i]}"
  parent="$BASE_REF"
  [[ "$i" -gt 0 ]] && parent="${BRANCHES[$i - 1]}"

  stack_note="## Stack"$'\n'
  for ((j = 0; j < n; j++)); do
    marker=" "
    [[ "$j" -eq "$i" ]] && marker="*"
    p="$BASE_REF"
    [[ "$j" -gt 0 ]] && p="${BRANCHES[$j - 1]}"
    stack_note+="${marker} $((j + 1)). \`${BRANCHES[$j]}\` -> \`${p}\` -- ${TITLES[$j]}"$'\n'
  done
  stack_note+=$'\n'
  stack_note+="Merge bottom-up. Delete each merged head (or \`gh pr edit <next> --base ${BASE_REF}\`) so the next PR retargets onto \`${BASE_REF}\`, not a dead feature branch."$'\n'

  if [[ -n "$body" ]]; then
    full_body="${body}"$'\n\n'"${stack_note}"
  else
    full_body="${stack_note}"
  fi

  existing=""
  if [[ "$DRY_RUN" -eq 0 ]]; then
    if [[ ${#GH_REPO_ARGS[@]} -gt 0 ]]; then
      existing=$(gh pr list "${GH_REPO_ARGS[@]}" --head "$branch" --state open --json number --jq '.[0].number // empty' 2>/dev/null || true)
    else
      existing=$(gh pr list --head "$branch" --state open --json number --jq '.[0].number // empty' 2>/dev/null || true)
    fi
  fi

  if [[ -n "$existing" ]]; then
    echo "Updating existing PR #${existing} for ${branch} (base -> ${parent})"
    gh_cmd pr edit "$existing" --base "$parent" --title "$title" --body "$full_body"
    gh_cmd pr ready "$existing" >/dev/null 2>&1 || true
    if [[ "$DRY_RUN" -eq 0 ]]; then
      if [[ ${#GH_REPO_ARGS[@]} -gt 0 ]]; then
        url=$(gh pr view "$existing" "${GH_REPO_ARGS[@]}" --json url --jq .url)
      else
        url=$(gh pr view "$existing" --json url --jq .url)
      fi
    else
      url="(dry-run PR #${existing})"
    fi
  else
    echo "Creating PR: ${branch} -> ${parent}"
    # Intentionally no --draft: PRs are open/ready when created.
    if [[ "$DRY_RUN" -eq 1 ]]; then
      gh_cmd pr create --base "$parent" --head "$branch" --title "$title" --body "$full_body"
      url="(dry-run)"
    else
      if [[ ${#GH_REPO_ARGS[@]} -gt 0 ]]; then
        url=$(gh pr create "${GH_REPO_ARGS[@]}" --base "$parent" --head "$branch" --title "$title" --body "$full_body")
      else
        url=$(gh pr create --base "$parent" --head "$branch" --title "$title" --body "$full_body")
      fi
    fi
  fi
  CREATED_URLS+=("$url")
done

echo
echo "Stack ready:"
for ((i = 0; i < n; i++)); do
  echo "  $((i + 1)). ${CREATED_URLS[$i]}"
done
