# Sourced by the remote bootstrap. Artifact names and hashes have one source: runtimes.json.
W=$1
LOG=$2
mkdir -p "$W/llama"
python3 - "$W/remote/runtimes.json" > "$W/llama-artifacts.txt" <<'PY'
import json,re,sys
profile=json.load(open(sys.argv[1],encoding='utf-8'))['llama']
version=profile['version']
if not re.fullmatch(r'b[0-9]+',version): raise ValueError('Invalid pinned llama.cpp release')
for item in profile['archives']:
    name=item['name']; digest=item['sha256']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.tar\.gz',name) or not re.fullmatch(r'[a-f0-9]{64}',digest):
        raise ValueError('Invalid pinned runtime artifact')
    print(name,digest,'https://github.com/ggml-org/llama.cpp/releases/download/'+version+'/'+name)
PY
while IFS=' ' read -r name fingerprint url; do
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --tlsv1.2 "$url" --output "$W/llama/$name"
  printf '%s  %s\n' "$fingerprint" "$W/llama/$name" | sha256sum --check --status
  # Python's data filter refuses absolute paths, parent traversal and links outside the destination.
  python3 - "$W/llama/$name" "$W/llama" <<'PY'
import sys,tarfile
with tarfile.open(sys.argv[1],'r:gz') as archive:
    archive.extractall(sys.argv[2],filter='data')
PY
  rm "$W/llama/$name"
done < "$W/llama-artifacts.txt" >> "$LOG" 2>&1
LLAMA_SERVER=$(find "$W/llama" -name llama-server -type f -print -quit)
test -x "$LLAMA_SERVER"
cuda_dir=$(find "$W/llama" -name 'libcudart.so*' -printf '%h\n' -quit)
export LLAMA_SERVER
export LD_LIBRARY_PATH="$(dirname "$LLAMA_SERVER")${cuda_dir:+:$cuda_dir}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
