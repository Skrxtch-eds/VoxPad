"""Verify hover/press/action ordering, unchanged colors, recording dots and compact layouts."""
from pathlib import Path
import json
import statistics
import sys
import tempfile
import time
from unittest.mock import Mock,patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from PySide6.QtCore import QObject,QPoint,QPointF,QTimer,Qt,qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qt_controller import Controller
from qt_app import create_ui,initial_window_size
from qt_window import ASPECT

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'work/qml-motion-qa'
OUT.mkdir(parents=True,exist_ok=True)


def main():
    app=QApplication([])
    app.setQuitOnLastWindowClosed(False)
    temporary=tempfile.TemporaryDirectory(dir=ROOT/'work',prefix='qml-motion-')
    c=Controller(Path(temporary.name),preview=True)
    c.setText('A draft that must survive theme changes.')
    warnings=[]
    notices=[]
    c.toastRequested.connect(notices.append)
    qInstallMessageHandler(lambda kind,context,message:warnings.append(message))
    engine,window=create_ui(app,c)
    frames=[]
    window.frameSwapped.connect(lambda:frames.append(time.perf_counter()))
    failures=[]
    result={}
    def visual_items(parent):
        yield parent
        for child in parent.childItems():yield from visual_items(child)
    def obj(name,parent=None):
        parent=parent or window
        found=parent.findChild(QObject,name)
        if found is None:
            for item in visual_items(window.contentItem()):
                if item.objectName()==name:return item
        assert found is not None,name
        return found
    def wait(predicate,seconds=4):
        until=time.perf_counter()+seconds
        while not predicate() and time.perf_counter()<until:QTest.qWait(2)
        assert predicate(),'state did not settle'
    def point(item):
        p=item.mapToScene(QPointF(item.width()/2,item.height()/2))
        return QPoint(round(p.x()),round(p.y()))
    def move(item=None):
        QTest.mouseMove(window,point(item) if item else QPoint(3,3))
    def capture(name):window.grabWindow().save(str(OUT/(name+'.png')))
    def page(name):
        c.navigate(name)
        wait(lambda:window.property('currentPage')==name)
        QTest.qWait(300)
    def check_hover(button):
        move();QTest.qWait(160)
        base=obj('buttonSurface',button) if button.objectName()!='soundsSwitch' else obj('switchSurface',button)
        before=base.property('fill')
        dimensions=(button.width(),button.height())
        move(button)
        wait(lambda:abs(button.scale()-1.03)<0.0001)
        assert base.property('fill')==before,'hover changed the fill'
        assert (button.width(),button.height())==dimensions,'hover changed layout dimensions'
        if base.property('castsShadow'):
            assert obj('restShadow',base).property('opacity')<.001
            assert obj('hoverShadow',base).property('opacity')>.999
        return base
    def run():
        try:
            QTest.qWait(450)
            native_id=int(window.winId())
            actual_size=(window.width(),window.height())
            assert actual_size==(initial_window_size(app.primaryScreen().availableGeometry().width(),app.primaryScreen().availableGeometry().height()).width(),
                                 initial_window_size(app.primaryScreen().availableGeometry().width(),app.primaryScreen().availableGeometry().height()).height())
            screen_checks=[]
            for width,height in [(1280,720),(1366,768),(1920,1080),(2560,1440),(3840,2160)]:
                for dpi in [1,1.25,1.5,2]:
                    available=(width/dpi,height/dpi-40)
                    size=initial_window_size(*available)
                    assert size.width()<=available[0]-23 and size.height()<=available[1]-23
                    assert abs(size.height()-size.width()/ASPECT)<=1
                    screen_checks.append(dict(screen=[width,height],scale=dpi,window=[size.width(),size.height()]))
            window.resize(600,783)
            QTest.qWait(250)
            for name in ['pauseButton','recordButton','settingsButton','copyTranscriptButton']:
                check_hover(obj(name))
            pause=obj('pauseButton')
            check_hover(pause)
            capture('hover-103-percent')
            old=c.paused
            calls=[]
            def state_changed():
                if c.paused!=old:calls.append(pause.scale())
            c.preferencesChanged.connect(state_changed)
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,point(pause))
            QTest.qWait(20)
            QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,point(pause))
            assert c.paused==old,'action ran before press return completed'
            QTest.qWait(20)
            assert c.paused==old,'fast click fired while still scaled'
            wait(lambda:c.paused!=old)
            assert calls and all(abs(scale-1)<.0001 for scale in calls),calls
            assert abs(pause.scale()-1)<.0001
            c.preferencesChanged.disconnect(state_changed)
            capture('pressed-100-percent')
            # A canceled click must never activate, including after the return finishes.
            move();QTest.qWait(150);check_hover(pause)
            old=c.paused
            QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,point(pause))
            move();QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,QPoint(3,3));QTest.qWait(180)
            assert c.paused==old
            pause.forceActiveFocus(Qt.TabFocusReason)
            QTest.keyClick(window,Qt.Key_Space)
            wait(lambda:c.paused!=old)
            move(pause)
            wait(lambda:abs(pause.scale()-1.03)<.0001)
            icon=obj('copyTranscriptButton')
            surface=check_hover(icon)
            assert not surface.property('bevel') and surface.property('fill').alphaF()==0
            assert not obj('keyboardFocusRing',icon).isVisible()
            # Recording changes only the icon area; there is no stop glyph or pulsing outline.
            move();QTest.qWait(180)
            c._preferences['paused']=False;c.preferencesChanged.emit();c.stateChanged.emit()
            record=obj('recordButton')
            wait(lambda:abs(record.opacity()-1)<.0001)
            record_surface=obj('buttonSurface',record)
            appearance=(record.width(),record.height(),record.opacity(),record_surface.property('fill'),record.property('cornerRadius'))
            c.started_at=time.perf_counter()
            c._set_phase('recording','Test recording')
            QTest.qWait(30)
            dots=obj('recordingDots')
            assert dots.isVisible() and record.property('glyph')==''
            assert appearance==(record.width(),record.height(),record.opacity(),record_surface.property('fill'),record.property('cornerRadius'))
            samples=[]
            for _ in range(14):
                samples.append([round(obj('recordingDot'+str(i)).property('lift'),2) for i in range(3)])
                QTest.qWait(40)
            assert all(any(row[i]>2 for row in samples) for i in range(3))
            assert any(abs(row[0]-row[1])>2 and abs(row[1]-row[2])>1 for row in samples)
            capture('recording-three-dots')
            c._set_phase('ready','Ready')
            QTest.qWait(40)
            assert not dots.isVisible()
            # Exercise a real QML hold click with fake capture/ASR, including release
            # before the visual press finishes. No clipboard or hardware is touched.
            c.audio_input.close()
            c.audio_input=Mock()
            c.audio_input.take.return_value=(Mock(),16000,0)
            c.audio_input.start.side_effect=lambda stream:c.audio_callback(np.full((1600,1),.1,dtype=np.float32),1600,None,None)
            c.audio_input.stop.side_effect=lambda stream:c.audio_callback(np.full((1600,1),.1,dtype=np.float32),1600,None,None)
            c.engine=Mock()
            c.engine.transcribe.return_value=('UI capture',.001)
            c._preferences['sounds']=True;c.preferencesChanged.emit()
            check_hover(record)
            with patch('qt_controller.copy_text'),patch('qt_controller.paste_if_focused',return_value=False), \
                 patch.object(c.audio_cues,'play') as cue:
                QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,point(record))
                cue.assert_called_once_with('start',50)
                QTest.qWait(15)
                QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,point(record))
                assert [call.args for call in cue.call_args_list]==[('start',50),('stop',50)]
                wait(lambda:c.engine.transcribe.call_count==1 and c.phase=='ready')
                assert len(c.engine.transcribe.call_args.args[0])==3200
                assert cue.call_count==2
            c.setText('A draft that must survive theme changes.')
            page('settings')
            theme_combo=obj('themeCombo')
            theme_options=theme_combo.property('model')
            if hasattr(theme_options,'toVariant'):theme_options=theme_options.toVariant()
            assert len(theme_options)==2
            switch=obj('soundsSwitch')
            check_hover(switch)
            old_sound=c.preferences['sounds']
            QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,point(switch))
            assert c.preferences['sounds']==old_sound
            wait(lambda:c.preferences['sounds']!=old_sound)
            assert abs(switch.scale()-1)<.0001
            shadows=[item for item in window.findChildren(QObject) if item.objectName()=='restShadow']
            assert len(shadows)>8
            assert len({item.property('blur') for item in shadows})==1
            light_alpha=shadows[0].property('color').alphaF()
            c.setSetting('ui_theme','dark')
            QTest.qWait(400)
            assert all(item.property('color').alphaF()>light_alpha for item in shadows)
            assert int(window.winId())==native_id and c.text=='A draft that must survive theme changes.'
            capture('settings-dark')
            c.setSetting('ui_theme','light')
            QTest.qWait(400)
            for width,height in [(391,510),(300,391),(600,783),
                                 (window.maximumWidth(),window.maximumHeight()),(383,500)]:
                window.resize(width,height)
                deadline=time.perf_counter()+3
                while abs(window.height()-window.width()/ASPECT)>1 and time.perf_counter()<deadline:
                    QTest.qWait(10)
                assert abs(window.height()-window.width()/ASPECT)<=1, (width,height,window.width(),window.height())
                for name in ['home','history','statistics','settings']:
                    page(name)
                    capture(f'{name}-{width}x{height}')
                    assert len(app.topLevelWindows())==1
                    stage=obj('stage')
                    top=stage.mapToScene(QPointF(61,78))
                    bottom=stage.mapToScene(QPointF(1039,1354))
                    assert top.x()>=-.01 and top.y()>=-.01
                    assert bottom.x()<=window.width()+.01 and bottom.y()<=window.height()+.01
            assert not warnings,warnings
            assert not notices,notices
            intervals=[(b-a)*1000 for a,b in zip(frames,frames[1:]) if .001<b-a<.05]
            result=dict(passed=True,initial_size=list(actual_size),screen_checks=screen_checks,
                        dpr=window.devicePixelRatio(),graphics_api=str(window.rendererInterface().graphicsApi()),
                        median_frame_ms=round(statistics.median(intervals),2),
                        p95_frame_ms=round(sorted(intervals)[int(len(intervals)*.95)],2),
                        action_scales=calls,dot_samples=samples,warnings=warnings,
                        checks=['exact hover 1.03','unchanged hover colors','smaller cached hover shadow',
                                'fast click waits for scale 1','canceled click does not activate','keyboard activation/hover recovery','flat icon has no frame',
                                'recording appearance unchanged','three sequential dots','QML immediate press/release cues and final audio block','two themes only',
                                'switch waits for return','uniform shadows/darker in dark theme',
                                'same HWND and draft','four complete pages at five portrait sizes','20 resolution/DPI combinations'])
        except Exception as error:
            import traceback
            failures.append(traceback.format_exc())
            result=dict(passed=False,error=str(error),traceback=failures[-1],warnings=warnings)
        finally:
            (OUT/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True)
            c.confirmQuit()
    QTimer.singleShot(50,run)
    app.exec()
    temporary.cleanup()
    if failures:raise SystemExit(1)


if __name__=='__main__':main()
