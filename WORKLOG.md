# Engine Room worklog

## Release bootstrap

2026-10-25: generated governance 3.0.0 in a fresh repository before product import.
Branched to codex/release-bootstrap. Established the neutral product brief and safety
constraints. No product source, credentials, archive history or local settings copied.
Governance is a proposal: ownership reference and remote policy await owner ratification.
No remote exists, no paid resources started, no licence selected and no release published.
Next: complete governance ownership/CI, inspect bootstrap source and first commits,
then import only reviewed, sanitized source through an explicit manifest.

## Recovery foundation

Created neutral account-bound receipt storage with atomic replacement/file sync,
allocation locking, isolated corrupt records and connector-neutral recovery. Recovery
requires original account identity, refuses unrelated resources, preserves ambiguous
allocation, confirms provider absence before off and disconnects attachments separately.
Self-check found a newly reconciled resource ID could be lost after deletion failure;
fixed and added a regression. Also isolated write failures so later known rentals can
still be cleaned up. 23 synthetic tests pass on Windows; no provider calls or paid work.
Added a Windows CI job and the complete open finding ledger. Final review and connector
integration remain outstanding. No finding is closed solely by these foundation tests.

The same 23 tests also passed under WSL Linux, exercising POSIX locking and directory
sync. This uses the same workstation and synthetic accounts; it is not clean-PC or
independent-provider-account acceptance.

## Named connections and shared model extraction

Added optional installed-connector discovery and explicit named connections with no default
provider. Account changes use distinct connection identities; removal is blocked by
unresolved or damaged records. An extension-discovery test uses a separately installed
synthetic connector without changing the central workflow. No actual accounts configured.

Inspected and extracted shared model planning/runtime from the development source into
neutral code. A single Python GGUF validator now serves both PowerShell preflight and
remote argv building. B3/B4 regression cases cover model/projector filenames, exact shard
indices, duplicates and mixed totals. Added conservative model disk sizing and GGUF
pre-download free-space/hash-verified cache checks. vLLM disk integration remains pending.
42 Python tests and 11 PowerShell planning checks passed locally. These modules are not
yet wired into the UI or real connectors; no release finding is closed solely by this.

The owner approved the organization team reference and implementation of the user-controlled
independent-controller design. Team creation/existence, governance ratification, deployment,
credential setup, paid tests and publication remain separate decisions/actions. No actual
provider credentials were read or resources rented. Next: implement the controller worker
and deadline monitor, then extract Colab/RunPod API and setup/health adapters into it.

## Independent controller lifecycle foundation

Implemented the approved controller worker plus separate deadline/lease monitor,
explicit independent-host enrollment, fresh quote/rate/disk gates, pre-POST persisted
intent, final lock-time uncertainty gate, late allocation cleanup and restart recovery.
A single-controller OS lock prevents a second process treating live work as abandoned.
Tests exposed an incorrect resource-ID requirement for never-submitted cancellation;
fixed without weakening provider-confirmed off. Self-check also tightened actual-rate
loss and model-returning-to-starting handling. Added regression tests for each.

Full Windows free suite passes: 62 Python tests and 11 PowerShell planning checks.
The 62 Python tests also pass under WSL, including a running background monitor
expiring a deadline without desktop calls. No actual provider credentials or resources
were used. Remote transport/service deployment and both real provider adapters remain
pending; independent final review has not occurred. See docs/CONTROLLER.md for policy,
guarantees, limits and evidence distinctions.

Created the empty private engine-room-project/engine-room GitHub repository and registered
origin. No source was pushed; pre-push inspection, governance-team existence and remote
policy planning remain outstanding. Follow-up self-check ensures a controller that failed
to acquire daemon ownership cannot clean up the active owner's rental even if its caller
runs close() in a finally block. The existing singleton regression covers that close path.

## RunPod API and credential boundary

Extracted bounded provider HTTP and RunPod account/market/ownership/recovery API helpers.
Implemented explicit credential storage: current-user DPAPI on Windows; owner-only Linux
files for direct controller authentication. Only temporary synthetic credentials were used.
API operations bind identity and requests to one key snapshot, fixing a rotation race
found during self-check. Unrelated resources coexist and are never deleted by recovery.

Full Windows free checks pass: 86 Python tests run (85 pass, one POSIX-only skip), plus
11 PowerShell planning checks. All 86 Python tests pass under WSL. Focused RunPod tests
pass after the final capacity-filter correction. API replies are synthetic, not live
provider/billing evidence. The adapter is not yet complete or registered as supported.

Research found GraphQL stopAfter/terminateAfter allocation fields absent from the inspected
REST schemas. Field presence is not proof of coverage/enforcement; investigate them as
native backstop candidates. Independent-controller architecture remains approved. No paid
probe, real credential access, source push or deployment occurred. Next: pinned runtime
payloads, protected allocation/setup/health integration and private controller transport.

## Pinned remote payload and supervision

Resolved/verified official linux/amd64 OCI manifest/config digests for the CUDA base
and vLLM v0.32.0 image. Current vLLM uses CUDA 13; do not advertise old-driver support.
Pinned Ubuntu snapshot, generated Hugging Face Hub 2.3.0 transitive hash lock and preserved
upstream notices. Both llama.cpp archives match recorded SHA-256 hashes (download only).
Clean isolated Linux Python 3.12.15 installation/import passed; lock regeneration is
byte-identical. No system Python changed and no real HF/provider credentials accessed.

Implemented deterministic allowlisted remote source archives, safe extraction/checksums,
separate runtime-ready and explicit model-start phases, and loopback-only supervision.
The supervisor consumes a private HF key before launch, strips ambient credentials,
suppresses backend output and verifies both model identities before ready. Windows skips
this POSIX-private-file test; the actual ordering test passes in Linux. Self-check fixed
a bootstrap that would otherwise exit while waiting for explicit model start.

Both engines now check actual disk space before download, using hash-verified cache only.
Extended canonical preflight/runtime filename validation to safetensors to avoid creating
a new paid-setup mismatch. Full Windows checks: 100 Python tests (98 pass, 2 platform skips)
and 13 planning checks. All 100 pass in isolated Linux Python 3.12; legacy Windows
PowerShell also passes 13 planning checks. No actual container boot, GPU/provider/billing
acceptance, deployment, source push or final independent review. Reserves remain estimates.
Next: wire pinned payload into actual RunPod protected allocation, SSH/credential transfer
and live tunnel/model health; implement controller transport and the Colab adapter.


RunPod integration checkpoint: added the registered optional rental connector,
account-bound fresh GPU quotes plus separately identified storage tariffs, pinned
SSH setup, explicit model-access verification before allocation, and actual
GPU/driver/model/tunnel health checks. Preparation precedes a second quote and
protection check; candidate allocation IDs survive partial responses. Saved
storage is explicit, preserved and never credited as guaranteed free capacity.
Cache exhaustion falls back to the planned disposable disk without deleting data.
No account/model tokens enter provider environment settings. Generated session
SSH material is controller-private state and is removed after confirmed absence.

Evidence: 120 Windows Python tests pass (two POSIX-only skips); the preceding
116-test state also passed all tests under isolated Linux Python 3.12.15 and
full Windows project checks including 13 PowerShell planning checks. Final
checks are repeated below before commit. Tests use synthetic accounts and
mock provider/SSH responses. No provider allocation, billing verification,
container execution, infrastructure deployment or final independent review.
Existing-machine connection, Colab extraction, controller transport/service,
UI integration and release-package acceptance remain required work.


## Private controller transport increment

Added bounded, duplicate-key/non-finite-refusing JSON RPC with strict command fields,
controller/client enrollment checks, paginated recovery history and safe errors.
A Linux owner-only Unix socket server verifies peer UID, bounds concurrent handlers
and leaves the independent monitor running when clients fail. A separate forced SSH
wrapper exposes no shell or credential-management RPC. The desktop client requires
an explicit private-network IP, dedicated SSH identity and independently pinned
Ed25519 host key; ambient SSH configuration/agents and forwarding are disabled.
Neither status reads nor a failed/lost SSH response silently renews leases or retries
allocation. Credential prompts refuse noninteractive input and echo fallback.

Prepared, but did not deploy, a dedicated-account user-service template and concrete
installation/removal proposal. Actual service sandbox, lingering, SSH forced command,
remote handshake, physical independence and real credentials are unvalidated. Model
traffic forwarding and desktop heartbeat/UI integration are following increments.
Existing-machine connection, Colab, full package/account acceptance and final independent
review still remain required. Source remains local pending pre-push/privacy/governance gates.

