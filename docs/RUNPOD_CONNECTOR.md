# RunPod connector extraction status

Status: the optional rental connector is registered and integrated locally; release
support is still unverified. No actual provider account, rental, billing or independently hosted controller
has been tested for this release candidate.

Implemented against the documented GraphQL and REST v1 interfaces:

- Explicit saved credential references. Windows records use current-user DPAPI; Linux
  controller files require owner-only permissions. No environment or other-app fallback.
- Bounded JSON HTTP with no inherited proxies, redirects or automatic POST retries.
  Provider errors omit response/request bodies and credential details.
- Minimal account ID/balance queries. Account verification and recovery operations use
  one credential snapshot so rotation cannot turn another account's 404 into shutdown.
- Fresh account-bound GPU offers, filtered by explicit Secure/Community choice, requested
  disk capacity and optional selected storage data center. Unknown stock or price is not
  offered. Returned rates are explicitly GPU-only; container/network storage tariffs are refreshed
  separately and changes invalidate confirmation.
- Positive resource ownership requires account/connection/operation markers plus a derived
  operation name and disposable local storage. A name match alone does not permit deletion.
- Known-resource absence requires same-account confirmation. Pending allocations with no
  match remain unknown. Unrelated pods/volumes never block recovery of an owned pod or
  receive deletion requests. Attached machines and changed persistent storage are refused.

The integrated path prepares deterministic pinned runtime payloads, verifies restricted
model download access before allocation, rechecks the offer/protection before one POST,
pins rental SSH identity and transfers an explicitly selected model key over SSH stdin
before model start. It checks actual GPU/driver capacity and model/tunnel health. Private
model traffic uses the operation's loopback forward through the independent controller.
Saved volumes are explicit, separately billed and preserved; capacity planning does not
assume they contain usable cache. Actual disk/cache checks retain ephemeral fallback.

Still required: durable volume-creation intent/reconciliation, Colab parity, application
onboarding/tool integration, actual service/SSH/independent-host verification and live
provider/billing/package acceptance. Runtime installation reserves are unvalidated estimates.
No finding is closed solely by automated local or mocked provider tests.

## Provider protection research update

The official GraphQL schema additionally exposes stopAfter and terminateAfter on the
on-demand allocation input, although the inspected REST create schemas did not. Presence
of these fields does not prove enforcement, allocation/setup coverage or read-back
verification. Investigate them as possible native backstops before relying on them or
concluding that provider-native protection is unavailable. No paid probe was performed.
The owner-approved independent controller remains the implementation path pending proof.

## Official references inspected

- https://graphql-spec.runpod.io/ (account identity, GPU offers, allocation input schema)
- https://docs.runpod.io/api-reference/pods/GET/pods/podId (pod identity/environment)
- https://docs.runpod.io/get-started/credentials (explicit API key permissions)
- https://docs.runpod.io/pods/pricing (compute/storage distinction)

These sources can change. Pin the tested interfaces/dependencies and retain separate live
validation. The source package must not include any user's credentials or recovery state.
