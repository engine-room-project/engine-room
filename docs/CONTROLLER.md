# Independent controller implementation status

The local implementation contains a separate worker/deadline monitor, a Linux
owner-only Unix socket daemon and a pinned private SSH client. The RunPod rental
adapter is integrated in code. None of this has been deployed or validated against
an independent host or actual rental. Model streaming and UI-liveness-bound desktop
leases are implemented locally. Colab, application UI/tool integration and
existing-machine connection still need implementation.

## Protection and recovery

The controller records intent before allocation and marks submission durably before
the provider request. A separate monitor runs during allocation and setup. Retrying
an operation identity after a lost desktop response does not request another rental.
A candidate returned resource ID is retained even when ownership needs a new query.

- A live, healthy controller monitor and explicit independent-host enrollment are required.
- Managed rentals need a finite duration and positive hourly GPU-rate ceiling.
- Provider quote/balance and separate storage prices must be fresh. The final offer is
  checked again after payload preparation, immediately before durable submission.
  Changed costs, balance, disk, stock or account require review.
- Providers without a pre-allocation rate report unknown. The chosen ceiling is still
  mandatory; missing actual rate readings cannot keep a rental running indefinitely.
- Desktop leases expire after 120 seconds; heartbeats cannot extend the absolute deadline.
  Running enforcement also uses monotonic time. Reading status never renews a lease.
- Sustained health loss is bounded to 90 seconds; terminal setup/model failure stops
  immediately. Setup stalls are bounded to 300 seconds and total setup to 2700 seconds,
  also subject to the confirmed deadline. API/SSH calls must remain bounded.
- Stop remains durable. Off requires same-account provider absence confirmation.
  An unsubmitted intent cancelled locally is labelled cancelled, never off.
- Restart recovers outstanding rentals instead of resuming paid work. OS locking prevents
  a second daemon from recovering a live daemon's rental as abandoned work.
- Service shutdown with unresolved receipts fails explicitly. Stopping the service or
  removing its host does not establish provider shutdown; inspect/recover those receipts.

A single controller can lose power/connectivity, and providers can reject deletion.
This protects against desktop loss while controller/provider remain available. It is
not an unconditional spending cap. Storage remains separately billed. Machine IDs
and explicit enrollment detect configuration mistakes; they do not prove separate
hardware/power or authenticate someone holding a stolen SSH key.

## Private transport

The desktop uses an explicitly selected dedicated SSH key and independently verified
Ed25519 host key. There is no trust-on-first-use, SSH agent or ambient SSH configuration.
The endpoint is an explicit private-network IP, including private mesh addresses.
The controller service opens no TCP listener. Its Unix socket and state directory are
accessible only to its Linux user; peer credentials must identify that same user.

SSH invokes only a fixed wrapper. Bounded JSON commands cover connector discovery,
named connections with saved credential references, quotes, rental requests,
heartbeats, cancellation and paginated recovery status. There is no credential
read/write, arbitrary command or executable-path RPC. A dedicated forced-command
SSH key is required at deployment; the protocol itself is not a replacement for SSH
or OS permissions. Account and host identifiers are private local state, never package data.
Messages and provider/SSH exceptions are not logged. Generic refusals preserve
uncertainty rather than implying that allocation did not happen or a rental is off.

Provider and optional model credentials are entered directly on the controller in an
interactive terminal. They are owner-only files there, not uploaded from the desktop
or silently read from another application's configuration. See the deployment proposal
in [controller/README.md](../controller/README.md). No credential has been configured.

## Current evidence and remaining gates

Automated tests cover synthetic provider ownership, rates, allocation uncertainty,
blocked setup, deadline/lease expiry and deletion confirmation; actual local socket
permissions and peer checks; malformed/oversized messages; pinned client identity;
and an actual local Linux daemon crash/restart. OpenSSH's offline parser checks the
isolated configuration, including a state path with spaces. These do not prove the
remote SSH handshake, systemd service restrictions/restart, network policy or physical
independence. No real provider account or paid resource is used by these tests.

