"""Fault cases from the 0.4.5 review; no real audio, network or clipboard writes."""
from datetime import datetime,timezone,timedelta
import json,queue,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace,MethodType
from unittest.mock import Mock,patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from app import CoreApp
from app_features import Features
from activity_window import ActivityWindow
from storage import Store,local_recording_time


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent)
        self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.store=Store(self.base/'data')

    def recovery_app(self):
        directory=self.base/'data/pending';directory.mkdir()
        self.raw=directory/('a'*32+'.raw');self.meta=self.raw.with_suffix('.json')
        self.raw.write_bytes(np.zeros(3200,dtype='<f4').tobytes())
        self.meta.write_text(json.dumps({'rate':16000,'created':time.time()}))
        engine=Mock();engine.transcribe.return_value=('Recovered fixture',.01)
        app=SimpleNamespace(active=True,busy=False,recording=False,loading_model=False,capture_action=None,paused=False,
            root=Mock(),store=self.store,engine=engine,events=queue.Queue(),
            enable_controls=Mock(),set_busy=Mock(),t=lambda value:value)
        app.offer_recovery=MethodType(Features.offer_recovery,app)
        return app

    def run_recovery(self,app):
        with patch('app_features.BASE',self.base),patch('app_features.messagebox.askyesno',return_value=True):
            app.offer_recovery()
            return app.events.get(timeout=3)[1]

    def test_recovery_retains_audio_when_no_text_was_recognised(self):
        app=self.recovery_app();app.engine.transcribe.return_value=('',.01)
        message=self.run_recovery(app)
        self.assertTrue(self.raw.exists() and self.meta.exists())
        self.assertEqual(self.store.history(),[])
        self.assertIn('Retained for another attempt: 1',message)

    def test_recovery_retains_audio_after_decoder_error(self):
        app=self.recovery_app();app.engine.transcribe.side_effect=RuntimeError('decoder failed')
        self.run_recovery(app)
        self.assertTrue(self.raw.exists() and self.meta.exists())

    def test_recovery_retains_audio_after_history_write_error(self):
        app=self.recovery_app()
        with patch.object(self.store,'add',side_effect=OSError('disk full')):self.run_recovery(app)
        self.assertTrue(self.raw.exists() and self.meta.exists())

    def test_recovery_removes_audio_only_after_history_saved(self):
        app=self.recovery_app();message=self.run_recovery(app)
        self.assertEqual(self.store.history()[0]['text'],'Recovered fixture')
        self.assertFalse(self.raw.exists() or self.meta.exists())
        self.assertIn('Recovered recordings: 1',message)

    def test_recovery_defers_while_another_operation_is_active(self):
        app=self.recovery_app()
        for flag in ('busy','recording','loading_model','capture_action'):
            with self.subTest(flag=flag):
                setattr(app,flag,True)
                with patch('app_features.messagebox.askyesno') as prompt:app.offer_recovery()
                prompt.assert_not_called();app.engine.transcribe.assert_not_called()
                self.assertTrue(app.events.empty());setattr(app,flag,False)
        self.assertEqual(app.root.after.call_count,4)

    def test_recovery_reserves_busy_state_before_the_confirmation(self):
        app=self.recovery_app()
        def decline(*args):
            self.assertTrue(app.busy)
            Features.start_recording(app,None)
            self.assertFalse(app.recording)
            return False
        with patch('app_features.BASE',self.base),patch('app_features.messagebox.askyesno',side_effect=decline):app.offer_recovery()
        self.assertFalse(app.busy);app.engine.transcribe.assert_not_called()

    def test_legacy_ai_flag_is_disabled_without_deleting_profiles(self):
        profile={'id':'old','name':'Saved profile','url':'https://example.invalid','model':'fixture'}
        self.store.save({'ai_enabled':True,'ai_profiles':[profile],'ai_profile':'old'})
        restored=Store(self.base/'data')
        self.assertFalse(restored.settings['ai_enabled'])
        self.assertEqual(restored.settings['ai_profiles'],[profile])
        # The AI connection and editor are absent from the runtime, not merely hidden.
        self.assertFalse(hasattr(Features,'build_ai_settings'))
        self.assertNotIn('ai_cleanup',sys.modules)

    def test_model_remains_ready_when_its_selection_cannot_be_saved(self):
        app=SimpleNamespace(store=self.store,events=queue.Queue(),
            root=Mock(),status=Mock(),detail=Mock(),paused=False,t=lambda value:value)
        app.root.after_idle.side_effect=lambda callback:callback()
        engine=object()
        with patch.object(self.store,'save',side_effect=OSError('settings locked')):
            Features.handle_event(app,'loaded_model',(engine,.01,'parakeet'))
        self.assertIs(app.engine,engine);self.assertFalse(app.loading_model)
        kind,value=app.events.get_nowait();self.assertEqual(kind,'ready')
        Features.handle_event(app,kind,value)
        self.assertIn('could not be saved',app.detail.set.call_args.args[0])

    def test_event_loop_continues_after_an_unexpected_handler_failure(self):
        app=SimpleNamespace(active=True,root=Mock(),status=Mock(),detail=Mock(),t=lambda value:value,
            _poll_once=Mock(side_effect=[OSError('temporary failure'),None]))
        app.poll=MethodType(CoreApp.poll,app)
        app.poll();self.assertEqual(app.root.after.call_count,1)
        app.root.after.call_args.args[1]()
        self.assertEqual(app._poll_once.call_count,2)
        self.assertEqual(app.root.after.call_count,2)

    def test_failed_copy_does_not_claim_clipboard_success(self):
        app=SimpleNamespace(enable_controls=Mock(),store=self.store,text=Mock(),root=Mock(),
            auto_paste=Mock(),target=None,status=Mock(),detail=Mock(),metrics=Mock(),
            active_model='parakeet',current_ending='space',release_at=time.perf_counter(),t=lambda value:value)
        with patch('app_features.copy_text',side_effect=OSError('clipboard locked')),patch('app_features.paste_if_focused') as paste:
            Features.finish_result(app,dict(text='Fixture transcript',duration=1,total=.01,warning='',journal=None))
        paste.assert_not_called()
        self.assertIn('Could not copy',app.detail.set.call_args.args[0])
        self.assertEqual(self.store.history()[0]['text'],'Fixture transcript')
        app.text.insert.assert_called_with('1.0','Fixture transcript')

    def test_old_and_new_timestamps_are_displayed_in_computer_time(self):
        local=datetime.now().astimezone().replace(microsecond=0)
        expected=local.strftime('%Y-%m-%d %H:%M:%S')
        self.assertEqual(local_recording_time(local.astimezone(timezone.utc).isoformat()),expected)
        self.assertEqual(local_recording_time(local.astimezone(timezone(timedelta(hours=9,minutes=30))).isoformat()),expected)
        self.assertEqual(local_recording_time(local.timestamp()),expected)
        self.assertEqual(local_recording_time(local.replace(tzinfo=None).isoformat()),expected)

    def test_history_table_uses_local_time_instead_of_slicing_utc(self):
        created='2026-11-01T12:00:00+09:30'
        app=SimpleNamespace(store=Mock());app.store.history.return_value=[dict(id=1,created=created,text='Fixture')]
        view=SimpleNamespace(app=app,query=Mock(),history_tree=Mock(),put_text=Mock(),history_result=Mock(),history_recent=Mock())
        view.history_tree.selection.return_value=();view.history_tree.get_children.return_value=()
        ActivityWindow.refresh_history(view)
        expected=datetime.fromisoformat(created).astimezone().strftime('%Y-%m-%d %H:%M:%S')
        self.assertEqual(view.history_tree.insert.call_args.kwargs['values'][0],expected)


if __name__=='__main__':unittest.main()
