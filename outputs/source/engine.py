"""Local Parakeet recognition without audio uploads."""
from pathlib import Path
import math
import json
import time
from contextlib import nullcontext

import numpy as np
import sherpa_onnx
from scipy.signal import resample_poly
from text_processing import normalize_transcript
from cpu_runtime import default_threads


def configured_threads(path, model='parakeet'):
    """Keep explicit legacy overrides; an invalid optional file cannot break ASR."""
    default=default_threads(model)
    try:
        value=json.loads(Path(path).read_text('utf-8'))['threads']
        if isinstance(value,bool) or not isinstance(value,(int,str)):return default
        threads=int(value)
        return threads if 1<=threads<=256 else default
    except (OSError,ValueError,KeyError,TypeError):return default


def configured_cpu_profile(path):
    try:
        return json.loads(Path(path).read_text('utf-8')).get('cpu_profile','auto')=='auto'
    except FileNotFoundError:return True
    except (OSError,ValueError,TypeError,AttributeError):return False


def mono16k(samples, sample_rate):
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if audio.ndim != 1:
        raise ValueError('Ожидается моно или стереозапись.')
    rate = int(sample_rate)
    if rate <= 0:
        raise ValueError('Неверная частота записи.')
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        audio = resample_poly(audio, 16000 // divisor, rate // divisor)
    return np.ascontiguousarray(audio, dtype=np.float32)


class Engine:
    def __init__(self, model_dir: Path, threads=4, provider='cpu'):
        model_dir = Path(model_dir)
        files = {name: model_dir / name for name in (
            'encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt')}
        missing = [name for name, path in files.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError('Не найдены файлы модели: ' + ', '.join(missing))
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(files['encoder.int8.onnx']),
            decoder=str(files['decoder.int8.onnx']),
            joiner=str(files['joiner.int8.onnx']),
            tokens=str(files['tokens.txt']),
            num_threads=threads,
            sample_rate=16000,
            feature_dim=80,
            decoding_method='greedy_search',
            model_type='nemo_transducer',
            provider=provider,
        )

    def transcribe(self, samples, sample_rate=16000, trace=None):
        started = time.perf_counter()
        span = trace.span if trace else lambda name: nullcontext()
        with span('mono16k'):
            audio = mono16k(samples, sample_rate)
        # Silence should not become a hallucinated dictation.
        if audio.size < 1600 or float(np.max(np.abs(audio))) < 0.0005:
            return '', time.perf_counter() - started
        with span('create_stream'):
            stream = self.recognizer.create_stream()
        with span('accept_waveform'):
            stream.accept_waveform(16000, audio)
        with span('inference'):
            self.recognizer.decode_stream(stream)
        with span('extract_normalize'):
            text = normalize_transcript(stream.result.text.strip())
        return text, time.perf_counter() - started

    def warm_up(self):
        # Exercise the real decoder, rather than the silence short-circuit.
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, np.zeros(16000, dtype=np.float32))
        self.recognizer.decode_stream(stream)
