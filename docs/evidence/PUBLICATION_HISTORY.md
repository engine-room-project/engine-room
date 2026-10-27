# Proposed publication history inspection

No product source has been pushed. The owner selected MIT and approved public repository visibility;
the owner-only maintainer team and active main ruleset exist. Governance ratification, live
acceptance and final owner publication approval remain open. Exact code review passed at
80ea9de; subsequent behavior changes require renewed coverage. This report
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

## Initial remote governance proposal

Only the minimal ignore-file base and a separate governance proposal were uploaded.
The public proposal is https://github.com/engine-room-project/engine-room/pull/1,
head2090bbe42700fb6a13de6b1c201b88f44c736636, base4e7c0b191ca55ce849b0bcb0673c0bf2ea5ff357.
It contains no product files or preserved development history. The proposal keeps bootstrap
checks appropriate to this governance-only state while adding Windows validation and the
quoted hook fix. All three reachable commits/31 unique blobs passed neutral metadata and
known-private-pattern inspection; Gitleaks found no leaks in62.85KB.

Independent review qualitatively passed the exact governance proposal. The configured
review classifier refused the empty policy base; no override or manufactured status was
used. Raw binary/full-index diff SHA-256 is
65eaa640e90f65c3f09335837e7e47a9fbeeedc7ab5d83380f9fe3d40b9d2ed6;
this is not a configured review digest. Remote run40489075847 completed successfully:
governance invariants, secrets, Actions security, Linux and Windows bootstrap checks.
The base-target exact-head Review Gate cannot run before its policy/workflow is ratified.

GitHub selected the minimal bootstrap branch as the initial default. Protected main is
still unborn; its active no-bypass ruleset is unchanged. Only the human owner may ratify
or merge governance. Initial main establishment and remote enforcement verification remain
separate required steps; no control exception, product upload or release is implied.

The owner subsequently ratified the exact PR1 governance content at2090bbe. This resolves
content approval only. The owner-controlled merge and protected-main bootstrap remain
pending; no agent merge or protection exception follows from that ratification.

Complete Windows checks at the product-import state passed525 tests (439 passed,86 skipped)
and17 planning checks. The same product code in the actual installed source package passed
525 Linux tests (518 passed,7 skipped). See SOURCE_PACKAGE_ACCEPTANCE.md for exact artifact
revisions/hashes and the distinction between same-machine automated and live evidence.
