"""Right Ctrl hold-to-talk and automatic insertion for Windows."""
import ctypes
from ctypes import wintypes
import threading

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HANDLE
user32.CallNextHookEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
user32.GetForegroundWindow.restype = wintypes.HWND
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class Hotkey:
    def __init__(self, events):
        self.events = events
        self.enabled = True
        self.held = False
        self.pressed = set()
        self.swallowed = set()
        self.bindings = {'dictate': frozenset([0xA3])}
        self.active_action = None
        self.active_chord = frozenset()
        self.capture = False
        self.captured = set()
        self.hook = None
        self.thread_id = None
        self.callback = HOOKPROC(self._callback)
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _callback(self, code, message, address):
        if code >= 0:
            key = ctypes.cast(address, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if key.flags & 0x10:
                return user32.CallNextHookEx(self.hook, code, message, address)
            vk=key.vkCode
            if vk==0x11: vk=0xA3 if key.flags&1 else 0xA2
            if vk==0x12: vk=0xA5 if key.flags&1 else 0xA4
            if vk==0x10: vk=0xA1 if key.scanCode==0x36 else 0xA0
            down=message in (0x100,0x104)
            up=message in (0x101,0x105)
            repeated=vk in self.pressed
            if down: self.pressed.add(vk)
            if up: self.pressed.discard(vk)
            if self.capture:
                if down and vk==0x1B:
                    self.capture=False; self.captured.clear(); self.swallowed.add(vk)
                    self.events.put(('shortcut_cancel',None))
                    return 1
                if down: self.captured.add(vk); self.swallowed.add(vk)
                if up:
                    self.swallowed.discard(vk)
                    if not self.pressed and self.captured:
                        self.events.put(('shortcut_capture', sorted(self.captured)))
                        self.captured.clear(); self.capture=False
                return 1
            consumed=False
            if down and self.enabled:
                matches=[(name,chord) for name,chord in self.bindings.items()
                         if vk in chord and chord.issubset(self.pressed)]
                if matches:
                    action,chord=max(matches,key=lambda item:len(item[1]))
                    consumed=True; self.swallowed.add(vk)
                    if not repeated and (action!=self.active_action or not self.held):
                        self.active_action=action; self.active_chord=chord; self.held=True
                        self.events.put(('shortcut',{'action':action,'phase':'press','target':user32.GetForegroundWindow()}))
            if up:
                consumed=vk in self.swallowed; self.swallowed.discard(vk)
                if self.held and vk in self.active_chord:
                    self.events.put(('shortcut',{'action':self.active_action,'phase':'release','target':None}))
                    self.held=False; self.active_action=None; self.active_chord=frozenset()
            if consumed: return 1
        return user32.CallNextHookEx(self.hook, code, message, address)

    def _run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        self.hook = user32.SetWindowsHookExW(13, self.callback, kernel32.GetModuleHandleW(None), 0)
        if not self.hook:
            self.events.put(('hook_error', str(ctypes.WinError(ctypes.get_last_error()))))
            return
        try:
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(self.hook)
            self.hook = None

    def start(self):
        self.thread.start()

    def close(self):
        self.enabled = False
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x12, 0, 0)
        if self.thread.is_alive():
            self.thread.join(timeout=1)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ULONG_PTR)]


class INPUTUNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.OpenClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)


def copy_text(text, owner):
    """Publish Unicode immediately, before another app receives Ctrl+V."""
    data = (text + '\0').encode('utf-16-le')
    handle = kernel32.GlobalAlloc(0x0002, len(data))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    transferred = False
    opened = False
    try:
        address = kernel32.GlobalLock(handle)
        if not address:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(address, data, len(data))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(owner):
            raise ctypes.WinError(ctypes.get_last_error())
        opened = True
        if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        transferred = True  # Windows now owns the allocation.
    finally:
        if opened:
            user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(handle)


def paste_if_focused(target):
    if not target or user32.GetForegroundWindow() != target:
        return False
    # Do not synthesize a paste while a user-held modifier could change its action.
    if any(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        return False
    events = (INPUT * 4)()
    for item, (key, flags) in zip(events, ((0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2))):
        item.type = 1
        item.ki = KEYBDINPUT(key, 0, flags, 0, 0)
    return user32.SendInput(4, events, ctypes.sizeof(INPUT)) == 4

def press_enter_if_focused(target):
    if not target or user32.GetForegroundWindow()!=target:
        return False
    if any(user32.GetAsyncKeyState(k)&0x8000 for k in (0x10,0x11,0x12,0x5B,0x5C)):
        return False
    events=(INPUT*2)()
    for item,flags in zip(events,(0,2)):
        item.type=1; item.ki=KEYBDINPUT(0x0D,0,flags,0,0)
    return user32.SendInput(2,events,ctypes.sizeof(INPUT))==2
