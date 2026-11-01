"""Distribute auditable sources and an unmodified private Python runtime."""
import argparse
import base64
import hashlib
from importlib import metadata
import json
from pathlib import Path
import shutil
import sys
import zipfile

from build_windows import ROOT,SOURCE,MODEL_FOLDER,MODEL_FILES,version,notices,checksum

PACKAGES=('numpy','scipy','Pillow','sherpa-onnx','sherpa-onnx-core','sounddevice','soundfile','av',
          'pystray','pycaw','comtypes','cffi','pycparser','typing_extensions','psutil','six')
SKIP={'__pycache__','tests','test'}


def package_files():
    """Verify wheel RECORD hashes before copying third-party code or binaries."""
    result={};versions={}
    for name in PACKAGES:
        distribution=metadata.distribution(name)
        versions[name]=distribution.version
        base=Path(distribution.locate_file('')).resolve()
        for file in distribution.files or ():
            path=Path(distribution.locate_file(file)).resolve()
            if not path.is_relative_to(base):continue  # Ignore build-time CLI entry points.
            relative=path.relative_to(base)
            if any(part in SKIP for part in relative.parts):continue
            if not path.is_file():raise ValueError('Missing dependency file: '+str(file))
            if file.hash:
                digest=hashlib.new(file.hash.mode,path.read_bytes()).digest()
                value=base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
                if value!=file.hash.value:raise ValueError('Dependency RECORD mismatch: '+str(file))
            if path.suffix not in ('.pyc','.pyo'):result[relative]=path
    return result,versions


def copy_tree(source,target):
    for path in source.rglob('*'):
        relative=path.relative_to(source)
        if any(part in SKIP or part in ('site-packages','idlelib','ensurepip') for part in relative.parts):continue
        if path.is_file() and path.suffix not in ('.pyc','.pyo'):
            destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,destination)


def build(args):
    if sys.platform!='win32' or sys.version_info[:2]!=(3,12) or sys.maxsize<=2**32:
        raise SystemExit('Build with 64-bit Python 3.12 on Windows.')
    files,versions=package_files()
    release=version()
    bundle=ROOT/'work'/('runtime-dist-'+release)/'VoxPad'
    if bundle.exists():raise SystemExit('Use a fresh version or output directory: '+str(bundle))
    runtime=bundle/'runtime';runtime.mkdir(parents=True)
    base=Path(sys.base_prefix)
    # Copy the original executables and DLLs verbatim, retaining their signatures.
    for name in ('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt'):
        shutil.copy2(base/name,runtime/name)
    for name in ('Lib','DLLs','tcl'):copy_tree(base/name,runtime/name)
    for relative,path in files.items():
        destination=runtime/'Lib/site-packages'/relative
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)
    # Isolate imports from installed Python, the registry, PYTHONPATH and the cwd.
    (runtime/'python312._pth').write_text('Lib\nDLLs\nLib/site-packages\n../app\nimport site\n',encoding='ascii')
    app=bundle/'app';app.mkdir()
    for path in SOURCE.glob('*.py'):shutil.copy2(path,app/path.name)
    shutil.copytree(SOURCE/'assets',app/'assets')
    shutil.copy2(ROOT/'scripts/runtime_bootstrap.py',bundle/'launch.py')
    (bundle/'VoxPad.cmd').write_bytes(b'@echo off\r\nstart "" "%~dp0runtime\\pythonw.exe" -I "%~dp0launch.py" %*\r\n')
    (bundle/'VoxPad-debug.cmd').write_bytes(b'@echo off\r\n"%~dp0runtime\\python.exe" -I "%~dp0launch.py" %*\r\nif errorlevel 1 pause\r\n')
    model=Path(args.model_dir) if args.model_dir else ROOT/'outputs/Transcriber/models'/MODEL_FOLDER
    destination=bundle/'models'/MODEL_FOLDER;destination.mkdir(parents=True)
    for name in MODEL_FILES:
        if not (model/name).is_file():raise ValueError('Missing model: '+name)
        shutil.copy2(model/name,destination/name)
    notices(bundle)
    (bundle/'START-HERE.txt').write_text(
        'VoxPad '+release+' — Windows 10/11 x64\n\n'
        '1. Закройте старый VoxPad через значок в трее.\n'
        '2. Извлеките всю папку VoxPad из ZIP.\n'
        '3. Откройте VoxPad.cmd. Python и установка не нужны.\n\n'
        'В этой сборке используется отдельный Python и открытые файлы приложения.\n'
        'Папки runtime, app и models должны оставаться рядом с VoxPad.cmd.\n'
        'Настройки и история хранятся в data. Для переноса скопируйте data из старой версии.\n'
        'Дополнительные модели можно перенести в models.\n'
        'При ошибке запуска используйте VoxPad-debug.cmd; подробности — data/startup-error.log.\n'
        'Не отключайте антивирус и не добавляйте исключения для запуска программы.\n',encoding='utf-8-sig')
    for path in bundle.rglob('*'):
        if path.is_file() and (path.suffix in ('.sqlite3','.raw') or path.name in ('settings.json','smoke-test.json')):
            raise ValueError('User data in distribution: '+str(path))
    manifest={'version':release,'format':'private-python-runtime','python':sys.version.split()[0],
              'dependencies':versions,'files':{}}
    for path in sorted(bundle.rglob('*')):
        if path.is_file():
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            manifest['files'][path.relative_to(bundle).as_posix()]=digest
    (bundle/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
    print('Bundle prepared: '+str(bundle),flush=True)
    if not args.no_archive:
        archive=ROOT/'outputs'/f'VoxPad-{release}-Windows-x64-runtime.zip'
        temporary=archive.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as package:
            for path in sorted(bundle.rglob('*')):
                if path.is_file():package.write(path,Path('VoxPad')/path.relative_to(bundle))
        temporary.replace(archive);checksum(archive)
        print('Archive prepared: '+str(archive),flush=True)
    return bundle


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir',type=Path)
    parser.add_argument('--no-archive',action='store_true')
    build(parser.parse_args())