Free evidence: 140 Windows tests pass with eight platform skips; all 140 pass in isolated
Linux Python 3.12.15. Linux tests exercise a real local daemon, cancel an unsubmitted
intent, refuse a second daemon, recover after SIGKILL, and clean the socket on SIGTERM. Stopping with unresolved allocation records returns failure and preserves the receipt.
OpenSSH offline parsing passes including a state path with spaces; no SSH connection
is made by that test. Provider behavior remains mocked and no paid resource is used.

The deployment wrapper's committed blob was LF-normalized but its Windows working copy
had CRLF. Corrected the working copy and added actual Linux kernel/shebang execution
with a spaced home path; the fake module fixture verifies wrapper arguments without
running controller/provider operations. Package assembly must use inspected, normalized
source and must test actual executable artifacts, not rely only on shell parsing.


## Desktop model streaming and UI-bound lease increment

Implemented a session-owned authenticated loopback relay and incremental model traffic
through the restricted controller SSH wrapper. The bridge chooses only the active,
freshly healthy owning connector endpoint and rechecks authorization while streaming.
Stable receipt scope hashes bind renew/stop/model commands across account, connection,
controller and confirmed duration/rate, including ambiguous allocation responses.

Desktop renewal requires UI pulses, so an orphaned helper stops renewing. Stop intent
is persisted before asynchronous cleanup. Disk failure cannot skip remote cancellation;
a failed local stream cleanup cannot skip remaining streams/listener. Windows tests
exposed an atomic-replace/read sharing conflict; bounded Windows retries preserve the
old receipt until successful atomic replacement without deleting it.

Evidence: complete project checks include 163 Python tests (153 pass, ten platform
skips on Windows), 13 PowerShell planning checks and source/governance/shell validation.
Isolated Linux Python 3.12 has 162 passes and one Windows-specific skip. Actual local
subprocess/socket tests transfer a >256KiB prompt, deliver SSE before completion and
cut an existing stream after revocation while its backend remains open. The local
process substitutes for SSH; provider responses are synthetic. No live credentials,
provider/GPU/billing validation, deployment, source push or final independent review.

WPF/tool settings preservation, Colab, existing-machine attachment, storage creation,
source/package privacy inspection and clean independent-account/provider acceptance
remain required; all 22 findings retain open release gates. No automatic startup
renewal of old receipts is authorized.


## Process-scoped coding-tool settings

Added child-only OpenCode inline merges and Codex per-run provider/model overrides.
Normal tool files, profiles, credentials, permissions and defaults are never edited.
Unique provider/key names prevent replacement of existing inline providers; session
keys remain outside arguments/config content and LaunchPlan representations. Effort
is changed only after explicit compatible selection. Read-only Windows discovery
never executes candidates or treats detection as registration. Single-instance GUI
launch requires the idle check; unsupported script/protocol paths remain explicit.

Evidence: full Windows checks pass with 174 Python tests (164 pass, ten platform
skips) and 17 planning/discovery checks; Windows PowerShell 5.1 also passes 17.
Isolated Linux Python 3.12.15 passes 173 tests with one Windows-only skip. Real fake-
child execution preserves the parent environment and normal settings bytes. Installed
Codex help and current official docs confirm per-run flags/profile behavior; no actual
coding conversation, model/provider account or paid resource was used. Coding-tool
versions, SDK pinning, protocol/model compatibility and WPF integration remain gates.
No source push, deployment, publication or final independent review occurred.


## Colab account/API foundation and final submission guard

Inspected official google-colab-cli source/published 0.7.5 wheel and recorded exact
hashes. Added protected explicit Colab OAuth records, reduced-scope direct-host PKCE
login, bounded fixed-origin protocol HTTP and compare-and-replace token refresh.
No shared ADC/gcloud/CLI cache fallback; no broader permission or silent revocation.
Login setup is prepared only, not performed. Added durable pre-POST allocation proof,
account/connection/operation notebook identity, no retry, scoped unassign and dual
mapping/listing absence checks. Aggregate CCU use is labelled account-wide, never a
rental price. The Colab runtime/registered connector is still incomplete.

The shared controller now supplies a required one-use final submission guard after
provider authentication/preflight. Stop, expiry, unhealthy protection and late recovery
blockers refuse the POST. The guard releases the receipt lock before network I/O;
existing delayed-allocation tests still prove recovery can run during a late result.
Reconciliation retains a known candidate ID even when ownership remains uncertain.
Credential refresh cannot overwrite an explicit rotation to another saved value.

Generated a separate optional Colab lock with uv 0.13.0 and preserved Google's notice.
An isolated Linux Python 3.12.15 install of all 53 pinned packages and offline kernel/
state/reduced-scope PKCE smoke pass. No account or model/provider API was contacted.
Final complete checks: 201 Windows Python tests (190 pass, eleven platform/optional
skips), 17 planning checks; Linux optional environment has 200 passes and one Windows-
specific skip. Shell/source/governance checks pass. An earlier Windows run failed,
but the truncated capture omitted the test name and a direct rerun passed. Removed a
real 40ms clock assumption from UI-liveness fixtures; 70 focused thread/heartbeat
checks and the full suites then pass. This does not establish the lost failure's exact
cause; full Windows output is now retained in ignored development scratch storage.

Actual host/auth/account/provider/billing, Colab runtime/pricing, storage lifecycle,
existing-machine attachment, UI/tool acceptance, package and final independent review
remain required. No source push, paid rental, deployment or publication occurred.

The staged scanner initially flagged the public upstream auth.py SHA-256 because the
filename was a JSON key. Verified it against the downloaded public wheel bytes, then
represented provenance as explicit file/sha256 records. No scanner rule, exclusion or
hook was weakened. The public digest and all source provenance remain intact.


Provider-independent billing increment: removed the closed USD/CCU enum and universal
prepaid assumption. Connector quotes and health now carry an explicit billing unit and
rental/account scope. Confirmation, durable receipts and desktop scope hashes preserve
that boundary; unlike observations stop the rental. Verified zero rates are accepted;
unknown rates retain the bounded health-loss grace. Terminal failure no longer waits for
a billing observation. RunPod remains explicitly USD and prepaid. The runtime payload
allowlist includes the shared billing validator; a real isolated interpreter imports the
extracted payload without the checkout. Focused regressions cover a third unit, postpaid,
zero versus unknown, changed scope/unit, quote changes and immediate terminal cleanup.
Windows complete checks: 208 tests (197 pass, eleven skips), 17 planning checks. No live
provider calls or billing validation. Isolated Linux Colab environment: 208 tests (207 pass, one Windows-only skip).


A subsequent full Windows run captured a real WinError 10053 during rejection of an
ambiguous request with unread body bytes. Added a bounded graceful half-close/discard
before socket teardown: at most 64 KiB and 100 ms, no backend stream or parsing of
ambiguous input. A real-socket incomplete-body regression proves the response arrives
without waiting for the declared body; 60 repeated Windows rejection tests pass. This
addresses the observed unread-body reset pattern, not every possible network abort.


Colab runtime access now requires fresh original-account, durable notebook mapping and
unambiguous assignment-list proof before returning a short-lived selected-runtime token.
Expired, cancelled, stopping and attachment records refuse before account access. Runtime
URLs require the inspected native HTTPS prod.colab.dev root origin; unsafe/alternate
origins, credentials in URLs, custom ports and invalid TTLs refuse. URL/token are hidden
from repr and not persisted by this boundary. Synthetic fixtures cover account drift,
mapping mismatch, duplicates, absent assignment, expiry and hostile proxy responses.
Final Windows checks: 212 tests (201 pass, eleven skips), 17 planning checks. Isolated
Linux optional Colab environment: 212 tests (211 pass, one Windows-only skip). No provider
authentication, actual proxy connection, kernel creation, rental or billing validation.
Colab remains unregistered until kernel/SSH/bootstrap/health/pricing and release gates pass.


Colab owned-kernel startup/execution increment: prepared runtime-token-only REST and
Jupyter WebSocket transport, separate from account allocation. Existing kernel baseline
is read first; a flushed operation-bound journal and final authority gate precede one
kernel POST. Baseline IDs are never adopted. Lost/malformed results retain uncertainty
and cannot repeat startup. Execution refreshes ownership, uses only the journal's kernel,
disables history/input, writes intent before sending and requires matching reply plus
idle. Failed execution retains executing state without replay; no remote kernel delete.

