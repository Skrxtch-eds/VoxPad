"""Resolution changes keep the capsule proportional and its renderer sharp."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
import recording_overlay as overlay
from recording_overlay import MonitorInfo,RecordingOverlay


def monitor(width,height,left=0,top=0,bottom_gap=48):
    info=MonitorInfo();info.size=C.sizeof(info)
    info.monitor=W.RECT(left,top,left+width,top+height)
    info.work=W.RECT(left,top,left+width,top+height-bottom_gap)
    return info


class OverlayScalingTests(unittest.TestCase):
    def test_resolution_changes_preserve_relative_size_and_aspect(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        for width,height in ((2880,1920),(1440,960),(1920,1080),(2560,1440),(3840,2160),(5760,3840)):
            with self.subTest(resolution=(width,height)):
                info=monitor(width,height)
                renderer.configure_monitor(info)
                factor=min(width/2880,height/1920)
                self.assertAlmostEqual(renderer.display_scale,factor)
                self.assertAlmostEqual(renderer.scaled(234)/renderer.scaled(117),2,delta=.03)
                self.assertLessEqual(abs(renderer.x+renderer.scaled(234)/2-width/2),1)
                self.assertEqual(renderer.y+renderer.scaled(117)+renderer.scaled(36),info.work.bottom)
                self.assertGreaterEqual(renderer.scale,2*factor)
                self.assertGreaterEqual(renderer.scale,2)
        renderer.configure_monitor(monitor(2880,1920))
        self.assertEqual((renderer.scaled(234),renderer.scaled(117)),(234,117))
        renderer.configure_monitor(monitor(1440,960))
        self.assertEqual((renderer.scaled(234),renderer.scaled(117)),(117,58))

    def test_secondary_monitor_origin_and_work_area(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        for width,height,left,top in ((1920,1080,-1920,0),(1440,2560,2880,-640)):
            info=monitor(width,height,left,top,bottom_gap=80)
            renderer.configure_monitor(info)
            margin=renderer.scaled(20)
            self.assertGreaterEqual(renderer.x-margin,info.work.left)
            self.assertGreaterEqual(renderer.y-margin,info.work.top)
            self.assertLessEqual(renderer.x-margin+renderer.scaled(274),info.work.right)
            self.assertLessEqual(renderer.y-margin+renderer.scaled(157),info.work.bottom)

    def test_button_recording_uses_foreground_monitor_and_recaptures_after_move(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay);renderer.root=Mock()
        selected=[];current=[monitor(2880,1920)]
        def get_info(handle,pointer):
            C.memmove(pointer,C.byref(current[0]),C.sizeof(MonitorInfo))
            return True
        def capture(x,y,width,height):
            selected.append((x,y,width,height))
            return Image.new('RGB',(width,height),'#4c6681')
        with patch.object(overlay.u,'GetForegroundWindow',return_value=123),\
             patch.object(overlay.u,'MonitorFromWindow',return_value=456) as locate,\
             patch.object(overlay.u,'GetMonitorInfoW',side_effect=get_info),\
             patch.object(overlay,'capture_backdrop',side_effect=capture),\
             patch.object(renderer,'prepare_surface'):
            renderer.prepare(None)
            locate.assert_called_with(123,2)
            self.assertEqual(selected[-1][2:],(234,117))
            current[0]=monitor(1440,960,-1440)
            renderer.prepare(789)
            locate.assert_called_with(789,2)
            self.assertEqual(selected[-1][2:],(117,58))
            self.assertLess(renderer.x,0)

    def test_supersampling_keeps_detail_and_antialiased_transparency(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        for width,height in ((1440,960),(2880,1920),(5760,3840)):
            with self.subTest(resolution=(width,height)):
                renderer.configure_monitor(monitor(width,height))
                renderer.prepare_surface(Image.new('RGB',(renderer.scaled(234),renderer.scaled(117)),'#4c6681'))
                self.assertGreaterEqual(renderer.glass.width,468)
                self.assertGreaterEqual(renderer.static_frame.width,2*renderer.scaled(274))
                for amplitude in (0,.5,1):
                    image=renderer.render(.37,amplitude)
                    self.assertEqual(image.size,(renderer.scaled(274),renderer.scaled(157)))
                    alpha=np.asarray(image.getchannel('A'))
                    self.assertTrue(np.any((alpha>0)&(alpha<255)))
                    self.assertEqual(int(alpha[0,0]),0)
                    self.assertEqual(int(alpha[-1,-1]),0)
                    self.assertGreater(int(alpha.max()),240)

    def test_dpi_context_restored_even_on_failure(self):
        context=Mock(return_value=42)
        with patch.object(overlay,'_set_dpi_context',context):
            with self.assertRaises(RuntimeError):
                with overlay.physical_pixels():raise RuntimeError('capture failed')
        self.assertEqual(context.call_args_list[-1].args,(42,))

    def test_native_window_is_per_monitor_aware_and_keeps_tk_context(self):
        get_thread=overlay.u.GetThreadDpiAwarenessContext
        get_thread.argtypes=[];get_thread.restype=W.HANDLE
        get_window=overlay.u.GetWindowDpiAwarenessContext
        get_window.argtypes=[W.HWND];get_window.restype=W.HANDLE
        equal=overlay.u.AreDpiAwarenessContextsEqual
        equal.argtypes=[W.HANDLE,W.HANDLE];equal.restype=W.BOOL
        previous=get_thread()
        renderer=RecordingOverlay(Mock(),lambda:0)
        try:
            self.assertTrue(equal(previous,get_thread()))
            context=get_window(renderer.hwnd)
            self.assertTrue(equal(context,W.HANDLE(-4)) or equal(context,W.HANDLE(-3)))
        finally:renderer.close()


if __name__=='__main__':unittest.main()
