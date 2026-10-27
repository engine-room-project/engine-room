# Source provenance and notices inventory

The release repository has fresh history. Shared model planning and model-server argv,
download and launch code were adapted from the existing Engine Room development snapshot
f8c3ad82b9fd49f1aff300379a1211fd66623423 after source inspection. The import excludes
provider offers, personal defaults, local state, private endpoints and old Git metadata.

The release foundation otherwise uses Python standard library code written for this
release. Adapted Colab protocol portions retain their Google attribution and Apache-2.0
notice. Required upstream licence texts are preserved in THIRD_PARTY_NOTICES; no runtime
executable binaries are bundled. Downloading dependencies at runtime does not authorize
omitting applicable notices from any bundled files. The owner selected MIT for Engine Room code;
this local development candidate is not an authorized public release.

Shared model runtime imports huggingface_hub only for GGUF download and executes either
vLLM or llama.cpp. Those dependencies, backend images, GPU libraries and setup tools need
a pinned provenance/licence inventory and validation before release. Nothing here claims
those backend dependencies have been reproduced or live-tested for this candidate.

RunPod API/HTTP behavior was extracted and hardened from the same development snapshot:
bounded header-authenticated requests, account identity binding and scoped resource
recovery. No old account-empty restriction, credential fallback, local watchdog claim,
private address or historical state was imported. New implementation uses the standard
library and documented provider interfaces; no third-party library source is bundled.


Read-only coding-tool discovery adapts the inspected conventional-location approach
from the same development snapshot, without private endpoints, automatic registration
or configuration writes. Process-scoped tool settings and launch code were written
for this release using the Python standard library and current official configuration
interfaces. No existing user settings, credentials or executable binaries were imported.


Colab account/API wire behavior follows the inspected official google-colab-cli 0.7.5
source; exact commit/file/wheel hashes are recorded in controller/colab-source.json.
Google's required licence text is retained. Engine Room's explicit record/refresh,
fixed-origin transport, no-retry submit proof and recovery boundary are implemented
separately; shared CLI auth/cache/update and unpinned SSH shortcuts are not imported.


Native Colab SSH/runtime protocol inspection additionally records the exact published
0.7.5 wheel files `colab_cli/commands/ssh.py` and `colab_cli/runtime.py`. Their source
hashes are explicitly labelled published-wheel in controller/colab-source.json. The
cached SSH source includes platform invocation/signal changes absent from that wheel;
its native wire behavior matches, and the cached file is not treated as byte-identical
wheel provenance. Existing Google notices are retained. The implementation uses its
own bounded scoped transport and does not import the upstream CLI/cache/auto-create or
disabled-host-check paths. No upstream credential/session file is copied.
