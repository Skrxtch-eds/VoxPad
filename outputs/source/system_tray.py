"""Windows tray integration; all Tk actions are queued to its main thread."""
import threading

from PIL import Image
import pystray
from branding import ASSETS


class SystemTray:
    def __init__(self, events):
        self.events = events
        self.ready = threading.Event()
        self.thread = None
        self.paused = False
        image = Image.open(ASSETS/'voxpad.png').convert('RGBA')
        self.icon = pystray.Icon('VoxPad', image,
                                'VoxPad. — правый Ctrl для диктовки', menu=pystray.Menu(
            pystray.MenuItem('Открыть', lambda icon, item: events.put(('tray_open', None)), default=True),
            pystray.MenuItem('Приостановить диктовку',lambda icon,item: events.put(('tray_pause',None)),checked=lambda item:self.paused),
            pystray.MenuItem('Настройки',lambda icon,item:events.put(('tray_settings',None))),
            pystray.MenuItem('История',lambda icon,item:events.put(('tray_history',None))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Выйти', lambda icon, item: events.put(('tray_exit', None))),
        ))

    def set_language(self, language):
        english=language=='en'
        names=['Open','Pause dictation','Settings','History','Exit'] if english else ['Открыть','Приостановить диктовку','Настройки','История','Выйти']
        actions=['tray_open','tray_pause','tray_settings','tray_history','tray_exit']
        self.icon.title='VoxPad. — dictation shortcuts' if english else 'VoxPad. — горячие клавиши'
        def callback(event):
            def invoke(icon,item): self.events.put((event,None))
            return invoke
        self.icon.menu=pystray.Menu(*[
            pystray.MenuItem(name,callback(event),
                            default=index==0,checked=(lambda item:self.paused) if index==1 else None)
            for index,(name,event) in enumerate(zip(names,actions))])
        self.icon.update_menu()

    def start(self):
        def setup(icon):
            icon.visible = True
            self.ready.set()
            self.events.put(('tray_ready', None))
        def run():
            try:
                self.icon.run(setup=setup)
            except Exception as error:
                self.events.put(('tray_error', str(error)))
            finally:
                self.ready.clear()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def close(self):
        self.icon.stop()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
