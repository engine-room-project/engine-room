#!/bin/bash
# Only for a new owned disposable Colab rental directory; never an attachment.
set -euo pipefail
umask 077
W=$1
/usr/bin/python3 - "$W" <<'PY'
import json,pathlib,re,sys
root=pathlib.Path(sys.argv[1])
if not root.is_absolute() or root.resolve()!=root.absolute(): raise ValueError('Invalid owned work directory')
proof=json.loads((root/'.engine-room-owner.json').read_text())
key=proof.get('operation_key','')
if not re.fullmatch('[a-f0-9]{64}',key) or root.name!='engine-room-'+key[:32] or proof.get('state')!='staged':
    raise ValueError('Owned staged source proof is required')
if json.loads((root/'model.json').read_text()).get('engine') not in {'llama.cpp','vLLM'}:
    raise ValueError('Unsupported native engine')
release=pathlib.Path('/etc/os-release').read_text()
if 'ID=ubuntu' not in release or 'VERSION_ID="24.04"' not in release:
    raise ValueError('This pinned native installer requires Ubuntu 24.04')
PY
phase() { printf '%s\n' "$1" > "$W/.phase-new"; mv "$W/.phase-new" "$W/phase"; }
trap 'phase "Setup failed"' ERR
phase "Installing pinned native prerequisites"
snapshot=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["ubuntu_snapshot"])' "$W/remote/runtimes.json")
[[ "$snapshot" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || exit 2
cat > "$W/snapshot.list" <<SOURCES
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/$snapshot noble main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/$snapshot noble-updates main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/$snapshot noble-security main universe
SOURCES
: > "$W/apt-auth.conf"
APT_OPTIONS=(-o "Dir::Etc::sourcelist=$W/snapshot.list" -o 'Dir::Etc::sourceparts=-' -o "Dir::Etc::netrc=$W/apt-auth.conf" -o 'Acquire::Check-Valid-Until=false')
export DEBIAN_FRONTEND=noninteractive
apt-get "${APT_OPTIONS[@]}" update -qq
apt-get "${APT_OPTIONS[@]}" install -y -qq --no-install-recommends python3.12 python3.12-venv curl ca-certificates libgomp1 libstdc++6
phase "Installing isolated model Python and pinned downloader"
/usr/bin/python3.12 -I -c 'import sys; assert sys.version_info[:2]==(3,12)'
/usr/bin/python3.12 -I -m venv "$W/venv"
engine=$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["engine"])' "$W/model.json")
if [ "$engine" = 'llama.cpp' ]; then
  PIP_CONFIG_FILE=/dev/null "$W/venv/bin/python" -m pip --isolated install --no-input --no-cache-dir --disable-pip-version-check --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -r "$W/remote/requirements.lock"
  phase "Installing hash-verified GGUF runtime"
  . "$W/remote/install-llama.sh" "$W" "$W/install.log"
  "$LLAMA_SERVER" --version >> "$W/install.log" 2>&1
  printf '%s\n' "$LLAMA_SERVER" > "$W/llama-path"
  printf '%s\n' "$LD_LIBRARY_PATH" > "$W/llama-libraries"
elif [ "$engine" = 'vLLM' ]; then
  phase "Installing pinned native vLLM packages"
  PIP_CONFIG_FILE=/dev/null "$W/venv/bin/python" -m pip --isolated install --no-input --no-cache-dir --disable-pip-version-check --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -r "$W/remote/requirements-vllm.lock"
  "$W/venv/bin/python" -m pip --isolated check
  phase "Verifying pinned native vLLM and GPU"
  "$W/venv/bin/python" -I "$W/remote/verify_vllm.py" "$W"
else
  exit 2
fi
printf '%s\n' "$W/venv/bin/python" > "$W/python-path"
phase "Runtime installed; waiting for explicit credentials and model start"
printf '%s\n' 'installed' > "$W/.runtime-ready-new"
mv "$W/.runtime-ready-new" "$W/runtime-ready"
