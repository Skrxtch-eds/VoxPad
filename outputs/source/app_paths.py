"""Persistent application files stay beside the EXE, outside its bundled runtime."""
from pathlib import Path
import sys


def application_root():
    if getattr(sys,'frozen',False):return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]/'Transcriber'


BASE=application_root()
