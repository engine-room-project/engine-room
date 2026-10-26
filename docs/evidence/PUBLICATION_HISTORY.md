# Proposed publication history inspection

No source has been pushed. Governance/team ratification, the project licence, live acceptance,
exact final independent review and final owner publication approval remain open. This report
is evidence for the inspected branch, not an authorization to publish.

The proposed codex/release-candidate branch retains these four foundation/import commits:

1. 4e7c0b1: exclude credentials and local runtime state.
2. d017cc7: neutral governance and project brief, before product code.
3. 8bc26e1: proposed Windows/Linux validation controls and quoted hook arguments.
4. 1ae554ea86aa940d5b5e9fd085c3999162ec7af1: one inspected product snapshot.

The product-import tree exactly matches the inspected development snapshot at00d8bda.
The preceding local development history is preserved on its existing local branch and is
not an ancestor of the proposed publication branch. Never push all refs or development
branches by default. No shared history was rewritten and no owner-controlled changes merged.

All author and committer identities in these four commits are Engine Room Contributors
with the neutral contributors@engine-room.invalid address. Gitleaks scanned only the four
reachable publication commits (1.81 MB), finding no secrets. Every reachable tree and the
commit metadata were scanned for known personal identifiers/private-network names and
private usage/resumption-state markers, with no matches. Required upstream notices retain
their original attribution. These scoped scans do not prove the absence of every possible
private identifier; final source/history/package inspection remains a release gate.

The linked worktree exposed an unquoted commit-message pathname in the governance hook.
Double quoting still failed under the Windows shell launcher. The single-quoted placeholder
passed the actual linked-worktree path and normal commits. This is a control-file proposal,
subject to owner ratification; no hooks, scans or checks were disabled or bypassed.

Complete Windows checks at the product-import state passed525 tests (439 passed,86 skipped)
and17 planning checks. The same product code in the actual installed source package passed
525 Linux tests (518 passed,7 skipped). See SOURCE_PACKAGE_ACCEPTANCE.md for exact artifact
revisions/hashes and the distinction between same-machine automated and live evidence.
