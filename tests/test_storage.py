from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from storage import Store


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
        self.store.clear_history()
        self.assertEqual(self.store.history(),[])
        self.assertEqual(self.store.statistics()['dictations'],105)

    def test_imported_files_do_not_change_dictation_statistics(self):
        self.store.add('Imported audio transcript',10,1,source='file')
        self.store.add('Recovered dictation',2,.2,source='recovery')
        self.assertEqual(len(self.store.history()),2)
        self.assertEqual(self.store.statistics()['dictations'],1)
        self.assertEqual(self.store.statistics()['audio_seconds'],2)

    def test_search_treats_sql_wildcards_as_text(self):
        self.store.add('Discount 50% today',1,.1)
        self.store.add('A different phrase',1,.1)
        self.assertEqual([r['text'] for r in self.store.history('%')],['Discount 50% today'])
        self.assertEqual(len(self.store.history('DISCOUNT')),1)

    def test_damaged_preferences_are_preserved(self):
        self.store.settings_path.write_text('{broken',encoding='utf-8')
        restored=Store(self.directory.name)
        self.assertEqual(restored.settings_path.read_text('utf-8'),'{broken')
        self.assertEqual(restored.history(),[])


if __name__=='__main__':unittest.main()
