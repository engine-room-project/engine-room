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

## Corrected-state independent follow-up

Exact reviewed commit:97606be93f85a71e1f4e7bd714371d8b993b6804.
Reviewer:/root/release_independent_review; implementation agent:/root.
Verdict:PASS for code review only. Both findings addressed; no further material defect
found in the corrections. No independent-account/provider/GPU/billing approval is implied.

Code digest with base d017cc7:
2aa2c339a00dc96609a23d9347452c919d36acd2a06c3dcfcc075a9902a1aec6.
The repository verifier confirms that digest against the reviewer-supplied attestation.
The reviewer role was read-only; the implementer faithfully recorded its explicit report
in the ignored attestation file. This local record is not cryptographically independent.
Future behavior-changing edits invalidate review; prose-only evidence follows the configured
classifier exemption. Owner-controlled hosting/governance/licence/publication gates remain.
