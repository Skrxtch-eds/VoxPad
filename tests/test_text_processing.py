from pathlib import Path
import sys,unittest
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from text_processing import normalize_transcript,format_ending
from engine import Engine


class TranscriptSpellingTests(unittest.TestCase):
    def test_yo_is_preserved_with_case_and_punctuation(self):
        text='Ёжик ещё живёт у ёлки. ВСЁ!'
        self.assertEqual(normalize_transcript(text),text)

    def test_decomposed_yo_is_also_replaced(self):
        self.assertEqual(normalize_transcript('Е\u0308жик и е\u0308лка'),'Ёжик и ёлка')

    def test_other_letters_languages_and_layout_are_unchanged(self):
        text='Café, naïve, Straße, Україна, йод.\n  123 — test@example.com'
        self.assertEqual(normalize_transcript(text),text)
        self.assertEqual(normalize_transcript(''),'')

    def test_engine_normalizes_before_returning_text_to_any_consumer(self):
        engine=Engine.__new__(Engine);engine.recognizer=Mock()
        stream=Mock();stream.result=SimpleNamespace(text='  Ёжик ещё живёт.  ')
        engine.recognizer.create_stream.return_value=stream
        text,seconds=engine.transcribe(np.ones(3200,dtype=np.float32)*.1,16000)
        self.assertEqual(text,'Ёжик ещё живёт.')
        self.assertGreaterEqual(seconds,0)
        engine.recognizer.decode_stream.assert_called_once_with(stream)
        self.assertEqual(format_ending(text,'period_space'),('Ёжик ещё живёт. ',False))

    def test_parakeet_unknown_in_russian_words_and_isolated_letter(self):
        for original,expected in (
            ('<unk>жик.','Ёжик.'),('<unk>','Ё'),('Вот <unk>лка, вс<unk> ещ<unk> впереди.','Вот ёлка, всё ещё впереди.'),
            ('ВС<unk> И <unk>ЛКА','ВСЁ И ЁЛКА'),('Первое. «<unk>жик»','Первое. «Ёжик»'),
            ('Алло, при<unk>м!','Алло, приём!')):
            with self.subTest(original=original):
                self.assertEqual(normalize_transcript(original),expected)

    def test_unknown_uses_the_same_fallback_in_other_languages(self):
        for original in ('Hello <unk>.','abc<unk>def','Café<unk>','שלום<unk>'):
            self.assertEqual(normalize_transcript(original),original.replace('<unk>','ё'))

    def test_parakeet_engine_repairs_decoder_marker_before_any_consumer(self):
        engine=Engine.__new__(Engine);engine.recognizer=Mock()
        stream=Mock();stream.result=SimpleNamespace(text='  <unk>жик вс<unk> ещ<unk> жив<unk>т.  ')
        engine.recognizer.create_stream.return_value=stream
        text,_=engine.transcribe(np.full(3200,.1,dtype=np.float32))
        self.assertEqual(text,'Ёжик всё ещё живёт.')


if __name__=='__main__':unittest.main()
