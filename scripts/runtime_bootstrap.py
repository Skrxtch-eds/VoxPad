"""Plain-source entry point for the private Python runtime distribution."""
from pathlib import Path
import sys
import traceback


def main():
    directory=Path(__file__).resolve().parent
    sys._voxpad_portable_root=directory
    if (directory/'installed.flag').is_file() and directory.parent.name == 'versions':
        sys._voxpad_data_root=directory.parent.parent/'data'
        sys._voxpad_launcher=directory.parent.parent/'VoxPad.exe'
    sys.path.insert(0,str(directory/'app'))
    try:
        from app import main as run
        run()
    except Exception:
        report=directory/'data/startup-error.log'
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(traceback.format_exc(),encoding='utf-8')
        if sys.stderr:traceback.print_exc()
        if '--smoke-test' not in sys.argv:
            try:
                import ctypes
                dialog=ctypes.windll.user32.MessageBoxW
                dialog.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_uint]
                dialog.restype=ctypes.c_int
                dialog(None,'Не удалось запустить VoxPad. Подробности сохранены в:\n'+str(report),'VoxPad',0x10)
            except Exception:pass
        raise SystemExit(1)


if __name__=='__main__':main()
