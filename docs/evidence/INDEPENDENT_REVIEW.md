# Independent code review and correction status

Reviewer: independent release_independent_review agent (separate from the implementation agent).
Reviewed exact candidate:7285cda7c5bb903bfb671990e50f4855af143d57.
Verdict:CHANGES REQUESTED. No approving attestation was issued.

## IR1: ambient model authentication (P1)

The remote supervisor inherited alternate Hub authentication settings and pointed HF_HOME
at persistent model storage. Hub2.3.0 can select OIDC, legacy environment or cached-file
credentials, allowing an unselected account to authenticate model downloads.

Correction candidate: remove inherited Hub settings, allocate a fresh operation-private auth
home/token path, disable implicit auth unless an explicit credential was selected, and consume
only that private selected credential. Model serving preserves the private auth home and
uses a separate selected model cache. The redundant second credential-file reader is removed.
The pinned Hub2.3.0 subprocess regression covers OIDC/legacy/ambient tokens, cached token files,
anonymous request headers and explicitly selected credentials without network/account access.

## IR2: linked model cache roots (P2)

The previous storage check followed a requested linked cache root before defining its allowed
root. Downloads could write into unrelated data on an attached volume.

Correction candidate: reject redirected root/parent paths before creating directories; inspect
existing cache links for escapes, including downloader metadata, under a bounded entry count.
Legitimate snapshot links inside the selected cache remain usable. Refuse unsafe storage or
use the existing dedicated disposable fallback. Linux regressions prove linked roots/parents
and metadata links leave unrelated directories/files unchanged.

These are implementation corrections, not an independent approval. Full checks, corrected
exact-state independent follow-up and rebuilt actual package acceptance remain required.
Live independent-account, host, GPU, tool-protocol and billing gates remain separately open.
