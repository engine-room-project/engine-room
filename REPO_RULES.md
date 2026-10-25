# Repository rules — Engine Room

`AGENTS.md` is the concise canonical policy. This document explains the enforcement model,
edge cases, recovery, and platform details. It does not grant an agent additional authority.

## 1. Repository shape and sources of truth

Windows PowerShell presentation and coordination, Python lifecycle/model helpers and
remote shell setup. Optional connectors own provider APIs; core owns the workflow,
account-bound receipts and tool overlays. No product code has been imported yet.

The root `AGENTS.md` controls security, governance, and authority. A nested `AGENTS.md` may
add directory-specific build or style instructions, but it may not weaken a root requirement.
The nearest applicable file wins only when instructions do not conflict with the root trust
boundary.

Agent entry points are adapters:

| Agent | Entry point | Role |
|---|---|---|
| Codex | `AGENTS.md` | Native canonical policy |
| Claude Code | `CLAUDE.md` | Thin import/pointer plus optional ergonomics |
| Gemini / Antigravity | `GEMINI.md` | Thin pointer |
| Cursor | `.cursor/rules/agents.mdc` | Thin pointer |

Do not duplicate policy text into adapters. Agent instructions are advisory; Git hooks, CI,
hosting rules, and human approval are separate controls.

## 2. Four control layers

| Layer | Examples | Enforces | Trust limit |
|---|---|---|---|
| Advisory policy | `AGENTS.md`, this file | Expected behavior and authority | A process can ignore prose |
| Local enforcement | Lefthook, Gitleaks, `scripts/hooks/` | Default-branch commits, secrets, large files, commit format, lockfile warning | A user controlling the workstation can bypass local hooks |
| Remote enforcement | CI and GitHub rulesets/branch protection | Re-runs checks, exact-state review, merge restrictions, force-push/deletion blocks | Availability varies by GitHub plan and repository visibility |
| Human-only | Governance ratification and exceptional risk decisions | Changes to the trust root and agent authority | Requires the named owner; never delegated to an implementation agent |

Controls should live at the lowest practical layer. Agent-specific hooks may make mistakes
harder, but no critical invariant depends only on Claude, Codex, or another agent remembering
instructions.

## 3. Git workflow

- Work on a branch named `<type>/<short-description>`; never commit or push directly to the
  protected default branch.
- Keep one cohesive deliverable per branch. Include required tests, documentation, and small
  supporting refactors; defer unrelated work.
- Use Conventional Commits. The `commit-msg` hook checks the subject.
- Never force-push a protected branch or use an administrative merge bypass.
- Push finished work to the authoritative remote and all declared mirrors. If histories
  diverge, stop rather than discarding either side.
- Open a PR containing the outcome, reason, exact test evidence, migrations, and limitations.
  Merge only when required checks and review are current and green.

### Authority ceiling

The paths listed in `.governance/policy.json` are the trust root. They include canonical policy,
local hooks, scanner configuration, governance metadata/updaters, CI workflows, agent permission
configuration, remote-policy configuration, and review-verification logic.

An agent may edit those files on a branch and open a PR. It may not approve or merge that PR.
Remote CODEOWNERS/ruleset protection is the primary enforcement. Optional agent hooks are only
secondary defense. If the hosting plan cannot enforce code-owner review, the fallback is a
protected branch requiring a human approval and a documented manual check of trust-root paths.
There is no automatic ratification path.

## 4. Local gates

Install with `lefthook install`. The default hooks are POSIX shell with LF line endings so they
run on Linux and in Git for Windows:

- `no-commit-on-main.sh` refuses commits on the protected default branch, including an unborn
  first commit.
- `gitleaks protect --staged` refuses staged credentials and redacts findings.
- `check-large-files.sh` refuses newly added files over 2048 KiB unless the repository sets a
  deliberate `governance.maxFileKB` value.
- `check-lockfiles.sh` warns when a lockfile changes without its manifest. It does not block
  legitimate package-manager regeneration.
- `check-commit-message.sh` enforces the supported Conventional Commit subject form.
- configured project lint/test commands run where the project adds them.

Do not use `--no-verify` to escape a failure. Local hooks are not the only trust boundary, so CI
re-runs critical checks after push.

## 5. Secrets, generated files, and large files

Never commit a credential, private key, access token, secret-bearing log, prompt transcript, or
real secret used as a test fixture. Commit an obviously fake example instead. If a real secret
enters history, rotate it first, then remove it from history; removal does not unexpose it.

Ignore dependencies, build output, caches, editor state, local configuration, and downloadable
data. Use Git LFS or external storage for intentionally versioned large assets. Never hand-edit a
generated lockfile: update its manifest and invoke the package manager.

