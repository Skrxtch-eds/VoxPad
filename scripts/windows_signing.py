"""Sign executable components before hashing; keep developer builds explicit."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from build_windows import ROOT

SCRIPT = ROOT / 'scripts/windows/sign.ps1'


def powershell():
    return shutil.which('pwsh.exe') or shutil.which('powershell.exe') or 'powershell.exe'


def run(mode, path=None, report=None, publisher=None):
    command = [powershell(), '-NoProfile', '-NonInteractive', '-File', str(SCRIPT), '-Mode', mode]
    if path is not None:
        command += ['-Path', str(Path(path).resolve())]
    if report is not None:
        command += ['-Report', str(Path(report).resolve())]
    if publisher is not None:
        command += ['-Publisher', publisher]
    subprocess.run(command, check=True)


def preflight(allow_unsigned=False):
    if allow_unsigned:
        print('UNSIGNED DEVELOPMENT BUILD: Smart App Control may block this build.', flush=True)
    else:
        run('Check')


def sign(path, allow_unsigned=False):
    if not allow_unsigned:
        run('Sign', path)


def prepare_nsis(compiler, allow_unsigned=False):
    """Sign private copies of NSIS plugins, which execute on the user's PC."""
    if allow_unsigned:
        return compiler
    destination = ROOT / 'work/signed-nsis'
    # A fresh copy prevents stale or modified plugins from entering another release.
    destination.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='nsis-', dir=destination))
    shutil.copytree(compiler.parent, folder, dirs_exist_ok=True)
    run('Sign', folder / 'Plugins/x86-unicode')
    return folder / compiler.name


def nsis_defines(allow_unsigned=False):
    if allow_unsigned:
        return []
    return [f'/DSIGN_POWERSHELL={powershell()}', f'/DSIGN_SCRIPT={SCRIPT}']


def verify_archive(archive):
    """Inspect actual release bytes rather than a potentially stale build folder."""
    with tempfile.TemporaryDirectory(prefix='voxpad-signatures-') as temporary:
        folder = Path(temporary)
        with zipfile.ZipFile(archive) as package:
            binaries = [entry for entry in package.infolist()
                        if Path(entry.filename).suffix.lower() in ('.exe', '.dll', '.pyd')]
            if not binaries or not any(entry.filename == 'VoxPad/VoxPad.exe' for entry in binaries):
                raise ValueError('Runtime archive must include VoxPad/VoxPad.exe.')
            # Flatten into unique names; ZIP member paths are never used as destinations.
            for index, entry in enumerate(binaries):
                (folder / f'{index:04d}{Path(entry.filename).suffix}').write_bytes(package.read(entry))
        run('Audit', folder)


def verify_release(archive, setup):
    verify_archive(archive)
    run('Audit', setup)


def verify_portable(archive):
    """Verify the source/CMD distribution without modifying upstream binaries."""
    python_files=('runtime/python.exe','runtime/pythonw.exe','runtime/python314.dll')
    with tempfile.TemporaryDirectory(prefix='voxpad-python-signatures-') as temporary:
        folder=Path(temporary)
        with zipfile.ZipFile(archive) as package:
            names=[entry.filename for entry in package.infolist() if not entry.is_dir()]
            if len(names)!=len(set(names)):
                raise ValueError('Duplicate files in portable archive.')
            manifest=json.loads(package.read('VoxPad/BUILD-MANIFEST.json'))
            if manifest.get('format')!='private-python-runtime' or manifest.get('entrypoint')!='VoxPad.cmd':
                raise ValueError('Expected a source distribution with VoxPad.cmd.')
            files=manifest['files']
            expected={'VoxPad/'+name for name in files}|{'VoxPad/BUILD-MANIFEST.json'}
            if set(names)!=expected:
                raise ValueError('Portable archive does not match its file manifest.')
            required={'VoxPad.cmd','launch.py','app/app.py',*python_files}
            if not required<=files.keys():
                raise ValueError('Required portable components are missing.')
            for name,digest in files.items():
                relative=Path(name)
                if (not relative.parts or relative.is_absolute() or relative.drive or '\\' in name or '..' in relative.parts or
                        relative.parts[0]=='data' or relative.name in ('settings.json','smoke-test.json') or
                        relative.suffix.lower() in ('.sqlite','.sqlite3','.db','.raw','.pfx','.p12','.key','.pem') or
                        (relative.suffix.lower() in ('.exe','.dll','.pyd') and relative.parts[0]!='runtime')):
                    raise ValueError('Unexpected file in source distribution: '+name)
                with package.open('VoxPad/'+name) as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=digest:
                        raise ValueError('Portable file hash mismatch: '+name)
            for name in python_files:
                (folder/Path(name).name).write_bytes(package.read('VoxPad/'+name))
        run('Audit',folder,publisher='Python Software Foundation')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--setup', type=Path)
    parser.add_argument('--portable',action='store_true',help='Verify CMD source distribution and original Python signatures')
    args = parser.parse_args()
    if args.portable:
        verify_portable(args.archive)
    elif args.setup:
        verify_release(args.archive, args.setup)
    else:
        parser.error('Use --portable or provide --setup.')
