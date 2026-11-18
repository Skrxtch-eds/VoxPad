"""Build a Windows launcher and a SHA-256 pinned online installer using .NET Framework."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

from build_windows import ROOT, SOURCE, version, checksum


def compile_exe(source, output):
    compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64',
                    '/reference:System.Windows.Forms.dll', '/reference:System.Drawing.dll',
                    '/reference:System.IO.Compression.dll', '/reference:System.IO.Compression.FileSystem.dll',
                    '/reference:Microsoft.CSharp.dll', '/win32icon:' + str(SOURCE/'assets/voxpad.ico'),
                    '/win32manifest:' + str(ROOT/'scripts/windows/application.manifest'),
                    '/out:' + str(output), str(source)], check=True)


def launcher(bundle):
    compile_exe(ROOT/'scripts/windows/Launcher.cs', bundle/'VoxPad.exe')


def build(archive):
    release = version()
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    url = f'https://github.com/Skrxtch-eds/VoxPad/releases/download/v{release}/{archive.name}'
    text = (ROOT/'scripts/windows/Setup.cs').read_text('utf-8')
    text = text.replace('@VERSION@', release).replace('@URL@', url).replace('@SHA256@', digest)
    generated = ROOT/'work'/f'Setup-{release}.cs'
    generated.write_text(text, 'utf-8-sig')
    output = ROOT/'outputs'/f'VoxPad-{release}-Setup-x64.exe'
    compile_exe(generated, output)
    checksum(output)
    print(output, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    build(parser.parse_args().archive.resolve())
