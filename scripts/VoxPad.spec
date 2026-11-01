# Build with Python 3.12 x64 and requirements-build.txt installed.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
source = root / 'outputs/source'
datas = [(str(source / 'assets'), 'assets')]
binaries = []
hiddenimports = ['pystray._win32']
for package in ('sherpa_onnx', 'av', '_sounddevice_data', 'pycaw', 'comtypes'):
    data, binary, hidden = collect_all(package, include_py_files=False,
                                      filter_submodules=lambda name: '.test' not in name,
                                      exclude_datas=['**/test/**', '**/tests/**'])
    datas += data
    binaries += binary
    hiddenimports += hidden

a = Analysis([str(source / 'app.py')], pathex=[str(source)],
             binaries=binaries, datas=datas, hiddenimports=hiddenimports,
             excludes=['matplotlib', 'pandas', 'IPython', 'pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='VoxPad',
          debug=False, strip=False, upx=False, console=False,
          icon=str(source / 'assets/voxpad.ico'),
          version=str(root / 'work/windows-build/version.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='VoxPad')
