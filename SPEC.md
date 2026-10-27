# Public release implementation specification

Status: local implementation in progress; no product source pushed. PRD.md defines the complete outcome.

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


## Current bounded increment: private controller transport

Implement `controller_protocol.py`, `controller_service.py`, `controller_client.py`,
Linux deployment templates under `controller/`, their focused tests and documentation.
Use owner-only local sockets and explicitly pinned private SSH, with no remote shell
or credential-management RPC. Preserve the independent monitor during client failures.
Do not deploy, configure real credentials or claim physical host independence from local tests.
Evidence: actual local socket permissions, protocol refusals, ambiguous response handling,
lease expiry, local daemon crash/restart and offline OpenSSH configuration parsing.
Desktop model forwarding, heartbeat/UI integration, existing-machine connection and Colab
remain following increments; no release gate is reduced by this sequencing.


## Session model transport and desktop leases

Implement operation-scoped streaming in `streaming.py`, `desktop_session.py`, the
controller protocol/service and RunPod's session endpoint. Keep SSH as the authentication
boundary and the connector registry as the sole provider dispatch. Use a per-session
loopback API key, bounded request framing and incremental responses. UI liveness must
bound helper renewal, and local receipt failure must not skip remote cleanup. Preserve
uncertain shutdown state. Test actual local subprocess/socket streaming, scope mismatch,
revocation, UI loss and concurrent Windows receipt reads. WPF/tool integration and actual
SSH/provider acceptance remain required following work, with no deployment or paid tests
in this increment.


## Coding-tool settings preservation

Implement `engine_room/tools.py` and read-only `tools.ps1` discovery, with tests and
neutral documentation. Generate child-only OpenCode inline configuration and Codex
CLI provider overrides; never rewrite normal configuration, profiles, credentials,
permissions or defaults. Preserve existing inline JSONC/provider settings, use a
unique per-launch provider/key namespace, and keep the session key out of arguments
and configuration content. Require a closed single-instance desktop app before launch;
never terminate another application to refresh settings. Native executable launch is
the initial tested path. Script wrappers, other tool protocols, version/preflight checks
and full WPF wiring remain explicit acceptance work. Evidence includes untouched
normal-file bytes, safe malformed-settings refusal, real synthetic child environment,
read-only discovery and actual tool/model/engine acceptance as a later live gate.


## Colab account/API boundary

Inspect/pin official google-colab-cli before extraction. Implement the private
`_colab` API/auth modules with explicit credential references, minimal scoped OAuth,
account-bound snapshots, one allocation POST and durable proof before that POST.
Use per-operation notebook identities; never adopt/delete a pre-existing assignment
or infer off from account-wide assignment counts. Preserve uncertain creation.
Token refresh must not overwrite an explicit credential rotation. Tests use synthetic
transport/credentials only. Runtime/proxy/bootstrap, direct interactive login, complete
connector registration, dependency installation and actual accounts remain separate
following work. Investigate account-wide pricing semantics instead of fabricating a
per-rental quote. No real authentication, allocation or paid probe in this increment.


## Provider-independent billing contract

Replace closed USD/CCU assumptions with safe opaque unit identifiers. Bind live rates
to the confirmed unit and rental/account scope; stop on explicit changes, preserve
bounded unknown-rate recovery and allow verified zero rates. Make prepaid balance
requirements explicit connector policy, with unavailable postpaid balances represented
honestly. No exchange-rate conversion or new live provider claims. Include the billing
helper in the inspected remote payload and test the actual extracted artifact imports.
Evidence: a synthetic third unit/provider runs unchanged core lifecycle, unit/scope
changes stop only owned resources, unknown readings do not become zero, zero readings
remain valid and mismatched quote policy requires confirmation. Actual UI/provider/
billing acceptance stays open.


Colab runtime-access increment: add `_colab/proxy.py`, ownership-gated access in
`_colab/api.py`, synthetic tests and connector documentation. Return only short-lived
runtime-proxy credentials after fresh original-account mapping/listing proof. Reject
unsupported origins, redirects in later transport, unsafe URLs and expired tokens;
never send the Google account token to a runtime. Kernel startup, SSH bridging and
actual GPU bootstrap remain subsequent work. Evidence: hostile response/ownership
fixtures and complete free checks; no real auth or provider resources.


