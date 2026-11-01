"""Exercise the real installer in a disposable directory, without shortcuts/registry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(installer, audio):
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    report = {'checks': []}
    with tempfile.TemporaryDirectory(prefix='installer-test-', dir=work) as temporary:
        install = Path(temporary).resolve() / 'VoxPad тестовая установка'
        assert install.is_relative_to(work.resolve())
        # /D is the final, unquoted NSIS argument, including any spaces in its path.
        command = f'"{installer}" /S /TESTMODE /D={install}'
        subprocess.run(command, check=True, timeout=180)
        exe = install / 'VoxPad.exe'
        assert exe.is_file()
        assert (install / 'licenses/Python-LICENSE.txt').is_file()
        assert not (install / 'data').exists(), 'Installer must not contain a user profile'
        report['checks'].append('Silent installation in a path with spaces and Cyrillic')
        clean = {key: value for key, value in os.environ.items() if not key.upper().startswith('PYTHON')}
        clean['PATH'] = os.environ['SystemRoot'] + r'\System32;' + os.environ['SystemRoot']
        args = [str(exe), '--smoke-test', '--smoke-audio', str(audio)]
        subprocess.run(args, env=clean, check=True, timeout=90)
        smoke = json.loads((install / 'smoke-test.json').read_text('utf-8'))
        assert smoke['ready'] and smoke['frozen'] and smoke['transcript'], smoke
        assert Path(smoke['base']) == install and Path(smoke['executable']) == exe
        assert smoke['cue_bytes'] > 44
        report['runtime'] = smoke
        report['checks'].append('Bundled Python, Parakeet, PyAV, audio cue, Windows audio COM; no external Python paths')
        sentinel = install / 'data/installer-test.txt'
        sentinel.write_text('Keep my history and settings', encoding='utf-8')
        saved = {p.name: digest(p) for p in (install / 'data').iterdir() if p.is_file()}
        subprocess.run(command, check=True, timeout=180)
        assert all(digest(install / 'data' / name) == value for name, value in saved.items())
        report['checks'].append('Reinstallation preserves every user data file byte for byte')
        subprocess.run(f'"{install / "Uninstall.exe"}" /S _?={install}', check=True, timeout=90)
        assert not exe.exists() and not (install / '_internal').exists()
        assert all(digest(install / 'data' / name) == value for name, value in saved.items())
        report['checks'].append('Uninstallation removes runtime and bundled model, preserving user data')
        assert not any((install / 'models').rglob('*.onnx'))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    parser.add_argument('audio', type=Path, help='Public speech fixture; never a private recording')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = run(args.installer.resolve(), args.audio.resolve())
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
