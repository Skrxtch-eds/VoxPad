"""Fault cases from the 0.4.5 review; no real audio, network or clipboard writes."""
import queue,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from qt_controller import Controller
from storage import Store


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent)
        self.addCleanup(temporary.cleanup);self.base=Path(temporary.name)
        self.store=Store(self.base/'data')
    def test_removed_ai_settings_are_not_carried_into_preferences(self):
        profile={'id':'old','name':'Saved profile','url':'https://example.invalid','model':'fixture'}
        self.store.save({'ai_enabled':True,'ai_profiles':[profile],'ai_profile':'old'})
        restored=Store(self.base/'data')
        self.assertNotIn('ai_enabled',restored.settings)
        self.assertNotIn('ai_profiles',restored.settings)
        self.assertNotIn('ai_profile',restored.settings)
        # The AI connection and editor are absent from the runtime, not merely hidden.
        self.assertFalse(hasattr(Controller,'build_ai_settings'))
        self.assertNotIn('ai_cleanup',sys.modules)

    def test_model_ready_does_not_require_writing_preferences(self):
        app=SimpleNamespace(store=self.store,_set_phase=Mock(),prepare_microphone=Mock(),paused=False,smoke=False)
        engine=object()
        with patch.object(self.store,'save',side_effect=OSError('settings locked')):
            Controller.handle_event(app,'ready',(engine,.01))
        self.assertIs(app.engine,engine)
        self.assertEqual(app._set_phase.call_args.args[0],'ready')
        app.prepare_microphone.assert_called_once()


    def test_event_loop_continues_after_an_unexpected_handler_failure(self):
        app=SimpleNamespace(active=True,preview=True,_phase='ready',events=queue.Queue(),
                            toastRequested=Mock(),handle_event=Mock(side_effect=[OSError('temporary failure'),None]))
        app.events.put(('first',None));app.events.put(('second',None))
        Controller.poll(app)
        app.toastRequested.emit.assert_called_once()
        Controller.poll(app)
        self.assertEqual(app.handle_event.call_count,2)
        self.assertTrue(app.events.empty())

    def test_failed_copy_does_not_claim_clipboard_success(self):
        # Persistence now runs in the dictation worker independently of the UI.
        self.store.add('Fixture transcript',1,.01)
        app=SimpleNamespace(store=self.store,setText=Mock(),_set_phase=Mock(),prepare_microphone=Mock(),
                            window=None,paused=False,toastRequested=Mock())
        with patch.object(self.store,'add',side_effect=AssertionError('UI must not write SQLite')),patch('qt_controller.copy_text',side_effect=OSError('clipboard locked')),patch('qt_controller.paste_if_focused') as paste:
            Controller.finish_result(app,dict(text='Fixture transcript',target=None))
        paste.assert_not_called()
        self.assertIn('Не удалось скопировать',app.toastRequested.emit.call_args.args[0])
        self.assertEqual(self.store.history()[0]['text'],'Fixture transcript')
        app.setText.assert_called_once_with('Fixture transcript')


if __name__=='__main__':unittest.main()
