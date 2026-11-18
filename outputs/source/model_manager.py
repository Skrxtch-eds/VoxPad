"""Explicit model downloads with progress, cancellation and atomic publication."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from urllib.request import Request, urlopen

MODELS={
 'parakeet':dict(title='Parakeet TDT 0.6B v3 INT8',folder='sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8',
                 size=670576784,files=['encoder.int8.onnx','decoder.int8.onnx','joiner.int8.onnx','tokens.txt']),
}

# The exact, complete revision used by the accelerated version's ASR benchmarks.
MODEL_URL='https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/resolve/ed5d745623472f97cfc2e6c2916ee248798fc5a8/'
MODEL_FILES={
 'encoder.int8.onnx':(652282294,'1afbe69c1ffdabee94755f42e4daf1d93549131a3da11356bda84fcef0f2c479'),
 'decoder.int8.onnx':(11845274,'0222a86147299d4dee90edf95b6d13827edb42ad8b7c9cf0b2582f030937c0b5'),
 'joiner.int8.onnx':(6355277,'cbd02f3696e9944970111fb439d9c3fd365a80374565f13f2b9c7007d253fc98'),
 'tokens.txt':(93939,'d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d'),
}

def installed(root, model):
    spec=MODELS[model]
    return all((Path(root)/spec['folder']/name).is_file() and (Path(root)/spec['folder']/name).stat().st_size>0 for name in spec['files'])

def download(root, model, cancel, progress, force=False):
    spec=MODELS[model]; root=Path(root); root.mkdir(parents=True,exist_ok=True)
    if not force and installed(root,model): return
    if shutil.disk_usage(root).free<spec['size']*2:
        raise OSError('Not enough disk space for download and extraction')
    with tempfile.TemporaryDirectory(prefix='download-',dir=root) as temporary:
        prepared=Path(temporary)/spec['folder'];prepared.mkdir()
        received=0
        for name,(size,checksum) in MODEL_FILES.items():
            if cancel.is_set(): raise InterruptedError('Download cancelled')
            digest=hashlib.sha256();count=0
            request=Request(MODEL_URL+name,headers={'User-Agent':'VoxPad/0.5.3'})
            with urlopen(request,timeout=30) as response,(prepared/name).open('wb') as stream:
                while True:
                    if cancel.is_set(): raise InterruptedError('Download cancelled')
                    chunk=response.read(256*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>size:raise ValueError('Downloaded size does not match the model manifest')
                    stream.write(chunk);digest.update(chunk);received+=len(chunk)
                    progress(received,spec['size'],'Downloading')
            if count!=size:raise ValueError('Downloaded size does not match the model manifest')
            if digest.hexdigest()!=checksum:raise ValueError('Model checksum mismatch')
        if cancel.is_set(): raise InterruptedError('Download cancelled')
        destination=root/spec['folder']
        previous=None
        if destination.is_symlink():raise ValueError('Invalid model folder')
        if destination.exists():
            # Retain an incomplete installation; never remove the user's model files.
            previous=root/(spec['folder']+'.incomplete-'+uuid.uuid4().hex)
            os.replace(destination,previous)
        try:os.replace(prepared,destination)
        except OSError:
            if previous is not None:os.replace(previous,destination)
            raise