Colab kernel-start increment: `_colab/kernel.py`, focused offline tests and connector
docs. Use only verified runtime-proxy headers and strict kernel REST routes; no account
tokens, environment proxies, redirects or POST retries. Preserve a flushed operation-
bound pre-POST record, baseline existing kernels, reject adopting a baseline kernel,
and retain uncertainty after a lost create response. Require final controller authority
immediately before POST. Subsequent WebSocket execution/bootstrap consumes the owned
kernel record; actual provider compatibility and model serving remain separate gates.

Kernel execution extends this increment with `_colab/channel.py` and exact pinned-
dependency socket-pair tests. Bind execution to the durable owned kernel and refresh
runtime ownership; disable history/input, require correlated reply plus idle, preserve
uncertainty without replay, bound output/frame/message/time and check cancellation.
Use direct verified TLS, no redirect/environment proxy or account-token forwarding.
No actual credentials, real kernels, SSH bootstrap or GPU resources are exercised.


Colab runtime probe increment: standalone `remote/probe.py`, connector-side validation
and credential-free kernel-code generation in `_colab/probe.py`, tests and docs. Read
only OS/Python/architecture, explicit root disk and NVIDIA driver/GPU capacity. Reject
unknown/changed accelerator, unsupported pinned-runtime driver, incomplete model memory,
precision and storage mismatch before bootstrap. Do not install, delete, mount or read
credentials. Verify standalone execution on an actual clean CPU environment separately
from synthetic GPU reports; neither proves real Colab hardware or native installation.


Owned native bootstrap staging increment: `remote/stage.py`, `_colab/bootstrap.py`,
focused staging/workflow tests and docs. Consume actual probe validation, then hash-check
and validate the exact regular-file source payload before creating a new operation-only
folder. Never reuse/overwrite a pre-existing directory, follow links or delete on failure.
Flush ownership/staging records and retain partial state for rental recovery. Execute
only credential-free staging through the owned kernel. Native engine installation and
SSH forwarding remain subsequent work; no paid/live system setup occurs in these tests.


Bounded provider reads: replace whole-body RunPod API/status reads with chunked reads
and a monotonic transfer deadline; share the already-required Colab bound. Keep byte
limits, safe errors and no retries. Test slow trickle/late completion and run full free
checks. A blocking socket read may last up to its socket timeout beyond the transfer
deadline; this change does not claim resolver or provider-outage hard billing limits.

Notebook/model interpreter correction: official Colab rollout evidence shows Python
3.13 notebooks on Ubuntu 24.04. Separate kernel_python inventory (3.12/3.13 bootstrap)
from the pinned isolated model Python 3.12 target; never reject the current notebook
solely for not being the model interpreter. Add a focused mismatch regression and run
the full free checks. Actual Python 3.12 provisioning remains native-bootstrap work.


Native Colab GGUF installation increment: add `remote/install-colab.sh` to the inspected
payload, generate ownership/hash-verified detached installer launch in `_colab/bootstrap.py`,
and test actual launcher code with subprocess replacement before any system install.
Use the signed Ubuntu snapshot, separate Python 3.12 venv/downloader hash lock and
verified llama artifacts. No SSH/service settings, model credentials, model process,
existing-machine attachment or real provider changes in free tests. Preserve an
exclusive start marker and uncertainty; require the owned kernel final-authority gate.
vLLM native lock/install and full supported connector registration remain required.


Owned installer status: add standalone `remote/install_status.py` and source-channel
queries/waiting in `_colab/bootstrap.py`. Bind the in-kernel process object to the
operation/root/source hash. An observed nonzero exit is failed even if marker files
claim readiness; zero exit requires owned proof, exact installed marker and expected
runtime paths. Missing process authority stays unknown. Return approved phase IDs and
log byte counts only, never raw logs. Use deadline/cancellation and owned kernel gates;
no remote PID signalling, process discovery, model readiness or provider-off claims.
Test actual generated code and process-like exits plus controller-facing acknowledgements.