The optional pinned websocket-client 1.9.2 path uses an explicit verified-TLS socket,
no redirects/environment proxies/account token or credential query, refuses tracing,
and limits per-frame allocation, fragmented-message aggregate, output and execution
length. Partial payload reads check cancellation. A real socket-pair test failed on
using ABNF.mask (a method) instead of ABNF.mask_value (the state field); corrected
against the actual installed library. Real upgraded-handshake/frame tests then pass,
including ping, fragments, masked/binary rejection, oversize header before payload,
aggregate bounds and cancellation during a partial body. These tests replace TLS and
provider endpoints; they do not establish live Colab compatibility or GPU serving.

Complete free Windows checks: 235 tests (215 pass, twenty platform/optional skips),
17 planning checks. Isolated Linux Colab environment: 235 tests (234 pass, one Windows-
only skip). Full Windows log retained in ignored development scratch. Colab remains
unregistered: actual SSH identity/bootstrap, driver/GPU/disk/model health, pricing and
all original live/package/independent-review/owner gates remain open. No real account,
rental, deployment, source push or publication.


Colab actual-hardware probe increment: standalone credential-free read-only inventory
runs through the owned kernel channel; validates selected accelerator, one GPU, actual
free/total memory, driver/libc, precision/context memory, exact model size set and disk
headroom. Missing GPU data stays unknown; no inherited account/model environment goes
to bounded NVIDIA subprocesses. Isolated actual Windows/Linux subprocess tests execute
the generated code without source imports and leave the temporary work folder empty.
Synthetic hardware incompatibility, old driver/libc, insufficient disk/free memory and
bad size reports refuse. Prepared native profile remains Ubuntu 24.04/Python 3.12.

Inspected all 30 regular ELF candidates of the hash-verified b11539 archive without
execution. The server library, unlike its small launcher, needs GLIBC_2.38,
GLIBCXX_3.4.32 and CXXABI_1.3.13. Recorded measured minima in runtimes.json and checked
actual glibc in the probe. The archive hash was reverified. Artifacts/ELF copies remain
ignored development scratch, never release source. A generated-code quote error was
caught immediately by the import check and corrected before tests passed.

Complete Windows checks: 243 Python tests (223 pass, twenty platform/optional skips),
17 planning checks. Isolated Linux optional environment: 243 (242 pass, one Windows-
only skip). Test handles are terminal. Finding ledger updated with current counts and
increment evidence; all 22 findings remain open pending integrated/live release gates.
No real account/proxy/kernel/GPU workload, paid rental, native install, deployment,
source push, final review or publication. Next consume this inventory in owned native
bootstrap/SSH integration; do not claim a supported Colab connector yet.


Colab native bootstrap source-staging increment: actual inventory validation precedes
hash-checked, exact-allowlisted regular-file extraction into a new operation-scope
folder. The stager bounds compressed/decompressed/archive sizes before writing, rejects
links/traversal/duplicates and never reuses an existing directory. Flushed ownership
intent, individual files/directories and final staged acknowledgement retain partial
state without deletion after failure. The owned kernel's final authority and uncertain-
execution rules apply. No credentials or unrecognized model fields enter the payload.

Actual generated staging code executes in isolated Windows/Linux processes, stages the
real source allowlist and refuses a second attempt. Tests preserve unrelated sentinel
files on directory collision/flush failure. An initial Windows test hit the command-
line length limit; the test now sends source through stdin, matching a data-transfer
boundary rather than a command-line workaround. Eight focused tests and complete free
checks pass: Windows 251 Python tests (231 pass, twenty platform/optional skips), 17
planning checks; isolated Linux 251 (250 pass, one Windows-only skip). All test handles
are terminal; full Windows output retained in ignored development scratch. Native
installation/SSH/model health and all original release/live/owner gates remain open.


Bounded lifecycle HTTP reads: the prior RunPod whole-body read could remain occupied
by a continuous trickle despite its socket timeout. Shared read_bounded now checks a
monotonic transfer deadline before and after each bounded read for RunPod account/API,
RunPod local runtime status and Colab account/kernel HTTP. Byte caps, no automatic
retry and safe errors are preserved. Slow-trickle and late-final-chunk tests refuse;
complete Windows checks: 252 tests (232 pass, twenty platform/optional skips), 17
planning checks; isolated Linux 252 (251 pass, one Windows-only skip). No running test
handle remains. Socket calls can still take their configured timeout after the transfer
deadline, and resolver/provider outages are not a hard billing cap. Live outage/shutdown
acceptance remains open. No actual provider request was made by these tests.


Official Colab issue #6087 confirms Ubuntu 24.04 rollout in September while notebook
Python stays 3.13. This exposed a genuine mistake: the probe required notebook Python
3.12 because that is the model's pinned interpreter. Inventory now names kernel_python;
credential-free bootstrap accepts 3.12/3.13 and retains isolated model Python 3.12 as a
separate target. No real notebook was downgraded or modified. The 3.13/3.12 boundary has
a regression, and actual generated bootstrap source already runs under local Windows
3.13 and isolated Linux 3.12. Native model interpreter provisioning is still unfinished.

Complete checks: Windows 253 tests (233 pass, twenty platform/optional skips), seventeen
planning checks; isolated Linux optional environment 253 (252 pass, one Windows-only
skip). Full Windows output retained in ignored scratch. Original live/provider/billing,
package, final review and owner gates remain open. All launched test handles polled
terminal.


Native Colab GGUF installation candidate added to the inspected payload: signed Ubuntu
snapshot prerequisites, isolated model Python 3.12/downloader hash lock and checked
llama archives, with a library-load check before a runtime-installed marker. It does
not alter SSH settings, transfer credentials or start a model. Launch rehashes every
staged file, verifies original operation/source proof, flushes an exclusive start record
and its directory, then starts a bounded detached installer with an explicit minimal
environment/private home. A missing launch acknowledgement cannot authorize retry.
The deadline wrapper is extra process hygiene, not independent shutdown/billing proof.

Actual generated launcher code is exercised in isolated Windows/Linux processes with
Popen replaced before system installation. It proves intent precedes launch, ambient
model credentials are omitted, source tampering refuses before launch, and a repeated
attempt cannot recreate intent. Native vLLM installation explicitly remains unprepared;
no unpinned fallback or supported-Colab claim. Complete Windows checks: 256 Python tests
(236 pass, twenty platform/optional skips), seventeen planning checks. Isolated Linux
256 (255 pass, one Windows-only skip). Test handles 35201/76588 polled terminal exit 0.
Actual APT/native/GPU installation, provider filesystem/footprint, own installer exit
monitoring, private SSH/model launch/health, connector registration and all original
release/live/owner gates remain open. No system package was installed by these tests.


Owned installer completion checks now retain the actual process object with operation,
root and source scope in the owned kernel. Nonzero exits override marker files, running
processes cannot become installed, and zero exit needs matching proof plus expected
runtime paths. Missing process authority stays unknown; no PID discovery/signalling.
Only approved phases and byte-count progress leave the collector, never raw logs.
Cancelled/expired waits issue no new query, and cancellation during a query cannot
advance to installation success. These states describe dependencies, not model or
provider-off confirmation.

Ten focused status/workflow tests include actual generated code, real owned local child
exits, forged/missing authority, misleading markers, private log text and cancellation.
Complete Windows checks: 266 Python tests (246 pass, twenty platform/optional skips),
seventeen planning checks. Isolated Linux optional environment: 266 (265 pass, one
Windows-only skip). Native APT/GPU/provider installation, private SSH/model health and
all original release/live/review/owner gates remain open. No system packages, credentials
or models were used in these status tests.


Colab native SSH transport foundation: scoped runtime-only access records require a
same-owner 0700 directory/0600 regular file, exact schema, operation hash, current token,
rental deadline, verified native origin and Ed25519 public-key wire format. No account
OAuth credential, shared CLI cache, auto-create or token command argument. Direct TLS
and zero redirects carry bounded native bytes; cancellation, parent pipe EOF and rental
deadline close this socket. The bidirectional bridge enforces output backpressure.
Concurrent closure now releases blocked readers/writers safely.

