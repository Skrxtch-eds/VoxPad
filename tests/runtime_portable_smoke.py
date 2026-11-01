"""Verify the unpacked private runtime without an external Python installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def run(archive,audio,session_check=True):
    with tempfile.TemporaryDirectory(prefix='runtime-test-',dir=ROOT/'work') as temporary:
        target=Path(temporary)/'Папка с пробелами'
        with zipfile.ZipFile(archive) as package:
            assert all((target/name).resolve().is_relative_to(target.resolve()) for name in package.namelist())
            assert not any(name.startswith('VoxPad/data/') for name in package.namelist())
            assert not any(name.endswith('/VoxPad.exe') for name in package.namelist())
            package.extractall(target)
        directory=target/'VoxPad'
        manifest=json.loads((directory/'BUILD-MANIFEST.json').read_text('utf-8'))
        assert manifest['format']=='private-python-runtime'
        for relative,expected in manifest['files'].items():
            path=directory/relative
            assert path.resolve().is_relative_to(directory.resolve())
            with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            assert actual==expected,relative
        clean={key:value for key,value in os.environ.items() if not key.upper().startswith('PYTHON')}
        clean['PATH']=os.environ['SystemRoot']+r'\System32;'+os.environ['SystemRoot']
        # A private runtime must ignore external environment settings as well.
        clean['PYTHONHOME']=str(target/'not-a-python-installation')
        clean['PYTHONPATH']=str(target/'untrusted-module-search-path')
        command=[str(directory/'runtime/python.exe'),'-I',str(directory/'launch.py'),'--smoke-test','--tray']
        if audio is not None:command.extend(('--smoke-audio',str(audio)))
        subprocess.run(command,
                       env=clean,cwd=temporary,check=True,timeout=120)
        report=json.loads((directory/'smoke-test.json').read_text('utf-8'))
        assert report['ready'] and report['portable_runtime'] and not report['frozen'],report
        if audio is not None:assert report['transcript'],report
        assert Path(report['base'])==directory
        assert Path(report['executable'])==directory/'runtime/python.exe'
        assert not (directory/'runtime/data').exists()
        if session_check:
            session=subprocess.run([str(directory/'runtime/python.exe'),'-I',str(ROOT/'tests/runtime_session_smoke.py'),
                                    str(directory)],env=clean,cwd=temporary,check=True,timeout=30,capture_output=True,text=True)
            report['normal_session']=json.loads(session.stdout.strip().splitlines()[-1])
        report['manifest_files_verified']=len(manifest['files'])
        report['version']=manifest['version']
        report['checks']=['Whole-archive integrity verified before launch','No PyInstaller executable',
                          'Cyrillic and spaces in paths; clean Windows PATH',
                          'Isolated imports ignore external PYTHONHOME and PYTHONPATH',
                          'Bundled model loads from the private runtime',
                          'Data root stays beside launcher instead of inside runtime']
        if audio is not None:report['checks'].append('Actual speech recognition and audio COM')
        if session_check:report['checks'].append('Normal startup with actual tray and native keyboard hook, without microphone capture')
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('audio',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--skip-session-check',action='store_true',help='For CI without a desktop session')
    args=parser.parse_args()
    result=run(args.archive.resolve(),args.audio.resolve(),not args.skip_session_check)
    if args.report:args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2))
