"""User-selected source updates, hash validation and rollback on write failure."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import uuid
import zipfile

def install_package(archive, source, backups):
    source=Path(source).resolve(); backups=Path(backups).resolve()
    payload={}
    with zipfile.ZipFile(archive) as package:
        if sum(item.file_size for item in package.infolist())>5_000_000:
            raise ValueError('Update package is too large')
        manifest=json.loads(package.read('manifest.json'))
        version=str(manifest['version'])
        if not manifest.get('files'): raise ValueError('Empty update package')
        for name,digest in manifest['files'].items():
            is_source=Path(name).name==name and name.endswith('.py') and '/' not in name and '\\' not in name
            is_cue=name in ('assets/record-start.wav','assets/record-stop.wav','assets/voxpad.ico','assets/voxpad.png')
            if not (is_source or is_cue):
                raise ValueError('Invalid update filename')
            data=package.read(name)
            if hashlib.sha256(data).hexdigest()!=digest: raise ValueError('Update checksum mismatch: '+name)
            if is_source: compile(data,name,'exec')
            payload[name]=data
        if 'app.py' not in payload: raise ValueError('No app.py in update package')
    backup=backups/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True)
    written=[]
    try:
        for name,data in payload.items():
            path=source/name
            if source not in path.resolve().parents: raise ValueError('Invalid update destination')
            path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists():
                (backup/name).parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(path,backup/name)
            temporary=path.with_name(path.name+'.update')
            temporary.write_bytes(data); temporary.replace(path); written.append(name)
    except Exception:
        for name in written:
            path=source/name; old=backup/name
            if old.exists(): shutil.copy2(old,path)
            else: path.unlink(missing_ok=True)
        raise
    return version
