"""Reproducible, offline CPU speech benchmark. Never changes performance.json.

Each configuration runs in a fresh process. Model loading and warm-up are
excluded. The optional pipeline is a headless application harness: microphone,
UI rendering and Windows paste are simulated, so it is NOT end-to-end latency.
"""
import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get('VOXPAD_BENCH_SOURCE', str(ROOT / 'outputs/source')))
import numpy as np
import soundfile as sf
from engine import Engine

_qt_application = None


def error_rate(reference, hypothesis):
    import re
    import unicodedata
    def normalize(text):
        return ' '.join(re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", unicodedata.normalize('NFC', text).casefold()))
    def distance(a, b):
        row = list(range(len(b) + 1))
        for i, left in enumerate(a, 1):
            following = [i]
            for j, right in enumerate(b, 1):
                following.append(min(following[-1] + 1, row[j] + 1, row[j-1] + (left != right)))
            row = following
        return row[-1]
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        raise ValueError('An empty reference cannot be scored')
    words, chars = ref.split(), list(ref.replace(' ', ''))
    return dict(word_errors=distance(words, hyp.split()), reference_words=len(words),
                character_errors=distance(chars, list(hyp.replace(' ', ''))), reference_characters=len(chars))


class TimedRecognizer:
    """Measure the real sherpa calls without changing the decoding algorithm."""
    def __init__(self, recognizer):
        self.recognizer = recognizer
        self.stages = {}

    @contextmanager
    def span(self, name):
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            self.stages[name] = (time.perf_counter_ns() - started) / 1e9

    def create_stream(self):
        with self.span('create_stream_seconds'):
            stream = self.recognizer.create_stream()
        owner = self
        class Stream:
            def accept_waveform(self, *args):
                with owner.span('accept_waveform_seconds'):
                    stream.accept_waveform(*args)
            @property
            def result(self):
                with owner.span('extract_result_seconds'):
                    return stream.result
        wrapped = Stream()
        wrapped.original = stream
        return wrapped

    def decode_stream(self, stream):
        with self.span('inference_seconds'):
            self.recognizer.decode_stream(stream.original)


def pipeline(engine, audio, rate, disk_delay=0):
    from PySide6.QtCore import QCoreApplication
    from qt_controller import Controller
    global _qt_application
    _qt_application = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix='.tmp-benchmark-', dir=ROOT / 'tests') as folder:
        app = Controller(Path(folder) / 'data', preview=True)
        app._preferences['sounds'] = False
        app.engine = engine
        app.target = 123
        app._phase = 'recording'; app.recording = True
        app.stream = None; app.rate = rate
        app.chunks = [audio[i:i+480].copy() for i in range(0, len(audio), 480)]
        timings = {}
        original_add = app.store.add
        saved = threading.Event()
        def add(*args, **kwargs):
            started = time.perf_counter()
            try:
                if disk_delay: time.sleep(disk_delay)
                return original_add(*args, **kwargs)
            finally:
                timings['history_seconds'] = time.perf_counter() - started
                saved.set()
        app.store.add = add
        paste_times = []
        result = None
        with patch('qt_controller.copy_text'), patch('qt_controller.paste_if_focused',
                side_effect=lambda target: paste_times.append(time.perf_counter()) or True):
            started = time.perf_counter()
            try:
                app.stop_recording()
                deadline = started + 60
                while not saved.is_set() or result is None:
                    if time.perf_counter() > deadline:
                        raise TimeoutError(f'Pipeline did not finish: result_received={result is not None}, history_finished={saved.is_set()}')
                    try: kind, value = app.events.get(timeout=.002)
                    except queue.Empty: continue
                    if kind == 'result':
                        result = value
                        app.finish_result(value)
                    elif kind == 'error': raise RuntimeError(value)
                    else: app.handle_event(kind, value)
            finally:
                for worker in tuple(app._workers): worker.join(15)
                app._poll_timer.stop(); app._device_timer.stop()
                app.audio_input.close(); app.hotkey.close()
                app._io.shutdown(wait=True)
                app.active = False
        if not paste_times: raise RuntimeError('No paste command in pipeline')
        timings['pipeline_surrogate_seconds'] = paste_times[0] - started
        timings['decode_seconds'] = result['seconds']
        return result['text'], timings


