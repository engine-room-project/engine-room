# Costs, shutdown, recovery, updates and removal

## Before spending

Choose a named connection explicitly. Review the exact model revision/files, context,
runtime, GPU, disposable disk and any persistent storage. Experimental model choices remain
available with an experimental label; availability is not a compatibility guarantee.
Storage-aware estimates include reserves, but real installation footprints need measurement.

Review a fresh quote before each rental. RunPod compute, disposable disk and saved storage
have separate cost components. Colab advance GPU price is not established by account-wide
compute-unit totals; the review discloses unknown costs and an explicit account-wide ceiling.
A displayed estimate or application budget is not a provider hard spending cap. Availability,
account balance, setup time and continuing storage fees can change the amount charged.

Persistent Standard storage below 1 TB is a separate explicit creation. Its monthly review
requires creation and continuing-charge approval. Closing the window or stopping compute
does not delete volumes. Premium storage is currently refused when reliable pricing is absent.
Use the provider account to remove an unwanted volume only after verifying identity and
preserving needed data; Engine Room never automatically deletes it.

## Shutdown protection

An independent Linux controller owns managed rental records, submission authority,
deadlines, leases and provider shutdown/recovery. Desktop loss stops lease renewal; the
controller continues cleanup while that host and provider remain available. A failed
controller and an unavailable provider can prevent prompt shutdown; no native provider
allocation-time deadline has been verified. Keep the controller running and retain recovery
records until provider absence is confirmed. No protected controller means no managed start.

Stop requests cleanup; it is not confirmation. Setup failure, interruption and ambiguous
allocation keep durable original-account evidence. Engine Room never reports a rental off
without provider confirmation. A saved off receipt is historical, not a new billing check.
Existing-machine disconnect closes Engine Room's access only. It never stops that machine,
its model or outside billing. Do not use rental cleanup to manage an existing machine.

## Recovery

Use saved-request recovery with the original enrollment and account. Do not delete damaged
records or change accounts to make an error disappear. Lost allocation/storage responses
must be reconciled instead of retried. Name matches are unconfirmed candidates; manual
volume identification requires explicit verification of the exact original-account ID.
A cancellation can forbid a delayed request; a submission already claimed may still finish
and bill. Provider absence of one volume ID does not establish billing closure.

If credentials rotate or a controller is unavailable, preserve state and use the original
provider account's console to inspect the exact owned resource. Obtain explicit authority
before terminating an existing machine. Never delete or modify unrelated resources. Recovery
records and backups contain sensitive information and need owner-only protection.

## Updates

Do not overwrite a running candidate. Stop/recover managed rentals, confirm provider absence,
and preserve uncertain records first. Verify the new source/archive digest and notices,
extract to a separate directory, run its free checks and confirm compatibility with existing
state before switching the shortcut. Preserve the previous source and protected state for
rollback. Do not run two controllers against the same state or two applications against the
same pending operation. No automatic migration or automatic-update guarantee is provided.

## Removal

Close local access, stop/recover each managed rental and verify provider absence. Check
saved storage separately; removing the application does not stop its fees. Preserve pending
and damaged recovery evidence. Revoke dedicated credentials/keys through their owners, then
remove only Engine Room's service/wrapper, shortcut and source directory. Do not stop a shared
SSH server, remove unrelated authorized keys, or alter coding-tool settings.

Windows state defaults to %LOCALAPPDATA%/EngineRoom; Linux defaults to XDG_DATA_HOME/engine-room
or ~/.local/share/engine-room. The controller templates instead use the explicit
~/.local/share/engine-room-controller root. ENGINE_ROOM_DATA_DIR can select a deliberate
isolated desktop test root. Deleting state is a separate explicit action after recovery;
ordinary source removal leaves it available. Coding tools use child-specific overlays and
must preserve normal configuration and existing sessions.
