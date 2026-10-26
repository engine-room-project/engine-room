# Colab extraction and validation status

The optional Colab candidate is registered for managed rentals through the same core
contract as RunPod. Account/API, owned runtime setup, private forwarding and account-wide
CCU telemetry are implemented. Client onboarding and independent-account live acceptance
remain required before release-supported status.
Nothing in this work authenticated a real account or allocated a runtime.

## Inspected upstream and dependency boundary

`controller/colab-source.json` records google-colab-cli 0.7.5, upstream commit
4025416a03361d2ff34d06a4523ae76ce4c9bbaf and verified wheel/source hashes. The published
client/auth/consumption files match the inspected upstream bytes. Required Google
licence text is preserved under THIRD_PARTY_NOTICES. No upstream OAuth client JSON,
credentials, session caches or old project history are copied into release source.

The optional Linux/Python 3.12 dependency set is pinned and hash-locked separately
from the standard-library core and RunPod. An isolated 53-package installation,
kernel/state imports and reduced-scope PKCE URL construction passed offline. That is
a dependency smoke test, not successful Google consent or independent-account proof.

The upstream CLI has shared-cache/ADC helpers, retries allocation by default and can
log request/response details at debug level. Its SSH wrapper disables host-key checking.
Engine Room does not invoke those paths. It uses explicit selected credentials, its
own bounded fixed-origin account transport and one controlled allocation submission.
Kernel/SSH/runtime integration must preserve these boundaries as it is completed.

## Explicit direct-host authorization

The prepared login command is `python -m engine_room_connectors._colab.auth --root
<private-state> --reference <chosen-reference>`. Actual host deployment and credential
setup need owner approval first. It runs only in an interactive controller terminal;
the authorization code is hidden and echo fallback is refused. Existing references
are not overwritten without `--replace`. No browser opens automatically.

Login constructs a PKCE flow using the public installed-application client included
in the pinned Google package. This is not a newly registered Engine Room OAuth app;
verify the account and consent client before granting access. Requested permissions
are limited to OpenID identity, user email authorization required by the session API,
and Colab. Drive and Cloud Platform scopes are excluded. Broader returned grants are
refused rather than silently accepted or automatically revoked. There is no ADC,
gcloud, environment or another application's cache fallback. If Google's real consent
or account policy rejects this narrowed flow, investigate a concrete solution; do not
broaden permissions by assumption.

The saved record uses Engine Room's selected credential reference and protected
controller storage. It drops email/profile fields. Refresh is fixed to Google's token
endpoint; compare-and-replace prevents an in-flight refresh from overwriting explicit
credential rotation. Each provider operation verifies the Google subject and binds
all of its requests to one access-token snapshot. The stored account identity is an
opaque subject hash, not a personal address.

## Allocation, ownership and shutdown

A deterministic notebook identity binds account, named connection and operation.
A pre-existing assignment returned before submission is not adopted or changed.
Durable allocation proof precedes one POST; neither the transport nor the adapter
retries an uncertain POST. The controller supplies a one-use final submission guard
that rechecks Stop, expiry, protection and newly appearing recovery blockers after
provider preflight. Its lock is released before network I/O so a late response remains
recoverable. Known candidate IDs survive incomplete ownership confirmation.

Cleanup requires original-account proof, matching operation mapping and a known
assignment. Only that assignment receives an unassign request. Existing-machine
attachment cannot use rental termination. An unassign acknowledgement is not off;
a later mapping/listing confirmation is required. Inconsistent or failed observations
remain unknown. The account's total assignment count is never shutdown proof.

## Costs and remaining acceptance

The inspected API exposes current account balance and aggregate CCU/hour, not a
pre-allocation per-rental tariff. The API labels that rate account-wide. The connector
must not present aggregate consumption, another job's usage or a stale heuristic as
this rental's quote. Safe ceiling/unknown-price presentation and rate attribution with
other active assignments still need implementation and real billing validation.

