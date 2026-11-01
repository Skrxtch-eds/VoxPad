"""Bounded-memory audio/video decoding and incremental crash recovery."""
from pathlib import Path
import json
import os
import queue
import threading
import time
import uuid

import av
import numpy as np

def audio_chunks(path, cancel, seconds=20):
    with av.open(str(path)) as container:
        if not container.streams.audio: raise ValueError('No audio track in this file')
        audio=container.streams.audio[0]
        resampler=av.AudioResampler(format='flt',layout='mono',rate=16000)
        pending=[]; count=0; limit=16000*seconds
        for frame in container.decode(audio):
            if cancel.is_set(): raise InterruptedError('Cancelled')
            for output in resampler.resample(frame):
                samples=output.to_ndarray().reshape(-1).astype(np.float32)
                offset=0
                while offset<len(samples):
                    take=min(limit-count,len(samples)-offset)
                    pending.append(samples[offset:offset+take]); count+=take; offset+=take
                    if count==limit:
                        yield np.concatenate(pending)
                        pending=[]; count=0
        for output in resampler.resample(None):
            pending.append(output.to_ndarray().reshape(-1).astype(np.float32))
        if pending: yield np.concatenate(pending)

class RecoveryWriter:
    def __init__(self, directory, rate):
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.identifier=uuid.uuid4().hex
        self.raw=self.directory/(self.identifier+'.raw')
        self.meta=self.directory/(self.identifier+'.json')
        self.meta.write_text(json.dumps({'rate':rate,'created':time.time()}),'utf-8')
        self.queue=queue.Queue(); self.error=None
        self.thread=threading.Thread(target=self.run,daemon=True); self.thread.start()

    def append(self, samples):
        self.queue.put(samples)

    def run(self):
        try:
            with self.raw.open('wb') as stream:
                last=time.monotonic()
                while True:
                    samples=self.queue.get()
                    if samples is None: break
                    stream.write(np.asarray(samples,dtype='<f4').tobytes())
                    if time.monotonic()-last>1:
                        stream.flush(); os.fsync(stream.fileno()); last=time.monotonic()
                stream.flush(); os.fsync(stream.fileno())
        except OSError as error:
            self.error=error

    def finish(self):
        self.queue.put(None); self.thread.join(timeout=10)
        if self.thread.is_alive(): raise TimeoutError('Recovery file is still being written')
        if self.error: raise self.error

    def remove(self):
        self.raw.unlink(missing_ok=True); self.meta.unlink(missing_ok=True)

def recoveries(directory):
    output=[]
    for meta in Path(directory).glob('*.json'):
        raw=meta.with_suffix('.raw')
        if raw.exists() and raw.stat().st_size>=400:
            try:
                data=json.loads(meta.read_text('utf-8'))
                rate=int(data['rate'])
                if not 8000<=rate<=192000: continue
                output.append((meta,raw,rate))
            except (ValueError,OSError,KeyError): pass
    return output
