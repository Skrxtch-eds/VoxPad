"""Non-activating, click-through Windows glass recording indicator."""
import ctypes as C
from ctypes import wintypes as W
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

u = C.WinDLL('user32', use_last_error=True)
g = C.WinDLL('gdi32', use_last_error=True)
u.GetForegroundWindow.restype = W.HWND
for name, args, result in (
    ('CreateWindowExW', [W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p], W.HWND),
    ('GetDC',[W.HWND],W.HDC), ('ReleaseDC',[W.HWND,W.HDC],C.c_int),
    ('DestroyWindow',[W.HWND],W.BOOL), ('ShowWindow',[W.HWND,C.c_int],W.BOOL),
    ('SetWindowPos',[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT],W.BOOL),
    ('MonitorFromWindow',[W.HWND,W.DWORD],W.HANDLE),
):
    f=getattr(u,name); f.argtypes=args; f.restype=result
g.CreateCompatibleDC.argtypes=[W.HDC]; g.CreateCompatibleDC.restype=W.HDC
g.SelectObject.argtypes=[W.HDC,W.HANDLE]; g.SelectObject.restype=W.HANDLE
g.DeleteObject.argtypes=[W.HANDLE]; g.DeleteDC.argtypes=[W.HDC]
g.BitBlt.argtypes=[W.HDC,C.c_int,C.c_int,C.c_int,C.c_int,W.HDC,C.c_int,C.c_int,W.DWORD]
g.BitBlt.restype=W.BOOL

class MonitorInfo(C.Structure):
    _fields_=[('size',W.DWORD),('monitor',W.RECT),('work',W.RECT),('flags',W.DWORD)]

class BitmapHeader(C.Structure):
    _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),
              ('bits',W.WORD),('compression',W.DWORD),('image_size',W.DWORD),
              ('xppm',W.LONG),('yppm',W.LONG),('used',W.DWORD),('important',W.DWORD)]

class Blend(C.Structure):
    _fields_=[('operation',C.c_ubyte),('flags',C.c_ubyte),('alpha',C.c_ubyte),('format',C.c_ubyte)]

u.GetMonitorInfoW.argtypes=[W.HANDLE,C.POINTER(MonitorInfo)]
g.CreateDIBSection.argtypes=[W.HDC,C.POINTER(BitmapHeader),W.UINT,C.POINTER(C.c_void_p),W.HANDLE,W.DWORD]
g.CreateDIBSection.restype=W.HBITMAP
u.UpdateLayeredWindow.argtypes=[W.HWND,W.HDC,C.POINTER(W.POINT),C.POINTER(W.SIZE),W.HDC,
                               C.POINTER(W.POINT),W.DWORD,C.POINTER(Blend),W.DWORD]
u.UpdateLayeredWindow.restype=W.BOOL


def capture_backdrop(x,y,width,height):
    """Copy just the indicator region, without reading the whole desktop."""
    screen=u.GetDC(None);memory=g.CreateCompatibleDC(screen)
    bits=C.c_void_p();header=BitmapHeader(40,width,-height,1,32,0,0,0,0,0,0)
    bitmap=g.CreateDIBSection(screen,C.byref(header),0,C.byref(bits),None,0)
    if not bitmap:
        g.DeleteDC(memory);u.ReleaseDC(None,screen)
        raise C.WinError(C.get_last_error())
    old=g.SelectObject(memory,bitmap)
    try:
        if not g.BitBlt(memory,0,0,width,height,screen,x,y,0x00CC0020):
            raise C.WinError(C.get_last_error())
        return Image.frombytes('RGB',(width,height),C.string_at(bits,width*height*4),'raw','BGRX')
    finally:
        g.SelectObject(memory,old);g.DeleteObject(bitmap);g.DeleteDC(memory);u.ReleaseDC(None,screen)

