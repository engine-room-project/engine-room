# Supported combinations and acceptance status

No combination has release-supported status yet. The rows below are implementation candidates;
automated checks do not prove real provider, GPU, account, tool-protocol or billing behavior.
Both initial connectors must pass the full release gates before publication.

| Component | Candidate combination | Current limits |
| --- | --- | --- |
| Desktop | Windows 11, PowerShell 5.1/WPF, Python >=3.12, OpenSSH Client | Native controls/child tests pass; clean packaged installation pending |
| Controller | Independent Linux, Python 3.12, OpenSSH, reviewed persistent service | Synthetic lifecycle/transport tests; approved live deployment pending |
| RunPod rental | Named explicit API connection, private owned runtime, GGUF or vLLM | Fresh offer/storage validation; independent account/GPU/billing pending |
| Colab rental | Named explicit OAuth connection, optional pinned controller dependency, GGUF or native vLLM | Narrow consent, actual quota/runtime/shutdown/billing acceptance pending |
| Existing model | Optional SSH connector, explicit host key/identity/model/context | Experimental read-only access; no provisioning or shutdown authority; live acceptance pending |
| Persistent storage | RunPod Standard, explicit data center, 1–999 GB | Continuing monthly fees; one-submit/recovery controls tested synthetically; live billing pending |
| Coding tools | Explicit session-scoped OpenCode or Codex child overlays | Experimental; actual tool versions/protocol acceptance pending; normal settings preserved |

Remote artifact versions, hashes, CUDA requirements and system snapshots are authoritative in
remote/runtimes.json and the generated lockfiles. See docs/DEPENDENCIES.md. GPU memory/disk
planning must match the selected runtime and actual machine; no particular desktop GPU,
private address, account, machine name or default provider is assumed.

Untested models remain selectable as experimental. Exact files/shard sets, revision, runtime,
precision and context must validate consistently in planning and launch. An experimental label
does not bypass capacity, credential, private-access or shutdown requirements.
