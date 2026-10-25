#!/bin/sh
# Commit-message gate. The first argument is the path supplied by Git/Lefthook.
set -eu

message_file=${1:-}
[ -n "$message_file" ] && [ -f "$message_file" ] || {
  echo "Refused: commit message file was not supplied."
  exit 1
}

subject=$(sed -n '1p' "$message_file")
case "$subject" in
  Merge\ *|Revert\ \"*) exit 0 ;;
esac

length=$(printf %s "$subject" | wc -c | tr -d ' ')
if [ "$length" -gt 72 ]; then
  echo "Refused: commit subject is $length characters; limit is 72."
  exit 1
fi

if ! printf '%s\n' "$subject" | grep -Eq '^(feat|fix|docs|chore|refactor|test|perf|build|ci|revert)(\([a-z0-9._/-]+\))?!?: [^[:space:]].*$'; then
  echo "Refused: use a Conventional Commit subject, for example 'fix(parser): reject empty input'."
  exit 1
fi

exit 0
