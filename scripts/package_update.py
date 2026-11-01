"""Build the source update without importing the application or its dependencies."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'outputs/source'


def build():
    module=ast.parse((SOURCE/'app_features.py').read_text('utf-8-sig'))
    version=next(ast.literal_eval(node.value) for node in module.body
                 if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets))
    paths=sorted(SOURCE.glob('*.py'))+[SOURCE/'assets'/name for name in ('record-start.wav','record-stop.wav','voxpad.ico','voxpad.png')]
    manifest={'version':version,'files':{}}
    target=ROOT/'outputs'/f'VoxPad-{version}-update.zip'
    temporary=target.with_suffix('.zip.tmp')
    try:
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as package:
            for path in paths:
                data=path.read_bytes();name=path.relative_to(SOURCE).as_posix()
                if path.suffix=='.py':compile(data,name,'exec')
                manifest['files'][name]=hashlib.sha256(data).hexdigest();package.writestr(name,data)
            package.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(f'{target.name}: {len(paths)} files, {target.stat().st_size:,} bytes')
    return target


if __name__=='__main__':build()
