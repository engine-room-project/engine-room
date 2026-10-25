#!/bin/sh
# Branch guard: refuse commits on the default branch. POSIX sh (lefthook runs `run:` via Git's
# bundled sh). Kept as a separate LF-only script so Windows CRLF / PowerShell quoting cannot break it.
# git symbolic-ref works on an unborn HEAD (before the first commit); git rev-parse HEAD would not.
branch=$(git symbolic-ref --short -q HEAD || echo HEAD)
configured=$(git config --get governance.defaultBranch 2>/dev/null || true)
remote_default=$(git symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')
if [ "$branch" = "main" ] || [ "$branch" = "master" ] || \
   { [ -n "$configured" ] && [ "$branch" = "$configured" ]; } || \
   { [ -n "$remote_default" ] && [ "$branch" = "$remote_default" ]; }; then
  echo "Refused: commit on $branch. Branch first: git switch -c <type>/<short-desc>"
  exit 1
fi
