"""CPU policy selection/fallback tests without changing real process affinity."""
import ctypes
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs/source'))
import cpu_runtime as cpu
from engine import configured_cpu_profile


class FakeKernel:
    def __init__(self):self.mask=(1<<18)-1;self.changes=[]
    def GetCurrentProcess(self):return 123
    def GetProcessAffinityMask(self,process,current,system):
        ctypes.cast(current,ctypes.POINTER(ctypes.c_size_t)).contents.value=self.mask
        ctypes.cast(system,ctypes.POINTER(ctypes.c_size_t)).contents.value=(1<<18)-1
        return True
    def SetProcessAffinityMask(self,process,mask):
        self.changes.append(mask);self.mask=mask;return True


class CpuRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.kernel=FakeKernel();self.original=self.kernel.mask
        self.rows=[dict(group=0,logical=index,core=index//2,efficiency=1 if index<8 else 0) for index in range(18)]
        self.enterContext(patch.object(cpu,'windows_cpu_api',return_value=self.kernel))
        self.enterContext(patch.object(cpu,'cpu_rows',return_value=self.rows))
        self.enterContext(patch.object(cpu,'is_measured_cpu',return_value=True))
        self.enterContext(patch.object(cpu,'_initial_mask',None))

    def test_success_uses_discovered_pcores_and_removes_provider_file_after_load(self):
        with cpu.recognition_cpu('parakeet',cpu.MEASURED_THREADS) as selected:
            path=Path(selected.provider.removeprefix('cpu:'))
            self.assertEqual(selected.name,'125h_pcores_no_spin')
            self.assertEqual(selected.logical_cpus,tuple(range(8)))
            self.assertEqual(self.kernel.mask,255)
            self.assertIn('session.intra_op.allow_spinning=0',path.read_text('utf-8'))
        self.assertFalse(path.exists())
        self.assertEqual(self.kernel.mask,255)

    def test_failed_model_load_restores_previous_affinity(self):
        with self.assertRaisesRegex(RuntimeError,'load failed'):
            with cpu.recognition_cpu('parakeet',cpu.MEASURED_THREADS) as selected:
                path=Path(selected.provider.removeprefix('cpu:'))
                raise RuntimeError('load failed')
        self.assertFalse(path.exists())
        self.assertEqual(self.kernel.mask,self.original)

    def test_other_model_or_explicit_opt_out_restores_initial_mask(self):
        for model,enabled in (('whisper',True),('gigaam',True),('parakeet',False)):
            with cpu.recognition_cpu('parakeet',cpu.MEASURED_THREADS):pass
            self.assertEqual(self.kernel.mask,255)
            with cpu.recognition_cpu(model,2,enabled) as selected:
                self.assertEqual(selected.provider,'cpu')
                self.assertEqual(self.kernel.mask,self.original)

    def test_unmeasured_machine_and_thread_count_keep_standard_policy(self):
        with patch.object(cpu,'is_measured_cpu',return_value=False):
            with cpu.recognition_cpu('parakeet',cpu.MEASURED_THREADS) as selected:
                self.assertEqual(selected.name,'standard')
            self.assertEqual(cpu.default_threads('parakeet'),2)
        with cpu.recognition_cpu('parakeet',1) as selected:self.assertEqual(selected.name,'standard')
        self.assertEqual(self.kernel.changes,[])

    def test_user_restrictions_and_homogeneous_or_multigroup_topology_are_retained(self):
        self.assertIsNone(cpu.performance_mask(self.rows,1<<9,4))
        self.assertIsNone(cpu.performance_mask(self.rows,(1<<6)-1,4))
        self.assertIsNone(cpu.performance_mask([dict(group=0,logical=0,core=0,efficiency=0)],1,1))
        self.assertIsNone(cpu.performance_mask([dict(group=1,logical=0,core=0,efficiency=1)],1,1))
        self.kernel.mask=(1<<10)|(1<<12)
        with cpu.recognition_cpu('parakeet',cpu.MEASURED_THREADS) as selected:
            self.assertEqual(selected.name,'standard')
        self.assertEqual(self.kernel.changes,[])

    def test_provider_file_permission_failure_does_not_prevent_recognition(self):
        with patch.object(cpu.tempfile,'NamedTemporaryFile',side_effect=PermissionError('temp unavailable')):
            with cpu.recognition_cpu('parakeet',cpu.MEASURED_THREADS) as selected:
                self.assertEqual(selected.provider,'cpu')
        self.assertEqual(self.kernel.mask,self.original)

    def test_thread_override_can_disable_automatic_cpu_profile(self):
        with tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).parent) as directory:
            path=Path(directory)/'performance.json'
            self.assertTrue(configured_cpu_profile(path))
            for text,expected in (('{"threads":4}',True),('{"cpu_profile":"standard"}',False),('[]',False),('{broken',False)):
                path.write_text(text,'utf-8');self.assertEqual(configured_cpu_profile(path),expected)


if __name__=='__main__':unittest.main()
