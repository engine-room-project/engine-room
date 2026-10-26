# Windows desktop candidate

`powershell.exe -NoProfile -STA -File EngineRoom.ps1` opens the source-checkout candidate.
Opening it never rents a machine. This is not yet an installer or accepted release package.
Fresh state has no provider, trusted controller or selected connection.

## Controller and connections

The window checks Python3.12+ and OpenSSH without network access or creating first-run
state. Controller enrollment requires an explicit private address, dedicated account and
identity file, separately verified host key and controller/host identities. Physical
independence is confirmed explicitly; host IDs alone do not prove separate power.
Temporary trust verifies the controller before saving. Existing enrollment is preserved.
Provider credentials are entered directly on the independent controller; this window
accepts only explicitly saved references. It never imports ambient accounts or credentials.

Named connections use installed connectors' declarative forms. Labels are plain text,
not executable markup. No connector or connection is selected automatically. Partial
selection forms can refresh available offers while preserving entered values. Rental
capability comes from connector descriptors, with no provider-ID branch in navigation.
Existing-machine attachment is a separate workflow and remains unfinished.

## Model and offer planning

Read-only model discovery verifies the named provider account and uses only its saved
HF credential reference. Public discovery reads no credential. It resolves/refetches
immutable revision metadata and inert config JSON with bounded size/time/redirects.
Redirects must remain on the same HTTPS origin and preserve the exact SHA path segment.
No model code executes and no weights download during discovery. Returned data excludes
raw cards/author fields. GGUF base configuration can resolve to a separate pinned revision.

The fixed local PowerShell planner reuses models.ps1 for both formats. Complete GGUF
variants have no default; conversation capacity is explicit and bounded by native context.
Published precision is preserved. Untested models and unknown tool families are labelled
experimental; unsupported metadata layouts fail validation rather than inventing a fit.
The worker has bounded JSON IO and an independent35second process deadline; individual
filename validators have10second deadlines. It uses no credentials or network.

A fresh offer displays the account, hourly unit/scope, balance, uncertain rate/availability
and separate storage charges. Account-total readings are distinct from a rental price.
The shared capacity planner is used by both desktop submission and the controller.
Known insufficient GPU/storage or missing memory estimates refuse before allocation.
RunPod market memory is confirmation-bound. Colab explicitly requires actual GPU/disk
checks before installation because advance capacity is unknown. Both connectors already
probe actual hardware during setup. Required storage includes every file, largest-file
staging, installation reserve and filesystem headroom, without unverified cache credit.

## Explicit confirmation and session lifecycle

The confirmation page freezes the reviewed connection, selection, pinned plan and quote.
It repeats model/experimental status, billing scope, unknown advance cost, separate storage,
capacity/deferred checks and independent-controller limitations. Positive finite hourly
rate and whole-number duration1..1440minutes have no defaults. Three unchecked approvals
cover spending, controller availability and experimental/deferred checks. Expired offers,
ceilings below the displayed rate, missing approvals and repeated clicks refuse locally.
Changed offers also fail controller confirmation checks. Each reviewed page submits once.

The persistent UI-owned helper rechecks healthy independent protection, original account,
fresh quote and model capacity before flushing a durable intent and making one request.
Lost replies are not automatically replayed. Controller request journals and durable start
denials cover delayed submission/cancellation. Preserve desktop and controller records.
An account rate ceiling is a shutdown trigger, not a provider-enforced spending cap.
Controller/provider outages may delay shutdown and billing even after desktop loss.

Only the live WPF dispatcher sends15second pulses. A60second dispatcher gap closes the
helper instead of reviving expired liveness. Slow RPC cannot hide EOF or pulse loss from
the helper's separate input reader. Stop/window close stops renewal and requests scoped
cancellation/recovery. Bounded queues keep pipe IO off the UI thread. The helper has a
confirmed-duration watchdog and bounded close grace; killing it never proves provider-off.
The UI shows off only for an off receipt plus a boolean provider-confirmation flag.
Uncertainty and helper exit retain recovery wording. A separate authenticated,
operation-key-scoped session_status reading distinguishes pending allocation, starting,
ready and stopping. Ready requires fresh valid controller health and active authorization;
stale/billing-unknown readings revoke the ready indicator. Reading status never renews a
lease. The host checks returned scope, boolean readiness and sample age before emitting
fixed phase data. The window maps these phases to plain English; readiness never implies
shutdown. The helper now accepts bounded, explicitly confirmed tool_launch requests for OpenCode or
Codex. It deduplicates request IDs, checks live UI/session, fresh readiness and open relay,
then uses the original model plan with child-only tool settings. Relay keys stay inside
the helper and selected child environment; results do not echo keys, addresses or paths.
Existing tools/settings are not terminated or rewritten. Native executable/project-folder
and idle acknowledgement are explicit. The WPF form requires an explicit tool choice, native.exe and project folder, with
unchecked idle/experimental confirmations. Only fresh readiness enables its launch
button; it expires locally after10seconds without another verified snapshot. A matched
request result clears the one pending launch; no automatic retry occurs. The fixed footer
keeps Stop visible outside the scrolling form. Helper exit offers saved-request recovery.
No tool receives provider credentials or changes to normal settings. Reasoning effort is
left at the tool's usual default; optional vision/effort handoff is not claimed.

## Recovery

Recovery is available from startup and named connections. Its bounded read-only local
index creates no directories and contacts no provider. Damaged records are preserved and
counted without echoing content. Saved off records are history, not a fresh provider check.
Pending requests allow status checks or a separate unchecked cancellation confirmation.
Both use the original saved controller/client enrollment and scoped Rental recovery.
A mismatched account, receipt, limits or missing proof refuses without replay. Active
session helpers block separate recovery actions until finished. Cancellation before
submission is distinct from provider-confirmed shutdown. Unrelated resources are untouched.

## Transport and validation evidence

The one-shot desktop_bridge reads one bounded strict JSON request from stdin and writes
one bounded response. Duplicate keys/extra frames/unknown commands refuse with fixed
errors; input and raw exceptions are not echoed. No request becomes a shell command.
Direct one-shot rental/lease/stream/cancel commands are refused. The persistent session
host accepts a confirmed begin followed only by pulse/stop frames. Source paths/modules
are fixed; SSH uses pinned trust and explicit configuration.

Automated tests use synthetic provider/controller records and actual OS pipes, Windows5.1
child processes and native WPF events. They cover stale UI, delayed replies, original-scope
recovery, immutable confirmation, limits, explicit credentials and planning checks. A free
anonymous metadata/config check resolved HuggingFaceTB/SmolLM2-135M-Instruct at
12fd25f77366fa6b3b4b768ec3050bf629380bac (25files,8192context). This is metadata evidence
only. A synthetic off-screen first-run render was inspected; it is not live acceptance.

Real controller enrollment, independent accounts, gated access, provider allocation,
hardware/inference, shutdown/billing failure scenarios, tool handoff, accessibility and
clean-package installation remain release gates. No paid resources were used for these
implementation checks. Owner budget/deployment/credential/governance/licence/publication
boundaries remain in force. This candidate is not ready for public publication.
