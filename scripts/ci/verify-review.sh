#!/bin/sh
# Verify independent review for the exact behavior-changing state in a branch.
set -eu

mode=${GOVERNANCE_REVIEW_MODE:-}
base=${GOVERNANCE_BASE_SHA:-}
head=${GOVERNANCE_HEAD_SHA:-HEAD}
print_digest=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) mode=$2; shift 2 ;;
    --base) base=$2; shift 2 ;;
    --head) head=$2; shift 2 ;;
    --print-digest) print_digest=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

root=$(git rev-parse --show-toplevel)
classifier="$root/scripts/ci/classify-change.sh"
[ -f "$classifier" ] || { echo "Missing classifier: $classifier" >&2; exit 2; }

if [ -z "$base" ]; then
  for ref in origin/main origin/master main master; do
    if git rev-parse --verify --quiet "$ref" >/dev/null 2>&1; then
      base=$(git merge-base "$head" "$ref")
      break
    fi
  done
fi
[ -n "$base" ] || { echo "Unable to determine review base; refusing." >&2; exit 2; }

tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM
paths="$tmp_dir/substantive-paths"
sh "$classifier" "$base" "$head" > "$paths"

if [ ! -s "$paths" ]; then
  echo "Prose-only change: independent review is not required."
  exit 0
fi

# Bind path, Git mode, and blob/object ID at both endpoints. Prose files and review evidence
# are omitted by the classifier, so a prose-only follow-up does not invalidate reviewed code.
state="$tmp_dir/reviewed-state"
while IFS= read -r path; do
  case "$path" in
    \"*)
      # Git quotes unusual names containing control characters. Hash the entire binary diff
      # instead of risking omission; this is stricter because prose also invalidates review.
      git diff --binary --full-index "$base" "$head" > "$state"
      break
      ;;
  esac
  printf 'path %s\n' "$path" >> "$state"
  printf 'base ' >> "$state"
  git ls-tree "$base" -- "$path" >> "$state" || true
  printf 'head ' >> "$state"
  git ls-tree "$head" -- "$path" >> "$state" || true
done < "$paths"

if command -v sha256sum >/dev/null 2>&1; then
  digest=$(sha256sum "$state" | awk '{print $1}')
elif command -v shasum >/dev/null 2>&1; then
  digest=$(shasum -a 256 "$state" | awk '{print $1}')
else
  echo "No SHA-256 tool found (sha256sum or shasum); refusing." >&2
  exit 2
fi

if [ "$print_digest" = true ]; then
  printf '%s\n' "$digest"
  exit 0
fi

if [ -z "$mode" ] && [ -f "$root/.governance/policy.json" ]; then
  mode=$(sed -n 's/.*"mode"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$root/.governance/policy.json" | sed -n '1p')
fi
mode=${mode:-github-review}

case "$mode" in
  github-review)
    : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required for GitHub review verification}"
    : "${GITHUB_EVENT_NUMBER:?GITHUB_EVENT_NUMBER is required for GitHub review verification}"
    : "${GITHUB_HEAD_SHA:?GITHUB_HEAD_SHA is required for GitHub review verification}"
    : "${GITHUB_PR_AUTHOR:?GITHUB_PR_AUTHOR is required for GitHub review verification}"
    : "${GH_TOKEN:?GH_TOKEN is required for GitHub review verification}"
    command -v gh >/dev/null 2>&1 || { echo "gh is required for GitHub review verification." >&2; exit 2; }
    approved=$(gh api --paginate "repos/$GITHUB_REPOSITORY/pulls/$GITHUB_EVENT_NUMBER/reviews" \
      --jq ".[] | select(.state == \"APPROVED\" and .commit_id == \"$GITHUB_HEAD_SHA\" and .user.login != \"$GITHUB_PR_AUTHOR\") | .user.login" |
      sed -n '1p')
    [ -n "$approved" ] || {
      echo "Refused: no independent APPROVED GitHub review is bound to HEAD $GITHUB_HEAD_SHA." >&2
      exit 1
    }
    echo "Independent GitHub review by $approved is bound to HEAD $GITHUB_HEAD_SHA."
    ;;
  local-attestation)
    receipt="$root/.governance/review-attestation.json"
    [ -f "$receipt" ] || { echo "Refused: missing $receipt." >&2; exit 1; }
    reviewer=$(sed -n 's/.*"reviewer"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$receipt" | sed -n '1p')
    implementer=$(sed -n 's/.*"implementationAgent"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$receipt" | sed -n '1p')
    verdict=$(sed -n 's/.*"verdict"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$receipt" | sed -n '1p')
    recorded=$(sed -n 's/.*"codeDigest"[[:space:]]*:[[:space:]]*"\([0-9a-fA-F]*\)".*/\1/p' "$receipt" | sed -n '1p' | tr 'A-F' 'a-f')
    [ -n "$reviewer" ] && [ -n "$implementer" ] && [ "$reviewer" != "$implementer" ] || {
      echo "Refused: local attestation does not identify an independent reviewer." >&2; exit 1;
    }
    case "$verdict" in PASS|CHANGES_ADDRESSED) ;; *) echo "Refused: invalid review verdict '$verdict'." >&2; exit 1 ;; esac
    [ "$recorded" = "$digest" ] || {
      echo "Refused: reviewed digest does not match current behavior-changing state." >&2
      echo "reviewed=$recorded current=$digest" >&2
      exit 1
    }
    echo "Local review evidence by $reviewer matches code digest $digest."
    echo "Warning: project-local evidence is not cryptographically independent."
    ;;
  *) echo "Unknown review mode '$mode'; refusing." >&2; exit 2 ;;
esac
