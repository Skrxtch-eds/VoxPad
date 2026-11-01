"""Shared product identity and window icon."""
from pathlib import Path
from PIL import Image,ImageTk

ASSETS=Path(__file__).resolve().parent/'assets'

def apply_icon(window):
    root=window._root()
    if hasattr(root,'_voxpad_icons'):
        window._voxpad_icons=root._voxpad_icons
        return
    path=ASSETS/'voxpad.png'
    if path.exists():
        with Image.open(path) as source:
            # Give Tk the original PNG and individual high-DPI sizes instead of
            # allowing Windows to enlarge the legacy default 32-pixel ICO frame.
            sizes=(16,20,24,32,40,48,64,96,128,192,256,512)
            root._voxpad_icons=[ImageTk.PhotoImage(source.resize((size,size),Image.Resampling.LANCZOS),master=root)
                                  for size in sizes]
        window._voxpad_icons=root._voxpad_icons
        root.iconphoto(True,*root._voxpad_icons)
