"""Check normal tray and keyboard-hook startup with no audio capture or typing."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import Mock,patch


def run(directory):
    sys._voxpad_portable_root=directory
    sys.path.insert(0,str(directory/'app'))
    from PySide6.QtCore import QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from qt_controller import Controller
    from qt_app import create_ui,create_tray
    from storage import Store
    store=Store(directory/'data')
    store.save({'paused':True,'sounds':False,'auto_paste':False,'autostart':False})
    qt=QApplication([]);qt.setQuitOnLastWindowClosed(False)
    with patch('qt_controller.Engine',return_value=Mock()):
        controller=Controller(directory/'data')
        engine,window=create_ui(qt,controller,hidden=True)
        tray=create_tray(qt,controller)
        failures=[]
        def verify():
            try:
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    QTest.qWait(10)
                    if controller.engine and controller.hotkey.hook and tray.isVisible():break
                assert controller.engine and controller.hotkey.hook and tray.isVisible()
                assert controller.paused and not controller.recording and controller.stream is None
                assert controller.audio_input.cached is None
                assert not controller.hotkey.enabled
                QTest.qWait(3000)
                print(json.dumps({'normal_startup':True,'native_keyboard_hook':bool(controller.hotkey.hook),
                                  'tray_ready':tray.isVisible(),'audio_capture':False,'ui':'Qt Quick'}),flush=True)
            except Exception as error:failures.append(error)
            finally:controller.confirmQuit()
        QTimer.singleShot(30,verify)
        qt.exec()
        if failures:raise failures[0]


if __name__=='__main__':run(Path(sys.argv[1]).resolve())