Inspected the pinned WebSocket HTTP-upgrade reader: its per-read timeout alone permits
continuous header trickle. Added a separate upgrade deadline/socket closure and an
actual local trickle test. Pinned native-frame/header tests and Linux file/pipe tests
pass. Published wheel SSH/runtime source hashes were verified; the earlier SSH cache
differs only in platform invocation/signal handling, so provenance uses exact wheel
bytes and does not claim cache identity. Existing Google notices are preserved.

Complete free Windows checks: 274 Python tests (247 pass, twenty-seven platform/optional
skips), seventeen planning checks. Isolated Linux optional environment: 274 (273 pass,
one Windows-only skip). Provider TLS/endpoints are replaced in these tests. SSH host-key
enrollment/OpenSSH integration, real native header acceptance, token-expiry/session
behavior, model/SSH serving and all original live/release/owner gates remain pending.
The transport foundation is not a supported Colab connector or a provider-off claim.


Strict Colab SSH client candidate: durable operation-owned client identity creation,
pending/pinned host enrollment through the selected authenticated runtime bridge and
isolated strict OpenSSH configuration. Host records are never silently replaced;
partial enrollment refuses a new scan. Current runtime access is refreshed per new
connection, token arguments/default SSH credentials/config/agents are excluded, and
one native forward blocks another command. Cleanup validates ownership and preserves
unrelated host files/sessions. The scanner requires an actually established provider
channel before trusting keyscan output, not output alone.

Nine Linux tests cover the actual single-use loopback byte bridge with simulated
provider transport, uncertain enrollment, changed pins, unowned files, native-session
exclusion and installed OpenSSH `-G` option parsing. Complete Windows checks: 283 Python
tests (247 pass, thirty-six platform/optional skips), seventeen planning checks. Isolated
Linux optional environment: 283 (282 pass, one Windows-only skip). Cryptographic SSH
and actual provider TLS/header/host-key acceptance remain unproven; no server/account/
resource/model was contacted. Existing private source/history/live/review/owner gates
remain open.

Identified a shared release blocker in model/status forwarding: free TCP port selection
releases the socket before SSH binds, and unauthenticated controller-loopback listeners
are broader than the owner-only control boundary. Both connectors need operation-private
Unix socket forwards and the generic endpoint/bridge contract migration. This remains
an explicit R1 gate; the new SSH client is not release-ready model access yet.

Shared private model/status forwards replace free-then-released TCP ports with
operation-owned Unix sockets. Core dispatch carries exact operation/resource and
socket instance/process identity; bridge and status clients verify private parents,
permissions, inode/device and Linux peer PID/UID before transmitting. Startup intent
and verified socket identities are durable; cleanup preserves unrelated/replaced
paths. Short socket namespaces are validated before rental allocation and are separate
from longer key-artifact paths. SSH keys use a neutral comment. Status HTTP header and
body reads share an overall deadline. Actual Unix HTTP/large stream/owned child-listener
tests cover readiness, cancellation, collision, permissions and scope mismatch.

A full Linux run exposed a test observation race: response bytes can reach the client
before the server's finally block closes its synthetic stream. The test now waits on
an explicit close event with a bounded timeout, preserving the cleanup assertion.
Provider SSH handshakes, forwarding and live billing remain unvalidated. This increment
neither registers Colab nor closes the overall R1 or other release gates.

Final automated evidence: complete Windows project checks passed, including 295 Python
tests (249 pass, 46 platform/optional skips) and seventeen planning checks. Isolated
Linux optional environment: 295 tests (294 pass, one Windows-only skip). No provider
requests or rentals were used. Independent exact-final-state review remains pending.

Colab explicit model-start candidate now rechecks the operation's staged source hashes,
private ownership/home, native installation marker and deadline over strict SSH. It
accepts only the original SSH rental. Optional HF credentials are read from an explicit
reference and sent only as SSH stdin, written exclusively with mode 0600 and never
included in notebook execution, commands or output. Existing credentials are preserved.
A flushed one-use start intent precedes the existing agent's minimal-environment launch;
uncertain submissions require recovery rather than replay. No live provider was used.

Seven focused tests cover authority/cancellation, wrong SSH resource, public-model input,
uncertain acknowledgement and actual generated Linux code over temporary owned source,
private credentials and intercepted child launch. Complete Windows checks: 302 tests
(254 pass, 48 platform/optional skips), seventeen planning checks. Isolated Linux optional
environment: 302 tests (301 pass, one Windows-only skip). Full connector orchestration,
model/health readiness, native vLLM and real provider/account/billing acceptance remain
required. All overall release and owner decision gates remain open.

Colab runtime coordinator now joins metadata/socket preparation, owned kernel startup,
actual capacity checks, source staging, installer launch/completion, scoped SSH enrollment,
explicit model start and private model/status forwards. Durable one-use setup intent
refuses replay after uncertainty. Side effects reread original receipt scope/resource,
connection/account, active protection, cancellation, deadline and desktop lease without
nested receipt locks. Cached installer progress avoids monitor use of a busy kernel.
Unknown local paths/identities are preserved after restart; only retained process handles
are closed. Native vLLM remains explicitly refused before allocation pending pinned setup.

Eight Linux coordinator tests cover ordered success, refreshed lease binding, uncertain
kernel no-replay, cancellation between stages, changed resource/cancel/expired lease,
unknown installer refusal, cancellation before forwards, and unrelated file preservation.
Complete Windows project checks:310 tests (254 pass,56 platform/optional skips), seventeen
planning checks. Isolated Linux optional environment:310 tests (309 pass,one Windows-only
skip). Provider transport and child execution are replaced in coordinator tests; no real
provider/account/credentials/installation/model/billing were used. Colab pricing and public
connector registration, all other release findings, live gates and final review remain.

Native vLLM dependency preparation resolves the existing pinned vLLM0.32.0 and downloader
2.3.0 into198 exact hashed wheel-available packages for Python3.12/Linuxx86_64/glibc2.39.
Generated by uv0.13.0 from a manifest with a neutral reproducible command; source/wheel
provenance and canonical LF hash recorded. Glibc2.28 wheel-only resolution fails for a
required llguidance dependency. The versioned documentation differs from pinned-source
CUDA requirements; the exact source and package metadata remain the dependency authority.
No installed wheel/import/GPU/footprint acceptance is claimed.

The large generated lock would exceed the current single-message kernel transfer once
combined with existing source. It is not in the runtime payload or native installer yet;
complete bounded transfer and installation before removing refusal. Full Windows checks:
311 tests (255 pass,56 platform/optional skips), seventeen planning checks. Isolated Linux
optional environment:311 (310 pass,one Windows-only skip). New artifact checks validate
exact hashes, pin count, source commit and runtime manifest version. No provider request,
rental or actual native installation. All live/review/owner and other release gates remain.

Native source transfer now uses an explicit native payload selection, leaving image-based
RunPod payload below its environment cap. Large Colab archives upload into an exclusive
operation/digest-scoped owned-kernel memory buffer in64KiB chunks, with exact offset,
size and hash acknowledgements. Complete buffer then enters the existing full archive
hash/allowlist/exclusive-directory stager. Existing kernel code and compressed/expanded/
regular-file caps remain unchanged. No upload files before full validation; cancelled,
uncertain or bad acknowledgements stop subsequent steps. Durable kernel execution proof
and setup intent continue to prevent unsafe replay. Unknown buffers/destinations persist.

Five new tests execute the actual generated large native-lock upload against temporary
files, including corrupt chunks/archive, wrong scope/offset, existing buffers/destination,
unchanged small image payload and uncertain/cancelled pipeline. Complete Windows checks:
316 tests (260 pass,56 platform/optional skips), seventeen planning checks. Isolated Linux
optional environment:316 (315 pass,one Windows-only skip). Native vLLM installer and status
integration remain incomplete; no real provider, credentials, installation or GPU used.

Native vLLM installer candidate now uses isolated Python3.12, generated wheel-only hash
lock, explicit index and no package cache. Package consistency, exact vLLM/PyTorch pins,
native extension import, bundled CUDA and one available supported GPU precede exclusive
flushed native proof. Installer status requires the retained successful process, marker,
Python path and matching engine-specific proof; running/failed processes cannot be masked
by readiness files. No credentials/model start in installation. Native payload preparation
now accepts the pinned engine; bounded launch generation does not embed the large archive.