Colab native SSH transport foundation: extend `_colab/channel.py` with bounded binary
messages and a shared direct-TLS opener; add `_colab/ssh_proxy.py` with strict private
runtime-only access records and a cancellation/backpressure-aware stdio bridge. No
account OAuth token, shared CLI cache, auto-create, credential URL, redirects or blind
SSH trust. Use only current owned rental scope, short-lived runtime token and generated
Ed25519 public key; same-owner private files stay inside the approved controller boundary.
Tests cover actual pinned WebSocket frames/handshakes, Linux private permissions and
real local byte bridges. Host-key enrollment/OpenSSH integration and actual native
provider header/SSH behavior remain required before a supported connector claim.


Colab strict SSH enrollment/client: add `_colab/ssh.py` and focused tests/docs. Generate
only operation-owned client identity with durable intent. Obtain initial Ed25519 host
key through the selected runtime's authenticated direct-TLS native bridge and a
single-use loopback scanner; never trust an unauthenticated direct network keyscan.
Persist pending/pinned operation+resource proof and refuse partial/changed identity.
Use fixed isolated ProxyCommand, strict private known-hosts, only the operation key,
no user config/agent/password/forwarded-agent access. Respect one active native SSH
connection and terminate only our local process handles. Actual provider TLS/header/
host-key behavior and full SSH/GPU acceptance remain separate release gates.


Next required shared endpoint correction: existing PinnedSSH.forward chooses free TCP
ports then closes them before SSH binds. Port numbers are not ownership proof, and
controller-loopback access is broader than the owner-only socket boundary. Replace
model/status forwards with private operation Unix sockets, refuse existing/unowned
paths (no auto-unlink), and carry a provider-neutral scoped Unix endpoint through
Controller/Dispatcher/controller_service and runtime status/model callers. Update
bridge/runtime tests with actual private sockets and collision/permission refusal.
This is required for R1/R3 and both initial connectors, not an optional cleanup.

Implemented endpoint contract: carry original resource and operation plus socket
instance/device/inode and owned SSH PID through core dispatch and stream authorization.
Check owner-only directories and Linux peer credentials before any model/status bytes.
Use a short state-root socket namespace independent of long identity-artifact paths;
reject invalid or overlong addresses before allocation. Persist startup intent before
SSH spawn and verified socket identities before declaring ready; preserve unknown or
replaced paths on cleanup. Bound status headers as well as body reads. Validate actual
Unix HTTP/stream traffic, owned child-process listener startup and preservation failures.

Colab credential-before-start increment: add a controller-generated fixed SSH command
that rechecks the owned staged source and installed runtime, reads an optional model
credential only from SSH stdin, writes it exclusively with private permissions, and
persists one-use model-start intent before launching the existing remote agent with a
minimal environment. No credentials enter kernel code, command arguments or output.
Refuse replay/changed source; provider recovery handles uncertain submission. Test the
actual generated code with local temporary owned files and intercepted child launch.
Full setup orchestration, native vLLM and live acceptance remain subsequent gates.

Owned Colab runtime orchestration: prepare verified metadata and short private endpoint
paths before allocation; persist scoped setup state. Re-read durable receipt authority
before each kernel/SSH side effect without nested receipt locks. Start only our kernel,
stage/verify/install once, persist bounded installer progress, enroll original-account
native SSH, transfer explicit model credentials, then open private status/model forwards.
Monitor reads cached setup progress until forwards exist. Recovery closes only owned
in-memory process handles; restart preserves unknown paths/identities. Validate ordered
success, uncertain no-replay, cancellation and changed resource/account/lease authority.

Native vLLM dependency preparation: resolve exact existing vLLM 0.32.0 and downloader
2.3.0 for Python 3.12, Linux x86_64/glibc2.39, wheel-only with generated hashes. Record
pinned-source requirements and resolution evidence separately from install/live proof.
Do not feed the large lock into the existing single-message/runtime-environment payload
without fixing its actual byte limits. Keep native installer refusal until complete.

Bounded native source transfer: retain existing compressed/extracted archive caps and
kernel code cap. Add explicit native-runtime payload files only when requested; RunPod
image payload stays small. Large Colab payloads upload in bounded chunks into the owned
kernel's scoped memory buffer, with exact offset/chunk digest acknowledgements, then
use the existing validated exclusive filesystem stager. No files are touched before full
archive verification; lost kernel/response refuses replay through existing durable kernel
execution proof. Test actual large pinned-lock payload, corruption, offset/scope changes,
pre-existing buffer, and cancelled/uncertain execution without subsequent steps.

