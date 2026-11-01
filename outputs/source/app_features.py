"""User-approved settings, history, files, models and text processing."""
import json
from pathlib import Path
import threading
import time
import tkinter as tk
from app_dialogs import messagebox

import numpy as np
import sounddevice as sd
from app_paths import BASE

from storage import Store
from settings_help import Choice
from ui_language import EN as EN_COPY, RU as RU_COPY
from text_processing import format_ending
from engine import Engine
from model_manager import MODELS, installed, remove
from media_jobs import RecoveryWriter, recoveries
from platform_features import TemporaryMute
from windows_input import copy_text, paste_if_focused, press_enter_if_focused
from audio_cues import AudioCues
from settings_actions import SettingsActions

VERSION='0.5.1'
NAMES={0xA0:'Left Shift',0xA1:'Right Shift',0xA2:'Left Ctrl',0xA3:'Right Ctrl',0xA4:'Left Alt',0xA5:'Right Alt',0x20:'Space',0x0D:'Enter',0x1B:'Escape'}


def chord_name(keys):
    return ' + '.join(NAMES.get(k,chr(k) if 48<=k<=90 else ('F'+str(k-111) if 112<=k<=135 else hex(k))) for k in keys)

class Features(SettingsActions):
    def __init__(self, root, smoke=False):
        self.store=Store(BASE/'data')
        self.audio_cues=AudioCues()
        self.recovery_writer=None
        self.mute=TemporaryMute()
        self.capture_action=None
        self.settings_window=None
        self.model_cancel=threading.Event()
        self.files_cancel=threading.Event()
        self.loading_model=False
        self.downloading=False
        self.current_ending=self.store.settings['ending']
        self.active_model=self.store.settings['model']
        self.paused=bool(self.store.settings.get('paused',False))
        self.activity_windows={}
        self.file_jobs=[]
        self.model_states={}
        self._request_checked=0.
        self._model_save_warning=''
        super().__init__(root,smoke)
        self.auto_paste.set(self.store.settings['auto_paste'])
        self.global_key.set(not self.paused)
        self.configure_bindings()
        self.configure_overlay()
        if not smoke:
            root.after(1000,self.offer_recovery)

    def t(self,text):
        return RU_COPY.get(text,text) if self.store.settings.get('language')=='ru' else EN_COPY.get(text,text)


    def chord_text(self,keys):
        value=chord_name(keys)
        if self.store.settings['language']=='ru':
            for original in sorted(NAMES.values(),key=len,reverse=True):
                value=value.replace(original,self.t(original))
        return value

    def build_ui(self):
        from main_window import build_main
        build_main(self)
        self.root.title('VoxPad. · '+VERSION)
        self.status.set(self.t('Loading model…'))

    def configure_bindings(self):
        settings=self.store.settings
        bindings={name:frozenset(keys) for name,keys in settings['shortcuts'].items() if keys and name in ('dictate','history')}
        self.hotkey.bindings=bindings

    def configure_overlay(self):
        self.overlay.backdrop_blur_mix=float(self.store.settings['glass_blur'])
        self.overlay.wave_color=self.store.settings['wave_color']

    def update_hotkey(self):
        super().update_hotkey()
        self.hotkey.enabled=self.hotkey.enabled and not self.paused and not self.loading_model

    def refresh_devices(self):
        self.input_devices=[None]
        super().refresh_devices()
        names=list(self.device['values'])
        if names: names[0]=self.t('System microphone'); self.device['values']=names
        selected=self.store.settings.get('microphone','')
        if selected in names: self.device.current(names.index(selected))
        self.device.bind('<<ComboboxSelected>>',lambda event:self.store.save({'microphone':self.device.get() if self.device.current()>0 else ''}))
        self.prepare_microphone()

    def load_model(self,requested_model=None):
        model=requested_model or self.store.settings['model']
        try:
            if model not in MODELS or not installed(BASE/'models',model):
                model='parakeet'
            self.loading_model=True
            threads=2
            config=BASE/'performance.json'
            if config.exists(): threads=int(json.loads(config.read_text())['threads'])
            started=time.perf_counter()
            engine=Engine(BASE/'models'/MODELS[model]['folder'],threads=threads,model=model,
                          language=self.store.settings['speech_language'])
            engine.warm_up()
            self.events.put(('loaded_model',(engine,time.perf_counter()-started,model)))
        except Exception as error:
            self.events.put(('load_failed',str(error)))

    def handle_event(self,kind,value):
        if kind=='tray_ready':
            if self.tray:
                self.tray.paused=self.paused
                self.tray.set_language(self.store.settings['language'])
            return True
        if kind=='loaded_model':
            self.engine,seconds,self.active_model=value
            self.loading_model=False
            try:
                self.store.save({'model':self.active_model})
                self._model_save_warning=''
            except (OSError,ValueError):
                self._model_save_warning=self.t('The model is ready, but its selection could not be saved. Check folder permissions and disk space.')
            self.events.put(('ready',(self.engine,seconds)))
            return True
        if kind=='ready':
            self.loading_model=False
            warning=self._model_save_warning
            self.root.after_idle(lambda:(self.status.set(self.t('Paused') if self.paused else self.t('Ready')),self.detail.set(warning or self.t('Select a field, use your dictation shortcut and release to insert.'))))
            return False
        if kind=='load_failed':
            self.loading_model=False; self.update_hotkey()
            if not self.engine and not installed(BASE/'models',self.active_model):
                self.status.set(self.t('Download the model first.'))
                self.detail.set(self.t('Open Settings → Recognition to download and select a model.'))
                self.enable_controls()
            else:self.show_error(self.t('Could not load the model. Check its files or download it again.'))
            return True
        if kind=='shortcut':
            self.shortcut(value); return True
        if kind=='shortcut_cancel':
            if self.capture_action:
                action,variable=self.capture_action
                variable.set(self.chord_text(self.pending_shortcuts.get(action,[])) or self.t('Not assigned'))
                self.capture_action=None
            return True
        if kind=='shortcut_capture':
            if self.capture_action:
                action,variable=self.capture_action
                conflict=any(name!=action and frozenset(keys)==frozenset(value) for name,keys in self.pending_shortcuts.items() if keys)
                if conflict:
                    variable.set(self.chord_text(self.pending_shortcuts.get(action,[])) or self.t('Not assigned'))
                    if getattr(self,'settings_ui',None): self.settings_ui.notice.set(self.t('This shortcut is already assigned to another action.'))
                else:
                    self.pending_shortcuts[action]=value
                    variable.set(self.chord_text(value))
                self.capture_action=None
            return True
        if kind=='file_job':
            identifier,changes=value
            for job in self.file_jobs:
                if job['id']==identifier: job.update(changes); break
            return True
        if kind=='model_state':
            model,changes=value
            self.model_states[model]=changes
            return True
        if kind=='tray_pause': self.toggle_pause(); return True
        if kind=='tray_settings': self.open_settings(); return True
        if kind=='tray_history': self.open_history(); return True
        if kind=='download_done':
            self.downloading=False
            if getattr(self,'model_progress',None): self.model_progress.set(self.t(value) if value else self.t('Done'))
            return True
        if kind=='batch_done':
            self.busy=False; self.enable_controls()
            self.status.set(self.t('Done')); self.detail.set(value)
            return True
        return False

    def on_poll(self):
        if self.smoke or time.monotonic()-self._request_checked<.5: return
        self._request_checked=time.monotonic()
        self.check_system_theme()
        if self.recording and self.mute.active:
            try:self.mute.refresh()
            except Exception:pass
        if self.recording and self.stream:
            try: connected=self.stream.active
            except Exception: connected=False
            if not connected:
                try:
                    previous_stream=self.stream
                    self.stream=None
                    self.audio_input.dispose(previous_stream)
                    if not self.store.settings.get('microphone_fallback',True):
                        raise RuntimeError()
                    with self.audio_input.io_lock:
                        self.stream=sd.InputStream(device=None,samplerate=self.rate,channels=1,dtype='float32',callback=self.audio_callback,blocksize=0,latency='low')
                    self._stream_device=self.audio_input.device_key(None)
                    self.audio_input.start(self.stream)
                    self.device.current(0)
                except Exception:
                    self.stop_recording()
                    self.detail.set(self.t('The selected microphone is disconnected. Choose another device.'))
        request=BASE/'data/show-window.request'
        if request.exists():
            request.unlink(missing_ok=True)
            self.open_window()

    def check_system_theme(self):
        """Follow Windows' application theme while the program is running."""
        if self.store.settings.get('ui_theme','system')!='system':return
        if self.recording or self.busy or self.loading_model or self.capture_action:return
        windows=[self.root]+[view.window for view in self.activity_windows.values()]
        if self.settings_window:windows.append(self.settings_window)
        if any(getattr(window,'_resize_handler',None) and window._resize_handler.sizing for window in windows):return
        from ui_style import theme_for
        if self.root.ui_theme!=theme_for('system'):self.rebuild_views()

    def rebuild_views(self,translate=False):
        """Recreate themed widgets while retaining window and editing state."""
        root=self.root;geometry=root.geometry();window_state=root.state()
        text=self.text.get('1.0','end-1c');cursor=self.text.index('insert')
        text_scroll=self.text.yview()[0];text_focus=root.focus_get()==self.text
        selection=tuple(map(str,self.text.tag_ranges('sel')))
        status=self.status.get();detail=self.detail.get();metrics=self.metrics.get()
        settings=getattr(self,'settings_ui',None)
        if settings and settings.alive:
            settings_state=(settings.current,settings.window.geometry(),
                {key:value.get() for key,value in settings.vars.items()},
                {key:list(value) for key,value in self.pending_shortcuts.items()},
                settings.scrolls[settings.current].yview()[0])
        else:settings_state=None
        activity_states={}
        tree_names={'History':'history_tree','File transcription':'file_tree','Recording recovery':'recovery_tree'}
        for kind,view in self.activity_windows.items():
            tree=getattr(view,tree_names.get(kind,''),None)
            activity_states[kind]={'geometry':view.window.geometry(),
                'query':view.query.get() if kind=='History' else None,
                'selection':tree.selection() if tree is not None else (),
                'scroll':tree.yview()[0] if tree is not None else 0,
                'result':bool(view.file_result.winfo_manager()) if kind=='File transcription' else False,
                'export':view.vars['export_folder'].get() if kind=='File transcription' else None}
        for view in list(self.activity_windows.values()):view.close()
        if settings_state:settings.close()
        for child in root.winfo_children():child.destroy()
        self.build_ui();root.geometry(geometry);self.refresh_devices()
        self.text.insert('1.0',text);self.text.mark_set('insert',cursor)
        if selection:self.text.tag_add('sel',*selection)
        root.after_idle(lambda:self.text.yview_moveto(text_scroll))
        if text_focus:self.text.focus_set()
        self.enable_controls()
        self.status.set(self.t('Paused') if self.paused else self.t('Ready') if translate else status)
        self.detail.set(detail);self.metrics.set(metrics)
        if settings_state:
            section,position,values,shortcuts,scroll=settings_state
            self.open_settings();ui=self.settings_ui
            for key,value in values.items():
                target=ui.vars[key]
                if isinstance(target,Choice):target.variable.set(target.labels[target.options.index(value)])
                else:target.set(value)
            self.pending_shortcuts=shortcuts
            for key,var in getattr(ui,'shortcut_labels',{}).items():var.set(self.chord_text(shortcuts.get(key,[])))
            ui.select(section);ui.window.geometry(position)
            ui.window.after_idle(lambda:ui.scrolls[section].yview_moveto(scroll) if ui.alive else None)
        for kind,state in activity_states.items():
            self.open_activity(kind);view=self.activity_windows[kind];view.window.geometry(state['geometry'])
            if kind=='History':view.query.set(state['query'])
            tree=getattr(view,tree_names.get(kind,''),None)
            if tree is not None:
                selected=[key for key in state['selection'] if tree.exists(key)]
                if selected:tree.selection_set(selected)
                view.window.after_idle(lambda view=view,tree=tree,scroll=state['scroll']:tree.yview_moveto(scroll) if view.alive else None)
            if kind=='File transcription':
                view.vars['export_folder'].set(state['export'])
                if state['result']:view.view_file()
        root.state(window_state)

    def shortcut(self,event):
        action,phase=event['action'],event['phase']
        if action=='history':
            if phase=='press': self.open_history()
            return
        if self.capture_action or self.loading_model or self.paused: return
        mode=action.split(':',1)[1] if action.startswith('ending:') else self.store.settings['ending']
        if phase=='press':
            self.current_ending=mode
            if self.recording:
                if self.store.settings['trigger_mode']=='toggle': self.stop_recording()
            else: self.start_recording(event['target'])
        elif phase=='release' and self.store.settings['trigger_mode']=='hold': self.stop_recording()

    def toggle_pause(self):
        if not self.paused and self.recording:
            self.stop_recording()
        self.paused=not self.paused
        if self.paused:self.audio_input.clear()
        else:self.prepare_microphone()
        self.global_key.set(not self.paused)
        self.store.save({'paused':self.paused})
        self.update_hotkey()
        if self.tray:
            self.tray.paused=self.paused; self.tray.icon.update_menu()
        self.status.set(self.t('Paused') if self.paused else self.t('Ready'))
        self.enable_controls()

    def sound(self,kind):
        if self.store.settings['sounds']:
            self.audio_cues.play(kind,self.store.settings.get('sound_volume',100))

    def mouse_press(self,event):
        if self.store.settings['trigger_mode']=='toggle':
            if self.recording: self.stop_recording()
            else: self.start_recording(None)
        else: super().mouse_press(event)

    def mouse_release(self,event):
        if self.store.settings['trigger_mode']=='hold': super().mouse_release(event)

    def start_recording(self,target):
        if self.loading_model or self.paused or self.recording or self.busy or not self.engine: return
        if target is None: self.current_ending=self.store.settings['ending']
        preferred=self.store.settings.get('microphone','')
        if preferred and preferred not in self.device['values'] and not self.store.settings.get('microphone_fallback',True):
            self.show_error(self.t('The selected microphone is disconnected. Choose another device.'))
            return
        super().start_recording(target)
        if self.recording:
            self.status.set(self.t('Recording…'))
            self.sound('start')
            if self.store.settings.get('mute_recording'):
                try:self.mute.begin()
                except Exception:self.restore_audio()
        else:
            self.restore_audio()

    def before_recording(self,rate):
        self.recovery_writer=RecoveryWriter(BASE/'data/pending',rate) if self.store.settings.get('save_unfinished',True) else None

    def cancel_recording_preparation(self):
        journal,self.recovery_writer=self.recovery_writer,None
        if journal:
            try:
                journal.finish()
                if not self.frames:journal.remove()
            except (OSError,TimeoutError):pass  # Retain any partial audio for recovery.

    def restore_audio(self):
        try: self.mute.restore()
        except Exception as error: self.detail.set(self.t('Audio restore')+': '+str(error))

    def stop_recording(self):
        if not self.recording: return
        super().stop_recording()
        self.restore_audio(); self.sound('stop')


    def recognize_chunks(self,chunks,rate):
        journal=self.recovery_writer
        try:
            if journal: journal.finish()
            samples=np.concatenate(chunks) if chunks else np.empty(0,dtype=np.float32)
            started=time.perf_counter()
            text,seconds=self.engine.transcribe(samples,rate)
            self.events.put(('result',dict(text=text,seconds=seconds,total=time.perf_counter()-started,
                                           duration=len(samples)/rate,journal=journal)))
        except Exception as error: self.events.put(('error',str(error)))

    def finish_result(self,result):
        text=result['text']; journal=result.get('journal')
        self.busy=False; self.enable_controls()
        if text:
            try:
                self.store.add(text,result['duration'],result['total'])
            except Exception as error:
                self.show_error(self.t('History could not be saved. Recovery audio retained.')+' '+str(error)); return
            self.text.delete('1.0','end'); self.text.insert('1.0',text)
            pasted=False;copied=False
            try:
                payload,enter=format_ending(text,self.current_ending)
                copy_text(payload,self.root.winfo_id())
                copied=True
                pasted=self.auto_paste.get() and paste_if_focused(self.target)
                if pasted and enter:
                    # Let the target consume Ctrl+V before posting Enter; no user delay setting.
                    self.root.after(80,lambda target=self.target:press_enter_if_focused(target))
            except (OSError,tk.TclError): pass
            self.status.set(self.t('Done'))
            destination=self.t('Text inserted.') if pasted else self.t('Copied. Press Ctrl+V to paste.') if copied else self.t('Could not copy the text. It is available in the text field and History.')
            self.detail.set(destination)
        else:
            self.status.set(self.t('No speech detected.'))
        if journal:
            journal.remove()
            if self.recovery_writer is journal: self.recovery_writer=None
        self.metrics.set(f"{self.active_model} · {time.perf_counter()-self.release_at:.2f} {self.t('s')} · {self.t('Recording time')}: {result['duration']:.1f} {self.t('s')}")

    def enable_controls(self):
        super().enable_controls()
        chord=self.chord_text(self.store.settings['shortcuts'].get('dictate',[]))
        label=self.t('Hold {shortcut} or this button').format(shortcut=chord) if self.store.settings['trigger_mode']=='hold' else self.t('Press {shortcut} or click to start / stop').format(shortcut=chord)
        theme=self.root.ui_theme
        keycap=chord.split()[-1] if chord and len(self.store.settings['shortcuts'].get('dictate',[]))==1 else ''
        self.record_button.configure(text=label,bg=theme.accent,fg=theme.accent_text,keycap=keycap,
                                     activebackground=theme.accent_hover,
                                     state='normal' if self.engine and not self.paused and not self.busy else 'disabled')
        if hasattr(self,'pause_button'):self.pause_button.configure(text=self.t('Resume dictation') if self.paused else self.t('Pause dictation'),icon='play' if self.paused else 'pause')

    def set_busy(self):
        super().set_busy()
        self.status.set(self.t('Transcribing…'))
        self.record_button.configure(text=self.t('Transcribing…'))
        self.detail.set(self.t('Recordings stay on this computer.'))

    def show_error(self,message):
        known=('Microphone unavailable. Check Windows permissions and the selected device.',
               'The selected microphone is disconnected. Choose another device.',
               'History could not be saved. Recovery audio retained.',
               'Could not load the model. Check its files or download it again.')
        safe=next((self.t(key) for key in known if str(message).startswith(key) or str(message).startswith(self.t(key))),
                  self.t('Could not complete this action. Please try again.'))
        super().show_error(safe)
        self.status.set(self.t('Error')); self.sound('error'); self.restore_audio()

    def offer_recovery(self):
        if not self.active:return
        if not self.store.settings.get('save_unfinished',True): return
        if self.busy or self.recording or self.loading_model or self.capture_action or not self.engine:
            self.root.after(1000,self.offer_recovery);return
        pending=recoveries(BASE/'data/pending')
        if not pending: return
        # Reserve the operation before the modal dialog starts its nested event loop.
        self.busy=True;self.enable_controls()
        try:accepted=messagebox.askyesno(self.t('Recover unfinished recordings?'),self.t('Interrupted recordings are available locally. Recover them into history?'))
        except Exception:
            self.busy=False;self.enable_controls();raise
        if not self.active:return
        if not accepted:
            self.busy=False;self.enable_controls();return
        self.set_busy()
        def worker():
            recovered=retained=0
            for meta,raw,rate in pending:
                try:
                    samples=np.fromfile(raw,dtype='<f4',count=raw.stat().st_size//4)
                    if not samples.size or not np.isfinite(samples).all():raise ValueError('Invalid audio')
                    text,seconds=self.engine.transcribe(samples,rate)
                    if not text.strip():
                        retained+=1;continue
                    self.store.add(text,len(samples)/rate,seconds,'recovery')
                    raw.unlink();meta.unlink(missing_ok=True);recovered+=1
                except Exception:retained+=1
            message=self.t('Recovered recordings: {recovered}. Retained for another attempt: {retained}.').format(recovered=recovered,retained=retained)
            self.events.put(('batch_done',message))
        threading.Thread(target=worker,daemon=True).start()


    def toggle_settings_busy(self):
        if self.busy or self.recording or self.loading_model:
            messagebox.showinfo(self.t('Settings'),self.t('Stop current work before changing settings.')); return True
        return False

    def open_activity(self,kind):
        previous=self.activity_windows.get(kind)
        if previous and previous.alive:
            previous.window.deiconify();previous.window.lift();return
        from activity_window import ActivityWindow
        self.activity_windows[kind]=ActivityWindow(self,kind)

    def open_history(self):self.open_activity('History')
    def open_statistics(self):self.open_activity('Statistics')
    def open_recovery(self):self.open_activity('Recording recovery')
    def open_files(self):self.open_activity('File transcription')

    def open_settings(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify(); self.settings_window.lift(); return
        from settings_window import SettingsWindow
        self.settings_ui=SettingsWindow(self)


    def switch_model(self,model):
        if self.toggle_settings_busy(): return
        if not installed(BASE/'models',model):
            messagebox.showinfo(self.t('Models'),self.t('Download the model first.')); return
        # Persist the model only after it has loaded successfully.
        self.loading_model=True; self.update_hotkey()
        self.record_button.configure(state='disabled')
        self.status.set(self.t('Loading model…'))
        def worker():
            self.load_model(model)
        threading.Thread(target=worker,daemon=True).start()

    def remove_model(self,model):
        if self.downloading: return
        if not messagebox.askyesno(self.t('Remove'),self.t(MODELS[model]['title'])+'?'): return
        try:
            remove(BASE/'models',model,self.active_model)
        except Exception as error: messagebox.showerror(self.t('Models'),str(error))


    def quit_app(self):
        if (self.recording or self.busy) and not self.smoke:
            self.open_window()
            if not messagebox.askyesno(self.t('Close'), self.t('Current work will be interrupted. Exit?')):
                return
        self.exit_confirmed=True
        if self.downloading:
            self.model_cancel.set()
        self.files_cancel.set()
        self.restore_audio()
        if getattr(self,'settings_ui',None):
            self.settings_ui.close()
        for activity in list(self.activity_windows.values()):activity.close()
        super().quit_app()
        if not self.active:
            if self.recovery_writer:
                try: self.recovery_writer.finish()
                except Exception: pass
            self.store.save({'auto_paste':self.auto_paste.get()})