Five verifier/proof tests and a Linux preparation test cover mismatched versions/lock,
missing extension, old CUDA/GPU, absent/multiple GPUs, failed installer and large bounded
launcher. Imports/hardware/child launch are simulated; temporary proof/source files are
real. Complete Windows checks322 tests(265pass,57platform/optional skips)+17planning checks;
isolated Linux322(321pass,oneWindows-onlyskip). Actual installation/import/driver/GPU,
measured footprint and live serving/shutdown/billing remain gates. No rental/provider or
real credentials used. Colab pricing/registration and overall release gates remain open.

Colab quote preparation now keeps selected rental price/availability unknown, separates
fresh account CCU baseline/count and applies the confirmed ceiling to account totals.
No invented rate by dividing account totals. Positive fresh balance/account/unit/scope
validation required. Unknown disk capacity is explicit and confirmation-bound with a
before-installation verification contract; core still validates every file size/reserve
and rejects known insufficient disks. Existing Colab probe verifies actual capacity before
staging/install; setup failure recovers only owned rental with provider confirmation.
Allocation/setup can consume units before a capacity rejection and shutdown.

Five tests cover quote semantics/staleness/account/scope/unit/balance, unknown-disk contract,
invalid file sizes and owned failure cleanup. Full Windows checks327(270pass,57skips)+17
planning checks; isolated Linux327(326pass,oneWindows-onlyskip). No provider/account/rental
or billing validation. Optional Colab connector registration remains to wire the prepared
auth/API/runtime/quote path; overall release findings/live/review/owner gates remain open.

Optional Colab connector now registers through ordinary trusted discovery alongside
RunPod without central provider branches/default connections. Explicit OAuth preflight,
Linux OpenSSH/pinned transport prerequisites, exact settings/selections and durable full
selection binding connect prepared auth/API/runtime/quote paths. Account/resource evidence
is checked before health or cleanup. Account-wide CCU telemetry keeps its scope; exhausted
balance/provider stop triggers failure. Attachments refuse termination; a stop request or
missing handle never establishes off. Only provider-confirmed absence discards owned keys.

Seven connector/discovery tests cover explicit reference, full selection changes, scope,
wrong account/resource/attachments, termination versus absence, unknown health and empty
fresh connections. Complete Windows checks334(277pass,57skips)+17planning checks; isolated
Linux334(333pass,oneWindows-onlyskip). Provider/account/SSH/runtime evidence is synthetic;
no real account/provider/model/rental/credential setup or billing test. Both connectors
remain candidates pending full client/package/independent-account/live acceptance and
exact final independent review; all broader release and owner gates remain open.

Desktop onboarding bridge now supplies read-only missing/damaged/configured startup,
Python/OpenSSH discovery and explicit independent controller enrollment. Failed verification
uses temporary trust and cannot overwrite existing persistent enrollment. Strict bounded
JSON stdin/stdout rejects duplicate/extra/oversized data with fixed errors, without echoing
input. Onboarding/status/quote/named connection calls use pinned client RPC; one-shot rental,
lease and stream calls are refused until UI-owned session lifecycle integration.

Seven tests include actual isolated subprocess input/output, no first-run filesystem/network
state, damaged-file preservation, fake enrollment verification and command refusal. Complete
Windows checks341(284pass,57platform/optional skips)+17planning checks; isolated Linux341
(340pass,oneWindows-onlyskip). Actual controller enrollment and account/provider access
remain untested. WPF interface/installer and all other release/live/review/owner gates remain.

Provider-neutral connector form contract now returns bounded declarative fields through
account-bound controller RPC and the desktop bridge. Both connectors provide optional
saved HF reference settings and runtime/selection fields. RunPod loads current GPU choices
only after explicit runtime/cloud/disk; final quote remains separate. Colab explains unknown
advance cost/capacity and account-total consumption. Labels are plain text; no markup,
callbacks or executable field kinds. Unknown properties, duplicate choices and bad bounds
refuse. A synthetic third connector supplies its field through the same core command.

Five form/protocol tests plus full Windows checks346(289pass,57skips)+17planning checks
and isolated Linux346(345pass,oneWindows-onlyskip) pass. All API/account/offer fixtures are
synthetic; no provider rental or real credentials. WPF renderer, installer and actual client/
package/live/provider/billing/final-review/owner gates remain. This is a contract increment,
not completed onboarding or a release candidate.

Windows WPF onboarding candidate now opens with no provider selected, prerequisite/
controller guidance, explicit independent enrollment and named connections rendered from
connector fields. No rental action is exposed before session liveness/recovery integration.
A fixed-command C# worker uses UTF-8 stdin, bounded stdout/stderr, timeout and owned-process
cancellation; callbacks run on the UI dispatcher. Labels remain text and blank optional
values are omitted. False booleans are preserved. Closing cancels retained owned work and
stops the UI timer. Windows PowerShell5.1 compilation caught unsupported input-encoding API;
raw UTF-8 input resolved it. The initial off-screen render was blank; showing the owned
preview off-screen before rendering produced a readable artifact, which was inspected.

Actual Windows tests exercise WPF button events, enrollment/no-preselected connector,
metadata control values, first-run child IO, UI dispatcher callback and cancellation.
Full Windows checks347(290pass,57skips)+17planning; isolated Linux347(345pass,2Windows-only
skips). Additional close-event ownership assertion passed focused native test after full
suite; production code unchanged. Visual preview is not live controller/account evidence.
Installer, rental session UI, actual clean package/provider/billing/review and owner gates
remain incomplete. No paid resource, real credentials or infrastructure were configured.

Desktop rental coordinator candidate now persists a scoped intent before one controller
request, validates confirmation/quote/plan/account/protection/limits and binds returned
receipts before starting the existing lease. Unknown model fields refuse before RPC.
Lost responses remain durable and prevent automatic replay. Actual UI pulse time reaches
DesktopSession, rejecting expired liveness after delayed responses. Known resource identity
cannot silently change. Stop delegates to the lease's latest receipt rather than overwriting
it with an older submission response. Recovery checks original account/quote/limit scope.

Six coordinator tests and two lease tests cover lost response, closing during submission,
confirmation/account/selection mismatch, unknown fields, terminal recovery, stale UI pulse
and resource replacement. Complete Windows355(298pass,57skips)+17planning; isolated Linux355
(353pass,2Windows-onlyskips). Provider/controller/session fixtures are synthetic. No rental.
The UI still cannot rent. Before enabling it, implement controller-side durable cancellation
for requests abandoned before a receipt exists, so late delivery cannot allocate. Missing
status alone never proves unsubmitted/off. Persistent pipe/session UI and all release gates
remain open; this increment is not a completed rental workflow.

Abandoned-request cancellation now persists a scoped permanent start denial under the
allocation lock; normal request/setup/final submit guard refuse delayed starts. Existing
receipts use normal owned recovery; in-flight allocation stays uncertain until observed
and confirmed off. A conservative initial request journal precedes receipt/worker creation.
Orphan journals block allocation and restore uncertain recovery rather than proving no
submission. Desktop archives a matching denied intent only when no local/server receipt
history exists; missing known evidence stays uncertain. Delayed initial replies cannot
overwrite terminal local cancellation or start a lease. No provider-off is inferred.

Nine new tests cover restart, preflight/after-submission races, orphan journals, wrong
connection/client, protocol scope, lost desktop replies and terminal-state preservation.
Full Windows364(307pass,57skips)+17planning; isolated Linux364(362pass,2Windows-onlyskips).
All provider/resource fixtures are synthetic, including delayed owned resources and an
unrelated resource preserved during cleanup. Persistent helper/UI rental wiring and live
provider/power-failure acceptance remain open; no paid resources or real credentials used.

Persistent session helper candidate now reads bounded confirmed begin/pulse/stop frames
on a dedicated input thread. Pulses/EOF remain visible during blocked RPC; active leases
receive only actual UI activity. One guarded cleanup thread stops renewal before scoped
recovery. Tests caught and fixed a join-before-thread-start race. A shared receipt-write
lock and terminal-state check prevent stale renewal replies from overwriting terminal
recovery. Delayed startup uses current actual pulse timestamps. Safe snapshots distinguish
pending/cancelled-before-submission from provider-confirmed off, and errors never echo input.

Actual pipe tests cover EOF during blocked submission, pulses during delay, malformed/
unconfirmed input and isolated missing-controller subprocess. A terminal receipt renewal
test covers stale state. Full Windows369(312pass,57skips)+17planning; isolated Linux369
(367pass,2Windows-onlyskips). Provider/session objects remain synthetic; no paid resources
or real credentials. Windows persistent transport and full rental UI/tool/recovery wiring
remain incomplete, so no rental control is enabled yet. All other release gates remain.