Native vLLM installer: branch only on the inspected model engine, use isolated Python3.12
and generated wheel-only hash lock with no package cache, then pip-check and verify exact
vLLM/PyTorch versions, native extension import, bundled CUDA and one actual GPU capability.
Write an exclusive flushed engine-specific proof before installed marker; status requires
successful retained installer process plus matching proof. No credentials or model start.
Test verifier refusal and real proof-file status logic with simulated imports/hardware;
actual installation/import/GPU/footprint remain live acceptance evidence to obtain later.

Colab quote integration: account CCU telemetry is not a selected GPU price. Return an
unknown rental price, account-wide ceiling scope, fresh positive balance and explicit
unknown availability/storage. Generic quotes may defer unknown disk capacity only with
an explicit before-installation verification contract in confirmation-bound details;
Colab's existing actual probe enforces this before staging/installation. Preserve known
small-disk rejection and validate all model sizes/reserves before allocation. No guessed
rates or disk sizes and no implication that account totals identify this rental's cost.

Optional Colab connector registration: discover trusted module without central branches;
wire explicit OAuth credential reference, prepared API/runtime and quote. Validate Linux
SSH/transport prerequisites and exact selections/settings. Account/resource-bound methods
never adopt or stop attachments. Health distinguishes provider-confirmed absence, unknown
ownership, exhausted balance, account-wide consumption and private runtime progress. Only
provider-confirmed absence permits final local cleanup; no handle is not shutdown proof.
Test connector contract, discovery without default connections, and ownership boundaries.

## Next bounded increment: provider-neutral desktop onboarding

Release inventory has no Windows application entry point or installer yet. Existing
models.ps1/tools.ps1 and controller client/protocol are reusable. Start with a bounded
Python desktop bridge (strict JSON stdin/stdout, no secrets/commands in arguments,
prerequisite discovery and missing-controller first-run state), then WPF onboarding.
Render connector-provided field/choice metadata rather than branching on provider IDs;
adding another connector must require no central workflow/UI edit. First screen has no
provider selected, distinguishes rentals from existing machines, and cannot submit a
rental while controller protection/quote/plan/confirmation is missing. Credentials are
configured explicitly on the independent controller, not silently copied from desktop.

Likely files: new desktop bridge and Windows entry point/installer, controller protocol
and connector metadata, related tests and installation/privacy documentation. Preserve
existing model planning and isolated tool settings. No paid runs, controller deployment,
real credentials, governance ratification, licence choice or publishing in this increment.
Evidence: actual isolated bridge subprocess over stdin, fresh no-provider startup,
missing dependency/controller and named connection paths, generic connector rendering,
UI cancellation/liveness/stop handling, package-based clean install later. Existing-machine
attachment and persistent volume creation remain separate required release increments.

WPF design: a single left-aligned working window with a narrow setup spine and one
content column, not dashboard cards. Palette: paper #F7FAFC, white #FFFFFF, ink #12324A,
blue-teal action #187D94, divider #DCE5EA, error #B24331. Segoe UI uses native Windows
metrics and keyboard focus; headings establish hierarchy. Sections follow the actual
sequence: verify controller, choose/add named connection, review rental choices. The
first screen is empty and directional; no provider is preselected. Typed metadata is
rendered into native controls with label targets, never parsed as XAML. Async bounded
child requests keep input responsive; close cancels only owned local work. Inspect a
rendered artifact and run actual Windows control/process smoke checks before claiming UI
verification. Rental/session controls remain gated until full liveness/recovery integration.

Desktop rental coordination: validate explicit confirmation, fresh quote, checked plan,
connection and controller protection before durable local request intent and one scoped
request. Persist uncertain submission across process loss; never infer unsubmitted/off.
Bind returned receipt to original controller/connection/quote/limits before starting the
existing DesktopSession. Preserve actual UI pulse time rather than granting a new lease
on delayed response. If UI closes during request, retain receipt and request owned cleanup.
Expose safe snapshots/recovery and keep local intent until fresh controller evidence is
terminal. No real rentals in implementation tests; persistent process/UI transport follows.

