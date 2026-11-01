"""Prepare a stopped microphone stream without capturing audio while idle."""
import threading
import sounddevice as sd


class PreparedInput:
    def __init__(self,callback):
        self.callback=callback
        self.lock=threading.Lock()
        self.ready=threading.Condition(self.lock)
        self.io_lock=threading.RLock()
        self.cached=None
        self.pending=None
        self.generation=0
        self.closed=False

    @staticmethod
    def device_key(device):
        return int(sd.default.device[0]) if device is None else device

    def open(self,key):
        with self.io_lock:return self._open(key)

    def _open(self,key):
        rate=int(sd.query_devices(key,'input')['default_samplerate'])
        options=dict(device=key,samplerate=rate,channels=1,dtype='float32',
                     callback=self.callback,blocksize=0)
        try:stream=sd.InputStream(**options,latency='low')
        except sd.PortAudioError:stream=sd.InputStream(**options)
        return stream,rate,key

    def prepare(self,device):
        key=self.device_key(device)
        with self.lock:
            if self.closed or self.pending==key or (self.cached and self.cached[2]==key):return
            self.generation+=1;generation=self.generation
            old,self.cached=self.cached,None
            self.pending=key
            self.ready.notify_all()
        def worker():
            if old:self.dispose(old[0])
            try:
                with self.io_lock:
                    with self.lock:current=not self.closed and generation==self.generation
                    opened=self.open(key) if current else None
            except Exception:opened=None  # Show actionable errors only on a recording attempt.
            with self.lock:
                current=not self.closed and generation==self.generation
                if current:
                    previous,self.cached=self.cached,opened
                    self.pending=None
                else:previous=opened
                self.ready.notify_all()
            if previous:self.dispose(previous[0])
        threading.Thread(target=worker,daemon=True).start()

    def take(self,device):
        key=self.device_key(device)
        with self.ready:
            self.ready.wait_for(lambda:self.closed or self.pending!=key)
            if self.closed:raise RuntimeError('Microphone input is closed')
            self.generation+=1;self.pending=None
            opened,self.cached=self.cached,None
            self.ready.notify_all()
        if opened and opened[2]==key:return opened
        if opened:self.dispose(opened[0])
        return self.open(key)

    def recycle(self,stream,rate,key):
        with self.lock:
            self.generation+=1;self.pending=None
            old,self.cached=self.cached,None
            closed=self.closed
            if not closed:self.cached=(stream,rate,key)
            self.ready.notify_all()
        if old:self.dispose(old[0])
        if closed:self.dispose(stream)

    def start(self,stream):
        with self.io_lock:stream.start()

    def stop(self,stream):
        with self.io_lock:stream.stop()

    def dispose(self,stream):
        with self.io_lock:
            try:stream.close()
            except Exception:pass

    def clear(self):
        with self.lock:
            self.generation+=1;self.pending=None
            old,self.cached=self.cached,None
            self.ready.notify_all()
        if old:self.dispose(old[0])

    def close(self):
        with self.lock:self.closed=True
        self.clear()
