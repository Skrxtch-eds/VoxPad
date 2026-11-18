"""Qt Quick integration checks, screenshots and measured animation frame intervals."""
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'outputs/source'))
from PySide6.QtCore import QObject, QPoint, QPointF, QTimer, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qt_app import create_ui
from qt_controller import Controller

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'work/qml-migration'


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    temp = tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='qml-integration-')
    c = Controller(Path(temp.name),preview=True)
    for i in range(20):
        c.store.add(f'Test transcript {i}',3,.1)
    with closing(c.store.connect()) as db, db:
        db.execute('UPDATE stats SET words=8640,dictations=128,audio_seconds=5040 WHERE id=1')
        db.execute('DELETE FROM daily_stats')
        for i,words in enumerate([400,620,355,470,0,390,460]):
            day=(datetime.now().astimezone().date()-timedelta(days=6-i)).isoformat()
            db.execute('INSERT INTO daily_stats VALUES(?,?,7,272)',(day,words))
    warnings=[]
    qInstallMessageHandler(lambda kind,context,message: warnings.append(message))
    engine,window=create_ui(app,c)
    window.requestActivate()
    frames=[]
    window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
    result={}
    failure=[]
    def obj(name):
        item=window.findChild(QObject,name)
        def find_visual(parent):
            if parent.objectName()==name:
                return parent
            for child in parent.childItems():
                found=find_visual(child)
                if found is not None:
                    return found
            return None
        if item is None:
            item=find_visual(window.contentItem())
        assert item is not None,name
        return item
    def wait(predicate,seconds=3):
        deadline=time.perf_counter()+seconds
        while not predicate() and time.perf_counter()<deadline:
            QTest.qWait(2)
        assert predicate(),'timeout waiting for QML state'
    def click(x,y):
        p=obj('stage').mapToScene(QPointF(x,y))
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,QPoint(round(p.x()),round(p.y())))
    def run():
        try:
            QTest.qWait(400)
            start=window.geometry()
            corner=QPoint(14,14)
            origin=window.mapToGlobal(corner)
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,corner)
            geometries=[]
            for dx,dy in [(-20,-30),(-50,-40),(-20,-30),(0,0)]:
                QTest.mouseMove(window,window.mapFromGlobal(origin+QPoint(dx,dy)))
                QTest.qWait(50)
                geometry=window.geometry()
                assert geometry.bottomRight()==start.bottomRight(), (start,geometry)
                geometries.append(geometry)
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,corner)
            first, larger, reversed_drag, returned=geometries
            assert start.width()<first.width()<larger.width(), geometries
            assert first==reversed_drag and returned==start, geometries
            assert window.geometry()==start, (start,window.geometry())
            window.resize(600,783)
            QTest.qWait(250)
            wait(lambda:len(c.daily)==7)
            c.setSetting('ui_theme','light')
            QTest.qWait(400)
            initial_id=int(window.winId())
            click(790,1230)
            wait(lambda:window.property('currentPage')=='statistics')
            assert obj('wordCounter').property('text')=='0'
            assert obj('dayBar0').property('height')==0
            wait(lambda:0<obj('statisticsPage').property('countProgress')<1)
            QTest.qWait(700)
            wait(lambda:obj('wordCounter').property('text')=='8 640')
            assert abs(obj('dayBar1').property('height')-190)<.1
            assert obj('dayBar4').property('height')==0
            click(905,1140)
            QTest.qWait(180)
            window.grabWindow().save(str(OUT/'smoke-statistics.png'))
            click(910,255)
            wait(lambda:window.property('currentPage')=='home')
            QTest.qWait(300)
            click(305,1230)
            wait(lambda:window.property('currentPage')=='history')
            QTest.qWait(300)
            assert obj('historyList').property('count')==20
            click(910,255)
            wait(lambda:window.property('currentPage')=='home')
            QTest.qWait(300)
            click(910,255)
            wait(lambda:window.property('currentPage')=='settings')
            QTest.qWait(300)
            old=c.preferences['sounds']
            click(930,601)
            wait(lambda:c.preferences['sounds']!=old)
            QTest.qWait(300)
            assert c.store.settings['sounds']==c.preferences['sounds']
            click(790,451)
            QTest.qWait(250)
            window.grabWindow().save(str(OUT/'smoke-dropdown.png'))
            assert len(app.topLevelWindows())==1
            click(790,587)
            wait(lambda:c.preferences['trigger_mode']=='toggle')
            click(790,993)
            QTest.qWait(250)
            click(790,1132)
            wait(lambda:c.preferences['ui_theme']=='dark')
            theme=obj('appTheme')
            QTest.qWait(140)
            middle=theme.property('ink').redF()
            assert 0.05<middle<0.92,middle
            window.grabWindow().save(str(OUT/'smoke-theme-midpoint.png'))
            QTest.qWait(250)
            assert theme.property('ink').redF()>0.9
            assert theme.property('primary').redF()>0.9
            assert int(window.winId())==initial_id
            window.grabWindow().save(str(OUT/'smoke-dark.png'))
            c.navigate('home')
            QTest.qWait(400)
            window.grabWindow().save(str(OUT/'smoke-dark-home.png'))
            c.navigate('settings')
            QTest.qWait(400)
            c.setSetting('ui_theme','light')
            QTest.qWait(200)
            window.resize(383,500)
            QTest.qWait(250)
            window.grabWindow().save(str(OUT/'smoke-compact.png'))
            window.resize(600,783)
            QTest.qWait(200)
            c.navigate('statistics')
            wait(lambda:window.property('currentPage')=='statistics')
            assert obj('wordCounter').property('text')=='0'
            frames.clear()
            QTest.qWait(950)
            assert int(window.winId())==initial_id
            assert len(app.topLevelWindows())==1
            intervals=[(b-a)*1000 for a,b in zip(frames,frames[1:]) if b-a<.1]
            result.update(passed=True,graphics_api=str(window.rendererInterface().graphicsApi()),
                          window_count=len(app.topLevelWindows()),warnings=warnings,
                          frame_count=len(frames),median_frame_ms=round(statistics.median(intervals),2),
                          p95_frame_ms=round(sorted(intervals)[int(len(intervals)*.95)],2),
                          checks=['corner drag and reversal','navigation','statistics zero/intermediate/final/reentry','independent bars/zero day',
                                  'chart tooltip','history','persisted toggle','in-window dropdown',
                                  'theme midpoint/final/inverted primary/same window','compact layout'])
            assert not warnings,warnings
        except Exception as error:
            import traceback
            failure.append(traceback.format_exc())
            result.update(passed=False,error=str(error),traceback=failure[0],warnings=warnings)
        finally:
            (OUT/'integration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True)
            c.confirmQuit()
    QTimer.singleShot(50,run)
    app.exec()
    temp.cleanup()
    if failure: raise SystemExit(1)


if __name__=='__main__':main()
