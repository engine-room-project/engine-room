# Runtime dependency candidates and reproducibility evidence

Status: pinned candidates, not a validated GPU support matrix. Both initial connectors
must pass release acceptance with the actual package before public release.

The desktop and controller foundation use Python's standard library. The remote GGUF
downloader has a separate manifest and generated hash lock. The vLLM runtime is pinned
as a complete upstream OCI image rather than installing a floating pip release.

| Component | Candidate | Evidence and limits |
| --- | --- | --- |
| GGUF base image | NVIDIA CUDA 12.8.1, Ubuntu 24.04, linux/amd64 | Immutable digest and config/architecture verified; image not booted |
| vLLM image | v0.32.0, source commit 5df63a7203cdb9328d824a27b682e77c7b9928be | Immutable digest and config verified; CUDA 13 runtime; no GPU compatibility validation |
| System packages | Ubuntu snapshot 20261025T000000Z, noble/updates/security | Signed snapshot indexes reachable; complete installation footprint remains unvalidated |
| llama.cpp | b11539, CUDA 12.8 artifacts | Both archives downloaded and SHA-256 verified; not executed on a GPU |
| Hugging Face Hub | 2.3.0 plus generated transitive lock | Hash-checked installation and API import passed in isolated Linux Python 3.12.15 |
| Lock generator | uv 0.13.0 | Regeneration produced byte-identical lock output |

remote/runtimes.json is the authoritative image/artifact manifest. remote/bootstrap.sh
receives its snapshot date from that manifest through the payload builder. The installer
also reads artifact hashes from that manifest; do not maintain separate checksum tables.
The lock is generated from remote/requirements.in by remote/update-lock.sh; never edit
it by hand. Its current SHA-256 is
73f57190983e6c5c56bed440d0a6111498143bc3a2fb39ab288c2fdacd4ba3da.

The bootstrap keeps APT signature/hash verification enabled. Historical snapshot metadata
needs its validity-date check disabled, while the chosen snapshot URL remains immutable.
There is no unauthenticated-package option or trusted=yes source. Python installation is
isolated, hash-required, wheel-only and restricted to the explicit public index.

Model startup is a separate operation after pinned setup and credential transfer. No
account API key is sent to a GPU. Any Hugging Face key goes through a private file into
the model child's environment, then the file is removed. Backend output is suppressed to
avoid retaining credentials, signed URLs or prompt data. Status reports safe phases and
requires both expected model identities. It has no remote logout/delete endpoint.

Both engines check actual free space after installation and before model download.
Cache credit requires the exact selected file hash; vLLM checks its pinned snapshot cache.
Installation reserves are conservative estimates, not measured guarantees. Validate their
actual footprint and provider disk semantics before closing the storage/reproducibility
findings. CUDA/driver restrictions must be checked before offering supported combinations.

Third-party licence texts and preservation guidance are in THIRD_PARTY_NOTICES. The
Engine Room code uses the owner-selected MIT licence. No runtime images/binaries are
bundled into the source package by these download references.

Evidence covers source checks and dependency/artifact integrity, not real container boot,
provider allocation, billing, independent accounts or independent-host shutdown behavior.


## Optional Colab controller transport

`controller/requirements.in` selects google-colab-cli 0.7.5 for its kernel transport
and bundled public OAuth client. `controller/update-lock.sh` generates the Linux
x86_64/Python 3.12 hash lock with uv 0.13.0; never edit the lock by hand. Current lock
SHA-256: 34938c4d10eb73ddab9a4d0965686b881c74952cec2052b047557e8dd2f9602a.
The clean isolated 53-package install and offline kernel/state/PKCE smoke pass.
Core/RunPod do not require installing these packages. No Google account was used.
Actual Colab runtime installation still needs its own pinned bootstrap and acceptance;
this controller lock is not a claim that a Colab GPU or either engine has been tested.


Native GGUF ABI inspection: readelf version requirements on the verified b11539
`libllama-server-impl.so` include GLIBC_2.38, GLIBCXX_3.4.32 and CXXABI_1.3.13.
The small `llama-server` launcher alone has weaker requirements; inspecting it alone
would miss the actual server-library constraint. All 30 regular ELF candidates in the
archive were inspected without execution. The measured minima and evidence are recorded
once under `llama.native_abi` in runtimes.json; the Colab probe checks actual glibc.
Ubuntu/Python/C++ library installation and GPU loading still need native runtime proof.
The archive's retained licence text is unchanged. No binary was added to release source.
