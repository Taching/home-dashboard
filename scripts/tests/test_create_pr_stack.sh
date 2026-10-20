#!/usr/bin/env bash
# Offline smoke tests for create-pr-stack.sh (--dry-run only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$ROOT/scripts/create-pr-stack.sh"
fail=0

assert_contains() {
  local haystack="$1" needle="$2" label="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "FAIL: $label (missing: $needle)" >&2
    fail=1
  else
    echo "PASS: $label"
  fi
}

assert_not_contains() {
  local haystack="$1" needle="$2" label="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    echo "FAIL: $label (unexpected: $needle)" >&2
    fail=1
  else
    echo "PASS: $label"
  fi
}

out=$("$SCRIPT" --dry-run --base master \
  --step 'b1|feat: one|body one' \
  --step 'b2|feat: two|body two' 2>&1)

assert_contains "$out" "Creating 2-PR stack" "reports stack size"
assert_contains "$out" "b1 -> master" "first PR bases on master"
assert_contains "$out" "b2 -> b1" "second PR bases on first branch"
assert_contains "$out" "gh pr create" "invokes gh pr create"
assert_not_contains "$out" "--draft" "never passes --draft"

# Invalid step should fail
if "$SCRIPT" --dry-run --step 'no-pipes-here' >/dev/null 2>&1; then
  echo "FAIL: invalid step should exit non-zero" >&2
  fail=1
else
  echo "PASS: invalid step rejected"
fi

exit "$fail"
