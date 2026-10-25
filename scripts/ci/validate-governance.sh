#!/bin/sh
# CI consistency checks for an installed governed repository and for this template kit.
set -eu
# jq -b: Windows jq.exe ends lines with CRLF otherwise, so read values carry a hidden CR
# and comparisons fail. -b is accepted, and a no-op, on Linux/macOS jq.
# Only wrap a real jq: an unconditional function would make the later `command -v jq` check
# find the function and pass even when jq is missing.
if command -v jq >/dev/null 2>&1; then jq() { command jq -b "$@"; }; fi

root=$(git rev-parse --show-toplevel)
cd "$root"

required='AGENTS.md
REPO_RULES.md
.governance-version
.governance/policy.json
lefthook.yml
.gitleaks.toml
scripts/hooks/no-commit-on-main.sh
scripts/hooks/check-large-files.sh
scripts/hooks/check-lockfiles.sh
scripts/hooks/check-commit-message.sh
scripts/ci/classify-change.sh
scripts/ci/verify-review.sh
.github/workflows/governance.yml
.github/workflows/review-gate.yml
.github/CODEOWNERS
.github/governance-profile.json'

# The kit stores templates rather than active installed names.
if [ -f governance-manifest.json ] && [ -f AGENTS.template.md ]; then
  required='AGENTS.template.md
REPO_RULES.template.md
governance-manifest.json
governance-policy.template.json
lefthook.template.yml
gitleaks.template.toml
no-commit-on-main.template.sh
check-large-files.template.sh
check-lockfiles.template.sh
check-commit-message.template.sh
scripts/ci/classify-change.template.sh
scripts/ci/verify-review.template.sh'
else
  version=$(tr -d '\r\n ' < .governance-version 2>/dev/null || true)
  case "$version" in 3.*) ;; *) echo "Expected governance generation 3.x, found '$version'." >&2; exit 1 ;; esac
fi

missing=0
printf '%s\n' "$required" | while IFS= read -r path; do
  [ -e "$path" ] || { echo "Missing governance file: $path" >&2; echo 1 > "${TMPDIR:-/tmp}/governance-missing-$$"; }
done
flag="${TMPDIR:-/tmp}/governance-missing-$$"
if [ -f "$flag" ]; then rm -f "$flag"; missing=1; fi
[ "$missing" -eq 0 ] || exit 1

if [ -f governance-manifest.json ] && [ -f AGENTS.template.md ]; then
  command -v jq >/dev/null 2>&1 || { echo "jq is required to validate the kit manifest." >&2; exit 2; }
  command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required to validate the kit manifest." >&2; exit 2; }
  mismatch=0
  manifest_flag="${TMPDIR:-/tmp}/governance-manifest-mismatch-$$"
  jq -c '.files[]' governance-manifest.json | while IFS= read -r entry; do
    template=$(printf '%s' "$entry" | jq -r .template)
    expected=$(printf '%s' "$entry" | jq -r .sha256)
    if [ ! -f "$template" ]; then
      echo "Manifest template missing: $template" >&2
      echo 1 > "$manifest_flag"
      continue
    fi
    actual=$(sed 's/\r$//' "$template" | sha256sum | awk '{print $1}')
    if [ "$actual" != "$expected" ]; then
      echo "Manifest hash is stale for $template" >&2
      echo 1 > "$manifest_flag"
    fi
  done
  if [ -f "$manifest_flag" ]; then rm -f "$manifest_flag"; mismatch=1; fi
  [ "$mismatch" -eq 0 ] || exit 1
fi

if [ -f .github/workflows/governance.yml ]; then
  if grep -Eq 'uses:[[:space:]]+[^#[:space:]]+@(v[0-9]+|main|master)([[:space:]]+#.*)?$' .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null; then
    echo "Workflow action is pinned to a movable ref instead of a commit SHA." >&2
    exit 1
  fi
fi

# One canonical trust-root list (governance-policy.template.json / installed .governance/policy.json)
# drives every enforcement surface. CODEOWNERS and the legacy PowerShell git-guard fallback must
# match it exactly, in both directions, or a path could silently fall out of owner review.
if [ -f governance-manifest.json ] && [ -f AGENTS.template.md ]; then
  trust_policy=governance-policy.template.json
  trust_codeowners=github/CODEOWNERS.template
  trust_fallback=git-guard.template.ps1
else
  trust_policy=.governance/policy.json
  trust_codeowners=.github/CODEOWNERS
  trust_fallback=''
fi

if [ -f "$trust_policy" ]; then
  command -v jq >/dev/null 2>&1 || { echo "jq is required to validate trust-root consistency." >&2; exit 2; }

  if [ -f "$trust_codeowners" ]; then
    expected_codeowners=$(jq -r '.trustRootPaths[] | if endswith("/**") then "/" + .[0:length-2] else "/" + . end' "$trust_policy" | sort -u)
    actual_codeowners=$(grep -Ev '^[[:space:]]*(#|$)' "$trust_codeowners" | awk '{print $1}' | sort -u)
    if [ "$expected_codeowners" != "$actual_codeowners" ]; then
      echo "CODEOWNERS has drifted from the canonical trust-root policy ($trust_policy)." >&2
      echo "Expected:" >&2
      printf '%s\n' "$expected_codeowners" | sed 's/^/  /' >&2
      echo "Actual ($trust_codeowners):" >&2
      printf '%s\n' "$actual_codeowners" | sed 's/^/  /' >&2
      exit 1
    fi
  fi

  if [ -n "$trust_fallback" ] && [ -f "$trust_fallback" ]; then
    fallback_patterns=$(awk '/BEGIN CANONICAL TRUST ROOT FALLBACK/{flag=1;next}/END CANONICAL TRUST ROOT FALLBACK/{flag=0}flag' "$trust_fallback" | grep -Eo "'[^']*'" | tr -d "'" | sort -u)
    [ -n "$fallback_patterns" ] || {
      echo "Could not locate the CANONICAL TRUST ROOT FALLBACK markers in $trust_fallback." >&2
      exit 1
    }
    canonical_patterns=$(jq -r '.trustRootPaths[]' "$trust_policy" | sort -u)
    if [ "$fallback_patterns" != "$canonical_patterns" ]; then
      echo "The legacy PowerShell git-guard fallback trust-root list has drifted from $trust_policy." >&2
      echo "Canonical:" >&2
      printf '%s\n' "$canonical_patterns" | sed 's/^/  /' >&2
      echo "Fallback ($trust_fallback):" >&2
      printf '%s\n' "$fallback_patterns" | sed 's/^/  /' >&2
      exit 1
    fi
  fi

  echo "Trust-root paths are consistent across the canonical policy, CODEOWNERS, and the legacy fallback."
fi

echo "Governance structure and version are consistent."
