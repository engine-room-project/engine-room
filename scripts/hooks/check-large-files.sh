#!/bin/sh
# Large-file gate: refuse to commit a newly ADDED file bigger than the limit.
#
# POSIX sh (lefthook runs `run:` through Git's bundled sh, not PowerShell). Kept LF-only
# by .gitattributes so Windows CRLF cannot break it. No dependencies beyond git.
#
# Limit: 2048 KB by default. Override per repo without editing this file:
#   git config governance.maxFileKB 512      (repo-local, committed by nobody)
# or per invocation:
#   GOVERNANCE_MAX_FILE_KB=512 git commit ...
#
# Only --diff-filter=A (newly added) files are checked. Growing a file that is already
# tracked is a different problem and blocking it would fight normal work.

mode=staged
base=
head=HEAD
if [ "${1:-}" = "--range" ]; then
  [ "$#" -eq 3 ] || { echo "usage: $0 [--range BASE HEAD]" >&2; exit 2; }
  mode=range
  base=$2
  head=$3
fi

max_kb="${GOVERNANCE_MAX_FILE_KB:-}"
if [ -z "$max_kb" ]; then
  max_kb=$(git config --get governance.maxFileKB 2>/dev/null)
fi
case "$max_kb" in
  ''|*[!0-9]*) max_kb=2048 ;;
esac
max_bytes=$((max_kb * 1024))

if [ "$mode" = range ]; then
  if ! staged=$(git diff --name-only --diff-filter=A "$base" "$head"); then
    echo "Refused: unable to inspect added files for range '$base..$head'." >&2
    exit 1
  fi
else
  staged=$(git diff --cached --name-only --diff-filter=A)
fi
[ -n "$staged" ] || exit 0

rc=0
# Read from a here-doc, not a pipe: a pipe runs the loop in a subshell and $rc is lost.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  # Size of the STAGED blob, which is what would actually enter history.
  if [ "$mode" = range ]; then
    size=$(git cat-file -s "$head:$f" 2>/dev/null) || continue
  else
    size=$(git cat-file -s ":$f" 2>/dev/null) || continue
  fi
  case "$size" in ''|*[!0-9]*) continue ;; esac
  if [ "$size" -gt "$max_bytes" ]; then
    echo "Refused: '$f' is $((size / 1024)) KB, over the ${max_kb} KB limit for a new file."
    rc=1
  fi
done <<EOF
$staged
EOF

if [ "$rc" -ne 0 ]; then
  cat <<'ADVICE'

Large files bloat the clone forever -- git keeps every version of them, and removing one
later means rewriting history for everybody.

Do one of these instead:
  * It is generated or downloadable -> add it to .gitignore and unstage it:
      git restore --staged <file>
  * It is real project data that must be versioned -> use Git LFS, or store it outside
    the repo and commit a small pointer/checksum.
  * The limit is genuinely wrong for this project -> raise it deliberately:
      git config governance.maxFileKB <number>
    and say why in the PR. Do not pass --no-verify.
ADVICE
fi

exit $rc
