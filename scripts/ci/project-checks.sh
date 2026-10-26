#!/bin/sh
# Free checks only: syntax, governance, and synthetic lifecycle tests; no provider calls.
set -eu
sh scripts/ci/validate-governance.sh
for path in scripts/ci/*.sh scripts/hooks/*.sh remote/*.sh; do
  bash -n "$path"
done
py=python3
"$py" -c "" 2>/dev/null || py=python
"$py" - <<'PY'
import json
from pathlib import Path
for path in (Path('.governance/policy.json'), Path('.github/governance-profile.json')):
    json.loads(path.read_text(encoding='utf-8'))
for name in ('AGENTS.md', 'REPO_RULES.md', 'PRD.md'):
    text = Path(name).read_text(encoding='utf-8')
    assert '<PLACEHOLDER>' not in text, name
    assert '<Project-specific hard constraints.>' not in text, name
import ast
for folder in ('engine_room', 'engine_room_connectors', 'tests'):
    for path in Path(folder).rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), str(path))
print('Source syntax, JSON and project brief checks passed.')
PY

"$py" -m unittest discover -s tests -v

ps=$(command -v pwsh || command -v powershell.exe || true)
[ -n "$ps" ] || { echo "PowerShell is required to verify the Windows model planner." >&2; exit 2; }
"$ps" -NoProfile -Command '
  $bad = 0
  Get-ChildItem -Path . -Filter *.ps1 -Recurse | Where-Object { $_.FullName -notmatch "[\\/]\.git[\\/]" } | ForEach-Object {
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$errors)
    if ($errors) { $bad = 1; $errors | ForEach-Object { Write-Error $_.Message } }
  }
  exit $bad'
"$ps" -NoProfile -File tests/test-model-planning.ps1
