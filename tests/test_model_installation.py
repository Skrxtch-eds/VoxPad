"""Verified, cancellable and atomic Parakeet installation without network access."""
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
import model_manager as models


class ModelInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent,prefix='.tmp-model-')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.folder=self.root/models.MODELS['parakeet']['folder']
        self.cancel=threading.Event();self.progress=Mock()
        self.payloads={name:('fixture '+name).encode() for name in models.MODEL_FILES}
        manifest={name:(len(value),hashlib.sha256(value).hexdigest()) for name,value in self.payloads.items()}
        self.enterContext(patch.object(models,'MODEL_FILES',manifest))
        self.network=self.enterContext(patch.object(models,'urlopen',side_effect=lambda request,**kw:io.BytesIO(self.payloads[request.full_url.rsplit('/',1)[1]])))

    def test_complete_verified_model_is_published_once(self):
        models.download(self.root,'parakeet',self.cancel,self.progress)
        self.assertTrue(models.installed(self.root,'parakeet'))
        self.assertEqual(self.network.call_count,4)
        for name,value in self.payloads.items():self.assertEqual((self.folder/name).read_bytes(),value)
        self.assertFalse(list(self.root.glob('download-*')))
        models.download(self.root,'parakeet',self.cancel,self.progress)
        self.assertEqual(self.network.call_count,4)

    def test_incorrect_checksum_never_publishes_or_changes_partial_model(self):
        self.folder.mkdir();old=self.folder/'tokens.txt';old.write_bytes(b'old partial')
        self.payloads['encoder.int8.onnx']=b'x'*len(self.payloads['encoder.int8.onnx'])
        with self.assertRaisesRegex(ValueError,'checksum'):models.download(self.root,'parakeet',self.cancel,self.progress)
        self.assertEqual(old.read_bytes(),b'old partial')
        self.assertFalse(list(self.root.glob('download-*')))

    def test_incorrect_size_never_publishes(self):
        self.payloads['encoder.int8.onnx']+=b'oversized'
        with self.assertRaisesRegex(ValueError,'size'):models.download(self.root,'parakeet',self.cancel,self.progress)
        self.assertFalse(self.folder.exists())

    def test_cancelled_download_keeps_existing_user_files(self):
        other=self.root/'whisper/weights';other.parent.mkdir();other.write_bytes(b'user model')
        self.cancel.set()
        with self.assertRaises(InterruptedError):models.download(self.root,'parakeet',self.cancel,self.progress)
        self.network.assert_not_called();self.assertEqual(other.read_bytes(),b'user model')
        self.assertFalse(self.folder.exists())

    def test_repaired_installation_retains_old_partial_files(self):
        self.folder.mkdir();(self.folder/'user-note.txt').write_bytes(b'keep')
        models.download(self.root,'parakeet',self.cancel,self.progress)
        self.assertTrue(models.installed(self.root,'parakeet'))
        backups=list(self.root.glob('*.incomplete-*'));self.assertEqual(len(backups),1)
        self.assertEqual((backups[0]/'user-note.txt').read_bytes(),b'keep')

    def test_failed_publication_restores_partial_installation(self):
        self.folder.mkdir();(self.folder/'user-note.txt').write_bytes(b'keep')
        replace=models.os.replace
        def publish(source,destination):
            if Path(source).parent.name.startswith('download-'):raise OSError('publication failed')
            return replace(source,destination)
        with patch.object(models.os,'replace',side_effect=publish),self.assertRaises(OSError):
            models.download(self.root,'parakeet',self.cancel,self.progress)
        self.assertEqual((self.folder/'user-note.txt').read_bytes(),b'keep')

    def test_explicit_redownload_replaces_a_corrupt_complete_installation_safely(self):
        self.folder.mkdir()
        for name in self.payloads:(self.folder/name).write_bytes(b'corrupt but nonempty')
        self.assertTrue(models.installed(self.root,'parakeet'))
        models.download(self.root,'parakeet',self.cancel,self.progress,force=True)
        for name,value in self.payloads.items():self.assertEqual((self.folder/name).read_bytes(),value)
        backups=list(self.root.glob('*.incomplete-*'));self.assertEqual(len(backups),1)
        self.assertEqual((backups[0]/'tokens.txt').read_bytes(),b'corrupt but nonempty')


if __name__=='__main__':unittest.main()
