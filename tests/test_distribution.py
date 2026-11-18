"""Packaging contracts after retiring the Tk runtime; no real builds or dialogs."""
import builtins
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_windows import version
from build_runtime_portable import copy_tree
import runtime_bootstrap


class DistributionTests(unittest.TestCase):
    def test_builder_reads_the_launcher_version_without_loading_the_ui(self):
        from app import VERSION
        self.assertEqual(version(),VERSION)

    def test_production_imports_do_not_load_a_second_ui_or_tray(self):
        command="import sys; import app,qt_app; assert not ({'tkinter','pystray','legacy_core','app_features'} & sys.modules.keys())"
        subprocess.run([sys.executable,'-c',command],cwd=ROOT/'outputs/source',check=True,capture_output=True,text=True,timeout=20)

    def test_runtime_copy_keeps_standard_library_and_omits_tk(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='.tmp-dist-') as temporary:
            root=Path(temporary)
            source=root/'source';target=root/'runtime'
            for name in ('json/__init__.py','ssl.py','tkinter/__init__.py','turtledemo/demo.py','turtle.py','_tkinter.pyd'):
                path=source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
            copy_tree(source,target)
            self.assertEqual(sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()),
                             ['json/__init__.py','ssl.py'])

    def test_startup_failure_keeps_a_log_and_uses_the_native_dialog(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests',prefix='.tmp-startup-') as temporary:
            root=Path(temporary)
            original_import=builtins.__import__
            def fail_app(name,*args,**kwargs):
                if name=='app':raise RuntimeError('fixture startup failure')
                return original_import(name,*args,**kwargs)
            with patch.object(runtime_bootstrap,'__file__',str(root/'launch.py')), \
                 patch.object(sys,'argv',['launch.py']),patch.object(sys,'path',sys.path.copy()), \
                 patch.object(sys,'_voxpad_portable_root',None,create=True), \
                 patch('builtins.__import__',side_effect=fail_app), \
                 patch('ctypes.windll.user32.MessageBoxW') as dialog,patch('runtime_bootstrap.traceback.print_exc'):
                with self.assertRaises(SystemExit) as stopped:runtime_bootstrap.main()
                self.assertEqual(stopped.exception.code,1)
                dialog.assert_called_once()
                self.assertIn('fixture startup failure',(root/'data/startup-error.log').read_text('utf-8'))


if __name__=='__main__':unittest.main()
