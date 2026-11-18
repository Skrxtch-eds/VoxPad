"""Fault-injected Qt capture/ASR lifecycle; no hardware, clipboard or registry changes."""
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/source'))
from PySide6.QtWidgets import QApplication
from qt_controller import Controller

APP = QApplication.instance() or QApplication([])


class QtControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent, prefix='.tmp-qt-')
        self.controller = Controller(Path(self.temp.name), preview=True)
        self.controller._preferences['sounds'] = False
        self.controller.engine = Mock()
        self.controller.engine.transcribe.return_value = ('test transcript', .001)
        self.copy = self.enterContext(patch('qt_controller.copy_text'))
        self.paste = self.enterContext(patch('qt_controller.paste_if_focused', return_value=True))

    def tearDown(self):
        c = self.controller
        for worker in tuple(c._workers):
            worker.join(3)
        c._poll_timer.stop()
        c._device_timer.stop()
        if c.overlay is not None:c.overlay.close()
        c.audio_input.close()
        c.hotkey.close()
        c._io.shutdown(wait=True)
        c.active = False
        self.temp.cleanup()

    def wait_for(self, predicate):
        deadline = time.monotonic() + 4
        while not predicate() and time.monotonic() < deadline:
            self.controller.poll()
            time.sleep(.002)
        self.assertTrue(predicate())

    def recording(self):
        c = self.controller
        c._phase, c.recording = 'recording', True
        c.stream = Mock()
        c.audio_input = Mock()
        c._stream_device = 0
        c.rate = 16000
        c.chunks = [np.full(3200, .1, dtype=np.float32)]
        c.frames = 3200
        c.target = 123
        return c

    def test_slow_history_does_not_delay_result_or_change_paste_target(self):
        c = self.recording()
        entered, release = threading.Event(), threading.Event()
        original = c.store.add
        def delayed(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(3))
            return original(*args, **kwargs)
        with patch.object(c.store, 'add', side_effect=delayed):
            c.stop_recording()
            self.assertTrue(entered.wait(2))
            c.target = 456
            try:
                self.wait_for(lambda: c.text == 'test transcript')
                self.paste.assert_called_once_with(123)
                self.assertEqual(c.phase, 'ready')
            finally:
                release.set()
            self.wait_for(lambda: len(c.store.history()) == 1)

    def test_stop_drains_final_audio_callback_on_worker(self):
        c = self.recording()
        def stop(stream):
            c.audio_callback(np.full((1600,1),.1,dtype=np.float32),1600,None,None)
        c.audio_input.stop.side_effect = stop
        c.stop_recording()
        self.wait_for(lambda: c.phase == 'ready')
        samples = c.engine.transcribe.call_args.args[0]
        self.assertEqual(len(samples),4800)
        self.assertFalse(c.recording)

    def test_release_during_async_open_stops_hold_recording(self):
        c = self.controller
        original = c.audio_input
        original.close()
        c.audio_input = Mock()
        c.audio_input.take.return_value = (Mock(),16000,0)
        opened, release = threading.Event(), threading.Event()
        def start(stream):
            opened.set()
            self.assertTrue(release.wait(3))
            c.audio_callback(np.full((1600,1),.1,dtype=np.float32),1600,None,None)
        c.audio_input.start.side_effect = start
        c.recordPressed()
        self.assertTrue(opened.wait(2))
        self.assertEqual(c.phase,'starting')
        c.recordReleased()
        release.set()
        self.wait_for(lambda: c.phase == 'ready')
        c.engine.transcribe.assert_called_once()

    def test_cues_do_not_wait_for_microphone_open_or_early_release(self):
        c=self.controller
        c._preferences['sounds']=True
        c.audio_input.close()
        c.audio_input=Mock()
        opening,release=threading.Event(),threading.Event()
        def take(device):
            opening.set()
            self.assertTrue(release.wait(3))
            return Mock(),16000,0
        c.audio_input.take.side_effect=take
        with patch.object(c.audio_cues,'play') as play:
            try:
                c.recordPressed()
                play.assert_called_once_with('start',50)
                self.assertTrue(opening.wait(2))
                self.assertEqual(c.phase,'starting')
                c.recordReleased()
                self.assertEqual([call.args for call in play.call_args_list],[('start',50),('stop',50)])
            finally:
                release.set()
            self.wait_for(lambda:c.phase=='ready')
            self.assertEqual(play.call_count,2,'microphone-ready event repeated a cue')

    def test_stop_cue_precedes_slow_capture_drain(self):
        c=self.recording()
        c._preferences['sounds']=True
        draining,release=threading.Event(),threading.Event()
        def stop(stream):
            draining.set()
            self.assertTrue(release.wait(3))
        c.audio_input.stop.side_effect=stop
        with patch.object(c.audio_cues,'play') as play:
            try:
                c.stop_recording()
                play.assert_called_once_with('stop',50)
                self.assertTrue(draining.wait(2))
                c.stop_recording()
                play.assert_called_once_with('stop',50)
            finally:
                release.set()
            self.wait_for(lambda:c.phase=='ready')

    def test_toggle_can_signal_stop_while_microphone_is_still_opening(self):
        c=self.controller
        c._preferences.update(sounds=True,trigger_mode='toggle')
        c.audio_input.close()
        c.audio_input=Mock()
        opening,release=threading.Event(),threading.Event()
        def take(device):
            opening.set()
            self.assertTrue(release.wait(3))
            return Mock(),16000,0
        c.audio_input.take.side_effect=take
        with patch.object(c.audio_cues,'play') as play:
            try:
                c.handle_event('shortcut',dict(phase='press',target=None))
                self.assertTrue(opening.wait(2))
                c.handle_event('shortcut',dict(phase='press',target=None))
                self.assertTrue(c._release_pending)
                self.assertEqual([call.args for call in play.call_args_list],[('start',50),('stop',50)])
            finally:
                release.set()
            self.wait_for(lambda:c.phase=='ready')
            self.assertEqual(play.call_count,2)

    def test_rejected_recording_does_not_play_start_cue(self):
        c=self.controller
        c._preferences['sounds']=True
        with patch.object(c.audio_cues,'play') as play:
            c._preferences['paused']=True
            c.start_recording(None)
            c._preferences.update(paused=False,microphone='Disconnected',microphone_fallback=False)
            c.start_recording(None)
            play.assert_not_called()

    def test_toggle_release_does_not_stop_recording(self):
        c = self.recording()
        c._preferences['trigger_mode'] = 'toggle'
        c.recordReleased()
        self.assertEqual(c.phase,'recording')
        c.recordPressed()
        self.wait_for(lambda: c.phase == 'ready')

    def test_history_failure_retains_text_copy(self):
        c = self.recording()
        with patch.object(c.store, 'add', side_effect=OSError('locked')):
            c.stop_recording()
            self.wait_for(lambda: bool(list((c.store.directory/'unsaved').glob('*.json'))))
        self.wait_for(lambda: c.text == 'test transcript')
        self.assertEqual(c.store.retry_unsaved(),0)
        self.assertEqual(c.store.history()[0]['text'],'test transcript')

    def test_setting_failure_rolls_back_visible_value(self):
        c = self.controller
        with patch.object(c.store, 'save', side_effect=OSError('read only')):
            c.setSetting('ui_theme','dark')
            self.wait_for(lambda: c.preferences['ui_theme'] == 'light')

    def test_shortcut_save_failure_keeps_the_previous_preference(self):
        c=self.controller
        old=c.preferences['shortcuts']
        c.captureShortcut()
        with patch.object(c.store,'save',side_effect=OSError('read only')):
            c.handle_event('shortcut_capture',[162,68])
            self.wait_for(lambda:c.preferences['shortcuts']==old)
        self.assertFalse(c.capturingShortcut)
        self.assertEqual(c.store.settings['shortcuts'],old)

    def test_shared_setting_writer_keeps_autostart_error_handling(self):
        for failure in (None,OSError('registry unavailable')):
            with self.subTest(failure=failure):
                app=SimpleNamespace(preview=False,store=Mock(),events=queue.Queue())
                with patch('platform_features.set_autostart',side_effect=failure) as autostart:
                    Controller._save_setting(app,'autostart',True,False)
                self.assertEqual(autostart.call_args.args[0],True)
                if failure:
                    app.store.save.assert_not_called()
                    self.assertEqual(app.events.get_nowait(),('setting_failed',('autostart',False,True)))
                else:
                    app.store.save.assert_called_once_with({'autostart':True})
                    self.assertTrue(app.events.empty())

    def test_external_shortcut_shows_capsule_and_stop_hides_it(self):
        c = self.recording()
        c.level = .42
        with patch('qt_controller.is_external_target',return_value=True), \
             patch('qt_controller.QtRecordingOverlay') as factory:
            c.handle_event('recording_started',None)
            factory.assert_called_once()
            self.assertEqual(factory.call_args.args[2](),.42)
            factory.return_value.show.assert_called_once_with(123)
            c.stop_recording()
            factory.return_value.hide.assert_called_once()
            self.wait_for(lambda:c.phase=='ready')

    def test_recording_inside_own_app_does_not_create_capsule(self):
        c = self.controller
        with patch('qt_controller.is_external_target',return_value=False), \
             patch('qt_controller.QtRecordingOverlay') as factory:
            c.target=123
            c.handle_event('recording_started',None)
            c.target=None
            c.handle_event('recording_started',None)
            factory.assert_not_called()

    def test_early_release_never_shows_a_late_capsule(self):
        c = self.recording()
        c._release_pending=True
        with patch('qt_controller.QtRecordingOverlay') as factory:
            c.handle_event('recording_started',None)
            self.wait_for(lambda:c.phase=='ready')
            factory.assert_not_called()

    def test_capsule_failure_does_not_abort_dictation(self):
        c = self.controller
        c.target=123
        with patch('qt_controller.is_external_target',return_value=True), \
             patch('qt_controller.QtRecordingOverlay',side_effect=OSError('unavailable')):
            c.handle_event('recording_started',None)
        self.assertEqual(c.phase,'recording')

    def test_recording_error_hides_capsule(self):
        c = self.controller
        c.overlay = Mock()
        c.handle_event('error','Microphone unavailable')
        c.overlay.hide.assert_called_once()
        self.assertEqual(c.phase,'error')

    def test_input_level_updates_only_while_recording(self):
        c = self.controller
        c.recording=True
        c.audio_callback(np.full((80,1),.05,dtype=np.float32),80,None,None)
        self.assertAlmostEqual(c.level,.5,places=4)
        c.recording=False
        c.audio_callback(np.zeros((80,1),dtype=np.float32),80,None,None)
        self.assertAlmostEqual(c.level,.5,places=4)


if __name__ == '__main__':
    unittest.main()
