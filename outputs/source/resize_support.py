"""Keep Windows' native sizing loop independent of child-widget reflow."""
import ctypes as C
from ctypes import wintypes as W
import sys

u=C.WinDLL('user32',use_last_error=True)
LRESULT=C.c_ssize_t
WNDPROC=C.WINFUNCTYPE(LRESULT,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
u.GetParent.argtypes=[W.HWND];u.GetParent.restype=W.HWND
u.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];u.GetWindowLongPtrW.restype=C.c_void_p
u.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_void_p];u.SetWindowLongPtrW.restype=C.c_void_p
u.CallWindowProcW.argtypes=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.CallWindowProcW.restype=LRESULT
u.IsWindow.argtypes=[W.HWND];u.IsWindow.restype=W.BOOL
u.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.SendMessageW.restype=LRESULT
u.RedrawWindow.argtypes=[W.HWND,C.c_void_p,W.HANDLE,W.UINT];u.RedrawWindow.restype=W.BOOL
u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.GetClientRect.restype=W.BOOL
u.IsZoomed.argtypes=[W.HWND];u.IsZoomed.restype=W.BOOL
u.IsIconic.argtypes=[W.HWND];u.IsIconic.restype=W.BOOL
WM_WINDOWPOSCHANGED=0x0047
WM_ENTERSIZEMOVE=0x0231
WM_EXITSIZEMOVE=0x0232


class ResizeHandler:
    def __init__(self,window):
        self.window=window;self.sizing=False;self.deferred_count=0;self.frozen=[]
        self.hwnd=u.GetParent(window.winfo_id()) or window.winfo_id()
        self.client=window.winfo_id()
        self.original=u.GetWindowLongPtrW(self.hwnd,-4)
        if not self.original:raise C.WinError(C.get_last_error())
        self.callback=WNDPROC(self.dispatch)
        if not u.SetWindowLongPtrW(self.hwnd,-4,C.cast(self.callback,C.c_void_p)):
            raise C.WinError(C.get_last_error())
        window.bind('<Destroy>',self.close,add='+')

    def begin(self):
        if self.sizing:return
        self.sizing=True;self.frozen=[]
        u.SendMessageW(self.client,0x000B,0,0)  # WM_SETREDRAW
        # Keep the visible containers at their current client coordinates.
        # Windows continues to resize/move the frame and Tk keeps its geometry
        # records current, but hundreds of child widgets are laid out only once.
        for child in self.window.winfo_children():
            manager=child.winfo_manager()
            if manager!='pack':continue
            info=child.pack_info()
            rectangle=(child.winfo_x(),child.winfo_y(),child.winfo_width(),child.winfo_height())
            self.frozen.append((child,info))
            child.pack_forget();child.place(x=rectangle[0],y=rectangle[1],width=rectangle[2],height=rectangle[3])

    def finish(self):
        self.sizing=False
        area=W.RECT();u.GetClientRect(self.hwnd,C.byref(area))
        frozen,self.frozen=self.frozen,[]
        for child,info in frozen:
            if child.winfo_exists():child.place_forget();child.pack(**info)
        if u.IsWindow(self.client):
            u.SendMessageW(self.client,0x000B,1,0)
            u.RedrawWindow(self.client,None,None,0x0001|0x0080|0x0400)
        # WM_SETREDRAW may suppress Tk's size notification when the client and
        # wrapper are the same HWND. Commit the real final client dimensions.
        if not u.IsZoomed(self.hwnd) and not u.IsIconic(self.hwnd) and area.right>0 and area.bottom>0:
            if (self.window.winfo_width(),self.window.winfo_height())!=(area.right,area.bottom):
                self.window.geometry(f'{area.right}x{area.bottom}')

    def dispatch(self,hwnd,message,wparam,lparam):
        try:return self._dispatch(hwnd,message,wparam,lparam)
        except Exception:
            # Never let a Python exception escape through a native WNDPROC.
            self.sizing=False
            if u.IsWindow(self.client):u.SendMessageW(self.client,0x000B,1,0)
            self.window._root().report_callback_exception(*sys.exc_info())
            return u.CallWindowProcW(self.original,hwnd,message,wparam,lparam) if u.IsWindow(hwnd) else 0

    def _dispatch(self,hwnd,message,wparam,lparam):
        if message==WM_ENTERSIZEMOVE:self.begin()
        elif message==WM_WINDOWPOSCHANGED and self.sizing:self.deferred_count+=1
        elif message==WM_EXITSIZEMOVE:
            result=u.CallWindowProcW(self.original,hwnd,message,wparam,lparam)
            self.finish()
            return result
        return u.CallWindowProcW(self.original,hwnd,message,wparam,lparam)

    def close(self,event):
        if event.widget==self.window and u.IsWindow(self.hwnd):
            u.SetWindowLongPtrW(self.hwnd,-4,self.original)
            self.sizing=False;self.frozen=[]


def attach(window):
    if not hasattr(window,'_resize_handler'):
        window._resize_handler=ResizeHandler(window)