Before R4 can close, deploy only on the explicitly approved host/account, configure
credentials there explicitly, verify the restricted SSH key, service survival across
logout/reboot and controller identity, then test actual allocation/setup/desktop loss/
provider failure/recovery under a separately approved budget. Inspect provider state
and billing independently. Never substitute the local daemon test for this evidence.


## Session model access and desktop liveness

The desktop relay opens a session-owned loopback port and requires a random session
API key. It rejects browser Origin headers, other Host values, URL query credentials,
ambiguous body framing and unsupported routes. Only selected OpenAI-style model API
routes pass through; availability depends on the selected engine/model and remains
subject to live compatibility tests. Requests need an explicit JSON content length,
up to 64 MiB. Streaming output is forwarded incrementally without a response-size or
thinking-token cap. The relay never logs prompts or forwards its local key/tool metadata.

Model streams use the same restricted SSH command. A bounded control handshake selects
only the owning connector's private Unix model forward. It requires an active, unexpired
rental, healthy independent protection and fresh ready/provider-rate evidence. The
controller bridge rechecks authorization during streaming with bounded backpressure;
revocation closes access even when the model backend remains open. All renewal, stop
and model commands include a stable receipt scope hash, detecting a mismatched account,
connection, deadline or controller. This scope hash is not authentication; SSH remains
the authentication boundary.

Desktop heartbeats run at most every 30 seconds and require UI pulses within 60 seconds.
An orphaned helper stops renewal, closes its relay and attempts selected-operation
cancellation. A whole desktop loss leaves the controller's 120-second lease to expire.
A helper surviving a UI crash can add its UI-liveness detection interval before the
last lease expires. Provider deletion/query latency still applies; this is not a hard
billing cap. Neither failure nor a Stop click is reported as off without a confirmed
controller receipt. Local stop intent is durable before asynchronous cleanup; disk
failure cannot prevent the remote cancel attempt. Startup must not silently renew an
old session or discard a pending stop record.

Automated local Linux tests cover a real subprocess/Unix-socket model bridge, prompts
larger than the control-frame limit, incremental SSE and mid-stream revocation. The
SSH network hop is replaced by a local process in those tests. Windows tests cover UI
liveness, receipt scope, durable stop and transient file-sharing conflicts. A failed
stream cleanup cannot skip other owned streams or the listener. Real SSH, WPF event
wiring, coding tools, independent accounts, provider health/rates and billing remain
separate acceptance gates.


The final provider submission contract now includes a required one-use `submit_gate`.
Adapters call it after account/provider preflight and immediately before their allocation
POST, without further provider calls in between. It rechecks durable Stop, expiry,
protection and other recovery blockers under the receipt lock, then releases that lock
before network I/O. Deterministically refused unsubmitted work becomes cancelled;
a timeout after submission remains uncertain. Slow allocation still cannot hold the
recovery lock. Synthetic stop-during-preflight and late-blocker regressions cover both
adapter boundaries. Do not omit this guard when adding a connector.


Billing observations carry a connector-defined uppercase unit and an explicit `rental`
or `account` scope. The core performs no currency conversion. Confirmation binds both;
a changed unit or scope triggers cleanup instead of comparing unlike rates. A confirmed
zero rate is valid; missing rates remain unknown and cannot renew health indefinitely.
Terminal model/setup failure triggers cleanup even if billing is unavailable. A connector
must explicitly declare whether verified positive prepaid credit is required; postpaid
connectors can declare that no prepaid balance exists. RunPod still requires prepaid
credit. Every rental retains its positive rate ceiling, finite deadline and independent
protection. An account-total ceiling is not represented as a rental-specific price.

Model/status endpoints are typed operation/resource descriptors, not port numbers.
The controller checks private directory and socket permissions, original device/inode
and Linux peer PID/UID before sending data. SSH binds without unlinking existing paths;
cleanup preserves unknown replacements. Socket address length is checked before rental
allocation. Status HTTP headers and bodies share a bounded deadline; model streams
retain incremental output without an artificial response cap.

Connectors that cannot report disk capacity before allocation must explicitly declare
verification before installation in the confirmed quote. Core validation still checks
all published file sizes and reserve values; known insufficient disks refuse allocation.
The connector must probe actual capacity before installation. Failed setup enters owned
provider-confirmed recovery, and may incur allocation/setup charges before shutdown.
