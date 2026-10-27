# Release findings and evidence

All 22 findings remain **OPEN**. Implementation and automated evidence below are partial
progress, not closure. Both initial rental connectors and the optional attachment connector remain candidates. Four unpublished source packages have same-machine inspection/installation evidence in
`docs/evidence/SOURCE_PACKAGE_ACCEPTANCE.md`. Independent-account provider/billing acceptance remains incomplete. Code review passed
at80ea9de after the security corrections and MIT packaging follow-up; any later behavioral
edits require exact-state follow-up. No product source has been pushed.

| Finding | Required outcome | Implementation and relevant tests | Remaining closure evidence |
| --- | --- | --- | --- |
| R1 | Session-owned private endpoint | `55b7c11`: operation/resource-scoped Unix forwards, private parent/socket and inode/device/peer PID checks; scoped desktop relay. `test_private_endpoint.py`, `test_desktop_session.py`, `test_colab_ssh.py` | Actual SSH/provider handshakes, private network, collision/revocation and both live connectors |
| R2 | Dependable clean onboarding | Windows entry point, prerequisite/controller/named-connection forms and empty first run; `bd93798` desktop candidate, `test_desktop_bridge.py`, `test-desktop-ui.ps1`, `test_connections.py` | `b7b113f`: verified new-directory per-user source installer and native shortcut tests; actual packaged installation/first launch pass on the development Windows account. Independent-account installation, prerequisite recovery and complete onboarding remain open |
| R3 | Full-session tunnel/model health | Private status, terminal tunnel/model failure, bounded streaming revocation and fresh scoped Windows readiness (`640c1dc`); `55b7c11`, `5544608`, `0361cc8`; `test_desktop_session.py`, `test_private_endpoint.py`, `test_colab_runtime.py` | Live full-session setup/serving/failure cleanup on both providers |
| R4 | Shutdown independent of desktop | Separate worker/monitor, receipt deadlines/leases, owner-only controller transport and UI-liveness-bound desktop renewal; persistent helper/dispatcher pulse, EOF, stop and stall tests (`06f9ff9`); `test_lifecycle.py`, `test_controller_transport.py`, `test_desktop_session.py`, `test_session_host.py`, native WPF tests | Credential-free independent host/service/private SSH deployment and own-service crash recovery now pass (CONTROLLER_HOST_ACCEPTANCE.md). Live desktop-loss rental cleanup, actual host reboot, provider outage and confirmed billing termination remain open |
| R5 | Credentials precede restricted model | `d673456` scoped SSH stdin/private file and one-use start intent; `3726cfe` read-only pinned discovery uses only the named connection model credential; `test_colab_model_start.py`, RunPod runtime tests, remote supervisor tests | Live restricted model with explicit credentials on both providers; no secret leakage in real failure paths |
| R6 | Storage-aware planning | `74f720e` shared pre-allocation GPU/storage fit plus actual setup probes, offer-bound RunPod memory and deferred Colab checks; Windows planning/disclosure/confirmation. `test_planning.py`, `test_colab_probe.py`, `test_colab_pricing.py`, model/desktop tests | Actual native footprints, disk exhaustion and installed UI acceptance; persistent storage lifecycle. Planning reserves are unmeasured |
| R7 | Explicit credentials | DPAPI/Linux private records, selected OAuth/API references, reduced-scope login and refresh CAS; both registered connectors (`0361cc8`). `test_colab_dependency.py`, `test_colab_connector.py`, credential tests | Actual full onboarding with independent consent/accounts/rotation; no implicit account import |
| R8 | Preserve unrelated resources | RunPod account/operation markers; Colab deterministic notebook/proof/mapping/listing ownership and no baseline-kernel adoption; exclusive staging and delayed-request start denials (`b6ef5ea`); connector attachment refusal; `attachment_identity.py` explicit read-only SSH argument candidate with synthetic/ssh-G checks. API/kernel/staging/connector/identity tests | Live unrelated resources in independent accounts remain untouched; independent existing-machine acceptance (core, desktop and tool handoff now implemented synthetically) |
| R9 | Reproducible dependencies | Immutable OCI/signed snapshot/GGUF hashes; `e6d6dc0` native vLLM lock/provenance; `eb4b1ce` bounded transfer; `6de9728` native installer proof. `test_payload.py`, `test_colab_upload.py`, `test_native_vllm.py` | Actual native/container installation/import/GPU matrix and measured footprint; clean actual package and tool dependencies |
| R10 | Accurate private access guidance | Strict operation host enrollment, no SSH agent/config fallback; runtime-only transport tokens and private forwards. SSH/proxy/endpoint tests | Actual provider token-header/host-key acceptance, device identity, expiry/revocation and private-network instructions |
| A1 | RunPod-only first run | Both modules discover independently; empty initial connection store. `test_colab_connector.py`, connection/discovery tests | Actual package RunPod-only onboarding without Colab login/dependencies/configuration |
| A2 | Preserve allocation uncertainty | `eee79c8` desktop intent before RPC, `b6ef5ea` journal/start denials and late-reply terminal preservation; one provider POST/candidate identity, no-match remains uncertain; owned-kernel/upload/install/model start do not replay. API/kernel/upload/lifecycle tests | Actual delayed/lost provider responses and controller restart for both providers |
| A3 | Account-bound recovery | `15c8724` original-enrollment desktop recovery, scoped API observations and provider identity verification; OAuth CAS; `0361cc8` checks returned account/resource/operation evidence. API/auth/connector/recovery tests | Actual independent accounts, rotation and delayed recovery on both providers |
| A4 | Durable volume creation intent | Validated account/operation/nonce/baseline/tier `VolumeIntent`; internal tier-explicit one-POST adapter with complete bounded inventory, partial-ID retention and nonunique-name candidates. Explicit manual identification checks original scope; `test_runpod_volumes.py`. Existing-volume quotes reject premium/unknown tiers | Core atomic journal, durable one-submit claim, restart/no-replay, exact quote binding and scoped manual identification now have synthetic tests (`test_persistent_storage.py`). Enrolled-controller scoped quote/create/status/recovery RPC and capability discovery now have synthetic tests; bounded listings omit credential settings and isolate damaged journals. Durable original-scope start denials now forbid delayed/preflight creation, with already claimed creation retained as potentially completing. `726ec66`, `3fed51d`, `0e28547`: durable desktop pending requests, scoped connector forms, frozen monthly review, explicit continuing-cost approval and recovery/denial controls have synthetic/native tests. Live storage/account/billing acceptance remains open; generic raw creation stays blocked |
| A5 | Prompt terminal setup failure | Retained owned installer process overrides markers; fixed safe progress; `6de9728` engine-specific native proof. Installer/runtime/connector tests | Windows candidate now maps startup/stopping/unresolved and verified-off states; live bootstrap/dependency/model failure, useful error reporting and provider-confirmed cleanup |
| A6 | Bounded health loss | Lease/deadline/stall/health-loss monitoring; bounded HTTP/WS headers/frames; both connectors supply health. Lifecycle/transport/connector tests | Actual independent host, provider/network loss and billing confirmation. Controller/provider availability remains a design limit |
| A7 | Atomic isolated receipts | fsync/replace, directory flush, corrupt record isolation, Windows sharing retries and durable source/setup intents. Record/recovery/staging tests plus desktop read-only damaged-record index and scoped recovery (`15c8724`) | Integrated interruption/power-failure evidence and actual installed package recovery |
| B1 | Cleanup continues past unresolved records | Mixed corrupt/pending/known receipts and write failures covered; both connector boundaries implemented. Recovery/API/lifecycle tests | Both live adapters with mixed interrupted operations; actual installed package recovery |
| B2 | Final lock-time allocation gate | One-use final submit guard after provider preflight; late blocker/stop tests. Both registered connectors pass the guard to one POST | Live ambiguous provider submission/recovery and exact final review |
| B3 | Consistent filenames | `7a0da3b` fixed Windows planner worker reuses shared planning/runtime validators, with explicit native context/precision; both payloads use shared launch validation. Planning/model/desktop worker tests | Actual package/UI and both provider acceptance |
| B4 | Exact GGUF shard set | Exact canonical 1..N validation; Windows variants filter complete shards without preselection. Missing/duplicate/out-of-range/mixed-total and actual Windows worker/WPF tests | Actual package/UI and both provider shard acceptance |
| B5 | Fresh quotes/balance | Quote age/confirmation binding; RunPod fresh market/storage tariffs; `ed3ff23` Colab account telemetry keeps rental price unknown and total-account ceiling explicit. `d78ba77` frozen Windows review with explicit hourly ceiling/duration/unknown-cost/scope disclosure, stale and repeated-click refusal. Pricing/lifecycle/connector/native WPF tests | Actual installed UI and live stock/prices/balance/billing. Colab advance GPU price is not verified by account totals |