## 6. Independent review

Normal and high-risk behavior changes need a reviewer other than the implementation agent.
Prose-only changes are exempt only when `scripts/ci/classify-change.sh` deterministically finds
no behavior-changing or governance path.

On GitHub, the default mode requires an `APPROVED` review whose `commit_id` equals the current PR
head SHA and whose reviewer is not the PR author. Any later behavior-changing commit changes HEAD
and invalidates the check. Branch/ruleset settings should dismiss stale approvals and require the
last push to be approved by someone else. CI re-checks this immediately before merge.

A repository may opt out entirely by setting `review.requireIndependentReview` to `false` in
`governance-profile.json`. This is meant for solo maintainers or AI-authored work with no second
human available; the reusable template ships this `true` by default. The workflow reads the flag
from the base branch's committed profile, never the pull request's own copy, so a PR cannot flip
it to escape review on itself. The `governance/exact-head-review` status still runs and posts on
every PR while the flag is off, but always succeeds, leaving a visible, auditable record of the
choice rather than silently removing the check.

For hosts without review APIs, `.governance/review-attestation.json` may record a deterministic
code digest. `scripts/ci/verify-review.sh` recomputes it. This proves which bytes were reviewed,
but it is not cryptographically independent: anyone able to write the branch can fabricate the
file. Treat it as evidence, not an external trust boundary. See `docs/security-model.md`.

## 7. Remote enforcement

`github/governance-profile.json` is the desired GitHub state. `github-governance.sh` and
`github-governance.ps1` inspect capabilities and print a plan by default. Mutation requires an
explicit `--apply` / `-Apply` after reviewing that plan.

The preferred GitHub ruleset requires PRs, designated checks, non-author review, code-owner review,
resolved conversations, and linear history; it blocks force pushes and deletion. The fallback is
classic branch protection with the strongest equivalent fields. Rulesets and some review/code-owner
features vary by plan and repository visibility. The tool reports `supported`, `fallback`, or
`manual-required`; it never silently claims a setting exists.

The `governance/exact-head-review` status can optionally be produced by a dedicated, least-
privilege GitHub App instead of the shared Actions identity every other check uses, so a required
check can trust that one producer specifically. This needs a human owner to register the App,
generate its private key, and install it — an agent never performs that setup. See
`docs/security-model.md`.

CI uses read-only permissions unless a job needs more. Third-party actions are pinned to immutable
commits. zizmor statically checks workflow files without requiring GitHub Advanced Security.

## 8. Verification and durable memory

During work, run the smallest check likely to catch the current mistake. Before review and PR,
run the complete relevant suite plus migration/acceptance checks for governance work. Report the
actual command and result.

Update `WORKLOG.md` when work materially advances or leaves durable context. Do not require a log
entry for a typo or add one merely to satisfy automation.

## 9. Installation and updates

Linux/Omarchy:

```sh
./new-governed-repo.sh --target /path/to/project --name "Project name"
./update-governance.sh --target /path/to/project --dry-run
```

Windows PowerShell 5.1+:

```powershell
& "$env:REPO_GOVERNANCE_HOME\new-governed-repo.ps1" -Target C:\path\to\project -Name "Project name"
& "$env:REPO_GOVERNANCE_HOME\update-governance.ps1" -Target C:\path\to\project -DryRun
```

Updaters only replace manifest-owned files that match a known shipped hash. Customized files are
reported and preserved. Replaced files are backed up, dry-run is non-mutating, a second run is a
no-op, and project source is outside the update set. Resolve conflicts deliberately; never use a
force option to erase project customizations.

## 10. Recovery

- Failed update: restore the timestamped `.governance-backup/` copy or use the updater's rollback.
- Diverged mirrors: identify the authoritative history and obtain a human decision; do not force.
- False-positive secret: narrow `.gitleaks.toml` with an exact path/regex and submit that governance
  change for human ratification.
- Incorrect gate: propose a fix with a reproducing test. Do not bypass it to continue other work.
- Missing GitHub capability: retain local/CI checks, apply classic branch protection where possible,
  and document the remaining human-only merge step.

These rules protect repository integrity, review independence, and the ceiling on agent authority.

## Release bootstrap policy proposal

The proposed governance owner is the organization team engine-room-project/maintainers.
The team is not yet verified or created; no remote policy may be applied until the owner
ratifies this proposal and the team exists. This repository is local and unpublished.
GitHub review settings must not require a second account. Independent reviewer-subagent
review is required locally for the final release code, with exact-state evidence recorded
using the configured local attestation mechanism. The hosted exact-head status does not
independently prove that local review occurred when requireIndependentReview is false.
Only the human owner may ratify or merge governance/control changes.
