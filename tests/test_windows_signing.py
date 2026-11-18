"""Release trust checks must cover inner binaries and fail before publishing."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_online_setup
import github_release
import windows_signing


class WindowsSigningTests(unittest.TestCase):
    def test_archive_checks_dlls_and_native_extensions_without_trusting_zip_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'runtime.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('VoxPad/VoxPad.exe', b'launcher')
                package.writestr('VoxPad/runtime/qt.dll', b'library')
                package.writestr('../../outside.pyd', b'extension')
                package.writestr('VoxPad/app/app.py', b'source')

            def audit(mode, folder):
                self.assertEqual(mode, 'Audit')
                self.assertEqual({p.suffix for p in folder.iterdir()}, {'.exe', '.dll', '.pyd'})
                self.assertEqual({p.read_bytes() for p in folder.iterdir()},
                                 {b'launcher', b'library', b'extension'})
                self.assertFalse((Path(temporary) / 'outside.pyd').exists())

            with patch.object(windows_signing, 'run', side_effect=audit) as check:
                windows_signing.verify_archive(archive)
            check.assert_called_once()

    def test_archive_requires_launcher(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'runtime.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('VoxPad/runtime/python.exe', b'fixture')
            with self.assertRaises(ValueError), patch.object(windows_signing, 'run') as check:
                windows_signing.verify_archive(archive)
            check.assert_not_called()

    def test_unsigned_release_fails_before_network_or_credentials(self):
        with patch.object(sys, 'argv', ['github_release.py', '--target', 'fixture', '--publish','--distribution','installer']), \
                patch.object(github_release, 'verify_release', side_effect=RuntimeError('unsigned')), \
                patch.object(github_release, 'request') as network:
            with self.assertRaisesRegex(RuntimeError, 'unsigned'):
                github_release.main()
            network.assert_not_called()

    def test_portable_rejects_modified_source_before_signature_checks(self):
        import hashlib
        import json
        with tempfile.TemporaryDirectory() as temporary:
            archive=Path(temporary)/'portable.zip'
            payload={'VoxPad.cmd':b'cmd','launch.py':b'launch','app/app.py':b'app',
                     'runtime/python.exe':b'python','runtime/pythonw.exe':b'pythonw','runtime/python314.dll':b'dll'}
            manifest={'format':'private-python-runtime','entrypoint':'VoxPad.cmd','version':'fixture',
                      'files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}}
            with zipfile.ZipFile(archive,'w') as package:
                package.writestr('VoxPad/BUILD-MANIFEST.json',json.dumps(manifest))
                for name,data in payload.items():
                    package.writestr('VoxPad/'+name,b'changed' if name=='app/app.py' else data)
            with patch.object(windows_signing,'run') as audit:
                with self.assertRaisesRegex(ValueError,'hash mismatch'):
                    windows_signing.verify_portable(archive)
                audit.assert_not_called()

    def test_portable_verifies_original_python_publisher(self):
        import hashlib
        import json
        with tempfile.TemporaryDirectory() as temporary:
            archive=Path(temporary)/'portable.zip'
            payload={'VoxPad.cmd':b'cmd','launch.py':b'launch','app/app.py':b'app',
                     'runtime/python.exe':b'python','runtime/pythonw.exe':b'pythonw','runtime/python314.dll':b'dll'}
            manifest={'format':'private-python-runtime','entrypoint':'VoxPad.cmd','version':'fixture',
                      'files':{name:hashlib.sha256(data).hexdigest() for name,data in payload.items()}}
            with zipfile.ZipFile(archive,'w') as package:
                package.writestr('VoxPad/BUILD-MANIFEST.json',json.dumps(manifest))
                for name,data in payload.items():package.writestr('VoxPad/'+name,data)
            with patch.object(windows_signing,'run') as audit:
                windows_signing.verify_portable(archive)
                self.assertEqual(audit.call_args.kwargs['publisher'],'Python Software Foundation')

    def test_setup_rejects_unsigned_payload_before_compiling_or_hashing(self):
        with patch.object(windows_signing, 'preflight'), \
                patch.object(build_online_setup, 'find_nsis', return_value=Path('makensis.exe')), \
                patch.object(windows_signing, 'verify_archive', side_effect=RuntimeError('unsigned payload')), \
                patch.object(build_online_setup, 'compile_exe') as compile_exe:
            with self.assertRaisesRegex(RuntimeError, 'unsigned payload'):
                build_online_setup.build(Path('payload.zip'))
            compile_exe.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'Windows Authenticode API')
    def test_preflight_fails_without_certificate_configuration(self):
        environment = {**os.environ, 'VOXPAD_SIGN_CERT_SHA1': ''}
        result = subprocess.run([windows_signing.powershell(), '-NoProfile', '-NonInteractive',
                                 '-File', str(windows_signing.SCRIPT), '-Mode', 'Check'],
                                env=environment, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'Trusted Code Signing is not configured', result.stderr)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows Authenticode API')
    def test_real_audit_rejects_unsigned_native_executable(self):
        compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
        if not compiler.is_file():
            self.skipTest('.NET Framework C# compiler unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'fixture.cs'
            source.write_text('class Fixture { static void Main() {} }', encoding='ascii')
            subprocess.run([str(compiler), '/nologo', '/out:' + str(folder / 'fixture.exe'), str(source)],
                           check=True, capture_output=True, timeout=30)
            report = folder / 'report.json'
            result = subprocess.run([windows_signing.powershell(), '-NoProfile', '-NonInteractive',
                                     '-File', str(windows_signing.SCRIPT), '-Mode', 'Audit',
                                     '-Path', str(folder), '-Report', str(report)],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('NotSigned', report.read_text('utf-8-sig'))

    @unittest.skipUnless(sys.platform == 'win32', 'NSIS Windows build')
    def test_nsis_signs_uninstaller_and_setup_and_stops_on_signing_failure(self):
        try:
            compiler = build_online_setup.find_nsis()
        except SystemExit:
            self.skipTest('NSIS compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='voxpad signing ') as temporary:
            folder = Path(temporary)
            hook = folder / 'sign fixture.ps1'
            calls = folder / 'calls.txt'
            # Exercise the real production NSIS finalizers, including quoted paths.
            hook.write_text('param($Mode, $Path)\n'
                            'if (!(Test-Path -LiteralPath $Path)) { exit 2 }\n'
                            'Add-Content -LiteralPath ($PSScriptRoot + "/calls.txt") -Value $Path\n',
                            encoding='utf-8')
            build_online_setup.switch_images(folder)
            command = [str(compiler), '/V2', '/INPUTCHARSET', 'UTF8', '/DVERSION=0.0.0',
                       f'/DWORKER={compiler}', f'/DOUTPUT={folder / "setup.exe"}',
                       f'/DASSETS={folder}', f'/DICON={ROOT / "outputs/source/assets/voxpad.ico"}',
                       f'/DSIGN_POWERSHELL={windows_signing.powershell()}', f'/DSIGN_SCRIPT={hook}',
                       str(ROOT / 'scripts/OnlineSetup.nsi')]
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, (result.stdout + result.stderr).decode(errors='replace'))
            self.assertEqual(len(calls.read_text('utf-8-sig').splitlines()), 2)
            hook.write_text('param($Mode, $Path)\nexit 1\n', encoding='utf-8')
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertNotEqual(result.returncode, 0, 'Failed signatures must stop NSIS')


if __name__ == '__main__':
    unittest.main()
