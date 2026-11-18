"""Render all QML pages at the process's actual Qt device-pixel ratio."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from PySide6.QtCore import QObject,QPointF,QTimer,qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qt_controller import Controller
from qt_app import create_ui
from qt_window import ASPECT

ROOT=Path(__file__).resolve().parents[1]


def main():
    app=QApplication([]);app.setQuitOnLastWindowClosed(False)
    temp=tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='qml-dpi-')
    c=Controller(Path(temp.name),preview=True)
    c.setText('Responsive Qt Quick interface')
    warnings=[]
    qInstallMessageHandler(lambda kind,context,message:warnings.append(message))
    engine,window=create_ui(app,c)
    out=ROOT/'work/qml-motion-qa'/('dpi-'+str(window.devicePixelRatio()))
    out.mkdir(parents=True,exist_ok=True)
    result={};failed=[]
    def run():
        try:
            QTest.qWait(250)
            sizes=[]
            assert window.findChild(QObject,'windowPanel').property('radius')==72
            for width,height in [(391,510),(300,391),(600,783),(383,500)]:
                window.resize(width,height)
                deadline=time.perf_counter()+3
                while abs(window.height()-window.width()/ASPECT)>1 and time.perf_counter()<deadline:
                    QTest.qWait(10)
                QTest.qWait(100)
                assert abs(window.height()-window.width()/ASPECT)<=1, (width,height,window.width(),window.height())
                sizes.append([window.width(),window.height()])
                stage=window.findChild(QObject,'stage')
                top=stage.mapToScene(QPointF(61,78))
                bottom=stage.mapToScene(QPointF(1039,1354))
                assert top.x()>=-.01 and top.y()>=-.01
                assert bottom.x()<=window.width()+.01 and bottom.y()<=window.height()+.01
                for name in ['home','history','statistics','settings']:
                    c.navigate(name)
                    QTest.qWait(450)
                    assert window.property('currentPage')==name
                    picture=window.grabWindow()
                    picture.save(str(out/f'{name}-{width}x{height}.png'))
                    assert abs(picture.width()-window.width()*window.devicePixelRatio())<=1
                    assert abs(picture.height()-window.height()*window.devicePixelRatio())<=1
                    assert picture.pixelColor(0,0).alpha()==0
                    assert picture.pixelColor(picture.width()-1,picture.height()-1).alpha()==0
                    assert picture.pixelColor(picture.width()//2,3).alpha()>=250
                    assert picture.pixelColor(3,picture.height()//2).alpha()>=250
            c.setSetting('ui_theme','dark');QTest.qWait(400)
            window.grabWindow().save(str(out/'dark-portrait-window.png'))
            assert not warnings,warnings
            result=dict(passed=True,dpr=window.devicePixelRatio(),qt_scale_factor=os.environ.get('QT_SCALE_FACTOR'),
                        graphics_api=str(window.rendererInterface().graphicsApi()),warnings=warnings,
                        pages=4,sizes=sizes)
        except Exception as error:
            import traceback
            failed.append(str(error));result=dict(passed=False,error=traceback.format_exc(),warnings=warnings)
        finally:
            (out/'report.json').write_text(json.dumps(result,indent=2),'utf-8')
            print(json.dumps(result),flush=True);c.confirmQuit()
    QTimer.singleShot(20,run);app.exec();temp.cleanup()
    if failed:raise SystemExit(1)


if __name__=='__main__':main()
