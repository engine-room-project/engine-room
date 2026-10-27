"""Build an argv list from checked, non-secret launch settings; never use a shell."""
import json
import os
import re
import hashlib
import shutil
from pathlib import Path

from .model_validation import gguf_files, safetensors_files
from .storage import plan_storage
from .records import atomic_json


def command(settings, weights='weights'):
    model = settings.get('id', '')
    revision = settings.get('revision', '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', model) or '..' in model:
        raise ValueError('Invalid model name')
    if not re.fullmatch(r'[a-fA-F0-9]{40}', revision):
        raise ValueError('Invalid model revision')
    context = settings.get('context')
    if type(context) is not int or not 8192 <= context <= 1048576:
        raise ValueError('Invalid conversation capacity')
    if settings.get('engine') not in ('vLLM', 'llama.cpp'):
        raise ValueError('Choose a supported model engine explicitly')
    if settings.get('engine') == 'llama.cpp':
        files, mmproj = gguf_files(settings)
        # One request slot gets the whole conversation capacity; --jinja uses the model's own chat
        # template for tool calls, and /metrics feeds the status panel.
        args = [os.environ.get('LLAMA_SERVER', 'llama-server'), '-m', f'{weights}/{files[0]}',
                '--host', '127.0.0.1', '--port', '8000', '--alias', f'engine-room,{model}',
                '-c', str(context), '-ngl', '999', '-np', '1', '--jinja', '--metrics']
        if mmproj:
            args += ['--mmproj', f'{weights}/{mmproj}']
        return args
    if 'fileSizes' in settings:
        safetensors_files(settings)
    dtype = settings.get('dtype')
    if dtype not in ('float16', 'bfloat16', 'float32'):
        raise ValueError('Invalid published precision')
    tool = settings.get('tool', '')
    reasoning = settings.get('reasoning', '')
    if tool not in ('', 'hermes', 'qwen3_xml', 'llama3_json', 'mistral') or reasoning not in ('', 'qwen3'):
        raise ValueError('Unrecognised model parser')
    args = ['vllm', 'serve', model, '--revision', revision, '--host', '127.0.0.1',
            '--port', '8000', '--served-model-name', 'engine-room', model,
            '--max-model-len', str(context), '--gpu-memory-utilization', '0.92',
            '--max-num-seqs', '4', '--enable-prefix-caching', '--dtype', dtype]
    if tool:
        args += ['--enable-auto-tool-choice', '--tool-call-parser', tool]
    if reasoning:
        args += ['--reasoning-parser', reasoning]
    return args


def checked_cache_root(weights):
    """Refuse redirected roots before creating anything in an attached volume."""
    absolute=os.path.abspath(weights)
    for path in (Path(absolute),*Path(absolute).parents):
        if path.is_symlink() or getattr(path,"is_junction",lambda:False)():
            raise ValueError('A model cache root or parent is linked')
    if os.path.normcase(os.path.realpath(absolute))!=os.path.normcase(absolute):
        raise ValueError('A model cache root was redirected')
    # Existing Hub blobs and local-dir metadata can also redirect later writes.
    # Legitimate snapshot file links inside this selected cache remain usable.
    count=0
    if os.path.isdir(absolute):
        for directory,dirs,files in os.walk(absolute,followlinks=False):
            for name in dirs+files:
                count+=1
                if count>10000: raise ValueError('The model cache exceeds the inspection bound')
                path=os.path.join(directory,name)
                if os.path.commonpath([absolute,os.path.realpath(path)])!=absolute:
                    raise ValueError('A model cache link points outside the selected storage folder')
    return absolute


