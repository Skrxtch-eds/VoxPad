"""Run the real .NET installer worker against small local payloads and HTTP errors."""
import configparser
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_online_setup import compile_exe, find_nsis, switch_images


class MissingDownload(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_error(404)

    def log_message(self, *args):
        pass


@unittest.skipUnless(sys.platform == 'win32', 'Windows .NET installer')
class SetupErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='voxpad-setup-tests-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.folder = Path(cls.temporary.name)
        cls.archive = cls.folder / 'VoxPad-0.0.0-Windows-x64-runtime.zip'
        with zipfile.ZipFile(cls.archive, 'w') as package:
            for name in ('runtime/pythonw.exe', 'launch.py', 'VoxPad.exe', 'BUILD-MANIFEST.json'):
                package.writestr('VoxPad/' + name, b'test fixture, not executable')
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), MissingDownload)
        thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)
        text = (ROOT / 'scripts/windows/Setup.cs').read_text('utf-8')
        text = (text.replace('@VERSION@', '0.0.0')
                .replace('@URL@', f'http://127.0.0.1:{cls.server.server_port}/runtime.zip')
                .replace('@SHA256@', hashlib.sha256(cls.archive.read_bytes()).hexdigest()))
        source = cls.folder / 'Setup.cs'
        source.write_text(text, 'utf-8-sig')
        cls.executable = cls.folder / 'InstallWorker.exe'
        compile_exe(source, cls.executable, console=True)

    def setUp(self):
        self.case = Path(tempfile.mkdtemp(dir=self.folder))
        self.target = self.case / 'Установка с пробелами' / 'VoxPad'
        self.summary = self.case / 'InstallError.ini'
        self.environment = {**os.environ, 'TEMP': str(self.case), 'TMP': str(self.case)}

    def worker(self, archive=None, **options):
        command = [str(self.executable), '--test-mode', '--target=' + str(self.target),
                   '--error-file=' + str(self.summary)]
        if archive is not None:
            command.append('--archive=' + str(archive))
        return subprocess.run(command, capture_output=True, timeout=30,
                              env=options.get('env', self.environment))

    def error(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(self.summary, encoding='utf-16')
        return parser['Error']

    def test_wrong_checksum_reports_actual_reason_in_utf16_summary(self):
        invalid = self.case / 'invalid.zip'
        invalid.write_bytes(b'invalid')
        result = self.worker(invalid)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Контрольная сумма ZIP не совпала', self.error()['Message'])
        self.assertIn('Этап: Проверка полного ZIP', self.error()['Message'])
        self.assertIn('IOException', (self.case / 'VoxPad-setup-error.log').read_text('utf-8'))
        self.assertFalse((self.target / 'current.txt').exists())

    def test_http_error_reports_status_and_offline_option(self):
        self.assertEqual(self.worker().returncode, 1)
        self.assertIn('HTTP 404', self.error()['Message'])
        self.assertIn('рядом с установщиком', self.error()['Message'])

    def test_existing_user_folder_is_preserved_and_reason_is_reported(self):
        self.target.mkdir(parents=True)
        sentinel = self.target / 'keep.txt'
        sentinel.write_text('user file', encoding='ascii')
        self.assertEqual(self.worker(self.archive).returncode, 1)
        self.assertIn('уже содержит файлы', self.error()['Message'])
        self.assertEqual(sentinel.read_text('ascii'), 'user file')

    def test_log_write_failure_does_not_hide_original_error(self):
        invalid = self.case / 'invalid.zip'
        invalid.write_bytes(b'invalid')
        not_a_folder = self.case / 'unwritable-temp'
        not_a_folder.write_bytes(b'file')
        result = self.worker(invalid, env={**self.environment, 'TMP': str(not_a_folder), 'TEMP': str(not_a_folder)})
        self.assertEqual(result.returncode, 1)
        self.assertIn('Контрольная сумма ZIP не совпала', self.error()['Message'])
        self.assertIn('Не удалось сохранить журнал', self.error()['Details'])

    def test_valid_local_archive_installs_and_preserves_data(self):
        (self.target / 'data').mkdir(parents=True)
        (self.target / 'data/settings.json').write_text('{"ui_theme":"dark"}', encoding='utf-8')
        self.assertEqual(self.worker(self.archive).returncode, 0)
        self.assertEqual((self.target / 'current.txt').read_text(), '0.0.0')
        self.assertEqual(json.loads((self.target / 'data/settings.json').read_text('utf-8'))['ui_theme'], 'dark')
        self.assertFalse(self.summary.exists())

    def compile_setup(self, worker, filename):
        try:
            compiler = find_nsis()
        except SystemExit:
            self.skipTest('NSIS compiler unavailable')
        switch_images(self.folder)
        setup = self.folder / filename
        subprocess.run([str(compiler), '/V2', '/INPUTCHARSET', 'UTF8', '/DVERSION=0.0.0',
                        f'/DWORKER={worker}', f'/DOUTPUT={setup}', f'/DASSETS={self.folder}',
                        f'/DICON={ROOT / "outputs/source/assets/voxpad.ico"}',
                        str(ROOT / 'scripts/OnlineSetup.nsi')], check=True, capture_output=True, timeout=60)
        return setup

    def test_nsis_automatically_uses_adjacent_zip_without_network(self):
        setup = self.compile_setup(self.executable, 'Setup.exe')
        # No /ARCHIVE argument: the production NSIS must discover the adjacent ZIP.
        result = subprocess.run(f'"{setup}" /S /TESTMODE /D={self.target}',
                                env=self.environment, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.target / 'current.txt').read_text(), '0.0.0')

    def test_nsis_records_worker_launch_failure_without_a_worker_log(self):
        invalid = self.case / 'not-an-executable.exe'
        invalid.write_bytes(b'test fixture that cannot be executed by Windows')
        setup = self.compile_setup(invalid, 'InvalidWorkerSetup.exe')
        result = subprocess.run(f'"{setup}" /S /TESTMODE /D={self.target}',
                                env=self.environment, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        self.assertFalse((self.case / 'VoxPad-setup-error.log').exists())
        logs = list(self.case.glob('VoxPad-setup-bootstrap-*.log'))
        self.assertEqual(len(logs), 1)
        self.assertIn('Worker result: error', logs[0].read_text('ascii'))
        self.assertFalse((self.target / 'current.txt').exists())


if __name__ == '__main__':
    unittest.main()
