"""Daily chart counters must survive history retention and idempotent retries."""
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/source'))
from storage import Store


class DailyStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent, prefix='.tmp-daily-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def test_daily_counters_outlive_retention_and_deletion(self):
        store = Store(self.directory)
        for _ in range(105):
            store.add('two words', 2, .1)
        self.assertEqual(len(store.history()), 100)
        self.assertEqual(store.daily_statistics()[-1]['words'], 210)
        for row in store.history():store.delete(row['id'])
        self.assertEqual(Store(self.directory).daily_statistics()[-1]['dictations'], 105)

    def test_retry_receipt_does_not_double_count_chart(self):
        store = Store(self.directory)
        identifier = 'a' * 32
        store.add('two words', 2, .1, identifier=identifier)
        store.add('two words', 2, .1, identifier=identifier)
        self.assertEqual(store.daily_statistics()[-1]['dictations'], 1)

    def test_backfill_available_history_once_without_modifying_totals(self):
        store = Store(self.directory)
        store.add('existing text', 3, .1)
        totals = store.statistics()
        with closing(store.connect()) as db, db:
            db.execute('DROP TABLE daily_stats')
        restored = Store(self.directory)
        self.assertEqual(restored.statistics(), totals)
        self.assertEqual(restored.daily_statistics()[-1]['words'], 2)
        self.assertEqual(Store(self.directory).daily_statistics()[-1]['words'], 2)

    def test_seven_contiguous_local_days_with_empty_days(self):
        store = Store(self.directory)
        day = datetime.now().astimezone().date()
        rows = store.daily_statistics(day)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]['day'], (day - timedelta(days=6)).isoformat())
        self.assertTrue(all(row['words'] == 0 for row in rows))
        store.add('file text', 2, .1, source='file')
        self.assertTrue(all(row['words'] == 0 for row in store.daily_statistics(day)))


if __name__ == '__main__':
    unittest.main()
