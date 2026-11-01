"""Settings operations wired to the existing recording, storage and model code."""
from pathlib import Path
import json
import threading
import time
import uuid
from tkinter import filedialog
import numpy as np

from media_jobs import audio_chunks
from model_manager import MODELS,download,installed
from app_paths import BASE


class Cancellation:
    def __init__(self,*events): self.events=events
    def is_set(self): return any(event.is_set() for event in self.events)

def pending_records(directory):
    directory=Path(directory)
    stems={p.stem for p in directory.glob('*.json')}|{p.stem for p in directory.glob('*.raw')}
    output=[]
    for stem in sorted(stems):
        if len(stem)!=32 or not all(c in '0123456789abcdef' for c in stem): continue
        meta=directory/(stem+'.json'); raw=directory/(stem+'.raw')
        record={'id':stem,'meta':meta,'raw':raw,'valid':False,'rate':0,'seconds':0,'size':0}
        try:
            data=json.loads(meta.read_text('utf-8')); rate=int(data['rate']); size=raw.stat().st_size
            if not 8000<=rate<=192000 or size<4 or size%4: raise ValueError('Invalid audio')
            record.update(valid=True,rate=rate,seconds=size/4/rate,size=size,created=data.get('created',0))
        except (OSError,ValueError,KeyError,TypeError): pass
        output.append(record)
    return output

class SettingsActions:
    def file_dialog_parent(self):
        activity=getattr(self,'activity_windows',{}).get('File transcription')
        return activity.window if activity and activity.alive else self.root

    def open_file(self):
        if self.busy or self.recording or self.loading_model or not self.engine: return
        paths=filedialog.askopenfilenames(parent=self.file_dialog_parent(),
            title=self.t('Choose files'),filetypes=[(self.t('Audio / video'),'*.wav *.flac *.ogg *.mp3 *.m4a *.mp4 *.mkv *.webm *.mov *.avi'),(self.t('All files'),'*.*')])
        if paths: self.enqueue_files(paths)

    def enqueue_files(self,paths):
        if self.busy or self.recording or self.loading_model or not self.engine: return
        folder=self.store.settings.get('export_folder')
        if not folder:
            folder=filedialog.askdirectory(parent=self.file_dialog_parent(),title=self.t('Export folder'))
            if not folder: return
            self.store.save({'export_folder':folder})
        jobs=[{'id':uuid.uuid4().hex,'path':str(path),'state':'Waiting','text':'','error':'',
               'duration':0.,'output':'','cancel':threading.Event()} for path in paths]
        self.file_jobs.extend(jobs)
        self.files_cancel.clear(); self.busy=True; self.set_busy()
        def worker():
            completed=0
            for job in jobs:
                cancel=Cancellation(self.files_cancel,job['cancel'])
                if cancel.is_set(): self.events.put(('file_job',(job['id'],{'state':'Cancelled'}))); continue
                self.events.put(('file_job',(job['id'],{'state':'Recognising'})))
                try:
                    pieces=[]; duration=0.; started=time.perf_counter()
                    for chunk in audio_chunks(job['path'],cancel):
                        if cancel.is_set(): raise InterruptedError()
                        text,_=self.engine.transcribe(chunk,16000)
                        if text: pieces.append(text)
                        duration+=len(chunk)/16000
                        self.events.put(('file_job',(job['id'],{'duration':duration})))
                    text=' '.join(pieces)
                    if cancel.is_set(): raise InterruptedError()
                    target=Path(folder)/(Path(job['path']).stem+'.txt'); index=1
                    while target.exists():
                        target=Path(folder)/(Path(job['path']).stem+f' ({index}).txt'); index+=1
                    with target.open('x',encoding='utf-8') as stream: stream.write(text+'\n')
                    self.store.add(text,duration,time.perf_counter()-started,'file')
                    self.events.put(('file_job',(job['id'],{'state':'Completed','text':text,'duration':duration,'output':str(target)})))
                    completed+=1
                except InterruptedError:
                    self.events.put(('file_job',(job['id'],{'state':'Cancelled'})))
                except Exception:
                    self.events.put(('file_job',(job['id'],{'state':'Failed','error':'Could not complete this action. Please try again.'})))
            self.events.put(('batch_done',f"{completed}/{len(jobs)} {self.t('files exported')}."))
        threading.Thread(target=worker,daemon=True).start()

    def download_model(self,model):
        if self.downloading or installed(BASE/'models',model): return
        self.downloading=True; self.model_cancel.clear()
        self.model_states[model]={'state':'Downloading model','done':0,'total':MODELS[model]['size'],'stage':'Downloading'}
        def progress(got,total,stage): self.events.put(('model_state',(model,{'state':'Downloading model','done':got,'total':total,'stage':stage})))
        def worker():
            try:
                download(BASE/'models',model,self.model_cancel,progress)
                state={'state':'Model ready'}; message=self.t('Done')
            except InterruptedError:
                state={'state':'Not downloaded'}; message=self.t('Download cancelled')
            except Exception as error:
                state={'state':'Download failed'}
                text=self.t(str(error)); message=text if text!=str(error) else self.t('Could not complete this action. Please try again.')
            self.events.put(('model_state',(model,state)))
            self.events.put(('download_done',message))
        threading.Thread(target=worker,daemon=True).start()

    def recover_record(self,record):
        if self.busy or self.recording or self.loading_model or not self.engine: return
        self.busy=True; self.set_busy()
        def worker():
            message='Recording is damaged or unavailable. Its files were retained.'
            try:
                if not record['valid']: raise ValueError()
                samples=np.fromfile(record['raw'],dtype='<f4')
                if not len(samples) or not np.isfinite(samples).all(): raise ValueError()
                text,seconds=self.engine.transcribe(samples,record['rate'])
                if text:
                    self.store.add(text,len(samples)/record['rate'],seconds,'recovery')
                    record['raw'].unlink(); record['meta'].unlink(missing_ok=True)
                    message='Recovered into history.'
                else: message='No speech was recognised. The saved audio was retained.'
            except Exception: pass
            self.events.put(('batch_done',self.t(message)))
        threading.Thread(target=worker,daemon=True).start()
