"""Qt/QML bridge. Audio, ASR and persistence never run on the GUI thread."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime
import json
from pathlib import Path
import queue
import sys
import threading
import time

import numpy as np
import sounddevice as sd
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from app_paths import BASE, DATA
from audio_cues import AudioCues
from audio_input import PreparedInput
from cpu_runtime import recognition_cpu
from diagnostics import LatencyTrace
from engine import Engine, configured_threads, configured_cpu_profile
from model_manager import MODELS, installed, download
from storage import Store
from text_processing import format_ending
from windows_input import Hotkey, copy_text, paste_if_focused
from qt_recording_overlay import QtRecordingOverlay, is_external_target


KEY_NAMES = {160: 'Левый Shift', 161: 'Правый Shift', 162: 'Левый Ctrl',
             163: 'Правый Ctrl', 164: 'Левый Alt', 165: 'Правый Alt',
             32: 'Пробел', 13: 'Enter', 27: 'Escape', 91: 'Win', 92: 'Win'}
WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
MONTH_SHORT = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']


def chord_text(keys):
    return ' + '.join(KEY_NAMES.get(k, chr(k) if 48 <= k <= 90 else
                     'F' + str(k - 111) if 112 <= k <= 135 else hex(k)) for k in keys)


class Controller(QObject):
    stateChanged = Signal()
    preferencesChanged = Signal()
    contentChanged = Signal()
    dataChanged = Signal()
    navigationRequested = Signal(str)
    toastRequested = Signal(str)
    exitConfirmationRequested = Signal()
    smokeFinished = Signal(bool)

    def __init__(self, directory=None, *, preview=False, smoke=False, smoke_audio=None, diagnostics=None):
        super().__init__()
        self.store = Store(directory or DATA)
        self._preferences = dict(self.store.settings)
        self.preview, self.smoke = preview, smoke
        self.smoke_audio, self.diagnostics_path = smoke_audio, diagnostics
        self.events = queue.Queue()
        self._io = ThreadPoolExecutor(max_workers=1, thread_name_prefix='VoxPad-storage')
        self._workers = set()
        self._phase = 'ready' if preview else 'loading'
        self._status = 'Готово к записи' if preview else 'Подготовка модели…'
        self._text = ''
        self._history, self._daily, self._statistics = [], [], {}
        self._devices, self._device_ids = ['Системный микрофон'], [None]
        self._date_range = ''
        self._capturing = False
        self.engine = None
        self.active = True
        self.recording = False
        self.stream = None
        self.target = None
        self.chunks = []
        self.frames = 0
        self.level = 0.0
        self.overlay = None
        self.rate = 16000
        self._release_pending = False
        self._stop_cue_played = False
        self._device_refreshing = False
        self._refreshing = False
        self._refresh_again = False
        self._recovering = False
        self._last_system_check = 0.0
        self.model_cancel = threading.Event()
        self.audio_input = PreparedInput(self.audio_callback)
        self.audio_cues = AudioCues()
        self.hotkey = Hotkey(self.events)
        self.hotkey.enabled = False
        self._configure_hotkey()
        self.window = None
        self.tray = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(8)
        self._poll_timer.timeout.connect(self.poll)
        self._poll_timer.start()
        self._device_timer = QTimer(self)
        self._device_timer.setInterval(2000)
        self._device_timer.timeout.connect(self.refresh_devices)
        if not preview and not smoke:
            self.hotkey.start()  # Capture can work even before the ASR model is ready.
            self.refresh_devices()
            self._device_timer.start()
        self.refresh_data()
        if not preview:
            self._worker(self.load_model)

    phase = Property(str, lambda self: self._phase, notify=stateChanged)
    status = Property(str, lambda self: self._status, notify=stateChanged)
    paused = Property(bool, lambda self: self._preferences['paused'], notify=preferencesChanged)
    canRecord = Property(bool, lambda self: not self._preferences['paused'] and
                         self._phase in ('ready', 'recording', 'missing', 'error'), notify=stateChanged)
    preferences = Property('QVariantMap', lambda self: self._preferences, notify=preferencesChanged)
    shortcutLabel = Property(str, lambda self: 'Нажмите сочетание…' if self._capturing else
                             chord_text(self._preferences['shortcuts']['dictate']), notify=preferencesChanged)
    capturingShortcut = Property(bool, lambda self: self._capturing, notify=preferencesChanged)
    text = Property(str, lambda self: self._text, notify=contentChanged)
    history = Property('QVariantList', lambda self: self._history, notify=dataChanged)
    statistics = Property('QVariantMap', lambda self: self._statistics, notify=dataChanged)
    daily = Property('QVariantList', lambda self: self._daily, notify=dataChanged)
    dateRange = Property(str, lambda self: self._date_range, notify=dataChanged)
    devices = Property('QStringList', lambda self: self._devices, notify=preferencesChanged)
    deviceIndex = Property(int, lambda self: self._devices.index(self._preferences['microphone'])
                           if self._preferences['microphone'] in self._devices else 0, notify=preferencesChanged)

    def _set_phase(self, phase, status):
        self._phase, self._status = phase, status
        self._configure_hotkey()
        self.stateChanged.emit()

    def _configure_hotkey(self):
        self.hotkey.bindings = {'dictate': frozenset(self._preferences['shortcuts']['dictate'])}
        self.hotkey.enabled = bool(self.active and self.engine and not self._preferences['paused']
                                   and not self._capturing and self._phase in ('ready', 'recording'))

    def _worker(self, function, *args):
        def run():
            try:
                function(*args)
            except Exception:
                self.events.put(('error', 'Не удалось выполнить действие. Попробуйте ещё раз.'))
            finally:
                self.events.put(('worker_done', threading.current_thread()))
        worker = threading.Thread(target=run, name='VoxPad-worker', daemon=False)
        self._workers.add(worker)
        worker.start()
        return worker

    @Slot(str)
    def setText(self, value):
        if self._text != value:
            self._text = value
            self.contentChanged.emit()

    @Slot(str)
    def copyText(self, value):
        if not value:
            return
        QGuiApplication.clipboard().setText(value)
        self.toastRequested.emit('Скопировано')

    @Slot(str)
    def navigate(self, page):
        if self._capturing:
            self.cancelShortcut()
        if page in ('history', 'statistics'):
            self.refresh_data()
        self.navigationRequested.emit(page)

    @Slot()
    def togglePause(self):
        if self._phase in ('starting', 'recording'):
            self._request_stop()
        self.setSetting('paused', not self._preferences['paused'])
        self._configure_hotkey()
        if self._phase in ('ready', 'error'):
            self._set_phase('ready', 'Диктовка на паузе' if self._preferences['paused'] else 'Готово к записи')
        if not self._preferences['paused']:
            self.prepare_microphone()

    @Slot(str, 'QVariant')
    def setSetting(self, key, value):
        if key not in ('trigger_mode', 'sounds', 'microphone', 'microphone_fallback',
                       'ui_theme', 'autostart', 'background_mode', 'paused'):
            return
        if key == 'trigger_mode' and value not in ('hold', 'toggle'):
            return
        if key == 'ui_theme' and value not in ('light', 'dark'):
            return
        if key in ('trigger_mode', 'microphone', 'microphone_fallback') and self._phase in ('starting', 'recording', 'transcribing'):
            self.toastRequested.emit('Дождитесь завершения записи')
            self.preferencesChanged.emit()
            return
        old = self._preferences[key]
        self._preferences[key] = value
        self.preferencesChanged.emit()
        self.stateChanged.emit()
        self._io.submit(self._save_setting, key, value, old)
        if key == 'microphone':
            self.prepare_microphone()

    @Slot(int)
    def selectDevice(self, index):
        if 0 <= index < len(self._devices):
            self.setSetting('microphone', self._devices[index] if index else '')

    @Slot()
    def captureShortcut(self):
        if self._phase in ('starting', 'recording', 'transcribing'):
            self.toastRequested.emit('Дождитесь завершения записи')
            return
        self._capturing = True
        self.hotkey.captured.clear()
        self.hotkey.capture = True
        self._configure_hotkey()
        self.preferencesChanged.emit()

    @Slot()
    def cancelShortcut(self):
        self.hotkey.capture = False
        self.hotkey.captured.clear()
        self._capturing = False
        self._configure_hotkey()
        self.preferencesChanged.emit()

    @Slot()
    def recordPressed(self):
        if self._phase == 'missing' or (self._phase == 'error' and not self.engine):
            self.download_model()
        elif self._preferences['trigger_mode'] == 'toggle' and self._phase in ('starting', 'recording'):
            self._request_stop()
        elif self._phase in ('ready', 'error'):
            self.start_recording(None)

    @Slot()
    def recordReleased(self):
        if self._preferences['trigger_mode'] == 'hold':
            self._request_stop()

    def _request_stop(self, timing=None):
        if self._phase == 'starting':
            self._release_pending = True
            self._play_stop_cue()
        else:
            self.stop_recording(timing)

    def _play_stop_cue(self):
        if not self._stop_cue_played:
            self._stop_cue_played = True
            self._sound('stop')

    def refresh_devices(self):
        if not self.active or self._device_refreshing or self._phase in ('starting', 'transcribing'):
            return
        self._device_refreshing = True
        def query_devices():
            ids, names = [None], ['Системный микрофон']
            try:
                devices, apis = sd.query_devices(), sd.query_hostapis()
                candidates = [(i, d) for i, d in enumerate(devices) if d['max_input_channels'] > 0]
                wasapi = [(i, d) for i, d in candidates if 'WASAPI' in apis[d['hostapi']]['name']]
                for index, device in wasapi or candidates:
                    ids.append(index)
                    names.append(device['name'])
            except Exception:
                pass
            self.events.put(('devices', (ids, names)))
        self._io.submit(query_devices)

    def prepare_microphone(self):
        if self.preview or self.smoke or not self.active or self._preferences['paused'] or self._phase != 'ready':
            return
        try:
            self.audio_input.prepare(self._device_ids[self.deviceIndex])
        except Exception:
            pass

    def load_model(self):
        try:
            if self.store.retry_unsaved():
                self.events.put(('notice', 'Часть текстов пока не сохранена в историю. Локальные копии сохранены.'))
            threads = configured_threads(BASE / 'performance.json')
            started = time.perf_counter()
            with recognition_cpu('parakeet', threads, configured_cpu_profile(BASE / 'performance.json')) as cpu:
                engine = Engine(BASE / 'models' / MODELS['parakeet']['folder'], threads=threads, provider=cpu.provider)
                engine.warm_up()
            self.events.put(('ready', (engine, time.perf_counter() - started)))
        except Exception:
            self.events.put(('model_failed', not installed(BASE / 'models', 'parakeet')))

    def download_model(self):
        if self.preview or self._phase in ('downloading', 'loading'):
            return
        self._set_phase('downloading', 'Загрузка модели… 0%')
        self.model_cancel.clear()
        def fetch():
            try:
                download(BASE / 'models', 'parakeet', self.model_cancel,
                         lambda done, total, stage: self.events.put(('progress', done / max(1, total))), force=True)
                self.events.put(('downloaded', None))
            except InterruptedError:
                pass
            except Exception:
                self.events.put(('error', 'Не удалось загрузить модель. Проверьте интернет и свободное место.'))
        self._worker(fetch)

    def audio_callback(self, data, frames, timing, status):
        if self.recording and self.frames < self.rate * 120:
            samples = data[:, 0].copy()
            self.chunks.append(samples)
            self.frames += len(samples)
            self.level = min(1.0, float(np.sqrt(np.mean(samples * samples))) * 10)

    def _show_recording_overlay(self):
        if not self.target or not is_external_target(self.target):
            return
        try:
            if self.overlay is None:
                self.overlay = QtRecordingOverlay(
                    self, lambda: int(self.window.winId()) if self.window else 0,
                    lambda: self.level)
            self.overlay.show(self.target)
        except Exception:
            self._hide_recording_overlay()
            self.toastRequested.emit('Не удалось показать индикатор записи')

    def _hide_recording_overlay(self):
        if self.overlay is not None:
            self.overlay.hide()

    def start_recording(self, target):
        if not self.engine or self._preferences['paused'] or self._phase not in ('ready', 'error'):
            return
        preferred = self._preferences['microphone']
        fallback = self._preferences['microphone_fallback']
        if preferred and preferred not in self._devices and not fallback:
            self._set_phase('error', 'Выбранный микрофон отключён')
            return
        self._stop_cue_played = False
        self._sound('start')
        self.target = target
        self.chunks, self.frames = [], 0
        self.level = 0.0
        self._release_pending = False
        device = self._device_ids[self.deviceIndex]
        self._set_phase('starting', 'Подключение микрофона…')
        def start():
            candidates = [device, None] if fallback and device is not None else [device]
            for index, candidate in enumerate(candidates):
                stream = None
                try:
                    stream, rate, stream_device = self.audio_input.take(candidate)
                    if not self.active:
                        self.audio_input.dispose(stream)
                        return
                    self.stream, self.rate, self._stream_device = stream, rate, stream_device
                    self.started_at = time.perf_counter()
                    self.recording = True
                    self.audio_input.start(stream)
                    self.events.put(('recording_started', None))
                    return
                except Exception:
                    self.recording = False
                    if stream:
                        self.audio_input.dispose(stream)
                    self.stream = None
                    self.chunks, self.frames = [], 0
                    if index + 1 == len(candidates):
                        self.events.put(('error', 'Микрофон недоступен. Проверьте устройство и разрешения Windows.'))
        self._worker(start)

    def stop_recording(self, timing=None):
        if self._phase != 'recording' or not self.recording:
            return
        self._play_stop_cue()
        self._hide_recording_overlay()
        if self._recovering:
            self._release_pending = True
            return
        trace = LatencyTrace(timing, self.diagnostics_path)
        trace.mark('stop_requested_ns')
        engine, target, rate = self.engine, self.target, self.rate
        self._set_phase('transcribing', 'Распознавание…')
        def recognize():
            result = None
            try:
                stream, self.stream = self.stream, None
                if stream:
                    try:
                        with trace.span('capture_stop'):
                            self.audio_input.stop(stream)
                        self.audio_input.recycle(stream, rate, self._stream_device)
                    except Exception:
                        self.audio_input.dispose(stream)
                # Accept the final callback until PortAudio stop() has drained it.
                self.recording = False
                chunks, self.chunks = self.chunks, []
                with trace.span('concatenate'):
                    samples = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.float32)
                trace.audio_seconds = len(samples) / rate
                trace.metadata = dict(model='parakeet', provider='cpu', sample_rate=rate)
                text, seconds = engine.transcribe(samples, rate, trace=trace)
                trace.mark('text_ready_ns')
                result = dict(text=text, target=target, duration=len(samples) / rate,
                              seconds=seconds, trace=trace, presented=threading.Event())
                self.events.put(('result', result))
                if text:
                    try:
                        with trace.span('history'):
                            self.store.add(text, result['duration'], seconds, identifier=trace.identifier)
                    except Exception:
                        try:
                            self.store.retain_result(trace.identifier, text, result['duration'], seconds)
                            self.events.put(('notice', 'История недоступна. Локальная копия текста сохранена.'))
                        except Exception:
                            self.events.put(('notice', 'Не удалось сохранить текст. Скопируйте его перед закрытием.'))
                self.events.put(('refresh', None))
            except Exception:
                self.recording = False
                self.events.put(('error', 'Не удалось распознать запись. Попробуйте ещё раз.'))
            finally:
                trace.mark('persistence_done_ns')
                if trace.output and result:
                    result['presented'].wait(1)
                trace.write()
        self._worker(recognize)

    def _sound(self, kind):
        if self._preferences['sounds']:
            self.audio_cues.play(kind, 50)

    def finish_result(self, result):
        trace = result.get('trace')
        span = trace.span if trace else lambda name: nullcontext()
        if trace:
            trace.mark('ui_result_received_ns')
        text = result['text']
        if text:
            self.setText(text)
            if trace:
                trace.mark('ui_text_set_ns')
            try:
                with span('clipboard'):
                    copy_text(format_ending(text), int(self.window.winId()) if self.window else 0)
                with span('paste_command'):
                    pasted = paste_if_focused(result['target'])
                if trace:
                    trace.pasted = pasted
                    trace.mark('paste_command_done_ns')
            except OSError:
                self.toastRequested.emit('Не удалось скопировать текст. Он доступен в основном окне.')
            self._set_phase('ready', 'Диктовка на паузе' if self.paused else 'Готово к записи')
        else:
            self._set_phase('ready', 'Речь не обнаружена')
        if result.get('presented'):
            result['presented'].set()
        self.prepare_microphone()

    @Slot()
    def refresh_data(self):
        if self._refreshing:
            self._refresh_again = True
            return
        self._refreshing = True
        def read():
            try:
                self.events.put(('data', (self.store.history(), self.store.statistics(), self.store.daily_statistics())))
            except Exception:
                self.events.put(('data_failed', None))
        self._io.submit(read)

    @Slot(int)
    def deleteHistory(self, identifier):
        def remove():
            try:
                self.store.delete(identifier)
                self.events.put(('refresh', None))
            except Exception:
                self.events.put(('notice', 'Не удалось удалить запись'))
        self._io.submit(remove)

    def _apply_data(self, data):
        self._history, self._statistics, daily = data
        for item in daily:
            day = datetime.fromisoformat(item['day'])
            item['label'] = WEEKDAYS[day.weekday()]
            item['dateLabel'] = f'{day.day} {MONTHS[day.month - 1]} · {item["label"]}'
        self._daily = daily
        start, end = [datetime.fromisoformat(item['day']) for item in (daily[0], daily[-1])]
        self._date_range = (f'{start.day}–{end.day} {MONTH_SHORT[end.month - 1]}' if start.month == end.month else
                            f'{start.day} {MONTH_SHORT[start.month - 1]} – {end.day} {MONTH_SHORT[end.month - 1]}')
        self.dataChanged.emit()

    def poll(self):
        if not self.active:
            return
        try:
            # Bound queue work so a burst of download events cannot starve rendering.
            for _ in range(64):
                try:
                    kind, value = self.events.get_nowait()
                except queue.Empty:
                    break
                self.handle_event(kind, value)
                if not self.active:
                    break
            if self._phase == 'recording' and time.perf_counter() - self.started_at >= 120:
                self.stop_recording()
            if not self.preview and not self.smoke and time.monotonic() - self._last_system_check >= 0.5:
                self._last_system_check = time.monotonic()
                request = self.store.directory / 'show-window.request'
                if request.exists():
                    request.unlink(missing_ok=True)
                    self.open_window()
                if self._phase == 'recording' and self.stream and not self._recovering:
                    try:
                        connected = self.stream.active
                    except Exception:
                        connected = False
                    if not connected:
                        self._recover_microphone()
        except Exception:
            self.toastRequested.emit('Не удалось выполнить действие. Попробуйте ещё раз.')

    def _recover_microphone(self):
        self._recovering = True
        if not self._preferences['microphone_fallback']:
            self.stop_recording()
            self.toastRequested.emit('Выбранный микрофон отключён')
            self._recovering = False
            return
        def recover():
            try:
                old, self.stream = self.stream, None
                if old:
                    self.audio_input.dispose(old)
                with self.audio_input.io_lock:
                    stream = sd.InputStream(device=None, samplerate=self.rate, channels=1,
                                            dtype='float32', callback=self.audio_callback, blocksize=0, latency='low')
                    self._stream_device = self.audio_input.device_key(None)
                    self.audio_input.start(stream)
                    self.stream = stream
                self.events.put(('microphone_recovered', True))
            except Exception:
                self.events.put(('microphone_recovered', False))
        self._worker(recover)

    def handle_event(self, kind, value):
        if kind == 'worker_done':
            self._workers.discard(value)
        elif kind == 'ready':
            self.engine, seconds = value
            self._set_phase('ready', 'Диктовка на паузе' if self.paused else 'Готово к записи')
            self.prepare_microphone()
            if self.smoke:
                def verify():
                    report = dict(ready=True, load_seconds=seconds, ui='PySide6 / Qt Quick',
                                  frozen=bool(getattr(sys, 'frozen', False)),
                                  portable_runtime=bool(getattr(sys, '_voxpad_portable_root', None)),
                                  executable=sys.executable, base=str(BASE))
                    try:
                        if self.smoke_audio:
                            import soundfile as sf
                            samples, rate = sf.read(self.smoke_audio, dtype='float32')
                            report['transcript'] = self.engine.transcribe(samples, rate)[0]
                            report['ready'] = bool(report['transcript'])
                    except Exception:
                        report['ready'] = False
                    (BASE / 'smoke-test.json').write_text(json.dumps(report, ensure_ascii=False), 'utf-8')
                    self.events.put(('smoke_finished', report['ready']))
                self._worker(verify)
        elif kind == 'model_failed':
            self._set_phase('missing' if value else 'error', 'Нажмите микрофон, чтобы загрузить модель' if value else 'Не удалось загрузить модель')
            if self.smoke:
                self.smokeFinished.emit(False)
        elif kind == 'progress':
            self._set_phase('downloading', f'Загрузка модели… {value:.0%}')
        elif kind == 'downloaded':
            self._set_phase('loading', 'Подготовка модели…')
            self._worker(self.load_model)
        elif kind == 'recording_started':
            self._set_phase('recording', 'Идёт запись…')
            if self._release_pending or self.paused:
                self.stop_recording()
            else:
                self._show_recording_overlay()
        elif kind == 'result':
            self.finish_result(value)
        elif kind == 'error':
            self._hide_recording_overlay()
            self._set_phase('error', value)
        elif kind == 'devices':
            self._device_refreshing = False
            ids, names = value
            if ids != self._device_ids or names != self._devices:
                self._device_ids, self._devices = ids, names
                self.preferencesChanged.emit()
            self.prepare_microphone()
        elif kind == 'setting_failed':
            key, old, proposed = value
            if self._preferences.get(key) == proposed:
                self._preferences[key] = old
            self.preferencesChanged.emit()
            self.stateChanged.emit()
            self.toastRequested.emit('Не удалось сохранить настройку')
        elif kind in ('data', 'data_failed'):
            self._refreshing = False
            if kind == 'data':
                self._apply_data(value)
            else:
                self.toastRequested.emit('История временно недоступна')
            if self._refresh_again:
                self._refresh_again = False
                self.refresh_data()
        elif kind == 'refresh':
            self.refresh_data()
        elif kind == 'shortcut':
            event = dict(value, ui_received_ns=time.perf_counter_ns())
            if self._capturing or self.paused:
                return
            if event['phase'] == 'press':
                if self._phase in ('starting', 'recording') and self._preferences['trigger_mode'] == 'toggle':
                    self._request_stop(event)
                elif self._phase in ('ready', 'error'):
                    self.start_recording(event['target'])
            elif self._preferences['trigger_mode'] == 'hold':
                self._request_stop(event)
        elif kind == 'shortcut_capture':
            if not self._capturing:
                return
            old = self._preferences['shortcuts']
            self._preferences['shortcuts'] = {'dictate': value}
            self._io.submit(self._save_setting, 'shortcuts', self._preferences['shortcuts'], old)
            self.cancelShortcut()
        elif kind == 'shortcut_cancel':
            self.cancelShortcut()
        elif kind == 'hook_error':
            self.toastRequested.emit('Горячая клавиша недоступна. Используйте кнопку записи.')
            self.cancelShortcut()
        elif kind == 'microphone_recovered':
            self._recovering = False
            if not value or self._release_pending or self.paused:
                self.stop_recording()
            if not value:
                self.toastRequested.emit('Выбранный микрофон отключён')
        elif kind == 'notice':
            self.toastRequested.emit(value)
        elif kind == 'smoke_finished':
            self.smokeFinished.emit(value)

    def _save_setting(self, key, value, old):
        try:
            if key == 'autostart' and not self.preview:
                from platform_features import set_autostart
                set_autostart(bool(value), Path(__file__).resolve().parents[1] / 'Launch.vbs')
            self.store.save({key: value})
        except Exception:
            self.events.put(('setting_failed', (key, old, value)))

    def open_window(self):
        if self.window:
            self.window.showNormal()
            self.window.raise_()
            self.window.requestActivate()

    @Slot()
    def requestClose(self):
        if self._preferences['background_mode'] and self.tray and self.tray.isVisible():
            self.window.hide()
        else:
            self.requestQuit()

    @Slot()
    def requestQuit(self):
        if self._phase in ('starting', 'recording', 'transcribing'):
            self.open_window()
            self.exitConfirmationRequested.emit()
        else:
            self.confirmQuit()

    @Slot()
    def confirmQuit(self):
        if not self.active:
            return
        if self._phase == 'starting':
            self._release_pending = True
            QTimer.singleShot(50, self.confirmQuit)
            return
        if self._phase == 'recording':
            self.stop_recording()
        self.active = False
        self.hotkey.close()
        self.model_cancel.set()
        self._poll_timer.stop()
        self._device_timer.stop()
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None
        if self.tray:
            self.tray.hide()
        # The window closes immediately; shutdown and persistence drain in background.
        if self.window:
            self.window.hide()
        def cleanup():
            for worker in tuple(self._workers):
                if worker is not threading.current_thread():
                    worker.join()
            self.audio_input.close()
            self._io.shutdown(wait=True)
            self.events.put(('closed', None))
        threading.Thread(target=cleanup, name='VoxPad-shutdown', daemon=False).start()
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(20)
        def wait_closed():
            while not self.events.empty():
                kind, value = self.events.get_nowait()
                if kind == 'closed':
                    self._shutdown_timer.stop()
                    QGuiApplication.quit()
                    break
        self._shutdown_timer.timeout.connect(wait_closed)
        self._shutdown_timer.start()
