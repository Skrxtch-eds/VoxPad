"""Capsule lifecycle and original animation, with every native window call mocked."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock,patch

from PIL import Image,ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from PySide6.QtCore import QCoreApplication,QEvent,QEventLoop,QObject,QTimer
from PySide6.QtWidgets import QApplication
import qt_recording_overlay as overlay
from recording_overlay import RecordingOverlay,MonitorInfo

APP=QApplication.instance() or QApplication([])


class QtCapsuleTests(unittest.TestCase):
    def pump(self,milliseconds):
        loop=QEventLoop()
        QTimer.singleShot(milliseconds,loop.quit)
        loop.exec()

    def wait_for(self,predicate):
        until=time.perf_counter()+3
        while not predicate() and time.perf_counter()<until:
            self.pump(5)
        self.assertTrue(predicate())

    def test_target_filter_rejects_own_process_and_invalid_handles(self):
        def owner(handle,pointer):
            ctypes.cast(pointer,ctypes.POINTER(wintypes.DWORD)).contents.value=handle
            return 1
        with patch.object(overlay.u,'GetWindowThreadProcessId',side_effect=owner), \
             patch('qt_recording_overlay.os.getpid',return_value=100):
            self.assertFalse(overlay.is_external_target(None))
            self.assertFalse(overlay.is_external_target(100))
            self.assertTrue(overlay.is_external_target(200))
        with patch.object(overlay.u,'GetWindowThreadProcessId',return_value=0):
            self.assertFalse(overlay.is_external_target(123))

    def test_qt_scheduler_cancels_callbacks(self):
        owner=QObject()
        scheduler=overlay.QtScheduler(owner,lambda:123)
        callback=Mock()
        job=scheduler.after(20,callback)
        scheduler.after_cancel(job)
        self.pump(40)
        callback.assert_not_called()
        scheduler.after(1,callback)
        self.wait_for(lambda:callback.called)
        self.assertEqual(scheduler.winfo_id(),123)
        self.assertFalse(scheduler.jobs)
        scheduler.close()

    def test_scheduler_handles_independent_jobs_and_repeated_cancellation(self):
        owner=QObject()
        scheduler=overlay.QtScheduler(owner,lambda:123)
        cancelled=Mock();fired=Mock();pending=Mock()
        cancelled_job=scheduler.after(20,cancelled)
        fired_job=scheduler.after(1,fired)
        scheduler.after_cancel(cancelled_job)
        self.wait_for(lambda:fired.called)
        scheduler.after_cancel(cancelled_job)
        scheduler.after_cancel(fired_job)
        scheduler.after(20,pending)
        scheduler.close()
        self.pump(40)
        fired.assert_called_once()
        cancelled.assert_not_called();pending.assert_not_called()
        self.assertFalse(scheduler.jobs)

    def capsule(self):
        self.create=self.enterContext(patch.object(overlay.u,'CreateWindowExW',return_value=12345))
        self.show=self.enterContext(patch.object(overlay.u,'ShowWindow'))
        self.destroy=self.enterContext(patch.object(overlay.u,'DestroyWindow'))
        self.capture_threads=[]
        def backdrop(x,y,width,height):
            self.capture_threads.append(threading.get_ident())
            image=Image.new('RGB',(width,height),'#16324e')
            draw=ImageDraw.Draw(image)
            draw.rectangle((width//2,0,width-1,height-1),fill='#edb471')
            draw.line((0,height//3,width,height*2//3),fill='#f7f4ed',width=max(1,width//12))
            return image
        # Synthetic background: no test reads pixels from the user's desktop.
        self.capture=self.enterContext(patch('qt_recording_overlay.capture_backdrop',side_effect=backdrop))
        def monitor(handle,pointer):
            info=MonitorInfo();info.size=ctypes.sizeof(info)
            info.monitor=wintypes.RECT(0,0,2880,1920)
            info.work=wintypes.RECT(0,0,2880,1872)
            ctypes.memmove(pointer,ctypes.byref(info),ctypes.sizeof(info))
            return True
        self.enterContext(patch.object(overlay.u,'MonitorFromWindow',return_value=7))
        self.enterContext(patch.object(overlay.u,'GetMonitorInfoW',side_effect=monitor))
        parent=QObject()
        capsule=overlay.QtRecordingOverlay(parent,lambda:111,lambda:.3)
        capsule._test_parent=parent
        def cleanup():
            capsule.close()
            capsule._executor.shutdown(wait=True,cancel_futures=True)
            QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        self.addCleanup(cleanup)
        return capsule

    def test_glass_and_wave_run_off_gui_thread_with_one_backdrop(self):
        capsule=self.capsule()
        main_thread=threading.get_ident()
        render_threads=[];present_threads=[];frames=[]
        original=RecordingOverlay.render
        def render(canvas,*args):
            render_threads.append(threading.get_ident())
            return original(canvas,*args)
        def present(image,opacity):
            present_threads.append(threading.get_ident())
            frames.append((image,opacity))
        capsule.present=Mock(side_effect=present)
        with patch.object(RecordingOverlay,'render',render):
            capsule.show(999)
            self.wait_for(lambda:capsule.amount==1. and len(frames)>=5)
            self.assertTrue(capsule.visible)
            self.assertEqual(frames[-1][0].size,(301,173))
            self.assertLess(frames[0][0].width,frames[-1][0].width/3)
            self.assertTrue(all(identifier!=main_thread for identifier in render_threads))
            self.assertTrue(all(identifier!=main_thread for identifier in self.capture_threads))
            self.assertTrue(all(identifier==main_thread for identifier in present_threads))
            self.assertGreater(frames[-1][1],frames[0][1])
            capsule.hide()
            self.wait_for(lambda:capsule.amount==0)
            self.assertFalse(capsule.visible)
        self.capture.assert_called_once_with(1311,1703,257,129)
        flags=self.create.call_args.args[0]
        self.assertTrue(flags & 0x08000000)  # WS_EX_NOACTIVATE
        self.assertTrue(flags & 0x20)        # WS_EX_TRANSPARENT

    def test_glass_surface_matches_original_lens_instead_of_flat_graphite(self):
        capsule=self.capsule()
        frames=[]
        capsule.present=Mock(side_effect=lambda image,opacity:frames.append(image))
        capsule.show(999)
        self.wait_for(lambda:bool(frames))
        expected=RecordingOverlay.__new__(RecordingOverlay)
        expected.display_scale,expected.scale=capsule.display_scale,capsule.scale
        background=self.capture.side_effect(1311,1703,257,129)
        expected.prepare_surface(background)
        self.assertEqual(capsule._canvas.output_frame.tobytes(),expected.output_frame.tobytes())
        self.assertNotEqual(capsule._canvas.output_frame.getpixel((55,80)),
                            capsule._canvas.output_frame.getpixel((215,80)))

    def test_stop_mid_entrance_collapses_current_shape_without_jumping(self):
        capsule=self.capsule()
        capsule.present=Mock()
        capsule.show(999)
        self.wait_for(lambda:capsule.motion.shape>.2)
        before=capsule.motion
        capsule.hide()
        at_stop=capsule.advance_motion(capsule.motion_started)
        self.assertAlmostEqual(at_stop.shape,before.shape)
        self.assertAlmostEqual(at_stop.offset,before.offset)
        self.wait_for(lambda:capsule.motion_phase=='hidden')
        self.assertEqual(capsule.amount,0.)
        self.assertIsNone(capsule.job)

    def test_restart_during_exit_starts_a_fresh_entrance(self):
        capsule=self.capsule()
        capsule.present=Mock()
        capsule.show(999)
        self.wait_for(lambda:capsule.amount==1.)
        capsule.hide()
        self.pump(30)
        capsule.show(999)
        self.wait_for(lambda:capsule.motion_phase=='idle')
        self.assertTrue(capsule.visible)
        self.assertEqual(capsule.motion.shape,1.)
        self.assertEqual(capsule.amount,1.)
        self.assertEqual(self.capture.call_count,2)

    def test_restart_on_another_monitor_recaptures_new_physical_bounds(self):
        capsule=self.capsule()
        capsule.present=Mock()
        capsule.show(999)
        self.wait_for(lambda:capsule.motion_phase=='idle')
        info=MonitorInfo();info.size=ctypes.sizeof(info)
        info.monitor=wintypes.RECT(-1920,0,0,1080)
        info.work=wintypes.RECT(-1920,0,0,1032)
        def get_info(handle,pointer):
            ctypes.memmove(pointer,ctypes.byref(info),ctypes.sizeof(info))
            return True
        with patch.object(overlay.u,'GetMonitorInfoW',side_effect=get_info):
            capsule.show(456)
            self.wait_for(lambda:capsule.motion_phase=='idle')
        self.assertLess(capsule.x,0)
        self.assertEqual(capsule.work_area,(-1920,0,0,1032))
        self.capture.assert_called_with(capsule.x,capsule.y,capsule.scaled(234),capsule.scaled(117))
        self.assertEqual(self.capture.call_count,2)

    def test_frame_queue_is_bounded_when_worker_is_slow(self):
        capsule=self.capsule()
        capsule.present=Mock()
        capsule.show(999)
        self.wait_for(lambda:capsule.motion_phase=='idle')
        original=capsule._canvas.render
        started=threading.Event();release=threading.Event()
        def blocked(*args):
            started.set()
            release.wait(2)
            return original(*args)
        try:
            with patch.object(capsule._canvas,'render',side_effect=blocked) as render:
                self.wait_for(started.is_set)
                pending=capsule._rendering
                self.pump(60)
                self.assertIs(capsule._rendering,pending)
                self.assertEqual(render.call_count,1)
                capsule.hide()
                self.wait_for(lambda:capsule.amount==0.)
        finally:
            release.set()

    def test_stop_while_preparing_cannot_show_capsule_later(self):
        capsule=self.capsule()
        capsule.present=Mock()
        capsule.show(999)
        capsule.hide()
        self.pump(150)
        capsule.present.assert_not_called()
        self.assertLessEqual(self.capture.call_count,1)
        self.assertIsNone(capsule.job)

    def test_close_cancels_animations_and_destroys_only_its_window(self):
        capsule=self.capsule()
        capsule.present=Mock()
        capsule.show(999)
        capsule.close()
        self.pump(80)
        capsule.present.assert_not_called()
        self.assertFalse(capsule.root.jobs)
        self.destroy.assert_called_once_with(12345)

    def test_failed_preparation_stops_callbacks_without_showing_window(self):
        capsule=self.capsule()
        capsule.present=Mock()
        with patch.object(RecordingOverlay,'prepare_surface',side_effect=RuntimeError('render failed')):
            capsule.show(999)
            self.wait_for(lambda:not capsule.visible)
        self.assertIsNone(capsule.job)
        capsule.present.assert_not_called()
        self.capture.assert_called_once()


if __name__=='__main__':unittest.main()
