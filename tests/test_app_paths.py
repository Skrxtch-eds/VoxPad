"""Source and frozen builds must use the same persistent data root."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'outputs/source'))
from app_paths import application_root
from platform_features import set_autostart


class ApplicationPaths(unittest.TestCase):
    def test_source_root(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(application_root(), Path(__file__).resolve().parents[1] / 'outputs/Transcriber')

    def test_frozen_root_uses_executable_not_internal_runtime(self):
        executable = Path(__file__).resolve().parent / 'install/VoxPad.exe'
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', str(executable)):
            self.assertEqual(application_root(), executable.parent)

    def test_frozen_autostart_uses_exe(self):
        import winreg
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', r'C:\VoxPad\VoxPad.exe'), \
             patch.object(winreg, 'CreateKey'), patch.object(winreg, 'SetValueEx') as write:
            set_autostart(True, r'C:\unused\Launch.vbs')
            self.assertEqual(write.call_args.args[-1], r'"C:\VoxPad\VoxPad.exe" --tray')

    def test_private_runtime_keeps_data_next_to_launcher(self):
        directory=Path(__file__).resolve().parent/'Папка с пробелами/VoxPad'
        with patch.object(sys,'frozen',False,create=True),patch.object(sys,'_voxpad_portable_root',directory,create=True):
            self.assertEqual(application_root(),directory.resolve())

    def test_private_runtime_autostart_preserves_paths_and_tray_argument(self):
        import subprocess,winreg
        directory=Path(__file__).resolve().parent/'Папка с пробелами/VoxPad'
        with patch.object(sys,'frozen',False,create=True),patch.object(sys,'_voxpad_portable_root',directory,create=True),\
             patch.object(winreg,'CreateKey'),patch.object(winreg,'SetValueEx') as write:
            set_autostart(True,r'C:\unused\Launch.vbs')
            self.assertEqual(write.call_args.args[-1],subprocess.list2cmdline([
                str(directory.resolve()/'runtime/pythonw.exe'),str(directory.resolve()/'launch.py'),'--tray']))


if __name__ == '__main__':
    unittest.main()
