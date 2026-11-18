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
from recording_overlay import CapsuleMotion,MonitorInfo,RecordingOverlay


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

    def test_wave_has_soft_continuous_edges_without_dots_at_any_level(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.prepare_surface(Image.new('RGB',(257,129),'#4c6681'))
        padding=round(renderer.vertical_padding*renderer.wave_scale)
        for amplitude in (0.,.2,.6,1.):
            for elapsed in (0.,.3,.8,1.6,2.4):
                alpha=np.asarray(renderer.wave_mask(elapsed,amplitude))
                self.assertFalse(alpha[:padding].any())
                self.assertFalse(alpha[-padding:].any())
                self.assertTrue(np.any((alpha>0)&(alpha<40)), 'missing soft glow')
                for threshold in (30,160):
                    solid=alpha>threshold
                    runs=np.sum(solid[1:]&~solid[:-1],axis=0)
                    self.assertLessEqual(int(runs.max()),1)

    def test_slit_grows_from_centre_before_opening_and_closes_from_both_sides(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920,bottom_gap=120))
        renderer.begin_enter()
        started=renderer.motion_started
        first=renderer.advance_motion(started)
        self.assertEqual(first.shape,0.)
        self.assertEqual((first.offset,first.opacity),(0.,0.))
        before_expansion=renderer.advance_motion(started+renderer.enter_duration*.10)
        self.assertEqual(before_expansion.shape,0.)
        self.assertGreater(before_expansion.opacity,0.)
        wider=renderer.advance_motion(started+renderer.enter_duration*.20)
        self.assertEqual(wider.shape,0.)
        self.assertGreater(wider.span,before_expansion.span)
        self.assertLess(wider.span,1.)
        self.assertGreater(renderer.advance_motion(started+renderer.enter_duration*.40).shape,0.)
        final=renderer.advance_motion(started+renderer.enter_duration+1e-6)
        self.assertEqual((final.shape,final.offset,final.opacity),(1.,0.,1.))
        self.assertEqual(renderer.motion_phase,'idle')
        renderer.visible=True
        renderer.hide()
        stopped=renderer.motion_started
        line=renderer.advance_motion(stopped+renderer.exit_duration*.80)
        self.assertEqual(line.shape,0.)
        self.assertGreater(line.span,0.)
        self.assertLess(line.span,1.)
        self.assertGreater(line.opacity,0.)
        self.assertGreater(line.gap,0.)
        end=renderer.advance_motion(stopped+renderer.exit_duration+1e-6)
        self.assertEqual((end.shape,end.opacity,end.span),(0.,0.,0.))
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

    def test_live_wave_has_visible_soft_glow_along_its_entire_length(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.prepare_surface(Image.new('RGB',(234,117),'#314059'))
        alpha=np.asarray(renderer.wave_mask(0.,0.))
        centre=alpha.shape[0]//2
        near=round(4.*renderer.wave_scale)
        far=round(10.*renderer.wave_scale)
        for fraction in (.15,.50,.85):
            x=round((alpha.shape[1]-1)*fraction)
            self.assertGreater(int(alpha[centre,x]),150)
            for side in (-1,1):
                halo=int(alpha[centre+side*near,x])
                tail=int(alpha[centre+side*far,x])
                self.assertGreater(halo,20)
                self.assertLess(halo,60)
                self.assertGreater(tail,0)
                self.assertLess(tail,halo)

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

    def test_invisible_first_frame_skips_native_presentation(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.begin_enter()
        renderer.hwnd=123
        with patch.object(overlay.u,'GetDC') as dc,patch.object(overlay.u,'ShowWindow') as show:
            renderer.present(Image.new('RGBA',(60,60),'white'),renderer.motion.opacity)
        dc.assert_not_called()
        show.assert_called_once_with(123,0)

    def test_thin_line_and_closing_edges_at_multiple_dpi(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        for resolution in ((1440,960),(2880,1920),(5760,3840)):
            renderer.configure_monitor(monitor(*resolution))
            renderer.prepare_surface(Image.new('RGB',(234,117),'#314059'))
            source=renderer.render(0.,0.)
            line=renderer.morph_frame(source,CapsuleMotion(shape=0.))
            short=renderer.morph_frame(source,CapsuleMotion(shape=0.,span=.4))
            self.assertEqual(line.size,source.size)
            alpha=np.asarray(line.getchannel('A'))
            rows=np.flatnonzero(alpha.max(axis=1)>100)
            self.assertLessEqual(len(rows),max(2,round(renderer.display_scale*2)))
            self.assertLess(short.getbbox()[2]-short.getbbox()[0],
                            (line.getbbox()[2]-line.getbbox()[0])*.5)
            # Closing removes the ends first, keeping the centre illuminated.
            self.assertEqual(int(alpha.max()),int(np.asarray(short.getchannel('A')).max()))
            closed=renderer.morph_frame(source,CapsuleMotion(shape=0.,span=0.))
            self.assertIsNone(closed.getbbox())

    def test_closing_line_fades_at_centre_and_outer_ends_together(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        for resolution in ((1440,960),(2880,1920),(5760,3840)):
            renderer.configure_monitor(monitor(*resolution))
            renderer.prepare_surface(Image.new('RGB',(234,117),'#314059'))
            source=renderer.render(0.,0.)
            renderer.begin_enter()
            renderer.advance_motion(renderer.motion_started+renderer.enter_duration+1e-6)
            renderer.visible=True
            renderer.hide()
            motion=renderer.advance_motion(renderer.motion_started+renderer.exit_duration*.80)
            full=np.asarray(renderer.morph_frame(source,CapsuleMotion(shape=0.)).getchannel('A')).max(axis=0)
            fading=np.asarray(renderer.morph_frame(source,motion).getchannel('A')).max(axis=0)
            centre=len(full)//2
            half=renderer.scaled(renderer.width)*.49
            self.assertEqual(int(fading[centre]),0)
            for side in (-1,1):
                outer=round(centre+side*.93*half)
                remaining=round(centre+side*.50*half)
                self.assertEqual(int(fading[outer]),0)
                self.assertGreater(int(fading[remaining]),int(full[remaining])*.8)
            lit=fading>40
            self.assertEqual(int(np.sum(lit[1:]&~lit[:-1])),2)
            # Bloom stays subtle but extends beyond the fine white core.
            line=np.asarray(renderer.morph_frame(source,CapsuleMotion(shape=0.)).getchannel('A'))
            y=line.shape[0]//2+round(4*renderer.display_scale)
            self.assertGreater(int(line[y,centre]),20)
            self.assertLess(int(line[y,centre]),50)

    def test_reflection_enters_at_upper_left_and_moves_only_along_top(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.prepare_surface(Image.new('RGB',(234,117),'#314059'))
        source=renderer.render(.5,.4)
        def luminance(image):
            pixels=np.asarray(image,dtype=np.float64)
            return pixels[:,:,:3].mean(axis=2)*pixels[:,:,3]/255.
        original=luminance(source)
        centres=[]
        for position in (.20,.60):
            frame=renderer.morph_frame(source,CapsuleMotion(glint=position,glint_strength=1.))
            increase=np.maximum(0.,luminance(frame)-original)
            total=increase.sum()
            self.assertGreater(total,0.)
            ys,xs=np.indices(increase.shape)
            centres.append(float((xs*increase).sum()/total))
            self.assertLess(float((ys*increase).sum()/total),source.height/2)
            self.assertLess(float(increase[source.height//2+1:].sum()),total*.001)
        self.assertLess(centres[0],source.width/2)
        self.assertGreater(centres[1],source.width/2)

    def test_reflection_runs_once_and_settled_frame_is_unchanged(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        renderer.prepare_surface(Image.new('RGB',(234,117),'#314059'))
        renderer.begin_enter()
        start=renderer.motion_started
        moving=renderer.advance_motion(start+renderer.enter_duration*.55)
        self.assertGreater(moving.glint_strength,.5)
        original=renderer.render(.5,.4)
        lit=renderer.morph_frame(original,CapsuleMotion(glint=.5,glint_strength=1.))
        self.assertNotEqual(lit.tobytes(),original.tobytes())
        for elapsed in (renderer.enter_duration+1e-6,2.,20.):
            settled=renderer.advance_motion(start+elapsed)
            self.assertEqual(settled.glint_strength,0.)
            self.assertIs(renderer.morph_frame(original,settled),original)

    def test_early_release_preserves_position_opacity_and_velocity(self):
        renderer=RecordingOverlay.__new__(RecordingOverlay)
        renderer.configure_monitor(monitor(2880,1920))
        for progress in (.04,.15,.35,.55,.76,.90):
            renderer.begin_enter()
            t=renderer.motion_started+renderer.enter_duration*progress
            before=renderer.advance_motion(t)
            renderer.visible=True
            with patch.object(overlay.time,'perf_counter',return_value=t):
                renderer.hide()
            self.assertEqual(renderer.advance_motion(t),before)
            epsilon=1e-6
            velocity=(renderer.advance_motion(t+epsilon).shape-before.shape)/epsilon
            self.assertAlmostEqual(velocity,renderer.exit_velocity,delta=.003)
            resuming=renderer.advance_motion(t+.10)
            incoming_velocity=renderer.shape_velocity
            with patch.object(overlay.time,'perf_counter',return_value=t+.10):
                renderer.begin_enter(resuming,incoming_velocity)
            resumed=renderer.advance_motion(t+.10)
            self.assertEqual((resumed.shape,resumed.span,resumed.opacity),
                             (resuming.shape,resuming.span,resuming.opacity))
            velocity=(renderer.advance_motion(t+.10+epsilon).shape-resumed.shape)/epsilon
            self.assertAlmostEqual(velocity,incoming_velocity,delta=.003)
            # Finish a fresh close after the interrupted opening.
            renderer.visible=True
            with patch.object(overlay.time,'perf_counter',return_value=t+.10+epsilon):
                renderer.hide()
            end=renderer.advance_motion(renderer.motion_started+renderer.exit_duration+epsilon)
            self.assertEqual((end.shape,end.span,end.opacity),(0.,0.,0.))


if __name__=='__main__':unittest.main()