Abandoned request cancellation: persist operation/connection/client/controller-scoped
start denial under the same receipt allocation lock; normal request and final submit
gates refuse it. Existing receipts use normal scoped recovery. Persist a conservative
initial receipt journal before receipt creation/worker launch; orphaned journal entries
block new allocation and are restored as uncertain for recovery, never reported as never
submitted. Only intact journal absence plus durable future-start denial can acknowledge
cancellation before submission. Desktop keeps any known receipt and never turns this
acknowledgement into provider-off. Test restart, preflight and in-flight races.

Persistent session pipe: a separate reader parses bounded begin/pulse/stop frames, keeps
actual UI pulse time and detects EOF during slow RPC. One guarded cleanup worker stops
renewal before recovery; missing evidence remains uncertain. Shared receipt-write locking
prevents stale renewal from overwriting terminal recovery. Exercise actual OS pipes and
isolated missing-controller process; do not expose paid UI actions until the Windows
persistent client and complete confirmation/recovery workflow are integrated.

Windows persistent client: fixed session_host module only; background writer/reader and
bounded queues so UI pulse/stop never block on pipe IO. No background auto-pulse. UTF-8
frames/strict output limits, bounded stderr and finite confirmed-duration watchdog. Close
sends stop/EOF then kills only its retained helper after a bounded grace; does not assert
provider shutdown. Test actual child duplex, queue/oversize refusal and explicit close.

Windows dispatcher integration: retain the persistent helper in window state; pulse only
from the live dispatcher every15seconds, refuse revival after a60second gap. Window close
and Stop send bounded helper Close. Drain bounded frames on dispatcher; only snapshot
receipt off plus boolean confirmed permits off wording. Helper exit/error remains uncertain.
Test callbacks, stale dispatcher, off/uncertain distinction and retained-child close.
Paid rental navigation stays disabled until confirmation and recovery are complete.

Recovery desktop increment: bounded read-only listing of local request/receipt identities,
including damaged records, without network or new directories. Local saved off is history,
not fresh confirmation. Scoped refresh/explicit cancellation use Rental and the original
saved enrollment, never submit/replay a request. Preserve damaged/missing evidence.
WPF recovery navigation refuses concurrent session and displays fixed plain status.

Generic rental-offer navigation: choose a named rental-capable connection without defaults;
render connector selection form and refresh its partial choices without provider branches.
Request a fresh quote and display account scope, unknown rate/capacity, balance and
separate storage details explicitly. No rental starts from offer browsing. Model metadata
planning and final confirmation follow; do not enable paid submission prematurely.

Model discovery increment: read-only controller RPC on a named connection, verify owning
account first, use only its explicit hf_credential_ref. Validate owner/model identifiers;
resolve metadata then refetch immutable SHA. Fetch inert config JSON at pinned revision,
allow at most3same-origin HTTPS redirects, never forward credentials to another host.
Return only bounded planner-required file/hash/task/base/config fields, no raw model card.
No remote code or downloads beyond metadata/config. Safetensors config and optional GGUF
base model config carry pinned revisions; missing config remains explicit. Tests mock
HTTP and protocol, including hostile redirects, oversized data and credential isolation.

Desktop planning worker: fixed PowerShell script via argv, bounded JSON stdin/stdout,
finite timeout and fixed errors. Reuse ModelPlan/GgufPlan/DescribeCheckpoint, require
explicit runtime and GGUF variant, reject context outside published capacity. Return
filtered executable plan plus experimental/native-context/estimated-memory summary;
metadata stays inert and no credentials/network are used by this worker. Test actual
Windows5.1 subprocess for both formats, unsafe files, missing choices and context.

Capacity contract: bind market GPU memory or explicit before-installation validation in
quote cost_details/confirmation hash. Shared offer planner requires finite positive
weight/overhead/KV estimates, rejects known insufficient GPU/storage before submission,
and preserves unknown capacity as deferred checks (both real connectors already probe).
Enforce in controller and desktop, expose read-only preview, test missing contracts and
undersized/currentlychanged offers; update synthetic providers to declare their capacity.

Final rental confirmation: freeze reviewed connection/selection/model/quote/capacity,
repeat account/unit/rate scope/unknown pricing/storage/experimental and controller
availability limitations. No prechecked approval or default rate/duration. Require finite
positive ceiling, explicit duration<=day, all acknowledgements, fresh quote<=120seconds
and no active job/session. Launch only persistent UI-owned helper; desktop/controller
recheck protection/account/quote/capacity before submission. Test actual WPF button with
synthetic Start-DesktopSession replacement; no paid actions during validation.

