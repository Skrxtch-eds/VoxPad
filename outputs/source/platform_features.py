"""Windows autostart."""
import winreg
import sys
import subprocess
from pathlib import Path


def set_autostart(enabled, launcher):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            portable=getattr(sys,'_voxpad_portable_root',None)
            installed_launcher=getattr(sys,'_voxpad_launcher',None)
            if installed_launcher:
                command=subprocess.list2cmdline([str(installed_launcher),'--tray'])
            elif portable:
                directory=Path(portable).resolve()
                command=subprocess.list2cmdline([str(directory/'runtime/pythonw.exe'),str(directory/'launch.py'),'--tray'])
            else:
                command='"'+sys.executable+'" --tray' if getattr(sys,'frozen',False) else 'wscript.exe "'+str(Path(launcher).resolve())+'" --tray'
            winreg.SetValueEx(key,'ParakeetTranscriber',0,winreg.REG_SZ,command)
        else:
            try: winreg.DeleteValue(key,'ParakeetTranscriber')
            except FileNotFoundError: pass