Windows persistent session client candidate: fixed-module hidden child process, bounded
UTF-8 frame queues and stderr, nonblocking UI pulse/close calls, stop/EOF plus bounded
owned-helper cleanup and confirmed-duration watchdog. No automatic background liveness.
Actual Windows 5.1 subprocess tests cover Unicode/spaced paths, explicit pulses, stop,
input framing and output limits. Full Windows checks: 370 tests, 313 passed, 57 skipped;
17 planning checks. Synthetic helper only; no live provider or billing validation.
Rental UI integration and all remaining release gates remain open.


WPF session dispatcher integration retains the helper, sends actual dispatcher pulses
every15seconds and closes after a60second gap rather than reviving expired liveness.
Stop/window close retain scoped helper cleanup. Bounded frame delivery shows off only
for an off receipt plus boolean confirmation; helper exit remains uncertain. Native WPF
tests cover explicit pulse, stale dispatcher, false/string confirmation and window close.
Full Windows370 tests (313 passed,57 skipped),17planningchecks passed. Rental navigation
remains disabled pending complete model/offer confirmation and durable recovery UI.
No real provider validation or paid resources.


Saved-request recovery candidate adds a bounded read-only local index, preserving damaged
files and treating local off as history rather than fresh confirmation. Bridge actions use
original enrollment plus Rental.refresh/abandon; no request replay or raw cancel RPC.
WPF recovery is reachable from startup/connections, refuses concurrent retained sessions,
and requires a separate unchecked cancellation confirmation. Tests cover read-only/no
network listing, changed-enrollment refusal, original request refresh without resubmission,
terminal-history distinction and unchecked native cancellation. Full Windows374 tests
(317passed,57skipped),17planningchecks; isolated Linux374(371passed,3Windows-onlyskips).
No live provider/billing validation. Full rental confirmation/navigation remains incomplete.


Generic rental offer navigation now filters named connections by descriptor rental mode,
with no default, renders connector selection forms and refreshes partial choices without
provider branches. Fresh quote view explicitly shows account/rate scope, unknown advance
rate/availability, balance, capacity/deferred disk validation and separate storage details.
It cannot allocate. Native WPF tests include a third synthetic connector, capability
filtering/no default and unknown-rate/account/storage wording. Full Windows374 tests
(317passed,57skipped),17planningchecks passed. Model planning/final confirmation remain
incomplete; live offers/provider/billing validation remains open.


Read-only model discovery RPC validates the named connection account, uses only its saved
HF credential reference, resolves/refetches immutable metadata and bounded inert config
JSON, and projects planner fields without raw cards/author data. GGUF base config can be
resolved separately. Same-origin redirects must retain the exact SHA path segment; no
remote code or weights are fetched. Free anonymous Hugging Face metadata/config acceptance
passed for SmolLM2-135M-Instruct at12fd25f77366fa6b3b4b768ec3050bf629380bac. This caught
and fixed a redirect handler mismatch: use StopRedirect preserving HTTPError inspection,
not the provider handler that hides redirect details. Seven new HTTP/protocol tests pass.
Full Windows381(324passed,57skipped)+17planning; Linux381(378passed,3Windows-onlyskips).
Focused discovery tests passed after exact redirect-segment tightening. No paid resources,
inference, gated-model, provider or billing validation. Desktop planning wiring remains.


Desktop model planning now uses a fixed bounded Windows5.1 worker reusing models.ps1,
with a worker-owned35second deadline and existing10second validators. Discovery-to-plan
WPF pages require explicit complete GGUF variant and conversation capacity; published
context/precision checks and experimental labels remain. Bridge filters launch fields and
checks finite positive memory estimates. Unknown safetensors families now explicitly say
Experimental. Explicit base-config overrides are honored even when a model has own config.
Full Windows385 tests (328passed,57skipped),17planningchecks passed before final numeric
summary tightening; focused5planner tests passed after tightening, including nonnumeric
memory refusal and actualWindows5.1 bothformat/context/filename checks. WPF native tests
pass completevariant/no-default and blankcontext. GPU capacity/storage/finalconfirmation
and tool handoff remain incomplete, with no rental submission button or live/paid runs.


Shared offer capacity/storage checks now run before desktop and controller submission.
RunPod offer memory is required and confirmation-bound; Colab explicitly declares actual
GPU validation before installation. Both existing runtime probes remain. Missing model
memory estimates, unknown GPU without contract, and known insufficient GPU/storage refuse
before allocation. WPF can refresh a model's capacity/storage preview; no rental starts.
Synthetic fixtures now declare the memory facts required of every connector/model plan,
without weakening production checks. Initial suite failures identified those obsolete
fixtures; after updates all392Windows tests completed (335passed,57skipped) plus17planning
checks. New tests cover market-memory changes/missing data, scope-bound capacity, no cache
credit, deferred checks and controller refusal before any provider allocation. No live
hardware/provider/billing validation or paid resources. Final confirmation remains open.


Final desktop confirmation connects reviewed offer/capacity/model to the persistent
UI-owned session. It freezes the snapshot, repeats account/rate/unknown-cost/storage/
experimental/controller limits, and requires blank rate/duration plus three unchecked
approvals. Nonfinite/below-offer rates, expired quotes and repeated clicks refuse. Actual
WPF button tests replace only the session launcher with a synthetic capture and verify
no default approval, rejection paths, exact frozen selection and one submission. No paid
rental was started. Full Windows392(335passed,57skipped)+17planningchecks passed.
DESKTOP.md consolidated to current behavior, removing stale disabled-flow descriptions.
The candidate still lacks tool handoff, existing-machine attachment, completed packaging
and live independent-account/provider/billing validation; no final review/publication.


Authenticated operation-key-scoped session_status now distinguishes allocation/startup,
ready, stopping and unresolved. Controller health tracks latest valid status/sample;
failed billing/health reads revoke displayed ready immediately. Desktop verifies scope,
boolean/phase consistency and sample age; host snapshots carry fixed phase data. WPF
shows plain-English phases, prioritizes stop requests and never equates ready with off.
Status reads do not renew leases; tests prove wrong-scope/stale/contradictory readiness
refusal and normal expiry cleanup. Full Windows394(337passed,57skipped)+17planning;
Linux394(388passed,6Windows-onlyskips). Focused protocol/nativeWPF tests passed after
last stale-ready phase wording fix. No real provider or paid validation. Coding-tool
launch remains to be connected through the existing session-scoped isolated overlay.


Session helper now accepts strict confirmed tool_launch frames through a bounded4command
queue; request IDs deduplicate up to16attempts. Launch processing is separate from pulse
reader and checks live UI/session, fresh scopedready and open relay before using original
model plan with tools.prepare/launch. Only explicit tool/native path/projectfolder/idle
acknowledgement is accepted; no arbitrary argv/env or secret-bearing response. Existing
normal settings and processes remain. C#Command uses the same bounded nonblocking queue.
Four tool tests cover child-overlay preservation, no secret/path echo, replay refusal,
unready/stopped/closed denial and stop during readiness RPC. Actual pipe test proves
blocked synthetic tool launch does not prevent pulses or stop detection. Full Windows399
(342passed,57skipped)+17planningchecks passed. WPF tool form and live tool compatibility
remain unfinished. No real tool/account/paid provider action was invoked by these tests.


WPF tool handoff form now requires explicit OpenCode/Codex/nativeexe/projectfolder and
unchecked idle/experimental acknowledgements. The retained helper receives a strict
command with one pending request ID; matching fixed results update the form without
secret/path echo or automated retry. Freshready expires after10seconds locally and
stop/uncertainty/exit disable launch. Stop moved to a fixed footer outside scroll content;
helper exit offers saved-request recovery. Native WPF fake-transport tests exercise no
defaults, unchecked refusal, one pending command, secret-free payload, matched result,
stale disable and fixed Stop location. Full Windows399(342passed,57skipped)+17planning
checks passed. No real coding tool or paid provider was opened. Live tool/Responses API
compatibility, gated models and release-package acceptance remain unvalidated.


