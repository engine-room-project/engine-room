# Existing-machine attachment implementation contract

Status: implementation plan, not a supported connector or live validation claim.
The current release still needs this workflow. It must not reuse managed-rental cleanup.

## Initial supported combination

Add an optional SSH connector with attachment capability only. Connect to an existing
private-network machine whose owner has already configured SSH and an OpenAI-compatible
model API on remote loopback. The model API must not require an additional HTTP credential
in this initial combination; SSH authenticates and encrypts the connection. Other endpoint
or authentication combinations require explicit implementation and validation.

Engine Room never installs software, writes remote files, starts/stops the model, provisions
resources, changes network policy or runs a remote shell command for attachment. It makes
only an explicitly selected SSH forward and read-only model API checks. The machine may
still incur externally managed costs; disconnecting does not stop those costs or compute.

## Explicit configuration and identity

The named connection requires private IP, SSH port/account, separately verified Ed25519
host key, remote loopback model port and selected model identity. No host/account/key/
model defaults or ambient SSH configuration/agent are used. The owner prepares the target
account and authorized key outside Engine Room. No server deployment is implied.

Use an explicitly saved credential reference containing the controller-side path to a
dedicated existing private identity file. The current credential store intentionally
rejects multiline secrets; do not weaken it to import a private key. Require an absolute,
owner-only regular key file, no links, and noninteractive authentication. Do not copy,
rewrite, chmod or borrow another application's identity. Passphrase/agent fallback is not
silently enabled. Real credential setup remains separately owner-controlled.

Bind account identity to the configured SSH principal, pinned host key and selected public
identity. A changed key/host/account must not authorize recovery of an old connection.
A local endpoint/resource scope is not proof of ownership of the existing machine.

## Lifecycle boundaries

Record mode=attachment with no rental deadline, price promise or protection receipt.
Persist a scoped connection intent before opening the local forward. Existing Receipt
validation forbids off for attachments; Receipt.unresolved is rental-only, so managed
recovery and deadline monitoring already skip them. Retain and test these distinctions.
Explicit disconnect uses Recovery.disconnect_attachment, never cancel/terminate.

The connector's terminate method always refuses. The controller must reject rental
requests for this descriptor and reject cancellation of attachment receipts. Separate
attach/disconnect RPC and UI actions are required; do not make a connector-specific core
branch. Model access checks attachment scope independently of rental shutdown protection.
Enrollment and pinned controller trust still authenticate desktop access.

The forward binds a new private operation-owned Unix socket on the controller, with no
unlink/adoption of existing paths. Preserve the private endpoint device/inode/UID/peer-PID
checks. Forward only the selected remote loopback model port using ssh -N; no agent,
user/global config, host-key update, local command, shell, SFTP or remote execution.

Close only retained owned forward processes/sockets. A helper must detect parent pipe
loss or bounded liveness expiry so controller loss cannot leave its connection accessible
indefinitely. Never kill a process by an unverified persisted PID. On uncertain restart,
preserve evidence and require scoped reconciliation; never adopt a foreign socket or
claim that the existing machine is off. No local disconnection authorizes machine shutdown.

Desktop attachment sessions relay only this connection, preserve coding-tool settings and
revoke relay access on close/stall/disconnect. The UI says Disconnect, not Stop rental,
and explicitly states that the machine/model and outside billing continue.

## Implementation and acceptance checklist

- Descriptor/form/preflight with explicit identity and no provisioning capability.
- Account/resource-scoped attachment records and attach/disconnect/model-access RPC.
- Read-only authenticated forwarding with owned-process loss/restart cleanup.
- Bounded model-list/API checks and selected-model validation without executing model code.
- Distinct desktop session/input/relay lifecycle, UI wording and isolated tool handoff.
- Tests asserting zero allocation/termination/remote-command calls, including errors,
  changed identity, corrupt records, cancellation, stale UI and controller restart.
- Actual clean-package acceptance against a separately configured independent existing
  machine, proving continued machine/model operation after disconnect and desktop loss.

These gates remain open. Implementing an attachment path does not establish Colab/RunPod
rental acceptance, provider billing correctness or release readiness.

## Identity/argument implementation evidence

