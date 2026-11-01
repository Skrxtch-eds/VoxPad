"""Run the portable ZIP after extraction, with no external Python environment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def run(archive,audio):
    work=ROOT/'work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-test-',dir=work) as temporary:
        destination=Path(temporary).resolve()/'Папка без установки'
        destination.mkdir()
        with zipfile.ZipFile(archive) as package:
            names=package.namelist()
            assert 'VoxPad/VoxPad.exe' in names and 'VoxPad/START-HERE.txt' in names
            assert not any(name.startswith('VoxPad/data/') for name in names)
            assert all((destination/name).resolve().is_relative_to(destination) for name in names)
            package.extractall(destination)
        app=destination/'VoxPad'
        assert not (app/'data').exists()
        assert (app/'models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/encoder.int8.onnx').is_file()
        # Inspect the actual packaged module, not the development source tree.
        from PyInstaller.archive.readers import CArchiveReader
        frozen=CArchiveReader(str(app/'VoxPad.exe')).open_embedded_archive('PYZ.pyz')
        namespace={}
        exec(frozen.extract('text_processing'),namespace)
        spelling=namespace['normalize_transcript']('<unk>жик вс<unk> ещ<unk> жив<unk>т. Ёлка.')
        assert spelling=='Ёжик всё ещё живёт. Ёлка.',spelling
        clean={key:value for key,value in os.environ.items() if not key.upper().startswith('PYTHON')}
        clean['PATH']=os.environ['SystemRoot']+r'\System32;'+os.environ['SystemRoot']
        subprocess.run([str(app/'VoxPad.exe'),'--smoke-test','--tray','--smoke-audio',str(audio)],
                       check=True,timeout=90,env=clean,cwd=app)
        report=json.loads((app/'smoke-test.json').read_text('utf-8'))
        assert report['ready'] and report['frozen'] and report['transcript'],report
        assert Path(report['base'])==app and Path(report['executable'])==app/'VoxPad.exe'
        assert '<unk>' not in report['transcript'],report
        report['checks']=['Extract ZIP and run EXE without installation',
                          'Path with Cyrillic and spaces; data stored next to EXE',
                          'Bundled Python and Parakeet; no external Python environment',
                          'Real speech decoding and recognition; cues and Windows audio COM',
                          'Packaged normalizer: <unk> becomes ё/Ё; existing ё/Ё retained']
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('audio',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    result=run(args.archive.resolve(),args.audio.resolve())
    if args.report:args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)
