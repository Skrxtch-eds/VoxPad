"""User-provided cues; volume changes only these sounds, never system volume."""
import io
from pathlib import Path
import threading
import wave
import winsound
import numpy as np
import soundfile as sf

class AudioCues:
    def __init__(self):
        self.cache={}
        self.directory=Path(__file__).resolve().parent/'assets'

    def wav_bytes(self,kind,volume):
        volume=max(0,min(100,int(round(volume))))
        key=kind,volume
        if key in self.cache: return self.cache[key]
        if kind in ('start','stop'):
            audio,rate=sf.read(self.directory/f'record-{kind}.wav',dtype='float32',always_2d=True)
        else:
            rate=44100
            t=np.arange(int(rate*.09))/rate
            audio=(.15*np.sin(2*np.pi*350*t)*np.sin(np.pi*np.arange(len(t))/len(t))**2)[:,None]
        pcm=np.int16(np.clip(audio*(volume/100),-1,1)*32767)
        stream=io.BytesIO()
        with wave.open(stream,'wb') as wav:
            wav.setnchannels(pcm.shape[1]); wav.setsampwidth(2); wav.setframerate(rate)
            wav.writeframes(pcm.tobytes())
        data=stream.getvalue()
        if len(self.cache)>12: self.cache.clear()
        self.cache[key]=data
        return data

    def play(self,kind,volume):
        if volume<=0: return
        def worker():
            try: winsound.PlaySound(self.wav_bytes(kind,volume),winsound.SND_MEMORY|winsound.SND_NODEFAULT)
            except (OSError,RuntimeError): pass
        threading.Thread(target=worker,daemon=True).start()
