# Persistent storage recovery candidate

Storage charges persist separately from disposable GPU rentals. Rental shutdown does not
remove network volumes. Engine Room never deletes an unrelated volume or infers ownership
from its display name.

The storage core and adapter expose enrolled-controller RPC for quoting, creation and
scoped recovery. Desktop creation remains unavailable until its durable local pending
request and approval flow are connected. The core saves one atomic journal before provider submission, including
the original connection, creation intent, reviewed monthly quote and submission claim.
A final gate persists its claim before the one POST. Lost replies and restarts never
resubmit creation. Desktop approval and manual recovery controls remain to be connected. Generic one-shot
desktop RPC refuses storage creation. The controller recovery index is paged and isolates
damaged records, and does not return connection credential settings. Listing records is
historical evidence; live provider reconciliation is a separate action.

The intent binds account, connection, operation, requested size/location/tier, a nonce and
the original inventory. The adapter uses one credential snapshot for account verification
and storage calls. It rechecks complete bounded inventory and the final submit gate before
one POST. A lost reply is never retried automatically. Partial response IDs are retained.
Name/size/location/tier matches are candidates, including a single match; explicit manual
identification must verify the original account and request. No delete operation is exposed. A partial creation-response ID can be verified by a
fresh direct observation of that exact ID. Name-only matches never become known storage
automatically. Explicit manual identification cannot substitute a different known ID.
A request proven not submitted can be closed without asserting deletion or billing relief.
Cancelling an original pending request can save a durable start denial even before a
controller journal appears. Delayed creation and the final gate honor that denial. If a
submission was already claimed, it may still complete and incur storage charges; the
record remains available for reconciliation, and cancellation does not delete it.

Existing-volume rental quotes currently support verified Standard storage below 1 TB.
Premium or unknown tiers are rejected, rather than priced using the Standard tariff.
Fresh Standard-storage monthly quotes are checked against the approved account, size,
location and tier. They are estimates of continuing storage charges, not provider spending
caps or automatic-removal deadlines. Live account/API/billing acceptance and the complete
desktop creation/recovery flow remain open.

Provider facts checked against official documentation:

- [v1 create schema](https://docs.runpod.io/api-reference/network-volumes/POST/networkvolumes)
  permits nonunique names and documents no idempotency key. Retry safety is not assumed.
- [v2 creation](https://docs.runpod.io/api-reference-v2/network-volumes/create-a-network-volume)
  supports an explicit tier and uses the already used api.runpod.io provider host.
- [v2 inventory](https://docs.runpod.io/api-reference-v2/network-volumes/list-network-volumes)
  includes tier and cursor pagination; a partial list cannot serve as a complete baseline.
- [Premium storage pricing](https://docs.runpod.io/storage/high-performance-storage)
  varies by data center and is shown in the provider console. A generic Standard tariff
  does not establish that price.

Evidence here is synthetic HTTP/account testing. No volume was created, billed or removed.

The desktop helper now saves the original controller enrollment, reviewed monthly quote, account, target and operation ID before submitting creation. Lost responses leave a pending local intent; recovery searches the original controller history and never repeats creation. An undelivered request can be explicitly denied before its controller journal exists. A submitted creation may still complete and incur fees after cancellation. Known volume identity survives late unresolved responses. The native desktop storage pages remain under implementation.

Native storage workflow: capability-filtered named connections, connector-owned explicit options, fresh monthly estimate and frozen target review. Two unchecked approvals precede one dedicated desktop submission. Paged local request recovery offers original-operation refresh, explicit manual ID verification and delayed-start denial; never deletes volumes. Recovery validates provider observation identity before updating local evidence, distinguishes present/absent/unresolved/manual results and never equates absence with bill closure. Candidate IDs remain unselected. Native Windows controls exercise no defaults, frozen quote, duplicate clicks, separate recovery approvals and billing language. Synthetic native review render inspected at 1024x720; no real provider/account actions. Full Windows checks: 514 tests (430 passed,84 skipped),17 planning checks; focused Linux desktop storage11 passed, final native controls2 passed. Live provider/billing acceptance remains open.
