"""Build a native launcher and NSIS setup with a SHA-256 pinned download worker."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import shutil

from build_windows import ROOT, SOURCE, version, checksum
import windows_signing


def compile_exe(source, output, *, console=False):
    compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(compiler), '/nologo', '/target:' + ('exe' if console else 'winexe'), '/platform:x64',
                    '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
                    '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
                    '/reference:Microsoft.CSharp.dll', '/win32icon:' + str(SOURCE/'assets/voxpad.ico'),
                    '/reference:System.Web.Extensions.dll',
                    '/win32manifest:' + str(ROOT/'scripts/windows/application.manifest'),
                    '/out:' + str(output), str(source)], check=True)


def launcher(bundle):
    compile_exe(ROOT/'scripts/windows/Launcher.cs', bundle/'VoxPad.exe')


def find_nsis(explicit=None):
    candidates = [explicit, shutil.which('makensis.exe'),
                  ROOT/'work/tools/nsis-3.13/makensis.exe',
                  Path('C:/Program Files (x86)/NSIS/makensis.exe'),
                  Path('C:/Program Files/NSIS/makensis.exe')]
    for path in candidates:
        if path and Path(path).is_file():
            return Path(path).resolve()
    raise SystemExit('Install NSIS 3, or pass --nsis path/to/makensis.exe.')


def switch_images(folder):
    """Small code-drawn controls using the application's monochrome palette."""
    from PIL import Image, ImageDraw
    for enabled in (False, True):
        image = Image.new('RGB', (224, 112), '#f7f7f9')
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((4, 4, 220, 108), radius=52,
                               fill='#111111' if enabled else '#d1d1d3')
        left = 120 if enabled else 16
        draw.ellipse((left, 16, left+80, 96), fill='#ffffff')
        image.save(folder/f'switch-{int(enabled)}.bmp')


def build(archive, nsis=None, allow_unsigned=False, output=None):
    windows_signing.preflight(allow_unsigned)
    compiler = find_nsis(nsis)
    if not allow_unsigned:
        # An unsigned payload cannot be repaired by signing its outer installer.
        windows_signing.verify_archive(archive)
    compiler = windows_signing.prepare_nsis(compiler, allow_unsigned)
    release = version()
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    url = f'https://github.com/Skrxtch-eds/VoxPad/releases/download/v{release}/{archive.name}'
    text = (ROOT/'scripts/windows/Setup.cs').read_text('utf-8')
    text = text.replace('@VERSION@', release).replace('@URL@', url).replace('@SHA256@', digest)
    generated = ROOT/'work'/f'Setup-{release}.cs'
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(text, 'utf-8-sig')
    worker = ROOT/'work'/f'VoxPad-{release}-InstallWorker.exe'
    compile_exe(generated, worker, console=True)
    windows_signing.sign(worker, allow_unsigned)
    switch_images(ROOT/'work')
    output = Path(output).resolve() if output else ROOT/'outputs'/f'VoxPad-{release}-Setup-x64.exe'
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(compiler), '/V3', '/INPUTCHARSET', 'UTF8',
                    *windows_signing.nsis_defines(allow_unsigned),
                    f'/DVERSION={release}', f'/DWORKER={worker}', f'/DOUTPUT={output}',
                    f'/DASSETS={ROOT / "work"}', f'/DICON={SOURCE / "assets/voxpad.ico"}',
                    str(ROOT/'scripts/OnlineSetup.nsi')], check=True, cwd=ROOT)
    checksum(output)
    print(output, flush=True)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--nsis', help='Path to the NSIS 3 makensis.exe compiler')
    parser.add_argument('--allow-unsigned', action='store_true', help='Development only; may be blocked by Smart App Control')
    parser.add_argument('--output', type=Path, help='Separate output path, e.g. for a diagnostic build')
    args = parser.parse_args()
    build(args.archive.resolve(), args.nsis, args.allow_unsigned, args.output)