def worker(args):
    import psutil  # Optional development dependency: requirements-dev.txt.
    if args.cpu_affinity:psutil.Process().cpu_affinity(args.cpu_affinity)
    manifest = json.loads(args.manifest.read_text('utf-8'))
    clips = []
    for item in manifest:
        path = (args.manifest.parent / item['path']).resolve()
        data, rate = sf.read(path, dtype='float32')
        if data.ndim > 1: data = data.mean(axis=1)
        if not len(data) or not np.isfinite(data).all(): raise ValueError('Invalid audio')
        clips.append((item, data, rate))
    loaded = time.perf_counter()
    if args.app_profile:
        from cpu_runtime import recognition_cpu
        policy=recognition_cpu(args.model,args.worker_threads)
    else:policy=nullcontext(None)
    with policy as cpu_policy:
        options={'provider':cpu_policy.provider} if cpu_policy else {}
        if args.ort_config:options={'provider':'cpu:'+str(args.ort_config.resolve())}
        engine = Engine(args.model_dir, args.worker_threads, **options)
        engine.warm_up()
    for _ in range(args.warmups):
        for _, audio, rate in clips:
            engine.transcribe(audio, rate)
    load_seconds = time.perf_counter() - loaded
    timed = TimedRecognizer(engine.recognizer)
    engine.recognizer = timed
    process = psutil.Process()
    peak = [process.memory_info().rss]
    stop = threading.Event()
    def monitor():
        while not stop.wait(.01): peak[0] = max(peak[0], process.memory_info().rss)
    sampler = threading.Thread(target=monitor, daemon=True); sampler.start()
    rows = []
    try:
        for repeat in range(args.repeats):
            idle=args.idle_seconds
            while idle>0:
                wait=min(idle,30);time.sleep(wait);idle-=wait
            for item, audio, rate in (clips if repeat % 2 == 0 else list(reversed(clips))):
                timed.stages.clear()
                psutil.cpu_percent(None)
                cpu = time.process_time(); started = time.perf_counter()
                if args.pipeline:
                    text, stages = pipeline(engine, audio, rate, args.disk_delay)
                else:
                    text, decode = engine.transcribe(audio, rate)
                    stages = {'decode_seconds': decode}
                elapsed = time.perf_counter() - started
                cpu = time.process_time() - cpu
                system_cpu=psutil.cpu_percent(None)
                peak[0] = max(peak[0], process.memory_info().rss)
                row = dict(clip=item['id'], repeat=repeat, audio_seconds=len(audio)/rate,
                           latency_seconds=stages.get('pipeline_surrogate_seconds', elapsed),
                           cpu_core_percent=100*cpu/elapsed, rss_peak_bytes=peak[0],
                           system_cpu_percent=system_cpu,
                           **stages, **timed.stages)
                row['rtf'] = row['decode_seconds'] / row['audio_seconds']
                row['text_sha256'] = hashlib.sha256(text.encode('utf-8')).hexdigest()
                if item.get('reference'): row.update(error_rate(item['reference'], text))
                if args.include_text: row['text'] = text
                rows.append(row)
                print(f"  {item['id']} / {repeat+1}: {row['latency_seconds']:.3f}s",flush=True)
    finally:
        stop.set(); sampler.join()
    output = dict(threads=args.worker_threads, load_and_warmup_seconds=load_seconds,
                  cpu_profile=cpu_policy.name if cpu_policy else 'explicit_benchmark_settings',
                  observed_cpu_affinity=process.cpu_affinity(),
                  peak_rss_bytes=peak[0], runs=rows, summary={})
    for item, _, _ in clips:
        runs = [row for row in rows if row['clip'] == item['id']]
        def percentile(name, quantile): return float(np.percentile([r[name] for r in runs], quantile))
        output['summary'][item['id']] = dict(
            latency_p50_seconds=percentile('latency_seconds', 50),
            latency_p95_seconds=percentile('latency_seconds', 95),
            inference_p50_seconds=percentile('inference_seconds', 50),
            decode_p50_seconds=percentile('decode_seconds', 50),
            cpu_core_percent_mean=statistics.mean(r['cpu_core_percent'] for r in runs),
            rtf_p50=percentile('rtf', 50),
            stable_text=len({r['text_sha256'] for r in runs}) == 1,
            wer=(sum(r['word_errors'] for r in runs)/sum(r['reference_words'] for r in runs)
                 if 'reference_words' in runs[0] else None),
            cer=(sum(r['character_errors'] for r in runs)/sum(r['reference_characters'] for r in runs)
                 if 'reference_characters' in runs[0] else None))
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), 'utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--model', choices=('parakeet',), default='parakeet')
    parser.add_argument('--threads', nargs='+', type=int, default=[1,2,4,6,8])
    parser.add_argument('--repeats', type=int, default=7)
    parser.add_argument('--warmups', type=int, default=1, help='Speech warm-ups after existing silence warm-up')
    parser.add_argument('--rounds', type=int, default=1, help='Reverse configuration order on alternate rounds')
    parser.add_argument('--pipeline', action='store_true')
    parser.add_argument('--disk-delay', type=float, default=0, help='Artificial SQLite delay, seconds; fault experiment only')
    parser.add_argument('--include-text', action='store_true', help='Explicitly allow transcripts in this report')
    parser.add_argument('--source-dir',type=Path,default=ROOT/'outputs/source',help='Read-only source snapshot for before/after comparisons')
    parser.add_argument('--ort-config',type=Path,help='Explicit CPU session options for an isolated experiment')
    parser.add_argument('--cpu-affinity',nargs='+',type=int,help='Isolated experiment: restrict benchmark process to these logical CPUs')
    parser.add_argument('--app-profile',action='store_true',help='Use the same measured CPU policy as application model loading')
    parser.add_argument('--idle-seconds',type=float,default=0,help='Idle before each repeat, outside measured latency')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker-threads', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.repeats < 1 or args.rounds < 1 or args.warmups < 0 or args.idle_seconds<0 or args.disk_delay<0 or any(t < 1 for t in args.threads):
        parser.error('Positive threads/repeats/rounds and nonnegative warmups required')
    if args.app_profile and (args.ort_config or args.cpu_affinity):parser.error('App profile and explicit runtime overrides are separate experiments')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.worker_threads is not None:
        worker(args); return
    report = dict(platform=platform.platform(), processor=platform.processor(), logical_cpus=os.cpu_count(),
                  python=sys.version, model=args.model, provider='cpu',
                  scenario='headless_pipeline_surrogate' if args.pipeline else 'whole_utterance_engine',
                  physical_release_to_visible_text_seconds=None, disk_delay_seconds=args.disk_delay,
                  repeats=args.repeats, warmups=args.warmups, configurations=[])
    report['app_profile']=args.app_profile
    report['idle_seconds']=args.idle_seconds
    if os.name=='nt':
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            report['cpu_name']=winreg.QueryValueEx(key,'ProcessorNameString')[0]
    report['source_sha256']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(args.source_dir.glob('*.py'))}
    if args.ort_config:report['ort_config']=args.ort_config.read_text('utf-8')
    report['cpu_affinity']=args.cpu_affinity
    import sherpa_onnx
    report['sherpa_onnx'] = sherpa_onnx.__version__
    report['model_files_sha256'] = {}
    for path in sorted(args.model_dir.glob('*')):
        if path.is_file():
            with path.open('rb') as stream: report['model_files_sha256'][path.name] = hashlib.file_digest(stream,'sha256').hexdigest()
    manifest = json.loads(args.manifest.read_text('utf-8'))
    report['clips'] = []
    for item in manifest:
        path = args.manifest.parent / item['path']
        with path.open('rb') as stream: digest = hashlib.file_digest(stream,'sha256').hexdigest()
        report['clips'].append(dict(id=item['id'], file_sha256=digest, has_reference=bool(item.get('reference'))))
    with tempfile.TemporaryDirectory(prefix='.tmp-bench-', dir=args.output.parent) as temporary:
        for round_index in range(args.rounds):
            for threads in (args.threads if round_index % 2 == 0 else list(reversed(args.threads))):
                output = Path(temporary) / 'worker.json'
                command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                    '--manifest', str(args.manifest.resolve()), '--model-dir', str(args.model_dir.resolve()),
                    '--model', args.model, '--repeats', str(args.repeats), '--warmups', str(args.warmups),
                    '--output', str(output), '--worker-threads', str(threads), '--disk-delay', str(args.disk_delay)]
                command.extend(['--idle-seconds',str(args.idle_seconds)])
                if args.pipeline: command.append('--pipeline')
                if args.include_text: command.append('--include-text')
                if args.ort_config:command.extend(['--ort-config',str(args.ort_config.resolve())])
                if args.cpu_affinity:command.extend(['--cpu-affinity',*map(str,args.cpu_affinity)])
                if args.app_profile:command.append('--app-profile')
                print(f'Round {round_index+1}: {threads} threads', flush=True)
                subprocess.run(command, check=True,env={**os.environ,'VOXPAD_BENCH_SOURCE':str(args.source_dir.resolve())})
                config = json.loads(output.read_text('utf-8')); config['round'] = round_index+1
                report['configurations'].append(config)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(f'Report: {args.output}', flush=True)


if __name__ == '__main__': main()
