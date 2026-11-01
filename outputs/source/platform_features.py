"""Windows autostart and temporary system audio ducking."""
import winreg
import os
import sys
from pathlib import Path


def set_autostart(enabled, launcher):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            command='"'+sys.executable+'" --tray' if getattr(sys,'frozen',False) else 'wscript.exe "'+str(Path(launcher).resolve())+'" --tray'
            winreg.SetValueEx(key,'ParakeetTranscriber',0,winreg.REG_SZ,command)
        else:
            try: winreg.DeleteValue(key,'ParakeetTranscriber')
            except FileNotFoundError: pass

class TemporaryMute:
    def __init__(self):
        self.sessions={}
        self.active=False

    def begin(self):
        if self.active:return
        self.active=True
        try:self.refresh()
        except Exception:
            self.restore()
            raise

    def refresh(self):
        if not self.active:return
        from pycaw.pycaw import AudioUtilities
        for session in AudioUtilities.GetAllSessions():
            try:
                # Cue playback belongs to this process and must retain its volume.
                if session.ProcessId==os.getpid():continue
                identity=session.InstanceIdentifier
                if identity in self.sessions:continue
                volume=session.SimpleAudioVolume
                previous=float(volume.GetMasterVolume())
                volume.SetMasterVolume(previous*.2,None)
                self.sessions[identity]=(volume,previous)
            except Exception:
                # A session can disappear while another application is closing.
                continue

    def restore(self):
        self.active=False
        sessions=self.sessions;self.sessions={}
        for volume,previous in sessions.values():
            try:volume.SetMasterVolume(previous,None)
            except Exception:pass  # Already-closed sessions have nothing to restore.
