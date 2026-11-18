"""Recording bypasses visual press delay; other button actions keep their timing."""
from pathlib import Path
import unittest

from PySide6.QtCore import QObject,Property,QMetaObject,QUrl,Qt
from PySide6.QtQml import QQmlComponent,QQmlEngine
from PySide6.QtTest import QSignalSpy,QTest
from PySide6.QtWidgets import QApplication

APP=QApplication.instance() or QApplication([])


class Theme(QObject):
    pressDuration=Property(int,lambda self:90,constant=True)
    hoverDuration=Property(int,lambda self:180,constant=True)
    leaveDuration=Property(int,lambda self:120,constant=True)


class RecordButtonLatencyTests(unittest.TestCase):
    def setUp(self):
        self.engine=QQmlEngine()
        self.theme=Theme()
        self.engine.rootContext().setContextProperty('appTheme',self.theme)
        source=Path(__file__).resolve().parents[1]/'outputs/source/qml/ButtonMotion.qml'
        self.component=QQmlComponent(self.engine,QUrl.fromLocalFile(str(source)))
        self.motion=self.component.create()
        self.assertIsNotNone(self.motion,str(self.component.errors()))
        self.motion.setProperty('holdAction',True)
        self.motion.setProperty('hovered',True)
        self.motion.setProperty('amount',1.)
        self.press=QSignalSpy(self.motion.pressReady)
        self.release=QSignalSpy(self.motion.releaseReady)

    def tearDown(self):
        self.motion.deleteLater()
        self.engine.deleteLater()
        APP.processEvents()

    def invoke(self,name):
        self.assertTrue(QMetaObject.invokeMethod(self.motion,name,Qt.DirectConnection))

    def test_record_press_and_quick_release_do_not_wait_for_animation(self):
        self.motion.setProperty('immediatePress',True)
        self.invoke('press')
        self.assertEqual(self.press.count(),1)
        self.assertGreater(self.motion.property('amount'),.9)
        self.invoke('release')
        self.assertEqual(self.release.count(),1)
        QTest.qWait(150)
        self.assertEqual((self.press.count(),self.release.count()),(1,1))

    def test_default_button_still_waits_for_its_visual_press(self):
        self.invoke('press')
        self.invoke('release')
        self.assertEqual((self.press.count(),self.release.count()),(0,0))
        QTest.qWait(150)
        self.assertEqual((self.press.count(),self.release.count()),(1,1))


if __name__=='__main__':unittest.main()
