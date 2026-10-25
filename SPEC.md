# Public release implementation specification

Status: proposed bootstrap, no product import. PRD.md defines the complete outcome.

## Sequence

1. Commit neutral governance and brief before importing product code.
2. Inspect candidate source and third-party provenance; import only sanitized allowlisted
   files, with fresh history and no local state. Verify Git metadata before first push.
3. Extract optional Colab and RunPod connectors behind a stable registry and lifecycle
   contract; keep the WPF interface and shared model execution. First start has no provider.
4. Establish verified shutdown protection from allocation onward, independent of desktop
   availability. Do not enable rental without proof. Any hosting/credential expansion
   requires the owner's concrete decision before deployment or credential transfer.
5. Resolve all inherited findings through implementation, relevant tests and evidence.
6. Build and inspect the source package; validate that package in clean independent
   configuration/accounts. Live provider and billing tests need a concrete approved budget.
7. Freeze, run final checks and independently review the exact candidate code state.
8. Prepare reviewed PRs and owner decisions on governance, licence and publication.

## Boundaries

No paid rentals, final licence selection, release publication, shared deployment or
expanded credential access without explicit authority. Do not alter unrelated resources
or terminate attached machines. Preserve ordinary coding-tool settings and required notices.

## Evidence

Maintain a neutral finding ledger for R1-R10, A1-A7 and B1-B5, linking implementing
revisions, tests and closure evidence. Retain distinctions between unit/mock checks,
clean-package installation, independent accounts and actual provider/billing validation.
No release readiness claim until both connectors and all required gates pass.
