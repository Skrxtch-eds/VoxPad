"""Explicit model downloads with progress, cancellation and atomic publication."""
import hashlib
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import Request, urlopen

MODELS={
 'parakeet':dict(title='Fast · Parakeet v3',folder='sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8',
                 size=487170055,files=['encoder.int8.onnx','decoder.int8.onnx','joiner.int8.onnx','tokens.txt'],
                 sha256='5793d0fd397c5778d2cf2126994d58e9d56b1be7c04d13c7a15bb1b4eafb16bf'),
 'whisper':dict(title='Accuracy · Whisper Small',folder='sherpa-onnx-whisper-small',size=639387718,
                files=['small-encoder.int8.onnx','small-decoder.int8.onnx','small-tokens.txt']),
 'gigaam':dict(title='Russian · GigaAM v2',folder='sherpa-onnx-nemo-transducer-giga-am-v2-russian-2025-04-19',
               size=172422327,files=['encoder.int8.onnx','decoder.onnx','joiner.onnx','tokens.txt']),
}

def installed(root, model):
    spec=MODELS[model]
    return all((Path(root)/spec['folder']/name).is_file() and (Path(root)/spec['folder']/name).stat().st_size>0 for name in spec['files'])

def download(root, model, cancel, progress):
    spec=MODELS[model]; root=Path(root); root.mkdir(parents=True,exist_ok=True)
    if installed(root,model): return
    if shutil.disk_usage(root).free<spec['size']*4:
        raise OSError('Not enough disk space for download and extraction')
    with tempfile.TemporaryDirectory(prefix='download-',dir=root) as temporary:
        archive=Path(temporary)/'model.tar.bz2'
        url='https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/'+spec['folder']+'.tar.bz2'
        digest=hashlib.sha256(); received=0
        with urlopen(Request(url,headers={'User-Agent':'ParakeetTranscriber/0.2'}),timeout=30) as response, archive.open('wb') as stream:
            while True:
                if cancel.is_set(): raise InterruptedError('Download cancelled')
                chunk=response.read(256*1024)
                if not chunk: break
                stream.write(chunk); digest.update(chunk); received+=len(chunk)
                progress(received,spec['size'],'Downloading')
        if received!=spec['size']: raise ValueError('Downloaded size does not match the model manifest')
        if spec.get('sha256') and digest.hexdigest()!=spec['sha256']: raise ValueError('Model checksum mismatch')
        progress(received,spec['size'],'Extracting')
        extract=Path(temporary)/'extract'; extract.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar:
                if cancel.is_set(): raise InterruptedError('Download cancelled')
                if not member.isfile() and not member.isdir(): raise ValueError('Unsupported archive entry')
                tar.extract(member,extract,filter='data')
        if not installed(extract,model): raise ValueError('Model files are missing or invalid')
        if cancel.is_set(): raise InterruptedError('Download cancelled')
        destination=root/spec['folder']
        if destination.exists(): raise FileExistsError('Existing model folder must be removed first')
        os.replace(extract/spec['folder'],destination)

def remove(root, model, active_model):
    if model==active_model: raise ValueError('Switch to another model before deleting the active one')
    root=Path(root).resolve(); destination=(root/MODELS[model]['folder']).resolve()
    if destination.parent!=root or destination.is_symlink(): raise ValueError('Invalid model folder')
    if destination.exists(): shutil.rmtree(destination)