Session status increment: authenticated operation-key-scoped read-only status, fixed
phase/ready indicators from fresh controller health, no lease renewal/provider mutations.
Host verifies scope before exposing phase; stale or unknown status cannot claim ready.
WPF maps fixed phases to plain English and keeps provider-off confirmation separate.
This readiness view gates later tool handoff; relay access independently checks scope.

Tool handoff helper: strict confirmed tool_launch frames, bounded4command queue and16
unique request IDs; no arbitrary argv/environment. Process on host worker, not pulse
reader. Require live UI/session, fresh scopedready, open relay, original saved modelplan
and explicit native executable/projectfolder/idle acknowledgement. Use tools.prepare/
launch child-only overlays; never print relaytoken/URL/path or terminate existingtools.
Deduplicate beforeattempt, fixed resultmessages and no automatic retry. Preserve default
reasoning settings; optional effort/vision UI is not claimed by the initial handoff.

WPF tool form: explicit OpenCode/Codex choice, native.exe and projectfolder pickers/fields,
unchecked idle/experimental approval. Stop always available. Only freshready snapshot
permits launch (10second local freshness), boundedCommand onretainedhelper, one pending
ID and matchedfixed tool_result. Never display relaykey or edit normaltoolsettings.
Clear ready onstatus loss/stop/exit; testsfakeownedtransport actualWPFevents, no real tools.

Attachment identity/argv increment: strict explicit private IP/port/user/hostkey/modelport/
model-ID settings; saved credential is an absolute dedicated key path. Validate owner-only
regular nonlinked bounded key without changing it, derive Ed25519 public identity with
fixed noninteractive ssh-keygen argv, bind principal fingerprint. Build Linux-only pinned
ssh -N single Unix-to-loopback forward, no config/agent/proxy/remote/local command. Create
only new private local trust; preserve existing paths. No connector registration or live
SSH yet. Test synthetic identity changes, invalid targets, key permissions and exact argv.

Attachment supervisor: one retained SSHchild, strict pulse/stop pipe, EOF/liveness/startup
deadlines. Validate attachment/principal/resource before startup, verify private Unix
endpoint inode/device/UID/peerPID before readiness; unlink only the verified owned socket.
Fixed Python child shim sets Linux parent-death SIGKILL and checks original parent before
exec; refuse privileged/capability executables that clear the setting. No arbitrary PID
kill/adoption and no off claim. Test local synthetic child processes, not live SSH.

Forward parent integration: fixed helper entry point reads a bounded operation-ID/key
frame, loads original saved receipt/connection/credential reference, checks principal and
resource before forwarding. Parent client bounds ready/status reads, retains only its
helper, nonblocking explicit pulses(no auto-renewal), stop/EOF grace then owned-helper
kill. A killed helper alone never proves disconnect; only scoped closed acknowledgement.
Tests use saved synthetic state/fake local socket children, with no live SSH/account.

Attachment connector increment (internal until core lifecycle complete): descriptor
attachment-only, explicit host/key/model fields and saved identity-path reference. Bind
receipt/principal/resource; one ForwardClient attempt, bounded read-only /v1/models
selected-ID check, explicit pulses and local disconnect. Refuse allocation/setup/quote/
termination, never remote commands. Preserve unknown restart state; only matching durable
closed proof or retained helper acknowledgement confirms local disconnection, never off.

Selected-model relay increment: attachment relays require an explicit served ID before binding. Validate bounded UTF-8 JSON with unique keys and no nonstandard constants before opening upstream inference access; require exact model match on every inference route and preserve accepted request bytes. Rental relay compatibility remains covered. Tests prove invalid/mismatched bodies open no stream. This desktop check is defense in depth: controller-side stream enforcement and attachment lifecycle integration must precede public connector registration.

Controller selected-model stream increment: share body validation with the desktop relay. For controller stream scopes carrying selected_model, read one bounded HTTP request under timeout/repeated authority checks before connecting upstream, rebuild fixed headers, and forward only the checked request. Extend existing backpressured duplex with a fixed-request mode that never reads additional client input. Revalidate the whole endpoint/model scope during response streaming. Linux pipe/socket tests cover malformed framing, duplicate lengths, revoked authority and pipelined model substitution. Attachment lifecycle must supply this model scope before enabling its connector.

