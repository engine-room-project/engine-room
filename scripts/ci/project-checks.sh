#!/bin/sh
# Bootstrap checks. Product tests are added with product import before release.
set -eu
sh scripts/ci/validate-governance.sh
for path in scripts/ci/*.sh scripts/hooks/*.sh; do
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
print('Bootstrap syntax, JSON and project brief checks passed; no product tests yet.')
PY
