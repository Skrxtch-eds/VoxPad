"""Windows dictation lifecycle, microphone capture and the UI event loop."""
import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from app_dialogs import messagebox

import numpy as np
import sounddevice as sd

from audio_input import PreparedInput
from windows_input import Hotkey
from recording_overlay import RecordingOverlay
from system_tray import SystemTray
from app_paths import BASE



class CoreApp:
    def __init__(self, root, smoke=False):
        self.root = root
        self.smoke = smoke
        self.events = queue.Queue()
        self.engine = None
        self.busy = False
        self.recording = False
        self.stream = None
        self.chunks = []
        self.frames = 0
        self.level = 0.0
        self.target = None
        self.active = True
        self.input_devices = [None]
        self.release_at = 0.0
        self.hotkey = Hotkey(self.events)
        self.hotkey.enabled = False
        self.audio_input = PreparedInput(self.audio_callback)
        self.auto_paste = tk.BooleanVar(value=True)
        self.global_key = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Подготовка модели…')
        self.detail = tk.StringVar(value='Первый запуск занимает немного больше времени.')
        self.metrics = tk.StringVar(value='Parakeet v3 · локально · без API')
        self.build_ui()
        self.overlay = RecordingOverlay(root, lambda: self.level)
        self.tray = None
        if not smoke:
            self.tray = SystemTray(self.events)
            self.tray.start()
        self.refresh_devices()
        root.protocol('WM_DELETE_WINDOW', self.close)
        self._poll_job=root.after(8, self.poll)
        threading.Thread(target=self.load_model, daemon=True).start()


    def refresh_devices(self):
        labels = ['Системный микрофон']
        try:
            devices = sd.query_devices()
            apis = sd.query_hostapis()
            # WASAPI devices avoid duplicate MME/DirectSound entries.
            candidates = [(i, d) for i, d in enumerate(devices) if d['max_input_channels'] > 0]
            wasapi = [(i, d) for i, d in candidates if 'WASAPI' in apis[d['hostapi']]['name']]
            for index, device in wasapi or candidates:
                self.input_devices.append(index)
                labels.append(device['name'])
        except Exception:
            pass
        self.device['values'] = labels
        self.device.current(0)


    def update_hotkey(self):
        self.hotkey.enabled = bool(self.engine and self.global_key.get())

    def mouse_press(self, event):
        if self.engine and not self.busy and not self.recording:
            self.start_recording(None)

    def mouse_release(self, event):
        if self.recording and self.target is None:
            self.stop_recording()

    def start_recording(self, target):
        if not self.engine or self.busy or self.recording:
            return
        self.chunks = []
        self.frames = 0
        self.level = 0
        self.target = target
        try:
            index = self.input_devices[self.device.current()]
            self.start_microphone(index)
            try:
                if self.store.settings.get('capsule_enabled',True):
                    self.overlay.show(target)
            except Exception:
                self.overlay.hide()
            self.status.set('Запись…')
            self.detail.set('Отпусти правый Ctrl, чтобы получить текст. Запись ограничена двумя минутами.')
            self.record_button.configure(text=self.t('Recording…'))
            self.device.configure(state='disabled')
        except Exception as error:
            self.recording = False
            if self.stream:
                self.audio_input.dispose(self.stream)
                self.stream = None
            self.cancel_recording_preparation()
            self.show_error(self.t('Microphone unavailable. Check Windows permissions and the selected device.')+'\n' + str(error))

    def start_microphone(self,index):
        devices=[index]
        if index is not None and self.store.settings.get('microphone_fallback',True):devices.append(None)
        for attempt,device in enumerate(devices):
            try:self.stream,self.rate,self._stream_device=self.audio_input.take(device)
            except Exception:
                if attempt+1<len(devices):continue
                raise
            self.before_recording(self.rate)
            self.recording=True;self.started_at=time.perf_counter()
            try:self.audio_input.start(self.stream)
            except Exception:
                self.recording=False
                self.audio_input.dispose(self.stream);self.stream=None
                self.cancel_recording_preparation()
                self.chunks=[];self.frames=0;self.level=0
                if attempt+1<len(devices):continue
                raise
            if device!=index:self.device.current(0)
            return

    def before_recording(self,rate):
        pass

    def cancel_recording_preparation(self):
        pass

    def prepare_microphone(self):
        if not self.smoke and self.active and not self.busy and not self.recording and not getattr(self,'paused',False):
            try:self.audio_input.prepare(self.input_devices[self.device.current()])
            except Exception:pass

    def audio_callback(self, data, frames, timing, status):
        if self.recording and self.frames < self.rate * 120:
            self.chunks.append(data[:, 0].copy())
            self.frames += frames
            self.level = min(1.0, float(np.sqrt(np.mean(data * data))) * 10)
            if getattr(self,'recovery_writer',None):
                self.recovery_writer.append(data[:,0].copy())

    def stop_recording(self):
        if not self.recording:
            return
        self.release_at = time.perf_counter()
        self.recording = False
        self.overlay.hide()
        self.busy = True
        if self.stream:
            stream=self.stream
            self.stream = None
            try:
                self.audio_input.stop(stream)
                self.audio_input.recycle(stream,self.rate,self._stream_device)
            except Exception:self.audio_input.dispose(stream)
        chunks = self.chunks
        self.chunks = []
        self.set_busy()
        rate = self.rate
        threading.Thread(target=self.recognize_chunks, args=(chunks, rate), daemon=True).start()

    def set_busy(self):
        self.status.set('Распознаю…')
        self.detail.set('Модель обрабатывает запись на этом компьютере.')
        self.record_button.configure(state='disabled', text='Распознаю…')


    def enable_controls(self):
        self.record_button.configure(state='normal' if self.engine else 'disabled',
                                     text='Удерживай правый Ctrl или эту кнопку')
        self.device.configure(state='readonly')

    def show_error(self, message):
        self.busy = False
        self.status.set('Не получилось')
        self.detail.set(message)
        self.enable_controls()

    def poll(self):
        self._poll_job=None
        if not self.active:return
        try:self._poll_once()
        except Exception:
            if self.active:
                self.status.set(self.t('Error'))
                self.detail.set(self.t('Could not complete this action. Please try again.'))
        finally:
            if self.active:self._poll_job=self.root.after(8,self.poll)

    def _poll_once(self):
        if not self.active:
            return
        try:
            while True:
                kind, value = self.events.get_nowait()
                if self.handle_event(kind,value):
                    continue
                if kind == 'ready':
                    self.engine, seconds = value
                    self.status.set('Готов к диктовке')
                    self.detail.set('Поставь курсор в поле ввода. Зажми правый Ctrl, говори и отпусти — текст вставится автоматически.')
                    self.metrics.set(self.active_model+' · '+self.t('Model ready in {seconds}s · offline recognition').format(seconds=f'{seconds:.1f}'))
                    self.enable_controls()
                    self.prepare_microphone()
                    if not self.smoke:
                        if not self.hotkey.thread.is_alive():
                            self.hotkey.start()
                        self.update_hotkey()
                    else:
                        report={'ready':True,'load_seconds':seconds,'frozen':bool(getattr(sys,'frozen',False)),
                                'portable_runtime':bool(getattr(sys,'_voxpad_portable_root',None)),
                                'base':str(BASE),'executable':sys.executable}
                        if getattr(self,'smoke_audio',None):
                            try:
                                from media_jobs import audio_chunks
                                from pycaw.pycaw import AudioUtilities
                                report['audio_sessions']=len(AudioUtilities.GetAllSessions())
                                report['cue_bytes']=len(self.audio_cues.wav_bytes('start',50))
                                report['transcript']=' '.join(self.engine.transcribe(chunk)[0]
                                    for chunk in audio_chunks(self.smoke_audio,threading.Event()))
                                if not report['transcript']:raise ValueError('Smoke audio produced no text')
                            except Exception as error:
                                report.update(ready=False,error=str(error))
                        (BASE / 'smoke-test.json').write_text(json.dumps(report), 'utf-8')
                        self.root.after(150, self.close)
                elif kind == 'tray_open':
                    self.open_window()
                elif kind == 'tray_exit':
                    self.quit_app()
                    if not self.active:
                        return
                elif kind == 'tray_error':
                    self.open_window()
                    self.detail.set(self.t('Tray unavailable. The window remains open.'))
                elif kind == 'result':
                    self.finish_result(value)
                elif kind == 'hook_error':
                    self.global_key.set(False)
                    self.detail.set(self.t('Shortcut unavailable. Use the recording button.'))
                elif kind == 'error':
                    self.show_error(value)
                    if self.smoke:
                        (BASE / 'smoke-test.json').write_text(json.dumps({'ready': False, 'error': value}), 'utf-8')
                        self.root.after(150, self.close)
        except queue.Empty:
            pass
        if not self.active:return
        self.on_poll()
        if self.recording:
            self.detail.set(f'{self.t("Recording…")} {time.perf_counter() - self.started_at:.1f}s')
            if time.perf_counter() - self.started_at >= 120:
                self.stop_recording()


    def close(self):
        if self.smoke:
            self.quit_app()
        elif not self.store.settings.get('background_mode',True):
            self.quit_app()
        elif self.tray and self.tray.ready.is_set():
            self.root.withdraw()
        else:
            self.detail.set(self.t('Preparing tray icon. Try closing the window again in a moment.'))

    def open_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit_app(self):
        if not self.active:
            return
        if (self.recording or self.busy) and not getattr(self,'exit_confirmed',False):
            self.open_window()
            if not messagebox.askyesno('Закрыть транскрибатор?', 'Текущая запись или обработка будет прервана.'):
                return
        self.active = False
        self.audio_input.close()
        self.overlay.close()
        self.recording = False
        self.hotkey.close()
        if self.tray:
            self.tray.close()
        if self.stream:
            self.audio_input.dispose(self.stream)
        if getattr(self,'_poll_job',None):
            self.root.after_cancel(self._poll_job)
        self.root.destroy()


from app_features import Features

class App(Features,CoreApp):
    pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--smoke-audio', type=Path, help='With --smoke-test, transcribe a local fixture without saving history')
    parser.add_argument('--tray', action='store_true')
    args = parser.parse_args()
    mutex=None
    if not args.smoke_test:
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
        kernel.CreateMutexW.restype=wintypes.HANDLE
        mutex=kernel.CreateMutexW(None,False,'Local\\ParakeetTranscriber')
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error()==183:
            request=BASE/'data/show-window.request'
            request.parent.mkdir(parents=True,exist_ok=True)
            request.touch()
            return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('VoxPad.Desktop')
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app=App(root, smoke=args.smoke_test)
    app.smoke_audio=args.smoke_audio
    if args.tray: root.withdraw()
    root.mainloop()


if __name__ == '__main__':
    main()
