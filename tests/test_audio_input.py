from pathlib import Path
import sys,threading,time,unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from audio_input import PreparedInput


def wait_for(predicate):
    end=time.monotonic()+2
    while not predicate():
        if time.monotonic()>end:raise AssertionError('Microphone preparation did not finish')
        time.sleep(.002)


class AudioInputTests(unittest.TestCase):
    def setUp(self):
        self.input=PreparedInput(Mock())
        self.addCleanup(self.input.close)

    def test_prepare_does_not_start_capture_and_reuses_stopped_stream(self):
        stream=Mock()
        with patch.object(self.input,'open',return_value=(stream,48000,4)) as factory:
            self.input.prepare(4);wait_for(lambda:self.input.cached is not None)
            stream.start.assert_not_called()
            self.assertEqual(self.input.take(4),(stream,48000,4))
            self.input.recycle(stream,48000,4)
            self.assertEqual(self.input.take(4),(stream,48000,4))
            self.assertEqual(factory.call_count,1)
        self.input.dispose(stream)

    def test_changing_device_closes_previous_stream(self):
        first,second=Mock(),Mock()
        with patch.object(self.input,'open',side_effect=[(first,48000,4),(second,16000,5)]):
            self.input.prepare(4);wait_for(lambda:self.input.cached is not None)
            self.input.prepare(5);wait_for(lambda:self.input.cached is not None)
            first.close.assert_called_once()
            self.assertEqual(self.input.cached,(second,16000,5))

    def test_new_default_does_not_reuse_old_default(self):
        first,second=Mock(),Mock()
        with patch('audio_input.sd.default') as default,patch.object(self.input,'open',side_effect=[(first,48000,4),(second,48000,5)]):
            default.device=[4,0];self.input.prepare(None);wait_for(lambda:self.input.cached is not None)
            default.device=[5,0]
            self.assertEqual(self.input.take(None),(second,48000,5))
            first.close.assert_called_once()
        self.input.dispose(second)

    def test_shutdown_closes_stream_still_opening(self):
        entered,release,finished=threading.Event(),threading.Event(),threading.Event()
        stream=Mock();stream.close.side_effect=finished.set
        def open_stream(key):
            entered.set();release.wait(2);return stream,48000,key
        with patch.object(self.input,'open',side_effect=open_stream):
            self.input.prepare(4);self.assertTrue(entered.wait(2))
            self.input.close();release.set();self.assertTrue(finished.wait(2))
        self.assertIsNone(self.input.cached)

    def test_failed_preparation_can_be_retried_on_press(self):
        stream=Mock()
        with patch.object(self.input,'open',side_effect=[RuntimeError('unplugged'),(stream,48000,4)]):
            self.input.prepare(4);wait_for(lambda:self.input.pending is None)
            self.assertEqual(self.input.take(4),(stream,48000,4))
        self.input.dispose(stream)

    def test_low_latency_unsupported_falls_back_to_driver_default(self):
        import sounddevice as sd
        with patch('audio_input.sd.query_devices',return_value={'default_samplerate':48000}),patch('audio_input.sd.InputStream',side_effect=[sd.PortAudioError('unsupported'),Mock()]) as factory:
            stream,rate,key=self.input.open(4)
            self.assertEqual((rate,key),(48000,4))
            self.assertEqual(factory.call_args_list[0].kwargs['latency'],'low')
            self.assertNotIn('latency',factory.call_args_list[1].kwargs)
        self.input.dispose(stream)

    def test_press_during_preparation_reuses_the_stream_being_opened(self):
        entered,release,finished=threading.Event(),threading.Event(),threading.Event()
        self.addCleanup(release.set);stream=Mock();taken=[]
        def open_stream(key):
            entered.set();release.wait(2);return stream,48000,key
        def take():
            taken.append(self.input.take(4));finished.set()
        with patch.object(self.input,'_open',side_effect=open_stream) as factory:
            self.input.prepare(4);self.assertTrue(entered.wait(2))
            taker=threading.Thread(target=take);taker.start()
            self.assertFalse(finished.wait(.02))
            release.set();self.assertTrue(finished.wait(2));taker.join()
            self.assertEqual(factory.call_count,1)
            self.assertEqual(taken,[(stream,48000,4)])
        self.input.dispose(stream)

    def test_shutdown_releases_a_press_waiting_for_preparation(self):
        entered,release,finished=threading.Event(),threading.Event(),threading.Event()
        self.addCleanup(release.set);stream=Mock();errors=[]
        def open_stream(key):
            entered.set();release.wait(2);return stream,48000,key
        def take():
            try:self.input.take(4)
            except RuntimeError as error:errors.append(str(error))
            finally:finished.set()
        with patch.object(self.input,'_open',side_effect=open_stream):
            self.input.prepare(4);self.assertTrue(entered.wait(2))
            taker=threading.Thread(target=take);taker.start()
            self.input.close();self.assertTrue(finished.wait(2));taker.join()
            release.set();wait_for(lambda:stream.close.called)
        self.assertEqual(len(errors),1)


if __name__=='__main__':unittest.main()
