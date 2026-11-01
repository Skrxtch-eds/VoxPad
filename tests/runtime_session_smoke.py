"""Check normal tray and keyboard-hook startup with no audio capture or typing."""
import json
from pathlib import Path
import sys
import time
import tkinter as tk
from unittest.mock import Mock,patch


def run(directory):
    sys._voxpad_portable_root=directory
    sys.path.insert(0,str(directory/'app'))
    from app import App
    from storage import Store
    store=Store(directory/'data')
    store.save({'paused':True,'sounds':False,'auto_paste':False,'autostart':False})
    root=tk.Tk();root.withdraw()
    with patch('app_features.Store',return_value=store),patch('app_features.Engine',return_value=Mock()):
        app=App(root,smoke=False)
    try:
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            root.update()
            if app.engine and app.hotkey.hook and app.tray.ready.is_set():break
            time.sleep(.01)
        assert app.engine and app.hotkey.hook and app.tray.ready.is_set()
        assert app.paused and not app.recording and app.stream is None
        assert app.audio_input.cached is None
        assert not app.hotkey.enabled
        # Give real-time protection time to observe ordinary initialization.
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:root.update();time.sleep(.01)
        print(json.dumps({'normal_startup':True,'native_keyboard_hook':bool(app.hotkey.hook),
                          'tray_ready':app.tray.ready.is_set(),'audio_capture':False}),flush=True)
    finally:app.quit_app()


if __name__=='__main__':run(Path(sys.argv[1]).resolve())
