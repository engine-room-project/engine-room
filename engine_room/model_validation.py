"""One GGUF filename/shard validator for preflight and remote execution."""
import json
import re
import sys

GGUF = re.compile(r"[A-Za-z0-9_.()+-]+(/[A-Za-z0-9_.()+-]+)*\.gguf")
SHARD = re.compile(r"(.*)-([0-9]{5})-of-([0-9]{5})\.gguf")


def gguf_files(settings):
    files=settings.get("files")
    projector=settings.get("mmproj","")
    if not isinstance(files,list) or not files or not isinstance(projector,str):
        raise ValueError("Invalid model files.")
    for name in files+([projector] if projector else []):
        if not isinstance(name,str) or not GGUF.fullmatch(name) or ".." in name:
            raise ValueError("Unsupported model filename. Use ordinary letters, numbers and punctuation without spaces or parent paths.")
    if len(set(files)) != len(files):
        raise ValueError("Duplicate model files.")
    matches=[SHARD.fullmatch(name) for name in files]
    if any(matches):
        if not all(matches):
            raise ValueError("Do not mix split and unsplit model files.")
        prefixes={m.group(1) for m in matches}
        totals={int(m.group(3)) for m in matches}
        if len(prefixes)!=1 or len(totals)!=1:
            raise ValueError("Model shards must have one name and consistent totals.")
        total=next(iter(totals))
        indices={int(m.group(2)) for m in matches}
        if total!=len(files) or indices!=set(range(1,total+1)):
            raise ValueError("Model shards must include exactly files 1 through the declared total.")
    elif len(files)!=1:
        raise ValueError("Choose one complete model variant.")
    if projector in files:
        raise ValueError("A projector must be separate from model weights.")
    return sorted(files),projector


def safetensors_files(settings):
    sizes=settings.get("fileSizes")
    if not isinstance(sizes,dict) or not sizes:
        raise ValueError("Published safetensors sizes are required.")
    for name,size in sizes.items():
        if (not isinstance(name,str) or not re.fullmatch(r"[A-Za-z0-9_.()+-]+\.safetensors",name)
                or ".." in name or type(size) is not int or size<=0):
            raise ValueError("Invalid safetensors filename or published size.")
    return sorted(sizes)


def main():
    try:
        # Bytes: Windows PowerShell prefixes a UTF-8 BOM when the console uses UTF-8.
        settings=json.loads(sys.stdin.buffer.read())
        if settings.get("engine","llama.cpp")=="llama.cpp":
            files,projector=gguf_files(settings)
        elif settings.get("engine")=="vLLM":
            files,projector=safetensors_files(settings),""
        else:
            raise ValueError("Unknown model engine.")
        print(json.dumps({"files":files,"mmproj":projector}))
    except (ValueError,TypeError,AttributeError):
        print("The selected model filenames or shard set are invalid.",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(main())
