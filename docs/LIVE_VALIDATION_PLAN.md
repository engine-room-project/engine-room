# Live validation proposal for owner review

The candidate has same-machine package, Windows/Linux automated and source/history scan
evidence. It has not passed real independent-account, GPU, shutdown or billing acceptance.
This proposal grants no deployment, credentials, paid rental, governance merge or publication
permission. The approved independent-controller design remains unchanged.

## Current owner decisions and evidence

The owner approved the existing independent Linux host deployment, and the dedicated
credential-free controller has deployed-host evidence in CONTROLLER_HOST_ACCEPTANCE.md.
Direct provider sign-in is approved but deferred while the owner prepares separate validation
accounts. MIT and public repository visibility are approved; neither grants final release
publication or agent authority to merge governance. Governance-only PR1 is open for owner
ratification, with successful bootstrap CI and an explicit initial base-policy limitation.

The owner authorized using current prepaid provider balances only after fresh authenticated
balance checks and concrete bounded test limits. No purchase, top-up or new subscription is
authorized, and no historical balance or budget can substitute for those current checks.
Independent-account/configuration acceptance remains mandatory. The staged sequence below
still governs uncompleted work; completed approvals must not be requested again.

## Decision 1: independent host and private deployment

Recommended deployment target: an owner-designated existing independently powered Linux
computer, using a new dedicated non-root Engine Room account. A shared host requires explicit
approval for the exact account, service and credential boundary before changes. Do not select
or deploy a commercial host, expose public ingress or modify unrelated applications by default.

Review controller/README.md and the supplied service/forced-command wrapper. The proposed
change is limited to a dedicated source directory, owner-only state, one private Unix socket,
one hardened controller service, and one dedicated desktop SSH public key restricted to the
Engine Room forced command. No TCP application listener, proxy route, public tunnel or
changes to other users' keys/services are needed. A trusted administrator must approve any
account creation, packages or persistent user-service execution across logout.

Before deployment, inspect the designated host read-only for Linux/Python/OpenSSH/systemd
versions, available disk, account/permission isolation and existing service conflicts. Resolve
the actual interpreter path in both service and wrapper. Core/RunPod use the standard library;
optional Colab dependencies require the pinned Python3.12 lock. Check private reachability,
verified Ed25519 host key, forced-command restrictions, negative/mismatched enrollment,
logout/reboot survival, source permissions and bounded RPC. Do not configure provider secrets
or submit resources during this initial host test.

Rollback while no provider operation has been submitted: remove only the new dedicated key,
stop/disable only the new Engine Room service and preserve its inspected state/source for
review. Once a provider operation exists, reconcile it and independently confirm provider
absence before stopping protection or removing state. No unrelated route/service/key is changed.

## Decision 2: independent accounts and explicit credentials

After host validation, the owner supplies separate test accounts/configuration for both
providers and a clean Windows user/VM environment. New accounts, consent and credentials are
owner actions; none is imported from the development archive or another tool's cache.

Enter provider and restricted-model secrets directly on the approved controller using the
interactive commands. Keep credentials out of chat, shell arguments and public evidence.
Verify original account identities, minimal consent, explicit credential references, rotation
and refusal of account substitution. Colab narrower-scope rejection is a blocker, not authority
to broaden grants. Inspect provider read-only identity, current offers/stock, balance and storage
pricing before preparing a paid test proposal. No paid operations are authorized by this stage.

## Decision 3: concrete paid-test budget

Prepare a separate proposal using those fresh authenticated quotes: exact provider/account
alias, GPU/runtime/model, disposable disk, persistent-volume tier/size/location, maximum
concurrency, bounded duration, compute and storage rates, account-wide limits and total
approved monetary/compute-unit ceiling. Include setup time, retry/failure reserve and manual
storage-removal responsibilities. Approval must precede every budget expansion. Historical
test budgets do not apply; no amount is approved in this document.

The first protected rental must already have healthy independent monitoring, receipt-before-
submission evidence and a finite deadline. Never rent first and add protection afterward.
Do not replay an ambiguous request or describe provider outage as confirmed shutdown.

## Acceptance sequence and retained evidence

1. Install the exact inspected package in a clean independent Windows configuration; prove
   empty first run and each connector's separate onboarding, with no ambient account import.
2. Confirm private controller enrollment and service survival independently of the desktop.
3. Under the separately approved budget, test both initial connectors across allocation,
   setup, operation, model/tool inference, stop, desktop loss, setup failure and controller
   restart/recovery. Bound intentional failures and confirm provider state/billing after each.
4. Verify storage capacity, actual installation footprint, exact model/shards/runtime and
   restricted-model credential delivery. Experimental models stay labelled; no safety gate
   is waived. Verify existing coding-tool settings remain unchanged after actual tool use.
5. Test persistent storage creation/lost response/manual identification and continuing fees;
   manually remove only the exact authorized test volume after preserving needed data.
6. Verify an explicitly authorized existing-machine attachment closes access without stopping
   that machine, its model or outside billing. Preserve unrelated resources in all accounts.
7. Retain private account/provider receipts and billing observations, publish only sanitized
   dispositions linked to each of the22 findings, then run final exact-state checks/review.

Final independent code review must cover the exact final code; later behavioral changes
invalidate it. Governance/team ratification and publication remain owner decisions;
MIT is selected for Engine Room code. No gate is closed solely because a synthetic test passed.
