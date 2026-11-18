"""Explicit one-time download of pinned public speech and Parakeet test assets.

Normal application startup and benchmark_asr.py never call this script.
Existing files are verified; originals are retained without modification.
"""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'work/benchmarks'
PARAKEET = 'csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8'
PARAKEET_REV = 'ed5d745623472f97cfc2e6c2916ee248798fc5a8'
SPEECH = 'csukuangfj2/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25'
SPEECH_REV = '68818b2313fe77bd06f6a7c5068ff3ef59d02b8a'
ASSETS = [
    (PARAKEET, PARAKEET_REV, 'encoder.int8.onnx', 'model/encoder.int8.onnx', 652282294,
     '1afbe69c1ffdabee94755f42e4daf1d93549131a3da11356bda84fcef0f2c479'),
    (PARAKEET, PARAKEET_REV, 'decoder.int8.onnx', 'model/decoder.int8.onnx', 11845274,
     '0222a86147299d4dee90edf95b6d13827edb42ad8b7c9cf0b2582f030937c0b5'),
    (PARAKEET, PARAKEET_REV, 'joiner.int8.onnx', 'model/joiner.int8.onnx', 6355277,
     'cbd02f3696e9944970111fb439d9c3fd365a80374565f13f2b9c7007d253fc98'),
    (PARAKEET, PARAKEET_REV, 'tokens.txt', 'model/tokens.txt', 93939,
     'git:fc43e1c723e262df60b70e1919614417162d1fe2'),
    (PARAKEET, PARAKEET_REV, 'test_wavs/en.wav', 'originals/english.wav', 184608,
     '148b936b43ce7c546a866e64da059f0458aee2d65e617f16e9d94f06e8d99ed6'),
    (SPEECH, SPEECH_REV, 'test_wavs/ru1.wav', 'originals/russian.wav', 152364,
     'e48b22f32d4d1c38f0a94a58acfc43bb8f5b7fc3b0ac01ea49372040ca831acf'),
    (SPEECH, SPEECH_REV, 'test_wavs/noise1-en.wav', 'originals/noise1-en.wav', 2831516,
     '3664ef02fa664da93d94a1afc271bda31c0f8d07a9f3c74ac6cd1e5aabe8572c'),
]


def verify(path, size, expected):
    if not path.is_file() or path.stat().st_size != size: return False
    digest = hashlib.sha1() if expected.startswith('git:') else hashlib.sha256()
    if expected.startswith('git:'): digest.update(f'blob {size}\0'.encode())
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''): digest.update(block)
    return digest.hexdigest() == expected.removeprefix('git:')


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    for repo, revision, name, local, size, digest in ASSETS:
        path = TARGET / local
        if verify(path, size, digest): continue
        if path.exists(): raise ValueError(f'Existing file failed verification: {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + '.part')
        print(f'Downloading {name} ({size} bytes)', flush=True)
        with urllib.request.urlopen(f'https://huggingface.co/{repo}/resolve/{revision}/{name}', timeout=60) as response, temporary.open('wb') as output:
            for block in iter(lambda: response.read(1024*1024), b''): output.write(block)
        if not verify(temporary, size, digest): raise ValueError(f'Hash mismatch: {name}')
        temporary.replace(path)
    import soundfile as sf
    manifest = [dict(id='russian_4.76s', path='originals/russian.wav',
                     reference='Барсук, живущий в киевском зоопарке, совершил побег из своего вольера'),
                dict(id='english_3.845s', path='originals/english.wav',
                     reference='Ask not what your country can do for you. Ask what you can do for your country.')]
    audio, rate = sf.read(TARGET / 'originals/noise1-en.wav', dtype='float32')
    for seconds in (2.5, 5, 8, 13):
        # Performance probes from real noisy speech. Crops have no verified text
        # and MUST NOT be used to assert WER, boundary quality or voice coverage.
        path = TARGET / f'noisy-english-{seconds:g}s.wav'
        if not path.exists(): sf.write(path, audio[:int(seconds*rate)], rate, subtype='FLOAT')
        manifest.append(dict(id=f'noisy_english_{seconds:g}s', path=path.name))
    (TARGET / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
    (TARGET / 'sources.json').write_text(json.dumps(ASSETS, indent=2), 'utf-8')
    print(f'Prepared {TARGET / "manifest.json"}', flush=True)


if __name__ == '__main__': main()
