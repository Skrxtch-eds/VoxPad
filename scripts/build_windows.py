"""Build an offline portable Windows folder or installer, without local user data."""
import argparse
import ast
import hashlib
from importlib import metadata
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'outputs/source'
MODEL_FOLDER = 'sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8'
MODEL_FILES = ('encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt')


def version():
    module = ast.parse((SOURCE / 'app_features.py').read_text('utf-8-sig'))
    return next(ast.literal_eval(node.value) for node in module.body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'VERSION' for t in node.targets))


def notices(bundle):
    target = bundle / 'licenses'
    target.mkdir(exist_ok=True)
    packages = ('numpy', 'scipy', 'Pillow', 'sherpa-onnx', 'sherpa-onnx-core',
                'sounddevice', 'soundfile', 'av', 'pystray', 'pycaw', 'comtypes',
                'cffi', 'pycparser', 'typing_extensions', 'psutil', 'six')
    lines = ['VoxPad: third-party components', '',
             'Parakeet TDT 0.6B v3 — NVIDIA, CC BY 4.0.',
             'Original weights: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3',
             'ONNX conversion / int8 quantization: sherpa-onnx contributors.',
             'https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models',
             'See licenses/parakeet-model-LICENSE.txt. No endorsement is implied.', '',
             'Python, Tcl/Tk and native library notices are also included in _internal.', '']
    shutil.copy2(ROOT / 'docs/licenses/parakeet-model-LICENSE.txt', target)
    for license_file in (ROOT / 'docs/licenses').glob('native-*'):
        shutil.copy2(license_file, target / license_file.name)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise SystemExit('Python LICENSE.txt is required for redistribution.')
    shutil.copy2(python_license, target / 'Python-LICENSE.txt')
    for name in packages:
        distribution = metadata.distribution(name)
        lines.append(f'{name} {distribution.version}')
        for file in distribution.files or ():
            if any('license' in part.lower() or 'copying' in part.lower() or 'notice' in part.lower()
                   for part in file.parts) and distribution.locate_file(file).is_file():
                relative = Path(name) / Path(*file.parts)
                if '..' in relative.parts:
                    continue
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(distribution.locate_file(file), destination)
    (bundle / 'THIRD-PARTY-NOTICES.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def build(args):
    if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
        raise SystemExit('Build on 64-bit Windows with 64-bit Python 3.12.')
    release = version()
    build_dir = ROOT / 'work/windows-build'
    build_dir.mkdir(parents=True, exist_ok=True)
    bundle = ROOT / 'work/windows-dist/VoxPad'
    compiler = None
    if args.format in ('installer','both'):
        compiler = Path(args.nsis).resolve() if args.nsis else shutil.which('makensis.exe')
        if not compiler or not Path(compiler).is_file():
            raise SystemExit('Install NSIS 3, or pass --nsis path/to/makensis.exe.')
    model = Path(args.model_dir).resolve() if args.model_dir else ROOT / 'outputs/Transcriber/models' / MODEL_FOLDER
    for name in MODEL_FILES:
        if not (model / name).is_file() or not (model / name).stat().st_size:
            raise SystemExit(f'Missing bundled model: {model / name}')
    (build_dir / 'version.txt').write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=" + repr(tuple(map(int, release.split('.'))) + (0,)) +
        ", prodvers=" + repr(tuple(map(int, release.split('.'))) + (0,)) +
        ", mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), "
        "kids=[StringFileInfo([StringTable('040904B0', [StringStruct('ProductName','VoxPad'), "
        "StringStruct('FileDescription','VoxPad'), StringStruct('FileVersion','" + release +
        "'), StringStruct('ProductVersion','" + release + "')])]), VarFileInfo([VarStruct('Translation',[1033,1200])])])",
        encoding='utf-8')
    if not args.skip_freeze:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                        '--distpath', str(bundle.parent), '--workpath', str(build_dir / 'pyinstaller'),
                        str(ROOT / 'scripts/VoxPad.spec')], check=True, cwd=ROOT)
    if not (bundle / 'VoxPad.exe').is_file():
        raise SystemExit('Frozen application not found.')
    destination = bundle / 'models' / MODEL_FOLDER
    destination.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        shutil.copy2(model / name, destination / name)
    notices(bundle)
    # Only the allowlisted model and the frozen runtime go into the installer.
    forbidden = [p for p in bundle.rglob('*') if p.is_file() and
                 (p.suffix in ('.sqlite3', '.raw') or p.name in ('settings.json', 'smoke-test.json'))]
    if forbidden:
        raise SystemExit(f'User data found in build directory: {forbidden}')
    if args.format in ('portable','both'):
        (bundle / 'START-HERE.txt').write_text(
            'VoxPad '+release+' — Windows 10/11 x64\n\n'
            '1. Извлеките ВСЮ папку VoxPad из ZIP в удобное место.\n'
            '2. Откройте VoxPad.exe. Установка и Python не нужны.\n'
            '3. Дождитесь готовности модели, зажмите правый Ctrl и говорите.\n\n'
            'Модель Parakeet уже включена; интернет для диктовки не нужен.\n'
            'Оставьте _internal, models и VoxPad.exe рядом. EXE нельзя переносить отдельно.\n'
            'Не запускайте EXE прямо внутри ZIP: сначала «Извлечь все».\n'
            'Настройки и история появятся в папке data рядом с EXE.\n'
            'Для обновления закройте VoxPad через значок в трее и замените файлы новой версии, сохранив data.\n\n'
            'Extract the entire VoxPad folder, then open VoxPad.exe. No installation or Python required.\n'
            'Keep _internal and models next to the EXE. User data is stored in data.\n', encoding='utf-8-sig')
        portable_folder = ROOT / 'outputs' / f'VoxPad-{release}-portable'
        shutil.copytree(bundle,portable_folder,dirs_exist_ok=True)
        output = ROOT / 'outputs' / f'VoxPad-{release}-Windows-x64-portable.zip'
        temporary = output.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for file in sorted(bundle.rglob('*')):
                if file.is_file():
                    archive.write(file,Path('VoxPad')/file.relative_to(bundle))
        temporary.replace(output)
        checksum(output)
        print(f'Created {output} ({output.stat().st_size / 1024**2:.1f} MiB)', flush=True)
    if compiler:
        output = ROOT / 'outputs' / f'VoxPad-{release}-Setup-x64.exe'
        subprocess.run([str(compiler), '/V2', '/INPUTCHARSET', 'UTF8',
                        f'/DVERSION={release}', f'/DBUNDLE={bundle}', f'/DOUTPUT={output}',
                        f'/DICON={SOURCE / "assets/voxpad.ico"}', str(ROOT / 'scripts/VoxPad.nsi')],
                       check=True, cwd=ROOT)
        checksum(output)
        print(f'Created {output} ({output.stat().st_size / 1024**2:.1f} MiB)', flush=True)


def checksum(output):
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format',choices=('portable','installer','both'),default='portable',
                        help='portable (default), installer, or both')
    parser.add_argument('--nsis', help='Path to the NSIS 3 makensis.exe compiler')
    parser.add_argument('--model-dir', help='Directory containing the four Parakeet model files')
    parser.add_argument('--skip-freeze', action='store_true', help='Reuse an existing frozen build')
    build(parser.parse_args())
