"""Fault-injected dictation lifecycle tests; no microphone or clipboard changes."""
from pathlib import Path
import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from PySide6.QtWidgets import QApplication
from qt_controller import Controller
from diagnostics import LatencyTrace
from storage import Store
from engine import configured_threads
from cpu_runtime import MEASURED_THREADS
from windows_input import Hotkey, KBDLLHOOKSTRUCT, input_timing
import ctypes


APP=QApplication.instance() or QApplication([])


class Harness(Controller):
    def __init__(self,directory):
        super().__init__(directory/'data',preview=True)
        self._preferences['sounds']=False
        self.engine=Mock();self.engine.transcribe.return_value=('Test transcript',.001)
        self.overlay=Mock();self.audio_input=Mock();self.stream=None
        self.target=123
        self._phase='recording';self.recording=True;self.rate=16000
        self.frames=3200;self.chunks=[np.full(3200,.1,dtype=np.float32)]
        self.notices=[]
        self.toastRequested.connect(self.notices.append)


class DictationLatencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='.tmp-latency-',dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name)
        self.copy=self.enterContext(patch('qt_controller.copy_text'))
        self.paste=self.enterContext(patch('qt_controller.paste_if_focused',return_value=True))

    def app(self):
        app=Harness(self.directory)
        def cleanup():
            for worker in tuple(app._workers):worker.join(3)
            app._poll_timer.stop();app._device_timer.stop()
            app.audio_input.close();app.hotkey.close()
            app._io.shutdown(wait=True)
            app.active=False
        self.addCleanup(cleanup)
        return app

    def event(self,app,kind):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            name,value=app.events.get(timeout=3)
            if name==kind:return value
            if name=='error':self.fail(value)
            app.handle_event(name,value)
        self.fail('Missing '+kind)

    def finish(self,app):
        for worker in tuple(app._workers):
            worker.join(3);self.assertFalse(worker.is_alive())
        while not app.events.empty():
            kind,value=app.events.get_nowait()
            app.handle_event(kind,value)


    def test_slow_sqlite_does_not_delay_paste_or_use_changed_target(self):
        app=self.app();entered=threading.Event();release=threading.Event()
        self.addCleanup(release.set);original=app.store.add
        def add(*args,**kwargs):
            entered.set();self.assertTrue(release.wait(3));return original(*args,**kwargs)
        with patch.object(app.store,'add',side_effect=add):
            app.stop_recording();self.assertTrue(entered.wait(2))
            result=self.event(app,'result')
            app.target=456
            app.finish_result(result)
            self.copy.assert_called_once_with('Test transcript ',0)
            self.paste.assert_called_once_with(123)
            self.assertEqual(app.phase,'ready')
            self.assertTrue(any(worker.is_alive() and not worker.daemon for worker in app._workers))
            release.set();self.finish(app)

    def test_history_failure_retains_text_without_preventing_insertion(self):
        app=self.app()
        with patch.object(app.store,'add',side_effect=OSError('database unavailable')):
            app.stop_recording();result=self.event(app,'result');app.finish_result(result);self.finish(app)
        self.paste.assert_called_once_with(123)
        self.assertEqual(app.text,'Test transcript')
        pending=list((app.store.directory/'unsaved').glob('*.json'))
        self.assertEqual(len(pending),1)
        self.assertEqual(json.loads(pending[0].read_text('utf-8'))['text'],'Test transcript')
        self.assertTrue(any('История недоступна' in message for message in app.notices))
        self.assertEqual(app.store.retry_unsaved(),0)
        self.assertEqual(len(app.store.history()),1)

    def test_result_retry_is_durable_without_audio_files(self):
        app=self.app()
        with patch.object(app.store,'add',side_effect=OSError('database locked')):
            app.stop_recording();app.finish_result(self.event(app,'result'));self.finish(app)
        self.assertEqual(len(list((app.store.directory/'unsaved').glob('*.json'))),1)
        self.assertEqual(app.store.retry_unsaved(),0)
        self.assertEqual(app.store.history()[0]['text'],'Test transcript')

    def test_next_dictation_reuses_model_and_snapshots_target(self):
        app=self.app()
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        original=app.store.add
        def add(*args,**kwargs):
            entered.set();self.assertTrue(release.wait(3));return original(*args,**kwargs)
        with patch.object(app.store,'add',side_effect=add):
            app.stop_recording();self.assertTrue(entered.wait(2))
            app.finish_result(self.event(app,'result'))
            app.engine.transcribe.return_value=('Second transcript',.002)
            app.target=456
            app._phase='recording';app.recording=True;app.rate=48000;app.chunks=[np.full(4800,.2,dtype=np.float32)]
            app.stop_recording();app.finish_result(self.event(app,'result'))
            self.assertEqual([call.args[0] for call in self.paste.call_args_list],[123,456])
            release.set();self.finish(app)
        self.assertEqual({row['text'] for row in app.store.history()},{'Test transcript','Second transcript'})

    def test_decoder_error_releases_busy_state_without_audio_files(self):
        app=self.app()
        app.engine.transcribe.side_effect=RuntimeError('inference failed')
        app.stop_recording()
        message=self.event(app,'error');app.handle_event('error',message)
        self.finish(app)
        self.assertEqual(app.phase,'error')
        self.paste.assert_not_called()
        self.assertFalse((self.directory/'data/pending').exists())

    def test_failed_text_fallback_still_keeps_the_result_visible(self):
        app=self.app()
        with patch.object(app.store,'add',side_effect=OSError('disk full')),patch.object(app.store,'retain_result',side_effect=OSError('disk full')):
            app.stop_recording();app.finish_result(self.event(app,'result'));self.finish(app)
        self.assertEqual(app.text,'Test transcript')
        self.assertFalse((self.directory/'data/pending').exists())

    def test_optional_thread_override_cannot_disable_model_loading(self):
        config=self.directory/'performance.json'
        self.enterContext(patch('cpu_runtime.is_measured_cpu',return_value=True))
        self.assertEqual(configured_threads(config),MEASURED_THREADS)
        for value in ('{broken','[]','{"threads":0}','{"threads":true}','{"threads":-1}'):
            config.write_text(value,'utf-8');self.assertEqual(configured_threads(config),MEASURED_THREADS)
        config.write_text('{"threads":6}','utf-8');self.assertEqual(configured_threads(config),6)


    def test_retry_after_commit_and_unlink_failure_does_not_duplicate_stats(self):
        store=Store(self.directory/'data');identifier='a'*32
        store.retain_result(identifier,'Saved once',1,.1)
        with patch.object(Path,'unlink',side_effect=OSError('file locked')):
            self.assertEqual(store.retry_unsaved(),1)
        self.assertEqual(store.retry_unsaved(),0)
        self.assertEqual(len(store.history()),1)
        self.assertEqual(store.statistics()['dictations'],1)


    def test_stop_drains_final_callback_and_shares_one_owned_copy(self):
        app=self.app();app.stream=Mock();app._stream_device=0
        last=np.full((31,1),.2,dtype=np.float32)
        app.audio_input.stop.side_effect=lambda stream:app.audio_callback(last,len(last),None,False)
        first=app.chunks[0].copy()
        app.stop_recording();result=self.event(app,'result');app.finish_result(result);self.finish(app)
        received=app.engine.transcribe.call_args.args[0]
        np.testing.assert_array_equal(received,np.concatenate((first,last[:,0])))
        last[:]=0
        np.testing.assert_array_equal(received[-31:],np.full(31,.2,dtype=np.float32))


    def test_input_timestamp_wrap_and_hook_release_are_preserved(self):
        with patch('windows_input.kernel32.GetTickCount64',return_value=2**32+5):
            timing=input_timing(2**32-5,100_000_000)
        self.assertEqual(timing['input_event_ns'],90_000_000)
        events=queue.Queue();hotkey=Hotkey(events)
        hotkey.held=True;hotkey.active_action='dictate';hotkey.active_chord=frozenset([0xA3])
        key=KBDLLHOOKSTRUCT(0xA3,0,0,25,0)
        with patch('windows_input.kernel32.GetTickCount64',return_value=30),patch('windows_input.user32.CallNextHookEx',return_value=0):
            hotkey._callback(0,0x101,ctypes.addressof(key))
        kind,event=events.get_nowait();self.assertEqual(kind,'shortcut')
        self.assertEqual(event['phase'],'release')
        self.assertEqual(event['hook_received_ns']-event['input_event_ns'],5_000_000)

    def test_diagnostics_contain_no_text_audio_or_window_identifier(self):
        path=self.directory/'timing.jsonl';trace=LatencyTrace(output=path)
        trace.mark('text_ready_ns');trace.write()
        report=json.loads(path.read_text('utf-8'))
        self.assertIsNone(report['physical_release_to_visible_text_ms'])
        self.assertIsNone(report['hook_to_paste_command_ms'])
        self.assertFalse({'text','audio','target','transcript','window_title'} & report.keys())


if __name__=='__main__':unittest.main()
