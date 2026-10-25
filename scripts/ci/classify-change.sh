#!/bin/sh
# Deterministically classify a branch diff. Governance is always substantive; prose is exempt
# by file type, never by directory name.
set -eu
# jq -b: Windows jq.exe ends lines with CRLF otherwise, so read values carry a hidden CR
# and comparisons fail. -b is accepted, and a no-op, on Linux/macOS jq.
# Only wrap a real jq: an unconditional function would make the later `command -v jq` check
# find the function and pass even when jq is missing.
if command -v jq >/dev/null 2>&1; then jq() { command jq -b "$@"; }; fi

base=${1:-}
head=${2:-HEAD}

if [ -z "$base" ]; then
  for ref in origin/main origin/master main master; do
    if git rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
      base=$(git merge-base "$head" "$ref")
      break
    fi
  done
fi

[ -n "$base" ] || {
  echo "Unable to determine the default-branch base; classification fails closed." >&2
  exit 2
}

command -v jq >/dev/null 2>&1 || {
  echo "jq is required to classify changes from the canonical governance policy." >&2
  exit 2
}

# The canonical policy is read from the BASE commit, never the working tree or head. Reading
# head/working-tree content here would let a single branch redefine which paths require review
# and use that redefinition to classify its own change -- exactly the drift this consolidation
# exists to close. GOVERNANCE_POLICY_PATH is an explicit operator/test override chosen by the
# invoker, not derived from the diff being classified, so it does not carry that risk.
policy_override=${GOVERNANCE_POLICY_PATH:-}
if [ -n "$policy_override" ]; then
  [ -f "$policy_override" ] || {
    echo "Canonical governance policy not found: $policy_override" >&2
    exit 2
  }
  policy_json=$(cat "$policy_override")
elif git cat-file -e "$base:.governance/policy.json" 2>/dev/null; then
  policy_json=$(git show "$base:.governance/policy.json")
elif git cat-file -e "$base:governance-policy.template.json" 2>/dev/null; then
  policy_json=$(git show "$base:governance-policy.template.json")
else
  echo "Canonical governance policy not found at base $base (.governance/policy.json or governance-policy.template.json)." >&2
  exit 2
fi

printf '%s' "$policy_json" | jq -e '.trustRootPaths | type == "array" and length > 0 and all(.[]; type == "string" and length > 0 and (test("[\\r\\n]") | not))' >/dev/null || {
  echo "Canonical governance policy has an invalid trustRootPaths list." >&2
  exit 2
}
trust_root_patterns=$(printf '%s' "$policy_json" | jq -r '.trustRootPaths[]')

is_trust_root() {
  path=$1
  while IFS= read -r pattern; do
    case "$path" in
      $pattern) return 0 ;;
    esac
  done <<EOF
$trust_root_patterns
EOF
  return 1
}

is_prose() {
  is_trust_root "$1" && return 1
  case "$1" in
    *.md|*.markdown|*.txt|*.rst|*.adoc|WORKLOG|CHANGELOG|CHANGES|NOTICE|LICENCE|LICENSE|AUTHORS|CONTRIBUTORS|README) return 0 ;;
    *) return 1 ;;
  esac
}

git -c core.quotePath=false diff --name-only "$base" "$head" | while IFS= read -r path; do
  [ -n "$path" ] || continue
  if ! is_prose "$path"; then
    printf '%s\n' "$path"
  fi
done