## Current automated evidence

The desktop-storage checkpoint passes complete `sh scripts/ci/project-checks.sh` on
Windows:514 Python tests (430 passed,84 platform/optional skips), plus17 PowerShell
planning/discovery checks. The previous isolated Linux full checkpoint passes513 tests
(507 passed,6 Windows-only skips), followed by the final desktop-storage suite11 passed.
Storage tests cover one-post boundaries, original-account credential snapshots, lost/partial
replies, nonunique-name candidates, explicit manual identification, tier mismatch and
complete bounded pagination. Native controls cover frozen review, unchecked approvals,
one submission per review and candidate/absence language. A synthetic storage review
render was inspected. Live provider/account/billing behavior is unverified.

Native WPF attachment events verify capability filtering, unchecked approvals, explicit
conversation limits, frozen submission and refusal of machine-off claims; a synthetic
native render was inspected. Existing-model tool overlays preserve normal configuration
and do not infer engine/parser/vision/reasoning capabilities. Optional SSH is experimental.
Model guards, backpressure, cancellation races, journal replay denial, rotated-key local
recovery and scoped RPC have automated coverage. Final-state suites remain a release gate.
Syntax/governance structure and normal local secret hooks pass.
Remote CI has not run: no product source has been pushed.

Tests include real local files, child processes, OS pipes, private Unix sockets, Windows5.1
compilation and native WPF events. Provider/account/SSH/GPU behavior is synthetic where
stated. Actual tool-form events use a fake retained transport, never a real tool launch.
Readiness is not shutdown; a local saved off receipt is history, not a fresh provider check.

