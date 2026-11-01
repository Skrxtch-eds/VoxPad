import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
from updates import install_package


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent);self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.source=self.root/'source';self.source.mkdir()
        (self.source/'app.py').write_text("VERSION='old'\n",encoding='utf-8')

    def package(self,files,bad_hash=False):
        archive=self.root/'update.zip'
        manifest={'version':'test','files':{name:('0'*64 if bad_hash else hashlib.sha256(data).hexdigest()) for name,data in files.items()}}
        with zipfile.ZipFile(archive,'w') as package:
            for name,data in files.items():package.writestr(name,data)
            package.writestr('manifest.json',json.dumps(manifest))
        return archive

    def test_install_preserves_a_backup(self):
        archive=self.package({'app.py':b"VERSION='new'\n"})
        self.assertEqual(install_package(archive,self.source,self.root/'backups'),'test')
        self.assertIn('new',(self.source/'app.py').read_text())
        backups=list((self.root/'backups').glob('*/app.py'))
        self.assertEqual(len(backups),1)
        self.assertIn('old',backups[0].read_text())

    def test_invalid_checksum_does_not_modify_installation(self):
        archive=self.package({'app.py':b'pass\n'},bad_hash=True)
        with self.assertRaises(ValueError):install_package(archive,self.source,self.root/'backups')
        self.assertIn('old',(self.source/'app.py').read_text())

    def test_path_traversal_is_rejected(self):
        archive=self.package({'app.py':b'pass\n','../outside.py':b'pass\n'})
        with self.assertRaises(ValueError):install_package(archive,self.source,self.root/'backups')
        self.assertFalse((self.root/'outside.py').exists())
        self.assertIn('old',(self.source/'app.py').read_text())

    def test_invalid_python_is_rejected_before_any_write(self):
        archive=self.package({'app.py':b'pass\n','broken.py':b'def syntax error'})
        with self.assertRaises(SyntaxError):install_package(archive,self.source,self.root/'backups')
        self.assertIn('old',(self.source/'app.py').read_text())


if __name__=='__main__':unittest.main()