def check_storage(settings, weights, names, snapshot_cache=False):
    """Count only usable hash-verified cache; check the real filesystem after installation."""
    sizes = settings.get('fileSizes')
    hashes = settings.get('fileHashes', {})
    if not isinstance(sizes, dict) or set(sizes) != set(names) or not isinstance(hashes, dict):
        raise ValueError('Published sizes for all selected model files are required')
    if any(type(sizes[n]) is not int or sizes[n] <= 0 for n in names):
        raise ValueError('Invalid published model sizes')
    weights=checked_cache_root(weights)
    os.makedirs(weights, exist_ok=True)
    checked_cache_root(weights)
    cached = 0
    for name in names:
        if snapshot_cache:
            if not re.fullmatch(r'[A-Za-z0-9_.()+-]+\.safetensors', name) or '..' in name:
                raise ValueError('Invalid selected safetensors filename')
            path = os.path.join(weights, 'hub', 'models--' + settings['id'].replace('/', '--'),
                                'snapshots', settings['revision'], name)
        else:
            path = os.path.join(weights, name)
        path = os.path.realpath(path)
        if os.path.commonpath([weights, path]) != weights:
            raise ValueError('A model cache link points outside the selected storage folder')
        expected = hashes.get(name)
        if isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected) and os.path.isfile(path) and os.path.getsize(path) == sizes[name]:
            with open(path, 'rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual == expected:
                cached += sizes[name]
    storage = plan_storage([sizes[n] for n in names], shutil.disk_usage(weights).free, 0, cached)
    if not storage.fits:
        raise ValueError('Not enough model storage. Choose a larger disk or free space without removing unrelated files.')
    return storage


def download(settings, weights):
    """Check space before download and use only the explicitly supplied model credential."""
    files, mmproj = gguf_files(settings)
    names = files + ([mmproj] if mmproj else [])
    check_storage(settings, weights, names)
    from huggingface_hub import hf_hub_download
    for name in names:
        hf_hub_download(settings['id'], name, revision=settings['revision'], local_dir=weights,
                        token=os.environ.get('HF_TOKEN') or False)


def weights_folder(root):
    """Remote work and cache paths are explicitly supplied by the connector."""
    folder = os.environ.get('ENGINE_ROOM_WEIGHTS', os.path.join(root, 'weights'))
    if not os.path.isabs(folder) or any(part == '..' for part in folder.split('/')):
        raise ValueError('Invalid model folder')
    return folder


def choose_weights(settings, root):
    requested=weights_folder(root)
    pointer=os.path.join(root,'weights-path')
    if os.path.isfile(pointer):
        with open(pointer,encoding='utf-8') as stream: requested=stream.read(4096).strip()
        if not os.path.isabs(requested) or '..' in requested.split('/'):
            raise ValueError('Invalid saved model storage path')
    if settings['engine']=='llama.cpp':
        files,projector=gguf_files(settings)
        names=files+([projector] if projector else [])
        snapshot=False
    else:
        names=safetensors_files(settings)
        snapshot=True
    fallback=os.path.join(root,'weights')
    try:
        check_storage(settings,requested,names,snapshot_cache=snapshot)
        selected=requested
    except (OSError,ValueError):
        if os.path.realpath(requested)==os.path.realpath(fallback): raise
        # The pre-rental disk plan already reserves full space without cache credit.
        # A full/inaccessible saved volume never causes deletion of existing files.
        check_storage(settings,fallback,names,snapshot_cache=snapshot)
        selected=fallback
    atomic_json(os.path.join(root,'model-storage.json'),{'path':selected,'using_fallback':selected!=requested})
    return selected


def main():
    root = os.environ['ENGINE_ROOM_ROOT']
    if not os.path.isabs(root):
        raise ValueError('An absolute remote workspace is required')
    with open(f'{root}/model.json', encoding='utf-8-sig') as src:
        settings = json.load(src)
    command(settings)  # Validate before inspecting any supplied storage path.
    weights = choose_weights(settings,root)
    args = command(settings, weights)
    # The supervisor consumes the sole selected credential before spawning this
    # clean process. Authentication state must never share persistent model storage.
    if settings.get('engine') == 'llama.cpp':
        download(settings, weights)
    else:
        sizes = settings.get('fileSizes')
        if not isinstance(sizes, dict) or not sizes:
            raise ValueError('Published safetensors sizes are required')
        os.environ['HF_HUB_CACHE'] = os.path.join(weights, 'hub')
        check_storage(settings, weights, list(sizes), snapshot_cache=True)
    os.execvp(args[0], args)


if __name__ == '__main__':
    main()
