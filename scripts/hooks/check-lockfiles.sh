#!/bin/sh
# Lockfile sanity check -- WARNS, never blocks.
#
# Why not a block: V1 flatly refused any edit to package-lock.json / poetry.lock / etc.
# That also refused the legitimate case (you added a dependency on purpose and the package
# manager regenerated the lockfile), so real work had to route around the guardrail --
# which is exactly the habit the guardrails exist to prevent.
#
# V2 instead surfaces the one shape that is actually suspicious: the lockfile changed but
# the manifest that is supposed to drive it did not. That is either a hand-edit, a stray
# `npm install` nobody asked for, or a dependency swap smuggled in without a manifest
# change -- all worth a second look, none worth stopping the commit.
#
# POSIX sh, LF-only, no dependencies beyond git.

staged=$(git diff --cached --name-only)
[ -n "$staged" ] || exit 0

flag=$(mktemp) || exit 0

# lockfile : the manifest that legitimately causes it to change
pairs="package-lock.json:package.json
pnpm-lock.yaml:package.json
yarn.lock:package.json
bun.lockb:package.json
poetry.lock:pyproject.toml
uv.lock:pyproject.toml
Pipfile.lock:Pipfile
Cargo.lock:Cargo.toml
go.sum:go.mod
composer.lock:composer.json
Gemfile.lock:Gemfile"

warned=0
# Iterate the known pairs, not the staged filenames -- an arbitrary staged filename must
# never end up inside a pattern.
echo "$pairs" | while IFS=: read -r lock manifest; do
  [ -n "$lock" ] || continue
  if echo "$staged" | grep -qE "(^|/)${lock}$"; then
    if ! echo "$staged" | grep -qE "(^|/)${manifest}$"; then
      echo "Note: '$lock' changed but '$manifest' did not."
      echo 1 > "$flag"
    fi
  fi
done
[ -s "$flag" ] && warned=1
rm -f "$flag"

if [ "$warned" -eq 1 ]; then
  cat <<'ADVICE'

A lockfile normally only moves because its manifest moved. A lockfile-only change means
one of:
  * you ran the package manager and it picked up drift  -- fine, say so in the commit body;
  * a dependency was pinned/bumped by hand              -- do it through the package manager instead;
  * something edited the lockfile directly              -- never do this; regenerate it.

Not blocking. Just make sure the change is one you meant.
ADVICE
fi

exit 0