Core attachment lifecycle integration: Attachments owns per-operation serialization, durable original connection/model journal, receipt before helper start, shared durable start denial and separate access pulses/disconnect commands. Late cancellation persists before waiting for startup; retries never reconnect. Restart/close reconcile local evidence without credential rereads or machine termination. Controller stream scopes bind the saved served model for guarded streaming. Attachment operations require enrolled-client authentication, while managed rental shutdown-health gates remain separate. Tests cover races, unknown disconnect, lost replies, changed credentials/connection and protocol scope. SSH connector registration and desktop attachment onboarding remain deferred until complete integration evidence.

Desktop attachment increment: reuse desktop access-pulse/relay infrastructure with separate attachment_pulse/disconnect RPC and explicit selected model. Bind controller startup to reviewed account/resource/model preview. Desktop attachment intents survive lost replies and use original controller scope for local-only recovery; late active replies cannot overwrite detached evidence. Keep rental pricing/protection/termination separate. Focused tests cover UI loss, changed replies, cancellation, terminal records and absence of rental RPC. UI and recovery-list integration remain required before connector registration.

Windows attachment/recovery controls: capability-filtered named connection selection, controller preview and frozen once-only target confirmation with separate access/continued-cost acknowledgements. Explicit helper mode gives local Disconnect access action and rejects attachment off claims. Merge local rental/attachment recovery indexes with mode-scoped dispatch and local-only attachment cancellation disclosure. Actual native WPF events cover no defaults, frozen targets, no repeated submission, false shutdown refusal and terminal local disconnect. Attachment coding-tool metadata/handoff and optional connector registration remain next.

Existing-model tool handoff: require an explicit user-declared conversation limit from the existing server settings, validate served ID separately from installation metadata, and reuse child-only tool overlays without guessing engine/parser/vision/reasoning capabilities. Bind tool model to selected relay model; compatibility stays experimental. Optional SSH factory enables trusted discovery after lifecycle/desktop checks. Tests cover invalid IDs/limits, normal settings preservation, exact served-ID scope and native WPF confirmation. Live SSH/account/tool acceptance remains a release gate.

Persistent-volume recovery increment: separate validated VolumeIntent from disposable rental receipts; nonce-scoped marker and bounded baseline inventory. RunPod adapter binds one credential snapshot to original account, rechecks inventory and final submit gate before one POST, retains partial response IDs and never retries. Name matches remain candidates, including single matches; manual identification requires explicit confirmation and original account/size/location/marker. No volume deletion or unrelated mutation. This adapter is not exposed for creation until core durable journaling, fresh tier-specific pricing and desktop approval/recovery are complete.

Provider capability follow-up: official v2 network-volume schema carries explicit tier and paginated inventory on the already-used api.runpod.io host. VolumeIntent and marker bind tier; adapter follows bounded pagination and refuses incomplete/repeated cursors. Existing-volume rental quoting now verifies Standard tier through v2 and rejects premium/unknown tiers before spend. Premium pricing is data-center-specific in the provider console; do not substitute the generic Standard tariff. Creation remains unexposed pending core durable journal and explicit fresh-price approval/recovery.

Persistent-storage core increment: one atomic journal stores original connection/account, nonce/baseline/tier intent, reviewed monthly quote, final submission claim and response/manual provenance. Persist before provider call; final gate durably claims once after account/inventory checks, checks unchanged connection/fresh quote, and refuses repeated claims. Lost replies/restarts never POST again. Partial IDs remain scoped and can be verified by direct observation; name candidates never auto-adopt. Explicit manual identification cannot replace a known ID. Unsubmitted intents may be closed without claiming deletion; submitted volumes remain persistent and are never automatically deleted. RunPod supplies optional storage methods; RPC/UI creation is still unexposed.

Persistent-storage RPC increment: optional persistent_storage descriptor capability requires complete installed connector methods. Core snapshot/list endpoints expose scoped historical records with bounded pagination and isolated damage, omitting raw connection/credential settings. Storage quote/create and operation-key-bound status/recover/unsubmitted-close commands require enrolled client authentication; manual identification stays explicit and cannot become rental cleanup. Ordinary desktop one-shot RPC continues to refuse storage creation until a dedicated durable desktop intent is integrated. Synthetic connector/controller tests prove scope and extension without provider branches.