Reconciled all22 release-finding IDs with desktop/planning/recovery/readiness/tool evidence;
all remain OPEN and live/package/owner gates are explicit. Latest Windows baseline399 and
older Linux394 checkpoint are distinguished; Linux refresh remains required. Source
inspection confirms Receipt.unresolved is rental-only and existing attachment disconnect
never invokes termination. Added bounded existing-machine SSH attachment contract: no
remote commands/installation/provisioning/shutdown, explicit pinned principal/key-path
reference, private owned forward, distinct lifecycle and continued external billing. This
is an implementation plan, not a supported attachment connector. No real target, credential
or infrastructure configured. Existing-machine implementation remains the next work item.


Existing-machine identity candidate validates explicit private target/account/ports/model,
verified Ed25519 pin and saved dedicated identity path, with private-file/link/size checks
without chmod/copy. Fixed noninteractive ssh-keygen derives the selected public identity;
account/resource fingerprints change with principal/key/target/model port. Linux-only
forward argv creates new local private trust, preserves existing files/socket paths and
uses one pinned ssh-N loopback forward with no config/agent/proxy/multiplex/local command.
No forward starts yet. Five tests pass on Linux (two portable/threePOSIX tests; Windows
skips3); real ssh-G parsing confirms configuration without network/socket actions. Full
Windows404(344passed,60skipped)+17planning and Linux404(398passed,6Windows-onlyskips) pass.
Ledger refreshed but all22findings remainOPEN. Actual SSH, supervisor, connector and
attachment controller/desktop workflow remain unfinished. No real keys/targets configured.


Attachment forward supervisor candidate validates original attachment identity, writes
durable intent before launch, verifies private Unix device/inode/UID/peerPID before ready,
and closes only its retained SSHchild/socket on strict pipe EOF/stop, malformed input or
liveness/startup deadlines. Fixed child shim uses Linux parent-death protection across
nonprivilegedexec; rejects setuid/capability binaries, no Pythonpreexec_fn or persistedPID
adoption. Changed sockets and old evidence are preserved without a disconnect/off claim.
Six real local-process/Unix-socket tests use a synthetic ssh/Python child: EOF, explicit
stop, liveness expiry, supervisor-loss child death, replacement socket and old evidence.
The initial short liveness fixture expired during startup; fixed to test expiry with its
control pipe held open, plus closed all fixture handles. Full Windows410(344passed,66
skipped)+17planning; Linux410(404passed,6Windows-onlyskips) pass. No liveSSH/credentials/
existingmachine used. Connector/core/desktop attachment integration remains unfinished.


Attachment ForwardClient now owns a fixed helper with bounded readiness/status reads,
nonblocking explicit pulses and bounded stop/EOF cleanup. It sends only operationID/key;
main loads original active receipt/connection/selected credential, refuses changed account
or detached receipts before credential access, and verifies returned private endpoint.
Final start gate reloads receipt/resource/complete connection under receipt lock; readiness
and pulses recheck authority. Parent EOF/stop is checked before child spawn. Helper loss
alone never confirms disconnect; only its closed acknowledgement does. Ten actual local
helper tests use fake identity/SSH children: successful scoped close/no replay, changed
account/receipt/resource and delayed disconnect, untrusted fields/no echo, no auto pulses,
helper loss uncertainty and pre-start EOF with zero SSHchildlaunch. Full Windows420
(344passed,76skipped)+17planning checks; Linux full419(413passed,6skipped) before lastEOF
guard, then all21attachment tests passed after it. No live SSH/account/credential or paid
resources. Connector registration/core/desktop attachment integration remains incomplete.


Internal SSHAttachment connector candidate has attachment-only descriptor/explicit form,
local identity preflight, one retained ForwardClient attempt and bounded read-only selected
/v1/models check. It always refuses renting/setup/termination. Principal changes revoke
pulse access; matching original local scope permits disconnect without reading a rotated
key. Matching private closed proof can reconcile local disconnect; unknown state is not
adopted or called off. Seven synthetic tests pass (6Windows+1Linux-only proof/preflight),
covering model mismatch, replay, changed principal/receipt and no rental actions. Full
Windows427(350passed,77skipped)+17planning checks pass. Linux focused7pass; preceding
full419/focused21transport evidence remains distinct. Module is underscore/internal and
not discovered until core/desktop attachment/model-selection relay guards are complete.
No real SSH/account/credential/provider or paid action. All22findings remainOPEN.

Attachment startup failures now retain conservative local recovery evidence. Before a helper supervisor starts, a verified saved operation can create a fresh never-started closed proof; an existing operation path is preserved and remains uncertain. The parent retains an explicit startup close acknowledgement. Connector attempts cannot replay after credential preflight failure, and matching completed no-helper attempts disconnect without rereading credentials; changed scope/resource is rejected. Linux synthetic helper tests: 12 passed; connector tests: 8 passed. Full Windows checks: 430 tests, 351 passed and 79 skipped, plus 17 planning checks. No live SSH, provider, credentials, billing or paid validation. Core/desktop attachment integration and release gates remain outstanding.

Desktop model relay can now bind an explicit served model ID, mandatory for attachment receipts. It rejects malformed/ambiguous JSON, missing or different model IDs and nonstandard constants before opening an upstream stream, across all inference routes; accepted bytes are preserved. Windows full suite passed 433 tests (354 passed,79 skipped) plus 17 planning checks, then focused suite passed 28 tests (26 passed,2 skipped) after adding all-route coverage. Attachment registration remains disabled pending controller-side model enforcement and core/desktop lifecycle integration. No live provider or billing validation.

Controller model streams carrying selected_model now validate one bounded HTTP request before upstream connection. Shared JSON validation avoids drift with the desktop. Fixed canonical headers discard credentials and ambiguous framing; only checked request bytes enter the existing backpressured transport, with no further client input forwarded. Complete endpoint/model scope is reauthorized during response streaming. Full Windows439 (356passed,83skipped)+17planning and Linux439(433passed,6skipped) passed. Subsequent Linux focused6 passed with actual bridge rejection-before-connect coverage and fixed-request transfer larger than the transport buffer. Attachments remain internal pending lifecycle metadata/core/UI integration. No live provider/account/billing evidence or paid actions.

Connector-neutral attachment lifecycle now saves original connection/model journal and receipt before helper startup, prevents replay/late abandoned starts, persists cancellation before waiting for startup, and exposes separately scoped access pulses/disconnect RPC. Confirmed local closure is detached; uncertain closure stays unresolved and blocks connection removal. Restart/close reconcile retained local evidence without reconnecting or requiring current credentials. Selected-model scope reaches the guarded controller stream; rental termination/protection paths remain separate. Fourteen lifecycle regressions cover races, journal loss/corruption, changed resource, key rotation and RPC scope. Full Windows454(370passed,84skipped)+17planning; Linux full451(445passed,6skipped), then focused14passed after final orphan-journal reporting. No live provider/account/billing or paid actions. Attachment UI/registration and all final release gates remain open.

Desktop attachment helper integration binds startup to reviewed account/resource/model preview, saves separate durable intents before RPC, retains lost-reply recovery and uses explicit attachment pulses/local disconnect rather than rental renewal/termination. Persistent session_host supports explicit attachment mode and keeps late detached evidence terminal. Full Windows465(381passed,84skipped)+17planning and Linux465(459passed,6skipped) passed. Subsequent Windows desktop attachment suite7passed, including real DesktopSession/controller Dispatcher with synthetic connector; no allocation/termination calls. Initial integration fixture incorrectly used a newly sampled clock value instead of a recorded UI timestamp; corrected fixture to match the production pulse contract. Visible WPF attachment page/recovery controls and connector registration remain incomplete; no real provider/account or paid actions.

Windows attachment selection/review/session and recovery controls now distinguish existing-machine access from renting. Capability filtering has no defaults; exact target is frozen with unchecked access/continued-cost approvals and once-only submission. Local disconnect is explicit and cannot assert off. Combined recovery index carries lifecycle mode; attachment recovery never calls rental cancellation. Native WPF events cover these controls. Full Windows467(383passed,84skipped)+17planning passed; Linux focused8 desktop attachment tests passed after recovery integration (preceding Linuxfull465 remains distinct). No live SSH/provider/account/billing validation. Optional SSH registration and attachment coding-tool metadata/handoff remain next, followed by full release gates.

Existing-model coding-tool handoff now validates an exact served alias and explicit user-declared conversation limit separately from provisioning metadata. It reuses child-only overlays, preserves normal tool settings and leaves engine/parser/vision/reasoning capabilities unspecified. SessionTools binds the tool model to the selected relay model. Native attachment review requires a blank-by-default limit; optional SSH connector discovery is enabled as experimental. Full Windows470(386passed,84skipped)+17planning and Linux470(464passed,6skipped) passed. Actual WPF review page rendered with synthetic data and inspected for fit/visible labels. No live account/SSH/tool/provider/billing acceptance, credentials or paid actions. All22 readiness findings remain open pending full closure evidence and release gates.

