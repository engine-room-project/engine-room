# Engine Room product brief

## Problem and outcome

Remote GPU inference is difficult to set up and can leave users paying for resources
that are no longer useful. Engine Room provides one Windows interface for connecting
coding tools to a privately reachable model, with explicit costs, resource ownership,
shutdown protection and recovery.

The release outcome is a reproducible source package that a new Windows user can
install with their own accounts and configuration. Both Colab and RunPod connectors
must pass the release gates before the candidate is ready for publication approval.

## Users and platform

Windows 11 users running supported coding tools. A local GPU is unnecessary.
Provider accounts, model access and private-network permissions belong to the user.
Prerequisite versions and supported combinations must be checked before paid allocation.

## Scope

- Provider-independent workflow, starting with no provider or account configured.
- Optional connectors add named, explicitly authenticated connections.
- First connectors: Colab and RunPod; another connector requires no central workflow edit.
- Distinct managed rental and existing-machine attachment lifecycles.
- Private model access, pinned model revisions and storage-aware planning.
- Compatible untested models are experimental, with clear limitations.
- Isolated coding-tool configuration, durable recovery and source-based packaging.

New model engines, public inference hosting and unsolicited changes to unrelated
resources or existing machines are outside this release.

## Security, privacy and costs

Never borrow credentials from another application or publish local state, personal
identifiers, private addresses or device-specific configuration. Credentials are
explicit per connection and excluded from arguments, logs, packages and history.
No managed rental starts without verified shutdown protection effective from allocation
and independent of the controlling computer. Off requires provider confirmation in
the verified owning account. Uncertain results remain recoverable and visible.
Persistent storage billing is separate from compute; estimates are not hard spend caps.
Attached machines are never terminated without separate explicit authority.

## Implementation constraints

Preserve the Windows PowerShell interface and reusable Python/shell model execution
where practical. Extract provider boundaries instead of rewriting working inference.
Dependencies and remote artifacts need immutable versions and verification evidence.
Preserve third-party notices. The owner selected MIT for Engine Room code; upstream licences remain separate.
No telemetry or additional credential delegation is introduced by assumption.

## Success criteria

- Zero-provider first start and independent connector onboarding succeed.
- Both initial connectors pass allocation, setup, operation and recovery tests.
- All 22 inherited readiness findings have evidence-backed dispositions.
- Tests cover ownership, account changes, ambiguous requests and interrupted records.
- Pricing and storage checks happen before confirmation and allocation.
- Actual source package passes privacy inspection and clean-environment installation.
- Independent accounts/configuration, provider state and billing are validated separately
  from mocks. Paid runs require an approved concrete budget.
- Final code is independently reviewed at the exact submitted state.
- Owner governance ratification and publication approval remain explicit; MIT is selected.

## Risks and decisions

Provider allocation APIs may lack enforceable deadlines. A separate controller could
be necessary and requires an owner-approved hosting and credential boundary.
Provider stock, model compatibility and billing differ from offline simulations.
Independent account validation needs real isolated accounts, not renamed mock identities.
This repository is an unpublished bootstrap proposal until governance is ratified.