Before release, complete and test runtime/proxy setup and token renewal, actual GPU/
driver/disk checks, restricted-model credential ordering, terminal failure, long model
requests, desktop/controller/provider loss and recovery. The upstream SSH shortcut must
not bypass Engine Room's pinned identities. Real Google consent, independent accounts,
actual provider state and billing require separate approved validation. All original
Colab and provider-independent release gates remain open.

## Primary references

- [Official Colab CLI client](https://github.com/googlecolab/google-colab-cli/blob/4025416a03361d2ff34d06a4523ae76ce4c9bbaf/src/colab_cli/client.py)
- [Official authentication implementation](https://github.com/googlecolab/google-colab-cli/blob/4025416a03361d2ff34d06a4523ae76ce4c9bbaf/src/colab_cli/auth.py)
- [Account consumption schema](https://github.com/googlecolab/google-colab-cli/blob/4025416a03361d2ff34d06a4523ae76ce4c9bbaf/src/colab_cli/consumption.py)
- [Official SSH implementation](https://github.com/googlecolab/google-colab-cli/blob/4025416a03361d2ff34d06a4523ae76ce4c9bbaf/src/colab_cli/commands/ssh.py)
- [Published package](https://pypi.org/project/google-colab-cli/0.7.5/)


## Runtime proxy boundary (prepared)

`runtime_access` refreshes identity, durable operation mapping and the exact assignment
listing under one account-token snapshot. It refuses stopped, cancelled, expired or
attached records before access; duplicates, absent/mismatched mapping and account drift
cannot return runtime credentials. It returns only the selected runtime's short-lived
proxy token, never the Google account OAuth token, and hides URL/token from object repr.
No proxy credentials are persisted by this boundary. The caller must check expiry at
connection time and refresh through ownership verification instead of extending it.

The initial allowlist accepts HTTPS root origins strictly below `prod.colab.dev`, with
no userinfo, custom port, query, fragment or alternate path. Google's native runtime
URLs are documented in its [VS Code issue tracker](https://github.com/googlecolab/colab-vscode/issues/206).
This is a deliberately narrow initial runtime origin policy; other domains fail closed
pending inspected provider evidence. Token TTL must be a positive integer no greater
than a day. These synthetic checks do not establish current live response compatibility.
Kernel execution, redirect-free proxy transport, pinned SSH identity and runtime bootstrap
remain unfinished and Colab remains unregistered.


## Owned kernel setup transport (prepared)

Kernel startup reads the existing-kernel list, writes and flushes operation-bound
submission intent, then requires a final controller-authority callback before one
`python3` kernel POST. Returning a baseline kernel is an ownership failure; Engine Room
does not adopt, interrupt or delete it. A timeout, malformed response or damaged proof
cannot cause another startup POST. The selected runtime's account/mapping/list proof
is refreshed through `runtime_access`; no shared Colab CLI cache is consulted.

The execution path opens only the owned kernel's Jupyter channel. A direct verified-TLS
socket bypasses environment proxy discovery; redirects are disabled. Only the runtime
proxy token is sent in a header. No Google account token or credential query parameter
is sent. Raw WebSocket tracing is refused before private transfer. The pinned optional
websocket-client 1.9.2 frame parser is extended to reject oversized frame lengths before
reading their payloads; aggregate messages are limited to 2 MiB and 256 frames. Partial
payload reads check cancellation and execution expiry at least once per socket timeout.
Bootstrap output is limited to 64 KiB; execution has a bounded timeout (maximum five
minutes). This setup timeout is separate from model response generation limits.

Only fixed, credential-free bootstrap code belongs in this channel. Account and model
credentials must not be embedded in executed code. Requests disable history storage
and input prompts. A flushed executing record precedes sending code; completion needs
both the matching execute reply and idle message. Timeout or channel loss preserves
uncertainty: code may still be running, so setup must not replay it. Recovery remains
responsible for provider-confirmed rental shutdown. This path never deletes a kernel
or terminates an existing-machine attachment.

Offline tests exercise the actual hash-locked WebSocket parser, HTTP upgrade, fragmented
messages and cancellation using local socket pairs. TLS connection construction and
provider responses are replaced in those tests. Real provider TLS, token/header
acceptance, kernel lifecycle, pinned SSH, GPU bootstrap and independent-host shutdown
remain release gates. Registration is a candidate; it does not establish live provider support.


## Actual runtime inventory (prepared)

The owned kernel channel now has a credential-free read-only probe for OS, Python,
architecture/libc, NVIDIA CUDA support, exact GPU identity and both total/free GPU
memory, plus the selected filesystem's real free space. No hostnames, serials,
account credentials, cache contents, system edits or deletion are collected. Missing
GPU information remains unknown. GPU subprocesses have a fixed executable-search path,
minimal environment and timeout; no inherited account/model credentials are forwarded.

Validation checks the selected accelerator, one GPU, checked model memory/context and
precision, exact model file-size set and runtime-plus-download disk headroom. A prepared
native model profile currently requires Ubuntu 24.04, isolated model Python 3.12 and the pinned engine's CUDA
minimum. For GGUF it also enforces the inspected server binary's glibc requirement.
This is an early compatibility gate, not proof the native installer or GPU model works.
Unsupported native environments must fail setup and enter rental cleanup; they must not
silently upgrade the system, fall back to unpinned packages or delete files for space.

Generated probe code runs in isolated Windows and Linux subprocesses without importing
the checkout. Hardware mismatch, low free memory/disk, incomplete sizes, old driver/
libc and precision fixtures refuse. Real Colab inventory, native system-library/engine
installation, measured footprint, restricted-model transfer and model health remain open.


## Owned source staging (prepared)

After validating actual inventory, the owned kernel stages only the inspected model
source payload in a new directory named from the operation scope hash. The payload
hash, exact regular-file allowlist and extraction limits are checked before directory
creation. Compressed input, expanded archive and total source sizes are bounded; links,
traversal, duplicate members and unsupported entries refuse. Existing directories are
never adopted, overwritten or deleted. A flushed ownership record precedes extraction;
files/directories and the final staged record are flushed before acknowledgement.
Partial failure leaves owned state for rental recovery, rather than deleting anything.

The source payload excludes credentials/unknown model fields and retains third-party
notices. The generated staging code runs standalone over the owned kernel and requires
its normal final-authority gate. A lost or mismatched acknowledgement remains uncertain;
staging is not runtime-ready or model-ready. Tests execute actual generated staging in
isolated Windows/Linux processes and demonstrate safe refusal of a second attempt.
Native installation, SSH integration, actual provider filesystem/footprint and model
acceptance remain unfinished. No real machine was prepared by these tests.


Notebook Python and model Python are separate. Google's [Ubuntu transition announcement](https://github.com/googlecolab/colabtools/issues/6087)
confirms Ubuntu 24.04 was deployed in September 2026 while notebook Python stayed at
3.13. The read-only/bootstrap channel accepts notebook Python 3.12 or 3.13; it does not
require downgrading the notebook. The model installation target remains isolated Python
3.12 from the pinned profile. Actual provisioning and engine acceptance are still needed.
The earlier probe incorrectly required the notebook itself to be Python 3.12; that gate
is corrected with a 3.13-notebook/3.12-model regression. Old notebook/runtime images still
need actual OS/driver/libc checks and are not silently assumed compatible.


## Native GGUF installation candidate

The prepared installer uses the signed Ubuntu snapshot, an isolated Python 3.12 venv,
hash-locked downloader packages and the verified GGUF archives. It does not downgrade
the notebook, install/configure SSH, transfer credentials or start a model. It checks
native library loading before writing runtime-ready. That marker means dependencies
installed; model readiness still needs explicit private credentials, server launch and
both expected model identities. The native vLLM candidate below uses a separate pinned dependency lock and
engine-specific completion proof; live acceptance is still required.

Before launch the owned kernel rechecks the operation/source proof and each staged
file hash. An exclusive flushed start record precedes the detached child. Retries
cannot recreate that record; missing/mismatched acknowledgement remains uncertain.
The installer gets a minimal environment and private empty home, no ambient account,
Hugging Face or proxy settings. Its own setup process is bounded by the remaining rental
deadline, with a maximum 45-minute setup duration. This is additional process hygiene;
it does not replace the independent controller or prove provider/billing shutdown.

APT package changes occur only inside an authorized disposable rental. Existing-machine
attachment is not an installer mode. Source/launcher tests replace the actual system
installer and demonstrate intent ordering, no ambient credential transfer, tamper refusal
and no replay. Shell checks do not establish successful APT/native/GPU installation.
Actual provider setup/exit monitoring, measured footprint, pinned SSH, model serving,
Client integration and live shutdown remain release gates.


## Owned installer completion

The launch retains its actual process object in the owned kernel, bound to operation,
root and source digest. Status queries never search or signal a remote PID. A nonzero
exit is terminal failure even if a readiness marker exists; a still-running process
cannot be labelled installed. Zero exit additionally needs the original source/start
proof, exact installed marker and expected Python/binary paths. Missing process proof
(such as a restarted kernel) remains unknown and requires rental recovery.

Only approved phase identifiers and log byte counts are returned, never log contents
or arbitrary phase text. Byte-count changes can indicate progress during a long
artifact download; the controller's absolute setup/rental deadlines remain required.
Cancelled/expired waits issue no new kernel command. Failed/unknown installation
cannot proceed to credential transfer or model start. Installed dependencies are not
model readiness, stopped compute or provider-confirmed off.

Tests use real local child exits alongside synthetic runtime files, actual generated
kernel status code and hostile/missing proof fixtures. They do not establish a live
Colab installer, provider filesystem, GPU driver, private SSH or billing behavior.


## Native SSH proxy foundation (not enrolled yet)

The native proxy connects only to the verified runtime's HTTPS/WSS origin and
`/colab/ssh`, with a runtime token and per-operation Ed25519 public key in headers.
It has no account OAuth access, allocation, shared CLI state or auto-create path.
The direct TLS socket and zero redirects prevent environment proxy/redirect forwarding.
Upgrade has a separate deadline guard against a steady header trickle. Frames/messages,
stdio chunks and output backpressure are bounded; parent input EOF, cancellation or
rental deadline close only this proxy's socket. SSH traffic is bytes, with no JSON
coercion or artificial model response duration/total-output cap.

A short-lived runtime-only access file is cached in the operation's same-owner 0700
controller directory with mode 0600, no symlinks or shared read permission. The child
receives its path and operation scope hash, never a token in command arguments. The
record schema excludes account credentials. Expired/mismatched scope and unsafe origins
refuse before connection. This remains inside the already approved controller-user
credential boundary; it does not grant a new host/user account access. The runtime token
must be current for connection; established SSH still follows the confirmed rental
lifetime and local closure. Provider behavior across token expiry needs live validation.

The pinned wheel's SSH protocol source is recorded in controller/colab-source.json.
The inspected cache differed from the wheel only in Windows invocation/signal handling;
the native wire functions agree. Engine Room does not invoke the upstream SSH CLI,
which disables host checks and can auto-create a session. Its query-token behavior
is not copied. Header acceptance for the actual native endpoint is still untested.

This foundation does not enroll an SSH host key or start OpenSSH. Enrollment through
an authenticated provider/bootstrap path and strict pinned host checking must precede
any credential/model transfer. One native SSH session at a time, exact selected-resource
binding, full-session status/model forwarding and independent-host/provider acceptance
remain required. Local Linux private-file/pipe and pinned-library frame/upgrade tests
replace provider TLS/endpoints and do not prove live SSH or billing behavior.


## Strict SSH enrollment/client candidate

`ColabSSH` generates an operation-owned Ed25519 client key with durable creation
intent and neutral key comment. It never adopts pre-existing unowned key files.
Initial host enrollment reaches only a single-use loopback scanner bridged to the
selected runtime's authenticated direct-TLS native endpoint. A bare Internet keyscan
is not a trust source. The runtime account/mapping/URL verification remains required
when supplying access. Enrollment writes pending proof before scanning and pins the
unique returned Ed25519 host key to operation and resource. Interrupted enrollment
cannot silently retry with a new key. Changed host records fail without replacement.

Subsequent OpenSSH uses strict private known-hosts, only the operation identity,
no user/system SSH config, agent, password, keyboard-interactive, hostbased/GSSAPI
or certificate fallback. Its fixed isolated Python proxy command receives only private
access path and scope; no runtime token appears in arguments. Fresh scoped access is
requested for each new connection. A running native forward blocks another command;
cleanup signals only the owned local process handle and validates file ownership before
removal. Normal SSH configuration and unrelated files/sessions are preserved.

Local Linux tests cover the actual single-use byte bridge with a simulated provider
channel, interrupted/changed enrollment, original scope and unowned file preservation.
The installed OpenSSH client successfully parses the strict configuration with `-G`.
There is no local SSH server in this validation environment: crypto handshakes, actual
Colab host key/header acceptance and complete live SSH behavior remain unproven.

Shared model/status forwarding now uses operation-private Unix sockets rather than
reserved TCP ports. Endpoints carry the original operation/resource, socket device and
inode, and owned SSH process identity. Callers verify owner-only parent directories,
socket permissions and Linux peer credentials before sending traffic. Existing or
replaced paths are preserved; cleanup removes only recorded owned socket instances.
The short socket namespace is checked before allocation. Actual provider forwarding
and complete Colab runtime integration remain required; R1 is still open.

## Explicit model start candidate

After the owned native installer is confirmed, the prepared SSH start command checks
original source hashes and ownership, private runtime home, installation marker and
rental deadline. Optional model credentials travel only through SSH stdin into an
exclusive mode-0600 file consumed by the existing agent. They never enter notebook
execution code, shell arguments, output or account-token storage. Existing credential
files are preserved and cause refusal. A flushed one-use start intent precedes child
launch, so uncertain submission requires rental recovery rather than automatic replay.
The agent receives a minimal environment and suppresses raw model output.

Generated-code tests use temporary owned files and intercept child launch; they verify
credential permissions, exact intent scope, changed-source refusal and replay refusal.
The startup candidate is wired into the optional connector. Real native SSH,
credential transfer, model readiness, provider shutdown and billing remain live gates.

## Runtime coordinator candidate

The coordinator now connects owned kernel creation, actual hardware/storage inspection,
source staging, verified installer completion, strict SSH enrollment, explicit model
start and operation-private forwards. Preparation verifies model metadata and socket
paths before allocation. A durable one-use setup intent prevents repeating uncertain
kernel, installation or model submissions. Each side effect rechecks the original
receipt, resource, account/connection, active protection, cancellation, deadline and
fresh desktop lease. These checks read atomic records without taking nested receipt
locks. Provider access still refreshes and verifies the owning account per connection.

The monitor reads durable bounded setup progress while the owned kernel is busy; after
forwarding, it queries only the private status endpoint. Cleanup signals only retained
owned process handles. After controller restart, unknown local sockets and SSH identity
files are preserved rather than adopted or deleted; provider recovery remains required.
Native vLLM now has pinned installer preparation. Colab pricing,
client onboarding and independent-account live acceptance are still incomplete.

## Native vLLM dependency preparation

`remote/requirements-vllm.in` and its generated hash lock resolve vLLM 0.32.0 plus
huggingface-hub 2.3.0 into 198 exact wheel-available packages for Python 3.12 and
Linux x86_64/glibc 2.39. Regenerate with uv 0.13.0 using the neutral command in the
lock header; use the explicit PyPI index. `remote/vllm-native.json` records pinned
source/wheel provenance and the canonical LF lock hash. No source build fallback was
used. The glibc 2.28 target fails wheel-only resolution for required llguidance; do not
claim the vLLM wheel's own minimum glibc proves compatibility of its full dependencies.

This lock feeds the native installer candidate described below. Its compressed transfer
plus existing runtime source exceeds the single-message kernel limit. Native payloads
now use the bounded upload below; image-based runtime payloads omit native-only files. Actual installed footprint, import, driver/GPU
compatibility and live model acceptance remain unvalidated. The current 32 GiB reserve
is conservative planning data awaiting measurement, not a verified sufficient bound.

Pinned sources: [CUDA requirements](https://raw.githubusercontent.com/vllm-project/vllm/5df63a7203cdb9328d824a27b682e77c7b9928be/requirements/cuda.txt),
[common requirements](https://raw.githubusercontent.com/vllm-project/vllm/5df63a7203cdb9328d824a27b682e77c7b9928be/requirements/common.txt),
[package metadata](https://pypi.org/pypi/vllm/0.32.0/json).

## Bounded native source upload

Large native source payloads use at most 64 KiB of encoded data per kernel request,
within the existing 256 KiB code limit. A new memory buffer belongs to the original
operation and archive digest; existing buffers are refused. Each chunk requires the
exact scope, offset, size and chunk hash and returns a fixed acknowledgement. Only the
complete buffer reaches the existing archive validator and exclusive directory stager.
The 1 MiB encoded, 5 MiB expanded and 4 MiB regular-file limits remain in force.

No filesystem upload state is created before complete archive verification. The owned
kernel's durable execution proof prevents replay after an uncertain message; lost buffer
or kernel state requires rental recovery. Cancellation or a bad acknowledgement stops
subsequent chunks. Unknown destinations are preserved. RunPod's image payload excludes
the native dependency lock and stays below its environment cap. Tests execute generated
upload code against the actual large lock and temporary directories; live Colab message
acceptance and native installation remain separate validation gates.

## Native vLLM installer candidate

The isolated Python 3.12 installer selects the inspected model engine. For vLLM it uses
the wheel-only hash lock with an explicit package index and no package cache, runs
package consistency checks, then verifies pinned vLLM/PyTorch versions, native extension
import, bundled CUDA and exactly one available GPU with supported compute capability.
Only then does it write an exclusive flushed native-runtime proof. No account/model
credentials are used, and no model is started during installation.

Installer observation requires the retained owned process to exit successfully, the
installed marker and Python path, and engine-specific proof matching the lock/version,
CUDA and GPU capability. A marker alone cannot override a running or failed process.
Native proof tests use simulated imports/hardware and real temporary source/proof files.
Actual package installation, imports against Colab's libraries/driver, measured disk
footprint, model serving and independent-host shutdown remain unvalidated release gates.

## Fresh quotes and deferred disk verification

The inspected CLI `ccu-info` protocol provides current balance, account-wide hourly
consumption and assignment count. It does not provide a selected rental's advance GPU
price. The quote therefore keeps that price and availability unknown, displays the
fresh account baseline separately, and applies the confirmed CCU ceiling to total account
consumption. Other assignments can increase that total; only Engine Room's own rental
is eligible for its shutdown action. No per-rental rate is inferred by dividing totals.
A fresh positive compute-unit balance is required. See the [Colab FAQ](https://research.google.com/colaboratory/faq.html)
for dynamic availability and positive-balance requirements for remote control.

Colab does not supply verified pre-allocation disk capacity in this protocol. Quotes
explicitly defer capacity verification until the owned runtime exists, before source
staging or installation. Published file sizes and installation reserves remain mandatory;
setup probes actual free disk and rejects a model that does not fit. Allocation/setup
can consume units before rejection and provider-confirmed shutdown. Unknown capacity is
confirmation-bound and cannot silently count as sufficient. Known insufficient disks
remain rejected before allocation. This is not a guarantee of capacity or a hard bill cap.

## Optional connector registration

Trusted module discovery now registers Colab and RunPod through the same core contract.
A fresh installation still has no named connection, provider account or implicit login.
Colab preflight requires an explicit saved OAuth reference, Linux controller, OpenSSH
client tools and pinned transport dependencies. Only an optional explicit HF credential
reference is accepted in connection settings. GPU, memory shape and engine are explicit
and matched to the complete durable prepared selection before allocation.

All observation, model and shutdown actions require the original account/connection and
rental scope. Attachments are refused. A termination request closes only owned local
handles; final key cleanup requires provider-confirmed absence. Missing runtime handles
or uncertain ownership report unknown, never off. Account balance exhaustion and provider
termination report failure so core recovery can stop only the owned rental. Connector
contract/discovery tests use synthetic provider evidence and do not authenticate accounts.
