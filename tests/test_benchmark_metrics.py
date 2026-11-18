from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_asr import error_rate,pipeline


class BenchmarkMetricsTests(unittest.TestCase):
    def test_insertions_deletions_and_substitutions_use_reference_denominator(self):
        score=error_rate('one two three','one three four')
        self.assertEqual(score['word_errors'],2)
        self.assertEqual(score['reference_words'],3)
        self.assertEqual(error_rate('one','one two three')['word_errors'],2)
        with self.assertRaises(ValueError):error_rate('','one')

    def test_case_punctuation_and_unicode_composition_do_not_hide_spelling_errors(self):
        score=error_rate('Ёжик, GitHub!','Е\u0308ЖИК github')
        self.assertEqual(score['word_errors'],0)
        self.assertEqual(score['character_errors'],0)
        self.assertEqual(error_rate('всё','все')['character_errors'],1)

    def test_pipeline_benchmarks_the_qt_controller_without_waiting_for_disk(self):
        engine=Mock()
        engine.transcribe.return_value=('Fixture transcript',.001)
        audio=np.full(3200,.1,dtype=np.float32)
        text,timings=pipeline(engine,audio,16000,disk_delay=.1)
        self.assertEqual(text,'Fixture transcript')
        np.testing.assert_array_equal(engine.transcribe.call_args.args[0],audio)
        self.assertLess(timings['pipeline_surrogate_seconds'],timings['history_seconds'])

    def test_pipeline_propagates_recognition_failure_and_cleans_up(self):
        engine=Mock()
        engine.transcribe.side_effect=RuntimeError('inference unavailable')
        with self.assertRaises(RuntimeError):pipeline(engine,np.ones(3200,dtype=np.float32),16000)


if __name__=='__main__':unittest.main()
