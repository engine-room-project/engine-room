#!/bin/bash
# Runs only inside an explicitly allocated disposable rental, never on an attached machine.
set -euo pipefail
umask 077
[ "$ENGINE_ROOM_ENGINE" = "llama.cpp" ] || [ "$ENGINE_ROOM_ENGINE" = "vLLM" ] || exit 2
W=/opt/engine-room
mkdir -p "$W"
phase() { printf '%s\n' "$1" > "$W/phase"; }
trap 'phase "Setup failed"' ERR
phase "Installing pinned system prerequisites"
cat > "$W/snapshot.list" <<'SOURCES'
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/@UBUNTU_SNAPSHOT@ noble main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/@UBUNTU_SNAPSHOT@ noble-updates main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://snapshot.ubuntu.com/ubuntu/@UBUNTU_SNAPSHOT@ noble-security main universe
SOURCES
APT_OPTIONS=(-o "Dir::Etc::sourcelist=$W/snapshot.list" -o 'Dir::Etc::sourceparts=-' -o 'Acquire::Check-Valid-Until=false')
export DEBIAN_FRONTEND=noninteractive
apt-get "${APT_OPTIONS[@]}" update -qq
apt-get "${APT_OPTIONS[@]}" install -y -qq --no-install-recommends python3 python3-venv openssh-server ca-certificates curl libgomp1
phase "Starting the pinned private SSH connection"
mkdir -p /root/.ssh /run/sshd
chmod 700 /root/.ssh
printf '%s\n' "$SESSION_SSH_PUB" > /root/.ssh/authorized_keys
printf '%s' "$SESSION_HOST_KEY" | base64 -d > /etc/ssh/ssh_host_ed25519_key
chmod 600 /root/.ssh/authorized_keys /etc/ssh/ssh_host_ed25519_key
unset SESSION_HOST_KEY SESSION_SSH_PUB
/usr/sbin/sshd -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o PermitRootLogin=prohibit-password -o HostKey=/etc/ssh/ssh_host_ed25519_key
phase "Checking the runtime source package"
printf '%s' "$SESSION_SOURCE" | base64 -d > "$W/source.tar.gz"
printf '%s  %s\n' "$SESSION_SOURCE_SHA256" "$W/source.tar.gz" | sha256sum --check --status
# This archive is generated from an explicit regular-file allowlist, with no links or local state.
tar -xzf "$W/source.tar.gz" -C "$W"
unset SESSION_SOURCE SESSION_SOURCE_SHA256
rm "$W/source.tar.gz"
export ENGINE_ROOM_ROOT="$W"
export PYTHONPATH="$W"
if [ -n "${ENGINE_ROOM_WEIGHTS:-}" ]; then printf '%s\n' "$ENGINE_ROOM_WEIGHTS" > "$W/weights-path"; fi
if [ "$ENGINE_ROOM_ENGINE" = 'llama.cpp' ]; then
  phase "Installing the pinned GGUF runtime"
  python3 -m venv "$W/venv"
  "$W/venv/bin/python" -m pip --isolated install --disable-pip-version-check --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -r "$W/remote/requirements.lock"
  . "$W/remote/install-llama.sh" "$W" "$W/install.log"
  printf '%s\n' "$W/venv/bin/python" > "$W/python-path"
  printf '%s\n' "$LLAMA_SERVER" > "$W/llama-path"
  printf '%s\n' "$LD_LIBRARY_PATH" > "$W/llama-libraries"
else
  phase "Checking the pinned vLLM runtime"
  python3 -c 'import vllm'
  command -v python3 > "$W/python-path"
fi
phase "Runtime ready; waiting for explicit model start"
# Credentials are delivered separately over pinned SSH before the model process is started.
touch "$W/runtime-ready"
exec sleep infinity
