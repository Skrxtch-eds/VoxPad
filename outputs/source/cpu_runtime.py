"""Measured Parakeet CPU policy, scoped to the tested Core Ultra 5 125H.

Only this process is affected. CPU indices are discovered from Windows; no
power plan, system setting or other process is changed. Other machines/models
keep their existing placement. Model-load failure restores the previous mask.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
from pathlib import Path
import re
import tempfile
import threading

MEASURED_THREADS=4
_initial_mask=None
_policy_lock=threading.RLock()


def is_measured_cpu():
    if os.name!='nt':return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            name=winreg.QueryValueEx(key,'ProcessorNameString')[0]
        name=name.lower().replace('(tm)','').replace('(r)','')
        return bool(re.search(r'core\s+ultra\s+5\s+125h\b',name))
    except (OSError,ImportError):return False


def default_threads(model):
    return MEASURED_THREADS if model=='parakeet' and is_measured_cpu() else 2


def performance_mask(rows, allowed, threads):
    """Require enough distinct P-cores and retain the original allowed mask."""
    if not rows or any(row['group'] for row in rows):return None
    classes={row['efficiency'] for row in rows}
    if len(classes)<2:return None
    fastest=max(classes)
    cores=[row for row in rows if row['efficiency']==fastest and allowed & (1<<row['logical'])]
    if len({row['core'] for row in cores})<threads:return None
    return sum(1<<row['logical'] for row in cores)


def windows_cpu_api():
    if os.name!='nt':return None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.GetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
    kernel.GetProcessAffinityMask.restype=wintypes.BOOL
    kernel.SetProcessAffinityMask.argtypes=[wintypes.HANDLE,ctypes.c_size_t]
    kernel.SetProcessAffinityMask.restype=wintypes.BOOL
    kernel.GetSystemCpuSetInformation.argtypes=[ctypes.c_void_p,wintypes.ULONG,ctypes.POINTER(wintypes.ULONG),wintypes.HANDLE,wintypes.ULONG]
    kernel.GetSystemCpuSetInformation.restype=wintypes.BOOL
    return kernel


def cpu_rows(kernel,process):
    length=wintypes.ULONG()
    kernel.GetSystemCpuSetInformation(None,0,ctypes.byref(length),process,0)
    if not 0<length.value<1024*1024:return []
    data=ctypes.create_string_buffer(length.value)
    if not kernel.GetSystemCpuSetInformation(data,length,ctypes.byref(length),process,0):return []
    offset=0;rows=[]
    while offset+8<=length.value:
        size=ctypes.c_uint32.from_buffer(data,offset).value
        kind=ctypes.c_uint32.from_buffer(data,offset+4).value
        if size<8 or offset+size>length.value:return []
        if kind==0 and size>=32:
            flags=data.raw[offset+19]
            if not flags&2 or flags&4:  # Ignore CPUs reserved for another process.
                rows.append(dict(group=ctypes.c_uint16.from_buffer(data,offset+12).value,
                                 logical=data.raw[offset+14],core=data.raw[offset+15],
                                 efficiency=data.raw[offset+18]))
        offset+=size
    return rows


@dataclass(frozen=True)
class CpuConfiguration:
    provider:str='cpu'
    name:str='standard'
    logical_cpus:tuple=()


@contextmanager
def recognition_cpu(model,threads,enabled=True):
    global _initial_mask
    with _policy_lock:
        kernel=None;process=None;previous=None;temporary=None;configuration=CpuConfiguration()
        try:
            kernel=windows_cpu_api()
            if kernel:
                process=kernel.GetCurrentProcess()
                current=ctypes.c_size_t();system=ctypes.c_size_t()
                if kernel.GetProcessAffinityMask(process,ctypes.byref(current),ctypes.byref(system)):
                    previous=current.value
                    if _initial_mask is None:_initial_mask=previous
                    desired=_initial_mask
                    import sherpa_onnx
                    if enabled and model=='parakeet' and threads==MEASURED_THREADS and is_measured_cpu() and sherpa_onnx.__version__=='2.0.1':
                        mask=performance_mask(cpu_rows(kernel,process),_initial_mask,threads)
                        if mask:
                            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.config',prefix='voxpad-ort-',delete=False) as stream:
                                temporary=Path(stream.name)
                                stream.write('SessionConfig.session.intra_op.allow_spinning=0\nSessionConfig.session.inter_op.allow_spinning=0\n')
                            if kernel.SetProcessAffinityMask(process,mask):
                                desired=mask
                                configuration=CpuConfiguration('cpu:'+str(temporary),'125h_pcores_no_spin',
                                                               tuple(index for index in range(64) if mask&(1<<index)))
                    if desired!=previous and configuration.name=='standard':
                        kernel.SetProcessAffinityMask(process,desired)
        except (OSError,AttributeError,ValueError):
            if kernel and previous is not None:kernel.SetProcessAffinityMask(process,_initial_mask or previous)
            configuration=CpuConfiguration()
        try:
            yield configuration
        except BaseException:
            if kernel and previous is not None:kernel.SetProcessAffinityMask(process,previous)
            raise
        finally:
            if temporary:
                try:temporary.unlink(missing_ok=True)
                except OSError:pass
