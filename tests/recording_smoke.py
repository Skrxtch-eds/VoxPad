"""Exercise real Tk button/hotkey paths with synthetic audio and temporary data."""
from pathlib import Path
import sys,tempfile,time,tkinter as tk
from unittest.mock import Mock,patch
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'outputs/source'))
import app as application,app_features,settings_window,activity_window,settings_actions
from app import App
from storage import Store


def pump(root,predicate):
    end=time.monotonic()+5
    while not predicate():
        root.update();time.sleep(.002)
        if time.monotonic()>end:raise AssertionError('Recording action timed out')


with tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent) as temp:
    directory=Path(temp)
    for module in (application,app_features,settings_window,activity_window,settings_actions):module.BASE=directory
    store=Store(directory);store.save({'language':'ru','ui_theme':'light','sounds':False,'auto_paste':False})
    errors=[];root=tk.Tk();root.withdraw();root.report_callback_exception=lambda kind,error,trace:errors.append(str(error))
    engine=Mock();engine.transcribe.return_value=('Проверка записи',.001)
    with patch('app_features.Store',return_value=store),patch('app_features.Engine',return_value=engine):
        app=App(root,smoke=True);app.close=lambda:None
        pump(root,lambda:app.engine is not None and not app.loading_model)
    root.deiconify();root.update()
    streams=[];first_frames=[]
    class Stream:
        def __init__(self):self.starts=0;self.closed=False;self.active=False
        def start(self):
            assert not self.closed
            self.starts+=1;self.active=True
            app.audio_callback(np.ones((480,1),dtype=np.float32)*.01,480,None,False)
        def stop(self):self.active=False
        def close(self):self.closed=True;self.active=False
    def open_stream(key):
        stream=Stream();streams.append(stream);return stream,48000,key
    real_present=app.overlay.present
    def present(image,opacity):
        if app.overlay.visible:first_frames.append((time.perf_counter(),opacity))
        real_present(image,opacity)
    with patch.object(app.audio_input,'open',side_effect=open_stream),patch.object(app.overlay,'present',side_effect=present),patch('app_features.copy_text'):
        app.audio_input.prepare(app.input_devices[app.device.current()])
        pump(root,lambda:app.audio_input.cached is not None)
        assert streams[0].starts==0 and not app.recording
        started=time.perf_counter();app.record_button.event_generate('<ButtonPress-1>',x=20,y=20)
        assert app.recording and app.frames==480 and app.recovery_writer
        assert first_frames and .45<=first_frames[0][1]<.9,first_frames
        pump(root,lambda:app.overlay.amount==1.)
        assert len(first_frames)>1 and first_frames[-1][1]==1.
        assert all(a[1]<=b[1] for a,b in zip(first_frames,first_frames[1:]))
        print(f'Button press to first visible capsule: {(first_frames[0][0]-started)*1000:.1f} ms; intro: {(first_frames[-1][0]-first_frames[0][0])*1000:.1f} ms',flush=True)
        app.record_button.event_generate('<ButtonRelease-1>',x=20,y=20)
        pump(root,lambda:not app.busy)
        assert not app.recording and not app.overlay.visible and streams[0].starts==1
        assert app.text.get('1.0','end-1c')=='Проверка записи'
        assert not list((directory/'data/pending').glob('*.raw'))
        # A second recording uses the same stopped stream; release cannot retrigger it.
        app.shortcut({'action':'dictate','phase':'press','target':root.winfo_id()})
        assert app.recording and streams[0].starts==2 and len(streams)==1
        app.shortcut({'action':'dictate','phase':'release','target':None});pump(root,lambda:not app.busy)
        app.shortcut({'action':'dictate','phase':'release','target':None});assert not app.recording
        store.save({'trigger_mode':'toggle'})
        app.mouse_press(None);assert app.recording
        app.mouse_release(None);assert app.recording
        app.mouse_press(None);pump(root,lambda:not app.busy);assert not app.recording
        app.toggle_pause();assert app.paused and app.audio_input.cached is None and streams[0].closed
        app.mouse_press(None);assert not app.recording
        app.toggle_pause()
        # A cached selected device can fail at start after being unplugged.
        # The same press must use the default device, with a fresh recovery rate.
        bad=Stream();bad.start=Mock(side_effect=RuntimeError('selected device unplugged'))
        app.input_devices=[None,9876];app.device['values']=['Default','Fixture microphone'];app.device.current(1)
        app.audio_input.recycle(bad,44100,9876)
        with patch.object(app,'show_error') as error:
            app.start_recording(None)
            assert app.recording and bad.closed and not error.called
            assert app.device.current()==0 and app.rate==48000
            assert __import__('json').loads(app.recovery_writer.meta.read_text())['rate']==48000
        app.stop_recording();pump(root,lambda:not app.busy)
        assert not list((directory/'data/pending').glob('*.raw'))
        # A failed driver start cleans up the recovery journal and never leaves recording enabled.
        bad=Stream();bad.start=Mock(side_effect=RuntimeError('device unplugged'))
        app.audio_input.recycle(bad,48000,app.audio_input.device_key(app.input_devices[app.device.current()]))
        with patch.object(app,'show_error') as error:
            app.start_recording(None)
            assert error.called and not app.recording and app.stream is None and bad.closed
            assert app.recovery_writer is None and not list((directory/'data/pending').glob('*.raw'))
        app.quit_app()
    assert not errors,errors
print('PASS: capture starts on press, immediate capsule, warm reuse, hold/toggle/release, recovery, pause and driver failure cleanup',flush=True)