Persistent-storage recovery adapter now has validated account/operation/nonce/baseline/tier intent, one credential snapshot, final gate before one POST, no implicit retry, retained partial response ID and explicit manual identification. Name matches remain candidates because provider names are not unique. Official v2 API investigation established tier fields and cursor pagination; the adapter validates both. Existing-volume rental quotes now reject premium/unknown tiers rather than applying Standard pricing. Full Windows481(397passed,84skipped)+17planning and Linux481(475passed,6skipped) passed. New creation adapter is not exposed until durable core one-submit journaling, fresh quote approval and desktop recovery are integrated. No volume/account/provider call or paid resource was used in testing. All22 findings remain open.

Persistent-storage core now saves an atomic original-connection/intent/quote journal before submission and persists a final one-submit claim before POST. No replay after lost replies, failed response writes or restart; partial creation IDs can be directly observed, name candidates never auto-adopt, and manual recovery requires approval without replacing a known ID. Pending unsubmitted operations can close without claiming deletion. Connection changes during quote/gate are refused; Standard monthly pricing uses decimal arithmetic. Full Windows495(411passed,84skipped)+17planning; Linux full494(488passed,6skipped), then final focused13 passed. Creation remains unexposed pending controller RPC/desktop approval and recovery controls. No actual provider account/API, billed storage or paid resource was used. All22 findings and remaining release gates stay open.

Storage controller API now uses an optional persistent_storage capability, validates installed methods, and exposes typed quote/create plus operation-key-bound status/recovery/unsubmitted-close commands. Paged snapshots omit original connection credential settings; damaged journals do not hide healthy records. Synthetic connector tests prove extension without provider branches. Generic desktop storage_create remains refused until durable local intent/approval is integrated. Full Windows497(413passed,84skipped)+17planning and Linux497(491passed,6skipped) passed. First Linux run hit an intermittent two-second daemon-start fixture window; isolated runs reproduced it. Fixture now uses a ten-second monotonic deadline and bounded retained-child cleanup, with all original exit/receipt assertions intact; three isolated runs and full rerun passed. No live provider/account/billing actions or paid resources. All22 findings and remaining release gates remain open.

Pending persistent-storage cancellation now saves an original account/connection/enrollment start denial even before the controller creation journal exists. Creation and its final gate refuse denied operations after restart. A denial during preflight closes a proven-unsubmitted intent; after a submission claim it explicitly reports that creation may still complete and incur charges. No volume deletion or false unsubmitted claim occurs. storage_abandon RPC requires explicit confirmation and known-only close shares this denial path. Full Windows501(417passed,84skipped)+17planning and Linux501(495passed,6skipped) passed. Desktop durable submission/approval/recovery remains next; all22 findings stay open pending full closure and live acceptance. No paid resources or live provider/account actions.

Desktop storage intent increment: persist original enrollment, connection/account, reviewed monthly quote, exact target and operation ID before the dedicated creation RPC. A lost reply remains pending; never replay creation. Recover the original controller record through bounded pagination, require explicit candidate identification, preserve known identity against late unresolved responses and persist confirmed delayed-start denial without claiming volume deletion. Generic desktop RPC still forbids raw creation. Synthetic tests exercise the dedicated bridge, real core dispatcher, lost and undelivered responses, changed scope/price, damaged history and explicit recovery. WPF storage controls remain the next integration step.

Desktop storage helper validation: 10 focused tests passed. Full Windows checks: 511 tests, 427 passed and 84 skipped, plus 17 planning checks. Isolated Linux full suite: 511 tests, 505 passed and 6 skipped. These are synthetic lifecycle/HTTP tests; live provider, account and billing acceptance remain outstanding.

Connector storage forms: generic connector_form accepts storage only for an advertised persistent_storage capability and the verified original named account. RunPod supplies explicit Standard tier, data center and size 1–999 GB fields without market or creation calls. No provider-specific desktop branch is needed. Focused connector tests (18) and persistent-storage tests (20) pass, including changed-account/capability refusal. Native desktop storage screens remain the next step.

Storage form validation: full Windows suite 513 tests (429 passed, 84 skipped), plus 17 planning checks; isolated Linux suite 513 tests (507 passed, 6 skipped). No live account or paid resource validation.

Native storage workflow: capability-filtered named connections, connector-owned explicit options, fresh monthly estimate and frozen target review. Two unchecked approvals precede one dedicated desktop submission. Paged local request recovery offers original-operation refresh, explicit manual ID verification and delayed-start denial; never deletes volumes. Recovery validates provider observation identity before updating local evidence, distinguishes present/absent/unresolved/manual results and never equates absence with bill closure. Candidate IDs remain unselected. Native Windows controls exercise no defaults, frozen quote, duplicate clicks, separate recovery approvals and billing language. Synthetic native review render inspected at 1024x720; no real provider/account actions. Full Windows checks: 514 tests (430 passed,84 skipped),17 planning checks; focused Linux desktop storage11 passed, final native controls2 passed. Live provider/billing acceptance remains open.

Source-package increment: explicit committed-blob allowlist for product, tests, curated guides and third-party notices; deterministic ZIP inventory/timestamps/modes and SHA-256 manifest. Exclusive output creation; reject state-bearing tracked paths, symlinks and missing notices. Build neither includes Git history/untracked working files nor implies publication permission. Native source-installation/operation/privacy/support guides explicitly retain live/provider/billing/owner gates. Real temporary Git/ZIP tests prove reproducibility, selected-byte hashes, untracked exclusion and refusal boundaries. Actual candidate build/extraction/privacy/clean-package checks follow the committed builder; automatic Windows shortcut installer remains a separate incomplete gate.

Source builder validation: full Windows checks518 tests(434 passed,84 skipped),17 planning checks; focused Linux Git/ZIP tests4 passed. Actual candidate contents and extracted-package acceptance remain to be inspected.

Per-user source installer: inspect bounded manifest and exact file bytes before creating a new destination; reject linked source/path parents, traversal, case collisions, modified files and existing installations. Copy only manifest files, preserve source manifest and write a local installation receipt. Windows frontend checks Python, creates only a new revision-named shortcut in the selected per-user directory and never launches or touches credentials/state/settings/policy. No recursive deletion or overwrite rollback. Native temporary-directory shortcut and refusal tests accompany integrity/path/state-preservation tests. Actual packaged installer acceptance remains required.

Installer validation: full Windows suite before final linked-parent regression524 tests(439 passed,85 skipped),17 planning checks. Final focused installer suite7 tests: Windows5 passed/2 Unix skips; Linux6 passed/1 Windows skip. Native shortcut target/arguments and no-overwrite verified in temporary directories. Actual rebuilt package installation/full final-state suite remains required.

Actual source candidate2 at b7b113f passed manifest/CRC/notices/known-identifier/Gitleaks inspection, installation into a new spaced path with a temporary shortcut, empty native first launch and packaged17 planning checks. Installed-source Windows525 tests(439/86), Linux525(518/7) passed. docs/evidence/SOURCE_PACKAGE_ACCEPTANCE.md records exact revisions/archive hashes, environment scope and initial sandbox failure separately. Independent OS/account/provider/billing and final review gates remain open.

Independent-review correction increment: IR1 isolates Hub auth in a new private operation directory, strips alternate env auth, disables implicit auth for anonymous operation and keeps HF_HOME separate from persistent model caches. One selected private credential is consumed before model spawn; no second unvalidated reader. IR2 validates requested cache roots/parents before mkdir and refuses escaping cache links under a bounded scan, preserving internal Hub snapshot links and using only the dedicated fallback. Pinned Hub2.3 subprocess tests prove anonymous/selected credential resolution; Linux cache tests prove unrelated targets untouched. No changes to provider APIs, approvals, shutdown or credentials scope. Independent original review7285cda requested changes; corrected exact-state review and new package acceptance remain required.

Review corrections validation: full Windows530 tests(441 passed,89 skipped),17 planning checks; full isolated Linux530 tests(522 passed,8 skipped). Separately, exact pinned Hub2.3 remote-agent8 tests all passed, including actual token/header resolution, and Linux model14 tests all passed. Corrected-state independent review and package rebuild remain open.
