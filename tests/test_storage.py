from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from storage import Store,DEFAULTS,migrate_settings


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent)
        self.addCleanup(self.directory.cleanup)
        self.store=Store(self.directory.name)

    def test_preferences_survive_restart(self):
        self.store.save({'language':'ru','ui_theme':'light','microphone':'Test microphone'})
        restored=Store(self.directory.name)
        self.assertEqual(restored.settings['microphone'],'Test microphone')
        self.assertEqual(restored.settings['ui_theme'],'light')

    def test_history_limit_does_not_limit_statistics(self):
        for index in range(105):self.store.add(f'Test message {index}',2,.5)
        self.assertEqual(len(self.store.history()),100)
        self.assertEqual(self.store.statistics()['dictations'],105)
        self.assertEqual(self.store.statistics()['average_processing_seconds'],.5)
        for row in self.store.history():self.store.delete(row['id'])
        self.assertEqual(self.store.history(),[])
        self.assertEqual(self.store.statistics()['dictations'],105)

    def test_imported_files_do_not_change_dictation_statistics(self):
        self.store.add('Imported audio transcript',10,1,source='file')
        self.store.add('Recovered dictation',2,.2,source='microphone')
        self.assertEqual(len(self.store.history()),2)
        self.assertEqual(self.store.statistics()['dictations'],1)
        self.assertEqual(self.store.statistics()['audio_seconds'],2)

    def test_damaged_preferences_are_preserved(self):
        self.store.settings_path.write_text('{broken',encoding='utf-8')
        restored=Store(self.directory.name)
        self.assertEqual(restored.settings_path.read_text('utf-8'),'{broken')
        self.assertEqual(restored.history(),[])

    def test_normalized_shortcuts_do_not_share_mutable_defaults_or_input(self):
        first=migrate_settings({})
        second=migrate_settings({})
        first['shortcuts']['dictate'].append(68)
        self.assertEqual(DEFAULTS['shortcuts']['dictate'],[163])
        self.assertEqual(second['shortcuts']['dictate'],[163])
        saved={'shortcuts':{'dictate':[162,68,68]}}
        normalized=migrate_settings(saved)
        normalized['shortcuts']['dictate'].append(69)
        self.assertEqual(saved['shortcuts']['dictate'],[162,68,68])

    def test_failed_atomic_replace_preserves_file_and_current_preferences(self):
        self.store.save({'ui_theme':'light'})
        before=self.store.settings_path.read_bytes()
        with patch('storage.os.replace',side_effect=OSError('file locked')):
            with self.assertRaises(OSError):self.store.save({'ui_theme':'dark'})
        self.assertEqual(self.store.settings_path.read_bytes(),before)
        self.assertEqual(self.store.settings['ui_theme'],'light')
        self.assertEqual(Store(self.directory.name).settings['ui_theme'],'light')

    def test_unknown_legacy_data_is_not_copied_to_new_preferences(self):
        self.store.settings_path.write_text(
            '{"ui_theme":"dark","password":"fixture","api_key":"fixture","unrelated_note":"fixture"}',
            encoding='utf-8')
        restored=Store(self.directory.name)
        self.assertEqual(set(restored.settings),set(DEFAULTS))
        restored.save({'sounds':False})
        saved=restored.settings_path.read_text('utf-8')
        self.assertNotIn('fixture',saved)
        self.assertEqual(Store(self.directory.name).settings['ui_theme'],'dark')


if __name__=='__main__':unittest.main()
