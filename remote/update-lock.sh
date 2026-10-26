#!/bin/sh
# Regenerate from the manifest using the recorded resolver. Never edit the lock by hand.
set -eu
cd "$(dirname "$0")/.."
uv --version | grep -Eq '^uv 0\.13\.0( |$)' || { echo 'Use uv 0.13.0 to reproduce this dependency lock.' >&2; exit 2; }
uv pip compile --no-config --no-python-downloads --python-version 3.12 \
  --python-platform x86_64-manylinux_2_28 --index-url https://pypi.org/simple \
  --keyring-provider disabled --generate-hashes --only-binary :all: \
  --no-header --no-annotate --quiet remote/requirements.in --output-file remote/requirements.lock
