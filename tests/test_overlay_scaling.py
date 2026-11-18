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
                factor=1.1*min(width/2880,height/1920)
                self.assertAlmostEqual(renderer.display_scale,factor)
                self.assertAlmostEqual(renderer.scaled(234)/renderer.scaled(117),2,delta=.03)
                self.assertLessEqual(abs(renderer.x+renderer.scaled(234)/2-width/2),1)
                self.assertEqual(renderer.y+renderer.scaled(117)+renderer.scaled(36),info.work.bottom)
                self.assertGreaterEqual(renderer.scale,2*factor)
                self.assertGreaterEqual(renderer.scale,3)
        renderer.configure_monitor(monitor(2880,1920))
        self.assertEqual((renderer.scaled(234),renderer.scaled(117)),(257,129))
        renderer.configure_monitor(monitor(1440,960))
        self.assertEqual((renderer.scaled(234),renderer.scaled(117)),(129,64))

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

    def test_supersampling_keeps_detail_and_antialiased_transparency(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        for width,height in ((1440,960),(2880,1920),(5760,3840)):
            with self.subTest(resolution=(width,height)):
                renderer.configure_monitor(monitor(width,height))
                renderer.prepare_surface(Image.new('RGB',(renderer.scaled(234),renderer.scaled(117)),'#4c6681'))
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

    def test_wave_glow_and_droplets_stay_inside_safe_band(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.prepare_surface(Image.new('RGB',(257,129),'#4c6681'))
        padding=round(renderer.vertical_padding*renderer.wave_scale)
        droplets=False
        for amplitude in (0.,.2,.6,1.):
            for elapsed in (0.,.3,.8,1.6,2.4):
                alpha=np.asarray(renderer.wave_mask(elapsed,amplitude))
                self.assertFalse(alpha[:padding].any())
                self.assertFalse(alpha[-padding:].any())
                self.assertTrue(np.any((alpha>0)&(alpha<40)), 'missing soft glow')
                solid=alpha>160
                runs=np.sum(solid[1:]&~solid[:-1],axis=0)
                if amplitude<=.2:
                    self.assertLessEqual(int(runs.max()),1)
                else:
                    droplets=droplets or bool(np.any(runs>1))
        self.assertTrue(droplets,'loud wave has no separated edge droplets')

    def test_orb_flight_morph_and_exit_finish_without_lingering(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920,bottom_gap=120))
        renderer.begin_enter()
        started=renderer.motion_started
        first=renderer.advance_motion(started)
        self.assertEqual(first.shape,0.)
        self.assertGreater(first.offset*renderer.display_scale,
                           1920-renderer.y-renderer.scaled(renderer.height)/2)
        before_expansion=renderer.advance_motion(started+.07)
        self.assertEqual(before_expansion.shape,0.)
        final=renderer.advance_motion(started+renderer.enter_duration+1e-6)
        self.assertEqual((final.shape,final.offset,final.opacity),(1.,0.,1.))
        self.assertEqual(renderer.motion_phase,'idle')
        renderer.visible=True
        renderer.hide()
        stopped=renderer.motion_started
        ball=renderer.advance_motion(stopped+renderer.exit_duration*.6)
        self.assertEqual(ball.shape,0.)
        end=renderer.advance_motion(stopped+renderer.exit_duration+1e-6)
        self.assertEqual((end.shape,end.opacity),(0.,0.))
        self.assertEqual(renderer.motion_phase,'hidden')
        self.assertEqual(renderer.amount,0.)

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

    def test_gaussian_wave_blurs_center_and_preserves_thin_ends(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.prepare_surface(Image.new('RGB',(257,129),'#4c6681'))
        width,height=renderer.wave_size
        source=Image.new('L',(width,height))
        source.paste(255,(0,0,width,height//2))
        result=np.asarray(renderer.blur_wave(source,1.))
        center=result[:,width//2]
        end=result[:,0]
        center_soft=np.count_nonzero((center>5)&(center<250))
        end_soft=np.count_nonzero((end>5)&(end<250))
        self.assertGreater(center_soft,20)
        self.assertLess(end_soft,center_soft/5)
        self.assertIs(renderer.blur_wave(source,0.),source)

    def test_taskbar_clips_every_edge_without_mutating_the_frame(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(1440,960,-1440,-640))
        left,top,right,bottom=renderer.work_area
        source=Image.new('RGBA',(20,20),(240,250,255,255))
        for position in ((left-10,top+30),(left+30,top-10),
                         (right-10,top+30),(left+30,bottom-10),
                         (left-10,bottom-10),(left+30,top+30)):
            with self.subTest(position=position):
                result=renderer.clip_to_work_area(source,position)
                pixels=np.asarray(result.getchannel('A'))
                x,y=position
                xs=np.arange(20)+x;ys=np.arange(20)+y
                expected=(ys[:,None]>=top)&(ys[:,None]<bottom)&(xs[None,:]>=left)&(xs[None,:]<right)
                np.testing.assert_array_equal(pixels>0,expected)
                self.assertEqual(source.getchannel('A').getextrema(),(255,255))
        self.assertIsNone(renderer.clip_to_work_area(source,(left,bottom)))
        self.assertIsNone(renderer.clip_to_work_area(source,(right,top)))

    def test_invisible_orb_skips_native_presentation_over_taskbar(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.begin_enter()
        renderer.hwnd=123
        with patch.object(overlay.u,'GetDC') as dc,patch.object(overlay.u,'ShowWindow') as show:
            renderer.present(Image.new('RGBA',(60,60),'white'),1.)
        dc.assert_not_called()
        show.assert_called_once_with(123,0)


if __name__=='__main__':unittest.main()