Delayed-storage denial increment: enrolled original-connection cancellation may persist a bounded start denial before any controller creation journal exists. Final submit gate checks it; denial survives restart and prevents late requests or claims. Already claimed creation is reported as potentially completing, stays journalled and is never deleted or described as unsubmitted. Known-only unsubmitted close delegates to the same denial path. RPC requires explicit cancellation confirmation; tests cover before-journal, during-preflight, after-claim and wrong-scope cases.

Desktop storage intent increment: persist original enrollment, connection/account, reviewed monthly quote, exact target and operation ID before the dedicated creation RPC. A lost reply remains pending; never replay creation. Recover the original controller record through bounded pagination, require explicit candidate identification, preserve known identity against late unresolved responses and persist confirmed delayed-start denial without claiming volume deletion. Generic desktop RPC still forbids raw creation. Synthetic tests exercise the dedicated bridge, real core dispatcher, lost and undelivered responses, changed scope/price, damaged history and explicit recovery. WPF storage controls remain the next integration step.

Connector storage forms: generic connector_form accepts storage only for an advertised persistent_storage capability and the verified original named account. RunPod supplies explicit Standard tier, data center and size 1–999 GB fields without market or creation calls. No provider-specific desktop branch is needed. Focused connector tests (18) and persistent-storage tests (20) pass, including changed-account/capability refusal. Native desktop storage screens remain the next step.

Native storage workflow: capability-filtered named connections, connector-owned explicit options, fresh monthly estimate and frozen target review. Two unchecked approvals precede one dedicated desktop submission. Paged local request recovery offers original-operation refresh, explicit manual ID verification and delayed-start denial; never deletes volumes. Recovery validates provider observation identity before updating local evidence, distinguishes present/absent/unresolved/manual results and never equates absence with bill closure. Candidate IDs remain unselected. Native Windows controls exercise no defaults, frozen quote, duplicate clicks, separate recovery approvals and billing language. Synthetic native review render inspected at 1024x720; no real provider/account actions. Full Windows checks: 514 tests (430 passed,84 skipped),17 planning checks; focused Linux desktop storage11 passed, final native controls2 passed. Live provider/billing acceptance remains open.

Source-package increment: explicit committed-blob allowlist for product, tests, curated guides and third-party notices; deterministic ZIP inventory/timestamps/modes and SHA-256 manifest. Exclusive output creation; reject state-bearing tracked paths, symlinks and missing notices. Build neither includes Git history/untracked working files nor implies publication permission. Native source-installation/operation/privacy/support guides explicitly retain live/provider/billing/owner gates. Real temporary Git/ZIP tests prove reproducibility, selected-byte hashes, untracked exclusion and refusal boundaries. Actual candidate build/extraction/privacy/clean-package checks follow the committed builder; automatic Windows shortcut installer remains a separate incomplete gate.

Per-user source installer: inspect bounded manifest and exact file bytes before creating a new destination; reject linked source/path parents, traversal, case collisions, modified files and existing installations. Copy only manifest files, preserve source manifest and write a local installation receipt. Windows frontend checks Python, creates only a new revision-named shortcut in the selected per-user directory and never launches or touches credentials/state/settings/policy. No recursive deletion or overwrite rollback. Native temporary-directory shortcut and refusal tests accompany integrity/path/state-preservation tests. Actual packaged installer acceptance remains required.

Independent-review correction increment: IR1 isolates Hub auth in a new private operation directory, strips alternate env auth, disables implicit auth for anonymous operation and keeps HF_HOME separate from persistent model caches. One selected private credential is consumed before model spawn; no second unvalidated reader. IR2 validates requested cache roots/parents before mkdir and refuses escaping cache links under a bounded scan, preserving internal Hub snapshot links and using only the dedicated fallback. Pinned Hub2.3 subprocess tests prove anonymous/selected credential resolution; Linux cache tests prove unrelated targets untouched. No changes to provider APIs, approvals, shutdown or credentials scope. Independent original review7285cda requested changes; corrected exact-state review and new package acceptance remain required.
