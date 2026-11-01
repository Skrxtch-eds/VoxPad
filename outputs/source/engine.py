"""Local Parakeet, Whisper and GigaAM recognition without audio uploads."""
from pathlib import Path
import math
import time

import numpy as np
import sherpa_onnx
from scipy.signal import resample_poly
from text_processing import normalize_transcript



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
    def __init__(self, model_dir: Path, threads=4, model='parakeet', language='auto'):
        model_dir = Path(model_dir)
        if model=='whisper':
            self.recognizer=sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=str(model_dir/'small-encoder.int8.onnx'),
                decoder=str(model_dir/'small-decoder.int8.onnx'),
                tokens=str(model_dir/'small-tokens.txt'),language='' if language=='auto' else language,
                num_threads=threads,provider='cpu',task='transcribe')
            return
        decoder='decoder.onnx' if model=='gigaam' else 'decoder.int8.onnx'
        joiner='joiner.onnx' if model=='gigaam' else 'joiner.int8.onnx'
        files = {name: model_dir / name for name in (
            'encoder.int8.onnx', decoder, joiner, 'tokens.txt')}
        missing = [name for name, path in files.items() if not path.is_file()]
        if missing:
            raise FileNotFoundError('Не найдены файлы модели: ' + ', '.join(missing))
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(files['encoder.int8.onnx']),
            decoder=str(files[decoder]),
            joiner=str(files[joiner]),
            tokens=str(files['tokens.txt']),
            num_threads=threads,
            sample_rate=16000,
            feature_dim=80,
            decoding_method='greedy_search',
            model_type='nemo_transducer',
            provider='cpu',
        )

    def transcribe(self, samples, sample_rate=16000):
        started = time.perf_counter()
        audio = mono16k(samples, sample_rate)
        # Silence should not become a hallucinated dictation.
        if audio.size < 1600 or float(np.max(np.abs(audio))) < 0.0005:
            return '', time.perf_counter() - started
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, audio)
        self.recognizer.decode_stream(stream)
        return normalize_transcript(stream.result.text.strip()), time.perf_counter() - started

    def warm_up(self):
        # Exercise the real decoder, rather than the silence short-circuit.
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, np.zeros(16000, dtype=np.float32))
        self.recognizer.decode_stream(stream)
