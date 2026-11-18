"""The production entry point: one Qt Quick window and a native Qt tray."""
import argparse
import ctypes
from pathlib import Path
import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app_paths import BASE, DATA
from qt_controller import Controller
from qt_window import WindowGeometry, portrait_size

SOURCE = Path(__file__).resolve().parent


def initial_window_size(available_width, available_height):
    """Fit the complete portrait panel in Qt logical screen pixels."""
    return portrait_size(available_width - 24, min(510, available_height - 24))


def create_ui(application, controller, *, hidden=False):
    QQuickStyle.setStyle('Basic')
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty('controller', controller)
    engine.rootContext().setContextProperty('startHidden', hidden)
    engine.load(QUrl.fromLocalFile(str(SOURCE / 'qml' / 'Main.qml')))
    if not engine.rootObjects():
        controller.confirmQuit()
        raise RuntimeError('Could not load the VoxPad QML interface')
    window = engine.rootObjects()[0]
    controller.window = window
    screen = application.primaryScreen().availableGeometry()
    size = initial_window_size(screen.width(), screen.height())
    window.resize(size)
    window.setProperty('resizeGeometry', WindowGeometry(window))
    window.setPosition(screen.x() + (screen.width() - window.width()) // 2,
                       screen.y() + (screen.height() - window.height()) // 2)
    return engine, window


def create_tray(application, controller):
    tray = QSystemTrayIcon(QIcon(str(SOURCE / 'assets' / 'voxpad.ico')), application)
    tray.setToolTip('VoxPad')
    menu = QMenu()
    for title, callback in [('Открыть', controller.open_window),
                            ('Приостановить диктовку', controller.togglePause),
                            ('Настройки', lambda: (controller.open_window(), controller.navigate('settings'))),
                            ('История', lambda: (controller.open_window(), controller.navigate('history')))]:
        action = QAction(title, menu)
        action.triggered.connect(callback)
        if title.startswith('Приостановить'):
            action.setCheckable(True)
            action.setChecked(controller.paused)
            controller.preferencesChanged.connect(lambda action=action: action.setChecked(controller.paused))
        menu.addAction(action)
    menu.addSeparator()
    action = menu.addAction('Выйти')
    action.triggered.connect(controller.requestQuit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: controller.open_window() if reason in
                           (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
    tray.show()
    controller.tray = tray
    controller._tray_menu = menu
    return tray


def single_instance():
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    mutex = kernel.CreateMutexW(None, False, 'Local\\ParakeetTranscriber')
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        request = DATA / 'show-window.request'
        request.parent.mkdir(parents=True, exist_ok=True)
        request.touch()
        return None
    return mutex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--smoke-audio', type=Path)
    parser.add_argument('--tray', action='store_true')
    parser.add_argument('--diagnostics', type=Path)
    parser.add_argument('--preview', action='store_true', help='Isolated UI preview; no ASR, microphone or global hook')
    parser.add_argument('--data-dir', type=Path, help='Alternate data directory for isolated testing')
    args = parser.parse_args()
    mutex = None
    if not args.smoke_test and not args.preview:
        mutex = single_instance()
        if mutex is None:
            return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('VoxPad.Desktop')
    except Exception:
        pass
    application = QApplication(sys.argv)
    application.setApplicationName('VoxPad')
    application.setOrganizationName('VoxPad')
    application.setWindowIcon(QIcon(str(SOURCE / 'assets' / 'voxpad.ico')))
    application.setQuitOnLastWindowClosed(False)
    directory = args.data_dir or (SOURCE.parents[1] / 'work' / 'qml-preview-data' if args.preview else None)
    controller = Controller(directory, preview=args.preview, smoke=args.smoke_test,
                            smoke_audio=args.smoke_audio, diagnostics=args.diagnostics)
    engine, window = create_ui(application, controller, hidden=args.tray or args.smoke_test)
    if not args.smoke_test and not args.preview:
        tray = create_tray(application, controller)
    if args.smoke_test:
        controller.smokeFinished.connect(lambda success: controller.confirmQuit())
    result = application.exec()
    if mutex:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(mutex))
    return result


if __name__ == '__main__':
    main()
