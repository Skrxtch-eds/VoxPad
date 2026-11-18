"""Render the real QML scene with isolated data and deterministic reference content."""
from datetime import datetime, timedelta
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/source'))
from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qt_controller import Controller
from qt_app import create_ui

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'work/qml-migration/screenshots'
OUT.mkdir(parents=True, exist_ok=True)
SAMPLES = ['Отправлю обновлённые\nмакеты сегодня\nдо конца дня.', 'Давайте обсудим детали\nна встрече.',
           'Запиши идею для нового\nпроекта.', 'Перезвоню позже.']


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    temp = tempfile.TemporaryDirectory(dir=ROOT / 'work', prefix='qml-capture-')
    controller = Controller(Path(temp.name), preview=True)
    for text in reversed(SAMPLES):
        controller.store.add(text, 68, .1)
    with closing(controller.store.connect()) as db:
        db.execute('UPDATE stats SET words=8640,dictations=128,audio_seconds=5040 WHERE id=1')
        db.execute('DELETE FROM daily_stats')
        today = datetime.now().astimezone().date()
        for index, words in enumerate([400, 620, 355, 470, 170, 390, 460]):
            db.execute('INSERT INTO daily_stats VALUES(?,?,?,?)', ((today-timedelta(days=6-index)).isoformat(), words, 7, 272))
        db.commit()
    controller._preferences.update(ui_theme='light', sounds=False, background_mode=True, microphone='Onboard MIC', autostart=True)
    controller._devices = ['Системный микрофон', 'Onboard MIC']
    controller._device_ids = [None, 1]
    controller.setText(SAMPLES[0])
    controller.refresh_data()
    warnings = []
    qInstallMessageHandler(lambda kind, context, message: (warnings.append(message), print(message, flush=True)))
    engine, window = create_ui(app, controller)
    window.resize(window.maximumSize())
    window.setPosition(100,50)
    def capture():
        window.grabWindow().save(str(OUT / (window.property('currentPage') + '.png')))
    def run():
        try:
            QTest.qWait(700)
            capture()
            for page in ('history','statistics','settings'):
                controller.navigate(page)
                QTest.qWait(1200)
                capture()
            controller.navigate('statistics')
            QTest.qWait(1200)
            p=window.findChild(QObject,'stage').mapToScene(QPointF(906,1140))
            QTest.mouseMove(window,QPoint(round(p.x()),round(p.y())))
            QTest.qWait(300)
            window.grabWindow().save(str(OUT/'statistics-tooltip.png'))
            print(json.dumps(dict(warnings=warnings, screenshots=str(OUT), windows=len(app.topLevelWindows())),ensure_ascii=False))
        finally:
            controller.confirmQuit()
    QTimer.singleShot(50,run)
    app.exec()
    temp.cleanup()


if __name__ == '__main__': main()
