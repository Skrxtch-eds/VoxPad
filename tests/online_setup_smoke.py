"""Exercise the actual EXE installer, native launcher, ASR and preserved data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(setup, archive, audio, online=False):
    with tempfile.TemporaryDirectory(prefix='online-setup-', dir=ROOT/'work') as temporary:
        target = Path(temporary)/'Установка с пробелами'/'VoxPad'
        (target/'data').mkdir(parents=True)
        sentinel = target/'data'/'keep.txt'
        sentinel.write_text('preserve user data', 'utf-8')
        invalid = Path(temporary)/'invalid.zip'
        invalid.write_bytes(b'invalid archive with a wrong SHA-256')
        def install_command(archive_path=None, *options):
            # NSIS /D is the final, unquoted argument and denotes the exact app root.
            command = f'"{setup}" /S /TESTMODE'
            if archive_path:
                command += f' /ARCHIVE="{archive_path}"'
            return command + ''.join(' ' + option for option in options) + f' /D={target}'

        rejected = subprocess.run(install_command(invalid), timeout=30)
        assert rejected.returncode == 1
        assert not (target/'current.txt').exists()
        assert sentinel.read_text('utf-8') == 'preserve user data'
        command = install_command(None if online else archive)
        subprocess.run(command, check=True, timeout=900)
        version = (target/'current.txt').read_text().strip()
        folder = target/'versions'/version
        preferences = target/'data/settings.json'
        assert json.loads(preferences.read_text('utf-8'))['autostart'] is True
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith('PYTHON')}
        clean['PATH'] = os.environ['SystemRoot'] + r'\System32'
        arguments = ['--smoke-test', '--tray', '--smoke-audio', str(audio)]
        subprocess.run([str(target/'VoxPad.exe'), *arguments], check=True, env=clean, timeout=120)
        deadline = time.monotonic() + 120
        report_file = folder/'smoke-test.json'
        while not report_file.exists() and time.monotonic() < deadline:
            time.sleep(.2)
        report = json.loads(report_file.read_text('utf-8'))
        assert report['ready'] and report['transcript'], report
        assert (target/'data'/'history.sqlite3').exists()
        assert not (folder/'data'/'history.sqlite3').exists()
        saved = json.loads(preferences.read_text('utf-8'))
        saved['ui_theme'] = 'dark'
        saved['microphone'] = 'test device'
        preferences.write_text(json.dumps(saved), 'utf-8')
        subprocess.run(install_command(archive, '/DESKTOP=0', '/STARTMENU=0', '/AUTOSTART=0'),
                       check=True, timeout=900)
        updated = json.loads(preferences.read_text('utf-8'))
        assert updated['autostart'] is False
        assert updated['ui_theme'] == 'dark' and updated['microphone'] == 'test device'
        assert sentinel.read_text('utf-8') == 'preserve user data'
        subprocess.run([str(target/'Uninstall.exe'), '/S'], check=True, timeout=90)
        deadline = time.monotonic() + 60
        while (target/'Uninstall.exe').exists() and time.monotonic() < deadline:
            time.sleep(.2)
        assert not (target/'versions').exists()
        assert not (target/'VoxPad.exe').exists()
        assert not (target/'Uninstall.exe').exists()
        assert sentinel.read_text('utf-8') == 'preserve user data'
        return dict(passed=True, version=version, online=online, transcript=report['transcript'],
                    checks=['wrong archive SHA-256 rejected without changing user data',
                            'actual NSIS setup', 'autostart enabled by default and switchable',
                            'other preferences preserved', 'native launcher with Cyrillic/spaces',
                            'bundled ASR', 'shared data root', 'reinstall preserves data',
                            'uninstall removes application and preserves data'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('setup', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('audio', type=Path)
    parser.add_argument('--online', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.setup.resolve(), args.archive.resolve(), args.audio.resolve(), args.online),
                     ensure_ascii=False, indent=2))
