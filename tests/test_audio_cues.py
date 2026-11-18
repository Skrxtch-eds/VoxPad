"""A first cue uses prepared PCM, without file reads or real audio playback."""
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from audio_cues import AudioCues


class AudioCueTests(unittest.TestCase):
    def test_first_start_and_stop_are_ready_before_press(self):
        cues=AudioCues()
        for kind in ('start','stop'):
            with self.subTest(kind=kind):
                played=threading.Event()
                with patch('audio_cues.sf.read',side_effect=AssertionError('file read on press')), \
                     patch('audio_cues.winsound.PlaySound',side_effect=lambda *args:played.set()) as play:
                    expected=cues.wav_bytes(kind,50)
                    cues.play(kind,50)
                    self.assertTrue(played.wait(1))
                    self.assertEqual(play.call_args.args[0],expected)


if __name__=='__main__':unittest.main()
