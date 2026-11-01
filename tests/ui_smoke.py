"""Windows UI regression checks using temporary data and a mock recognizer."""
from pathlib import Path
import io,json,sys,tempfile,threading,time,tkinter as tk,wave
from tkinter import ttk
from unittest.mock import Mock,patch
import numpy as np
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/source'))
from app import App
from storage import Store
from text_processing import format_ending
from audio_cues import AudioCues

def pump(root,predicate,timeout=8):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        root.update()
        if predicate():return
        time.sleep(.02)
    raise AssertionError('Operation did not finish')

def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)

def texts(widget):
    result=[]
    for child in walk(widget):
        try:result.append(child.cget('text'))
        except tk.TclError:pass
    return result

with tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent) as temporary:
    directory=Path(temporary)
    # Keep model lookups, smoke reports and recovery scans in the fixture too.
    import app as application,app_features,settings_window,activity_window,settings_actions
    for module in (application,app_features,settings_window,activity_window,settings_actions):module.BASE=directory
    for language in ('ru','en'):
        store=Store(directory/language)
        export=directory/language/'export';export.mkdir()
        store.save({'language':language,'export_folder':str(export),'sounds':False})
        root=tk.Tk();root.withdraw()
        engine=Mock();engine.transcribe.return_value=('Is it ready?',.01)
        with patch('app_features.Store',return_value=store),patch('app_features.Engine',return_value=engine):
            app=App(root,smoke=True)
            app.close=lambda:None
            pump(root,lambda:app.engine is not None and not app.loading_model)
        app.open_settings();ui=app.settings_ui;ui.window.withdraw();root.update()
        assert set(ui.vars).isdisjoint({'punctuation','remove_interjections','sound_start_enabled','sound_stop_enabled'})
        assert set(app.pending_shortcuts)=={'dictate','history'}
        assert 'ui_theme' in ui.vars and 'paused' in ui.vars
        assert set(app.main_nav)=={'Dictation','History','Recording recovery','File transcription','Statistics'}
        visible_labels=texts(ui.pages['Recognition'])
        for title in ('Speed','Accuracy','Russian speech'):
            assert any(str(label).startswith(app.t(title)+' · ') for label in visible_labels)
        # A downloaded default model must remain selectable after a clean start
        # where its first load failed because no model files were present.
        ready_engine=app.engine;app.engine=None
        with patch('settings_window.installed',return_value=True):
            ui.refresh()
            assert ui.model_rows[app.active_model][3].winfo_manager()=='pack'
        app.engine=ready_engine;ui.refresh()
        assert not any(hasattr(ui,name) for name in ('file_tree','history_tree','stats','recovery_tree'))
        visible=texts(ui.window)
        explanation=app.t('After recognition, text appears in the field where your cursor was.')
        assert explanation not in visible
        title=next(w for w in walk(ui.window) if isinstance(w,ttk.Label) and w.cget('text')==app.t('Paste automatically'))
        assert title._tooltip.text==explanation
        title._tooltip.show();root.update();assert title._tooltip.window is not None
        title._tooltip.hide()
        ui.vars['sounds'].set(True);ui.vars['sound_volume'].set(42);ui.save()
        assert store.settings['sounds'] and store.settings['sound_volume']==42
        for key in ('remove_interjections','sound_start_enabled','sound_stop_enabled','punctuation','ending_shortcuts'):
            assert key not in Store(directory/language).settings
        assert not app.device.winfo_manager()
        assert not hasattr(app,'meter') and not hasattr(app,'file_button')
        assert app.pause_button.cget('text')==app.t('Pause dictation')
        app.toggle_pause();assert app.paused and app.record_button.cget('state')=='disabled'
        app.toggle_pause();assert not app.paused
        with patch.object(app.audio_cues,'play') as play:
            app.sound('start');app.sound('stop')
            assert [c.args for c in play.call_args_list]==[('start',42),('stop',42)]
        store.add('A saved transcript?',2,.1)
        for kind in ('History','Recording recovery','File transcription','Statistics'):
            app.open_activity(kind);window=app.activity_windows[kind]
            window.window.withdraw();window.refresh()
            assert not window.notice.get(),(kind,window.notice.get())
            assert str(window.window)!=str(ui.window)
            if kind=='Recording recovery':
                assert all(button.cget('state')=='disabled' for button in window.recovery_buttons.values())
            elif kind=='File transcription':
                assert all(button.cget('state')=='disabled' for button in window.file_buttons.values())
        history=app.activity_windows['History']
        key=history.history_tree.get_children()[0];history.history_tree.selection_set(key);history.view_history()
        assert history.history_result.get('1.0','end-1c')=='A saved transcript?'
        history.query.set('unmatched');assert not history.history_tree.get_children()
        media=directory/language/'sample.wav';sf.write(media,np.zeros(16000,dtype=np.float32),16000)
        app.enqueue_files([media]);pump(root,lambda:not app.busy)
        files=app.activity_windows['File transcription'];files.refresh()
        assert app.file_jobs[-1]['state']=='Completed'
        files.file_tree.selection_set(app.file_jobs[-1]['id']);files.view_file()
        assert files.file_result.get('1.0','end-1c')=='Is it ready?'
        assert (export/'sample.txt').read_text('utf-8').strip()=='Is it ready?'
        # Language changes rebuild all open windows without stale refresh timers.
        target='en' if language=='ru' else 'ru'
        ui.vars['language'].variable.set(ui.vars['language'].labels[ui.vars['language'].options.index(target)])
        ui.save();root.update()
        assert set(app.activity_windows)=={'History','Recording recovery','File transcription','Statistics'}
        assert all(w.alive for w in app.activity_windows.values())
        app.quit_app()
        print('PASS:',language,'hover-only help, reduced settings, unified cues, independent windows, history, file export, pause, language rebuild',flush=True)

for ending in ('period_space','period_enter'):
    assert format_ending('Is it ready?',ending)[0].rstrip()=='Is it ready?'
    assert format_ending('Stop!',ending)[0].rstrip()=='Stop!'
assert format_ending('Hello','period_space')==('Hello. ',False)
cue=AudioCues()
for kind in ('start','stop'):
    full=cue.wav_bytes(kind,100);half=cue.wav_bytes(kind,50)
    with wave.open(io.BytesIO(full)) as audio:
        a=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(float)
    with wave.open(io.BytesIO(half)) as audio:
        b=np.frombuffer(audio.readframes(audio.getnframes()),dtype='<i2').astype(float)
    assert abs(np.max(abs(b))/np.max(abs(a))-.5)<.001
print('PASS: contextual model punctuation preserved; both PCM cue files valid with real volume scaling',flush=True)

