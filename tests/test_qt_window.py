"""Regressions for portrait resizing."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/source'))
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qt_app import initial_window_size
from qt_window import ASPECT, WindowGeometry

APP = QApplication.instance() or QApplication([])


class WindowGeometryTests(unittest.TestCase):
    def setUp(self):
        self.window = QWindow()
        self.window.setFlags(Qt.Window | Qt.FramelessWindowHint)
        self.window.resize(391, 510)
        self.geometry = WindowGeometry(self.window)

    def tearDown(self):
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_initial_size_fits_both_screen_dimensions(self):
        for width, height in [(1920, 1080), (640, 320), (280, 700), (360, 240)]:
            with self.subTest(screen=(width, height)):
                size = initial_window_size(width, height)
                self.assertLessEqual(size.width(), width - 23)
                self.assertLessEqual(size.height(), height - 23)
                self.assertLessEqual(abs(size.height() - size.width() / ASPECT), 1)

    def test_programmatic_resize_preserves_portrait_and_limits(self):
        for size in [(600, 400), (400, 700), (900, 300), (300, 391)]:
            self.window.resize(*size)
            QTest.qWait(30)
            self.assertLessEqual(abs(self.window.height() - self.window.width() / ASPECT), 1)
            self.assertGreaterEqual(self.window.width(), self.window.minimumWidth())
            self.assertLessEqual(self.window.height(), self.window.maximumHeight())

    def test_corner_drag_tracks_pointer_without_geometry_feedback(self):
        start = QRect(120, 140, 391, 510)
        for horizontal in (Qt.LeftEdge, Qt.RightEdge):
            for vertical in (Qt.TopEdge, Qt.BottomEdge):
                with self.subTest(horizontal=horizontal, vertical=vertical):
                    edges = (horizontal | vertical).value
                    left, top = horizontal == Qt.LeftEdge, vertical == Qt.TopEdge
                    sizes = []
                    for index in (*range(31), 80, 30, 0):
                        # A near-horizontal drag deliberately alternates which axis moves.
                        dx, dy = index, index // 3
                        delta = QPointF(-dx if left else dx, -dy if top else dy)
                        self.geometry.resize_from_drag(edges, start, delta)
                        QTest.qWait(2)
                        result = self.window.geometry()
                        sizes.append(result.width())
                        self.assertLessEqual(abs(result.height() - result.width() / ASPECT), 1)
                        self.assertEqual(result.right() if left else result.left(),
                                         start.right() if left else start.left())
                        self.assertEqual(result.bottom() if top else result.top(),
                                         start.bottom() if top else start.top())
                    self.assertGreater(sizes[30], start.width())
                    self.assertTrue(all(0 <= b - a <= 1 for a, b in zip(sizes[:30], sizes[1:31])))
                    self.assertEqual(sizes[30], sizes[-2])
                    self.assertEqual(self.window.geometry(), start)


if __name__ == '__main__':
    unittest.main()
