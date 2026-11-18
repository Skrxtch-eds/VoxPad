"""Migration, ASR input and safe Windows insertion for the reduced application."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from qt_controller import Controller
from engine import Engine,mono16k
from model_manager import MODELS
from storage import Store,DEFAULTS
from text_processing import format_ending
from windows_input import paste_if_focused


class SimplifiedDictationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent,prefix='.tmp-simple-')
        self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name)

    def test_legacy_settings_preserve_kept_preferences_and_remove_old_controls(self):
        saved=dict(language='en',model='whisper',speech_language='en',ending='period_enter',
                   auto_paste=False,save_unfinished=True,glass_blur=.1,wave_color='#ff0000',
                   sound_volume=100,mute_recording=True,export_folder='legacy',
                   shortcuts={'dictate':[162,164,68],'history':[72]},microphone='USB microphone',
                   trigger_mode='toggle',ui_theme='dark',sounds=False,autostart=True,
                   background_mode=False,microphone_fallback=False,paused=True)
        (self.directory/'settings.json').write_text(json.dumps(saved),'utf-8')
        store=Store(self.directory)
        self.assertEqual(set(store.settings),set(DEFAULTS))
        for key in ('microphone','trigger_mode','ui_theme','sounds','autostart','background_mode','microphone_fallback','paused'):
            self.assertEqual(store.settings[key],saved[key])
        self.assertEqual(store.settings['shortcuts'],{'dictate':[162,164,68]})
        store.save({'sounds':True})
        self.assertEqual(Store(self.directory).settings['shortcuts'],{'dictate':[162,164,68]})

    def test_invalid_legacy_values_use_safe_defaults(self):
        for shortcuts in (None,[],{'dictate':[]},{'dictate':['Ctrl']},{'dictate':[False]}):
            (self.directory/'settings.json').write_text(json.dumps(dict(shortcuts=shortcuts,ui_theme=None,trigger_mode='unknown',sounds='yes',microphone=7)),'utf-8')
            self.assertEqual(Store(self.directory).settings,DEFAULTS)

    def test_startup_and_text_retry_never_touch_legacy_audio_or_model_files(self):
        pending=self.directory/'pending';pending.mkdir()
        raw=pending/('a'*32+'.raw');meta=raw.with_suffix('.json')
        raw.write_bytes(b'legacy audio');meta.write_text('{"rate":16000}','utf-8')
        old=self.directory/'models/whisper/weights.onnx';old.parent.mkdir(parents=True);old.write_bytes(b'legacy weights')
        before={p:hashlib.sha256(p.read_bytes()).digest() for p in (raw,meta,old)}
        store=Store(self.directory)
        store.retain_result('b'*32,'Сохранённый текст',2,.2)
        text_copy=self.directory/'unsaved'/('b'*32+'.json')
        value=json.loads(text_copy.read_text('utf-8'));value['journal_identifier']='a'*32
        text_copy.write_text(json.dumps(value),'utf-8')
        self.assertEqual(store.retry_unsaved(),0)
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).digest() for p in before})
        self.assertEqual(store.history()[0]['text'],'Сохранённый текст')

    def test_existing_history_and_all_five_totals_survive_reopening(self):
        store=Store(self.directory);store.add('Первый текст.',2,.4);store.add('Ещё три слова!',3,.6)
        before=store.statistics();rows=store.history()
        store.settings_path.write_text('{"model":"gigaam","language":"en"}','utf-8')
        restored=Store(self.directory)
        self.assertEqual(restored.history(),rows);self.assertEqual(restored.statistics(),before)
        restored.add('Новая фраза.',4,.8)
        stats=restored.statistics()
        self.assertEqual(stats['dictations'],3)
        self.assertEqual(stats['words'],7)
        self.assertEqual(stats['characters'],len('Первый текст.Ещё три слова!Новая фраза.'))
        self.assertEqual(stats['audio_seconds'],9)
        self.assertAlmostEqual(stats['average_processing_seconds'],.6)

    def test_model_punctuation_and_no_punctuation_are_preserved(self):
        for text in ('Привет.','Вопрос?','Да!','Wait…','Hello','«Привет!»','你好。'):
            self.assertEqual(format_ending(text+'\n'),text+' ')
        self.assertEqual(format_ending('  '),'')

    def test_only_parakeet_factory_and_automatic_language_are_used(self):
        for name in MODELS['parakeet']['files']:(self.directory/name).write_bytes(b'model')
        self.assertEqual(set(MODELS),{'parakeet'})
        with patch('engine.sherpa_onnx.OfflineRecognizer.from_transducer') as factory:
            Engine(self.directory,threads=4)
        options=factory.call_args.kwargs
        self.assertTrue(options['decoder'].endswith('decoder.int8.onnx'))
        self.assertTrue(options['joiner'].endswith('joiner.int8.onnx'))
        self.assertNotIn('language',options)
        self.assertEqual(options['num_threads'],4)

    def test_resampling_retains_float32_mono_and_full_duration(self):
        t=np.arange(48000)/48000
        left=np.sin(2*np.pi*400*t).astype(np.float32)
        result=mono16k(np.column_stack((left,left)),48000)
        self.assertEqual(result.shape,(16000,));self.assertEqual(result.dtype,np.float32)
        self.assertTrue(result.flags.c_contiguous)
        self.assertGreater(np.sqrt(np.mean(result**2)),.7)

    def test_download_success_starts_one_model_load(self):
        app=SimpleNamespace(_set_phase=Mock(),_worker=Mock(),load_model=Mock())
        Controller.handle_event(app,'downloaded',None)
        app._set_phase.assert_called_once_with('loading','Подготовка модели…')
        app._worker.assert_called_once_with(app.load_model)

    def test_missing_model_does_not_trigger_implicit_download(self):
        app=SimpleNamespace(_set_phase=Mock(),_worker=Mock(),smoke=False)
        Controller.handle_event(app,'model_failed',True)
        self.assertEqual(app._set_phase.call_args.args[0],'missing')
        app._worker.assert_not_called()

    def test_changed_foreground_window_prevents_paste(self):
        with patch('windows_input.user32.GetForegroundWindow',return_value=456),patch('windows_input.user32.SendInput') as send:
            self.assertFalse(paste_if_focused(123));send.assert_not_called()

    def test_cues_use_fixed_moderate_volume_and_can_be_disabled(self):
        app=SimpleNamespace(_preferences={'sounds':True},audio_cues=Mock())
        Controller._sound(app,'start');Controller._sound(app,'stop')
        self.assertEqual([c.args for c in app.audio_cues.play.call_args_list],[('start',50),('stop',50)])
        app._preferences['sounds']=False;Controller._sound(app,'start')
        self.assertEqual(app.audio_cues.play.call_count,2)


if __name__=='__main__':unittest.main()