A free anonymous Hugging Face metadata/config path resolved
HuggingFaceTB/SmolLM2-135M-Instruct at12fd25f77366fa6b3b4b768ec3050bf629380bac.
This is metadata evidence only. It establishes neither model inference nor restricted
access, independent account behavior, provider state or billing. No real account credentials,
paid rentals or shared infrastructure were configured for these implementation checks.

## Cross-cutting gates still open

- Independent-account source-package installer/prerequisites/onboarding acceptance. Same-machine
  packaged installation and fresh-state first launch now pass. Windows entry point,
  plain-English forms, confirmation, session/recovery and tool handoff are implementation candidates,
  with native automated tests; they have not passed installed independent-account acceptance.
- Existing-machine attachment core/transport is implemented and tested synthetically, with no
  implicit provisioning or termination authority. Desktop connection/recovery pages now have
  native automated evidence; explicit existing-model tool metadata/handoff and optional
  experimental SSH registration are implemented. Independent live acceptance remains open.
- Persistent-volume creation/reconciliation and desktop approval/recovery are implemented
  with synthetic evidence; actual account, persistent billing and manual-removal acceptance remain open.
- Coding-tool isolation now has session-helper/form plus fake-child/config preservation evidence; real tool versions,
  protocol/model compatibility and existing project/admin policy acceptance remain open.
- Initial source packages are built and inspected; full source/history/package privacy
  review and independent-account clean install remain open.
  Publication history is separate from preserved local development refs; only the inspected
  publication branch may be proposed for upload, with fresh scans before its first push.
- Independent accounts/configuration and live provider, shutdown and billing acceptance,
  with a separately approved concrete budget for paid validation.
- Code review passed at80ea9de; preserve exact-state coverage through remaining validation.
  The owner selected MIT and approved public repository visibility; the owner-only maintainer
  team and no-bypass main ruleset are established. The public repository is still empty.
  Initial governance ratification, remaining live validation and final publication approval
  remain open. The independent credential-free controller has deployed-host evidence.

Required third-party notices remain part of source/payload inspection. Any behavioral edit
after final review invalidates that review. No row above has an evidence-backed CLOSED status.