class RecordingOverlay:
    width, height, margin, scale = 234, 117, 20, 1
    fps = 60
    vertical_padding = 15
    backdrop_blur_mix = .60  # 20% stronger than the previous .50 mix.
    edge_refraction = 20.4   # 70% stronger than the previous 12px displacement.

    def __init__(self, root, get_level):
        self.root, self.get_level = root, get_level
        self.hwnd = u.CreateWindowExW(0x080800A8,'STATIC','Recording capsule',0x80000000,
                                      0,0,320,180,None,None,None,None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.visible=False
        self.closed=False
        self.job=None
        self.amount=0.
        self.level=0.
        self.glass=None
        self.last_tick=time.perf_counter()

    def prepare(self, target):
        info=MonitorInfo(); info.size=C.sizeof(info)
        monitor=u.MonitorFromWindow(target,2)
        if not u.GetMonitorInfoW(monitor,C.byref(info)):
            raise C.WinError(C.get_last_error())
        rect=info.work
        self.x=(rect.left+rect.right-self.width)//2
        self.y=rect.bottom-self.height-36
        # Capture only the small area behind the indicator; never saved or uploaded.
        backdrop=capture_backdrop(self.x,self.y,self.width,self.height)
        self.prepare_surface(backdrop)

    def prepare_surface(self,backdrop):
        """Shared real/preview renderer. No microphone or window capture here."""
        s=self.scale; w,h=self.width*s,self.height*s
        backdrop=backdrop.resize((w,h),Image.Resampling.BICUBIC)
        backdrop=Image.blend(backdrop,backdrop.filter(ImageFilter.GaussianBlur(13*s)),self.backdrop_blur_mix)
        pixels=np.asarray(backdrop)
        gx,gy=np.meshgrid(np.arange(w),np.arange(h))
        px,py=gx-w/2,gy-h/2
        dx=px-np.clip(px,-(w-h)/2,(w-h)/2)
        radius=np.maximum(np.hypot(dx,py),1)
        inset=np.maximum(0,h/2-radius)
        bevel=np.exp(-inset/(5.5*s))
        sx=np.clip(np.rint(gx-dx/radius*self.edge_refraction*s*bevel-px*.035).astype(int),0,w-1)
        sy=np.clip(np.rint(gy-py/radius*self.edge_refraction*s*bevel-py*.035).astype(int),0,h-1)
        lens=pixels[sy,sx].astype(float)*.975+255*.025
        shine=np.exp(-((inset-2*s)/(1.3*s))**2)*np.clip(-py/radius*.65-dx/radius*.3+.2,0,1)*53
        # A brighter, broader reflection follows the upper curved surface.
        upper=np.clip(-py/radius,0,1)**2
        crown=np.exp(-((inset-3*s)/(2.5*s))**2)*upper*68
        soft_gloss=np.exp(-((inset-7*s)/(5*s))**2)*upper*13
        lens+=(shine+crown+soft_gloss)[:,:,None]
        mask_large=Image.new('L',(w*4,h*4)); d=ImageDraw.Draw(mask_large)
        d.rounded_rectangle((1,1,w*4-2,h*4-2),radius=h*2,fill=255)
        self.mask=mask_large.resize((w,h),Image.Resampling.LANCZOS)
        self.glass=Image.fromarray(np.uint8(np.clip(lens,0,255))).convert('RGBA')
        self.glass.putalpha(self.mask)
        d=ImageDraw.Draw(self.glass)
        d.rounded_rectangle((s,s,w-s-1,h-s-1),radius=h/2,outline=(245,251,255,150),width=s)
        self.started=time.perf_counter()
        self.last_tick=self.started
        # Cache everything static so higher FPS does not repeat glass/shadow work.
        self.v=np.linspace(0,1,w,dtype=np.float32)
        self.sin_envelope=np.maximum(0,np.sin(np.pi*self.v))
        self.env=self.sin_envelope**3.2
        self.mask_values=np.asarray(self.mask,dtype=np.float32)/255.
        self.static_frame=Image.new('RGBA',((self.width+40)*s,(self.height+40)*s))
        shadow=Image.new('RGBA',self.static_frame.size)
        ImageDraw.Draw(shadow).rounded_rectangle((20*s,26*s,(20+self.width)*s,(26+self.height)*s),radius=h/2,fill=(0,0,0,55))
        self.static_frame.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9*s)))
        self.static_frame.alpha_composite(self.glass,(20*s,20*s))

    def show(self, target=None):
        if self.closed: return
        if not self.visible:
            self.prepare(target)
            # Be clearly visible in the first frame, then settle over ~110 ms.
            self.amount=.5; self.level=0.
            self.last_tick=time.perf_counter()
        self.visible=True
        if self.job is not None:self.root.after_cancel(self.job)
        self.tick()

    def hide(self):
        self.visible=False

    def render(self, t, amp):
        s=self.scale; w,h=self.width*s,self.height*s
        xs=np.arange(w); v=self.v; env=self.env
        ratio=self.width/280.
        alpha=Image.new('L',(w,h)); d=ImageDraw.Draw(alpha)
        if amp<.01:
            d.line((0,h/2,w,h/2),fill=255,width=round(1.3*s))
        else:
            center=h/2+amp*28*s*ratio*env*np.sin(2*np.pi*(v*1.2-t*.56))
            thick=(.65*s+amp*24*s*env*(.55+.45*np.sin(np.pi*v*1.65-t*.9)**2))*ratio
            d.polygon(list(zip(xs,center-thick))+list(zip(xs[::-1],(center+thick)[::-1])),fill=255)
            sigma=7.5*s*ratio*amp*self.sin_envelope**2.2
            radii=np.array([0,1,2.5,4.5,7.5])*s
            layers=[np.asarray(alpha if r==0 else alpha.filter(ImageFilter.GaussianBlur(float(r))),dtype=np.float32) for r in radii]
            out=np.zeros((h,w),dtype=np.float32)
            for i in range(4):
                sel=(sigma>=radii[i])&(sigma<=radii[i+1])
                weight=np.clip((sigma-radii[i])/(radii[i+1]-radii[i]),0,1)
                mixed=layers[i]*(1-weight)+layers[i+1]*weight
                out[:,sel]=mixed[:,sel]
            alpha=Image.fromarray(np.uint8(out))
        # Fit the entire visible wave, including its blur, inside the safe band.
        padding=math.ceil(self.vertical_padding*s)
        bounds=alpha.getbbox()
        if bounds:
            extent=max(h/2-bounds[1],bounds[3]-h/2)
            allowed=h/2-padding
            if extent>allowed:
                new_height=max(1,min(h-2*padding,math.floor(h*allowed/extent)))
                compressed=alpha.resize((w,new_height),Image.Resampling.BICUBIC)
                alpha=Image.new('L',(w,h))
                alpha.paste(compressed,(0,(h-new_height)//2))
        # Resampling cannot place any alpha outside this exact 15px boundary.
        safe=np.asarray(alpha,dtype=np.float32).copy()
        safe[:padding,:]=0
        safe[h-padding:,:]=0
        alpha=Image.fromarray(np.uint8(safe*self.mask_values))
        color=getattr(self,'wave_color','#FFFFFF')
        white=Image.new('RGBA',(w,h),color); white.putalpha(alpha)
        frame=self.static_frame.copy()
        frame.alpha_composite(white,(20*s,20*s))
        return frame.resize((self.width+40,self.height+40),Image.Resampling.LANCZOS)

    def present(self, image, opacity):
        w,h=image.size
        arr=np.asarray(image).copy()
        arr[:,:,:3]=(arr[:,:,:3].astype(np.uint16)*arr[:,:,3,None]//255).astype(np.uint8)
        data=arr[:,:,[2,1,0,3]].tobytes()
        dc=u.GetDC(None); memory=g.CreateCompatibleDC(dc)
        bits=C.c_void_p(); header=BitmapHeader(40,w,-h,1,32,0,0,0,0,0,0)
        bitmap=g.CreateDIBSection(dc,C.byref(header),0,C.byref(bits),None,0)
        if not bitmap:
            g.DeleteDC(memory); u.ReleaseDC(None,dc)
            raise C.WinError(C.get_last_error())
        old=g.SelectObject(memory,bitmap)
        try:
            C.memmove(bits,data,len(data))
            position=W.POINT(self.x-20,self.y-20+round((1-opacity)*12))
            size=W.SIZE(w,h); origin=W.POINT(0,0); blend=Blend(0,0,round(255*opacity),1)
            if not u.UpdateLayeredWindow(self.hwnd,dc,C.byref(position),C.byref(size),memory,C.byref(origin),0,C.byref(blend),2):
                raise C.WinError(C.get_last_error())
            u.SetWindowPos(self.hwnd,W.HWND(-1),0,0,0,0,0x13)
            u.ShowWindow(self.hwnd,4)  # SW_SHOWNOACTIVATE: keep the input field focused.
        finally:
            g.SelectObject(memory,old); g.DeleteObject(bitmap); g.DeleteDC(memory); u.ReleaseDC(None,dc)

    def tick(self):
        self.job=None
        if self.closed: return
        now=time.perf_counter()
        dt=min(.1,max(0.,now-self.last_tick))
        self.last_tick=now
        self.amount=min(1.,self.amount+dt/.22) if self.visible else max(0.,self.amount-dt/.25)
        if not self.visible and self.amount==0:
            u.ShowWindow(self.hwnd,0); return
        desired=self.get_level() if self.visible else 0.
        desired=0. if desired<.015 else min(1.,desired*1.8)
        tau=.055 if desired>self.level else .12
        self.level+=(desired-self.level)*(1-math.exp(-dt/tau))
        if self.level<.008: self.level=0.
        eased=self.amount**3*(self.amount*(self.amount*6-15)+10)
        try:
            self.present(self.render(time.perf_counter()-self.started,self.level),eased)
        except Exception:
            self.visible=False; u.ShowWindow(self.hwnd,0); return
        elapsed=time.perf_counter()-now
        self.job=self.root.after(max(1,round(1000*(1/self.fps-elapsed))),self.tick)

    def close(self):
        self.closed=True
        if self.job is not None: self.root.after_cancel(self.job)
        u.DestroyWindow(self.hwnd)