engine_room/attachment_identity.py now validates explicit private targets, owner-only
nonlinked key paths and Ed25519 pins, derives the selected public identity noninteractively,
and binds account/resource fingerprints. Its Linux-only argument builder creates new
private local trust and one pinned ssh -N Unix-to-remote-loopback forward, without starting
it. User/global config, agents, certificates, proxies, multiplexing, host-key updates and
local commands are disabled. Existing key modes, trust files and socket paths are preserved.

Five synthetic tests cover key/target changes, private-file refusal and exact arguments.
A real Linux ssh -G parser check accepts the arguments without connecting or binding a
socket. This is not SSH authentication/forwarding acceptance. The forward supervisor candidate now exists; connector registration, attachment
controller/session lifecycle and desktop flow remain unimplemented.

## Owned forward supervisor candidate

attachment_forward.ForwardSupervisor validates attachment principal/resource scope,
writes a durable start intent, and retains only its newly spawned child. A strict local
pulse/stop pipe closes it on EOF, malformed input, startup timeout or liveness expiry.
Readiness requires a private Unix socket with verified device/inode/UID and matching child
peer PID. Close removes only that verified socket instance and retains changed/unknown
paths. Existing forward evidence is neither overwritten nor adopted; no persisted PID is
used to kill a process. Closed results always state shutdown_confirmed=false.

A fixed single-thread child shim sets Linux parent-death SIGKILL, checks the original
supervisor before exec, and refuses setuid/setgid/capability-bearing executables that could
clear the protection. It avoids Python preexec_fn in a threaded parent. See the
[Linux parent-death signal contract](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html).
Its control pipe must remain exclusive to its owning parent; future connection/session
integration must not manufacture liveness after desktop loss.

Local Linux integration tests use an isolated fake ssh executable that resolves to Python
and serves a temporary Unix socket. They prove EOF, explicit stop, liveness expiry,
supervisor-loss child death, preserved replacement socket and preserved old evidence.
They do not authenticate to or modify any real existing machine. Actual OpenSSH transport,
model checks, independent-machine continuation and clean-package acceptance remain open.

## Parent control candidate

attachment_client.ForwardClient launches a fixed isolated Python helper and passes only
the operation ID/key. The helper bounds the first frame and loads the original active
attachment receipt, saved connection and explicit credential reference from private state.
Detached/cancelled or changed-account records refuse before credential access. IPC cannot
replace settings, paths or credential references. Startup checks the returned endpoint's
scope/resource and actual private socket again before accepting readiness.

Only explicit pulse calls renew forward access; there is no automatic pulse thread.
Writes are nonblocking after startup. Close sends stop/EOF and waits within a bounded
grace period, ending only its retained helper if needed. Killing that helper never proves
disconnect: only its closed acknowledgement can confirm local disconnection. Unknown
socket/evidence paths stay preserved. This never reports machine shutdown.

Local helper-process tests use saved synthetic records and an injected fake identity/SSH
socket child. They cover successful scoped startup/close, no replay, account changes,
detached receipt refusal, untrusted start fields, no implicit liveness and helper-loss
uncertainty. SSH authentication and the complete registered connector/controller/desktop
attachment workflow remain release gates, not established by these tests.

## Internal attachment connector candidate

engine_room_connectors._ssh_attachment.SSHAttachment now declares attachment capability
only. Its explicit form has no rental offer/defaults. Preflight verifies the selected key
and configured identity locally; real SSH authentication happens during connection. One
retained ForwardClient attempt checks only a bounded read-only /v1/models response for
the exact selected model. Failed model verification closes local access and never starts
software, provisions or terminates resources. Renting, setup and termination always refuse.

Explicit pulses recheck principal/resource identity; a changed principal revokes the owned
forward. Local disconnect needs matching original saved scope rather than access to a
rotated private key. It accepts only the retained helper's confirmation or matching private
durable closed proof; uncertain restart state remains preserved, without PID adoption or
machine-off claims. Existing external billing remains outside this connection lifecycle.

Seven synthetic connector tests cover mode/form, selected-model checks, replay refusal,
failed model cleanup, changed principal/receipt, local key-independent disconnect and
Linux closed-proof recovery. The module remains internal and undiscovered: core attach/
disconnect/model-access handling and the separate desktop lifecycle are not finished.
Before enabling attachment model relay, bind POST model selection to the selected existing
model so a coding tool cannot silently choose another served model. Existing rental relay
and rental deadline/heartbeat paths must remain unchanged.
