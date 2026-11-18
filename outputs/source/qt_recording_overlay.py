"""Nonblocking Qt scheduling for the liquid-glass recording capsule."""
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
import os

from PySide6.QtCore import QObject, QTimer, Qt

from recording_overlay import RecordingOverlay, MonitorInfo, capture_backdrop, physical_pixels, u

u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.GetWindowThreadProcessId.restype = wintypes.DWORD


def is_external_target(target):
    """Window identity only; no text, screenshot or accessibility inspection."""
    if not target:
        return False
    process = wintypes.DWORD()
    if not u.GetWindowThreadProcessId(target, ctypes.byref(process)):
        return False
    return process.value != os.getpid()


class QtScheduler(QObject):
    """Precise Qt timers for the native capsule renderer."""
    def __init__(self, parent, get_window_id):
        super().__init__(parent)
        self.get_window_id = get_window_id
        self.jobs = set()

    def winfo_id(self):
        return self.get_window_id()

    def after(self, milliseconds, callback):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setTimerType(Qt.PreciseTimer)
        def fire():
            self.jobs.discard(timer)
            timer.deleteLater()
            callback()
        timer.timeout.connect(fire)
        self.jobs.add(timer)
        timer.start(max(1, milliseconds))
        return timer

    def after_cancel(self, timer):
        if timer in self.jobs:
            self.jobs.remove(timer)
            timer.stop()
            timer.deleteLater()

    def close(self):
        for timer in tuple(self.jobs):
            self.after_cancel(timer)


class QtRecordingOverlay(RecordingOverlay):
    """Glass and wave frames run on one CPU worker, without a frame backlog."""
    def __init__(self, parent, get_window_id, get_level):
        scheduler = QtScheduler(parent, get_window_id)
        try:
            super().__init__(scheduler, get_level)
        except Exception:
            scheduler.close()
            scheduler.deleteLater()
            raise
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='VoxPad-capsule')
        self._preparing = None
        self._rendering = None
        self._canvas = None
        self._frame = None

    @physical_pixels()
    def prepare(self, target):
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        monitor = u.MonitorFromWindow(target or self.root.winfo_id(), 2)
        if not u.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.configure_monitor(info)
        canvas = RecordingOverlay.__new__(RecordingOverlay)
        canvas.display_scale, canvas.scale = self.display_scale, self.scale
        # Freeze this recording's physical bounds before another show can move us.
        region = (self.x, self.y, self.scaled(self.width), self.scaled(self.height))
        def build():
            # The old liquid-glass lens needs the actual background, once per
            # appearance. Keep capture and lens construction off the GUI thread;
            # subsequent wave frames reuse the surface and never read the screen.
            with physical_pixels():
                backdrop = capture_backdrop(*region)
            canvas.prepare_surface(backdrop)
            return canvas, canvas.render(0, 0)
        self._preparing = self._executor.submit(build)

    def show(self, target=None):
        if self.closed:
            return
        if self.job is not None:
            self.root.after_cancel(self.job)
            self.job = None
        for future in (self._preparing, self._rendering):
            if future is not None:
                future.cancel()
        self._rendering = None
        self._canvas = self._frame = None
        # Keep an old fading frame from reappearing at a new monitor position.
        u.ShowWindow(self.hwnd, 0)
        self.prepare(target)
        self.visible = True
        self.amount = 0.
        self.level = 0.0
        self.motion_phase = 'preparing'
        self.job = self.root.after(1, self._check_prepared)

    def _check_prepared(self):
        self.job = None
        if self.closed or not self.visible:
            if self._preparing is not None:
                self._preparing.cancel()
            return
        if not self._preparing.done():
            self.job = self.root.after(4, self._check_prepared)
            return
        try:
            self._canvas, self._frame = self._preparing.result()
            self._preparing = None
            self.begin_enter()
            self.tick()
        except Exception:
            self.visible = False
            self.amount = 0.
            self.motion_phase = 'hidden'
            u.ShowWindow(self.hwnd, 0)

    def render(self, elapsed, amplitude):
        if self._rendering is not None and self._rendering.done():
            self._frame = self._rendering.result()
            self._rendering = None
        # At most one pending frame: the GUI never waits and frames cannot queue up.
        if self._rendering is None and not self.closed:
            self._rendering = self._executor.submit(self._canvas.render, elapsed, amplitude)
        return self._frame

    def hide(self):
        super().hide()
        if self._canvas is None:
            if self.job is not None:
                self.root.after_cancel(self.job)
                self.job = None
            if self._preparing is not None:
                self._preparing.cancel()
            self.amount = 0.
            self.motion_phase = 'hidden'
            u.ShowWindow(self.hwnd, 0)

    def close(self):
        if self.closed:
            return
        super().close()
        self.root.close()
        self.root.deleteLater()
        self._executor.shutdown(wait=False, cancel_futures=True)
