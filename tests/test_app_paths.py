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


if __name__ == '__main__':
    unittest.main()
