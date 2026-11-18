"""Non-activating, click-through Windows glass recording indicator."""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
from dataclasses import dataclass
import math
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

u = C.WinDLL('user32', use_last_error=True)
g = C.WinDLL('gdi32', use_last_error=True)
_set_dpi_context=getattr(u,'SetThreadDpiAwarenessContext',None)
if _set_dpi_context:
    _set_dpi_context.argtypes=[W.HANDLE]
    _set_dpi_context.restype=W.HANDLE


@contextmanager
def physical_pixels():
    """Keep the native window crisp without changing the GUI thread's DPI mode."""
    previous=None
    if _set_dpi_context:
        previous=_set_dpi_context(W.HANDLE(-4)) or _set_dpi_context(W.HANDLE(-3))
    try:
        yield
    finally:
        if previous:_set_dpi_context(previous)


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

@dataclass(frozen=True)
class CapsuleMotion:
    shape: float = 1.
    offset: float = 0.
    opacity: float = 1.


def smoothstep(value):
    value = min(1., max(0., value))
    return value * value * (3. - 2. * value)


def smootherstep(value):
    value = min(1., max(0., value))
    return value ** 3 * (value * (value * 6. - 15.) + 10.)


class RecordingOverlay:
    # Design coordinates stay fixed: resizing must not alter the glass or wave.
    width, height, margin, scale = 234, 117, 20, 3
    size_multiplier = 1.10
    # Overall wave height grows 30%, including the capsule's own 10% increase.
    wave_gain = 1.30 / size_multiplier
    reference_size = (2880, 1920)
    display_scale = 1.
    fps = 120
    enter_duration, exit_duration = .320, .180
    orb_diameter = 44.
    vertical_padding = 15
    backdrop_blur_mix = .60  # 20% stronger than the previous .50 mix.
    edge_refraction = 20.4   # 70% stronger than the previous 12px displacement.

    def __init__(self, root, get_level):
        self.root, self.get_level = root, get_level
        with physical_pixels():
            self.hwnd = u.CreateWindowExW(0x080800A8,'STATIC','Recording capsule',0x80000000,
                                          0,0,320,180,None,None,None,None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.visible=False
        self.closed=False
        self.job=None
        self.amount=0.
        self.level=0.
        self.motion = CapsuleMotion(0., 0., 0.)
        self.motion_phase = 'hidden'
        self.last_tick=time.perf_counter()

    def scaled(self, value):
        return max(1,round(value*self.display_scale))

    def configure_monitor(self, info):
        """Use physical monitor bounds with 2880×1920 as the size reference."""
        screen=info.monitor;rect=info.work
        self.work_area=(rect.left,rect.top,rect.right,rect.bottom)
        self.display_scale=self.size_multiplier*min((screen.right-screen.left)/self.reference_size[0],
                                                    (screen.bottom-screen.top)/self.reference_size[1])
        # Include the shadow and lower gap when fitting unusually small work areas.
        self.display_scale=min(self.display_scale,(rect.right-rect.left)/(self.width+40),
                               (rect.bottom-rect.top)/(self.height+76))
        # Higher-resolution glass source; the final native window uses physical pixels.
        self.scale=max(3,math.ceil(self.display_scale*2.5))
        self.x=(rect.left+rect.right-self.scaled(self.width))//2
        self.y=rect.bottom-self.scaled(self.height)-self.scaled(36)
        # Travel beyond the monitor edge, including a taskbar outside the work area.
        self.travel=(screen.bottom-self.y-self.scaled(self.height)/2)/self.display_scale+self.orb_diameter

    def prepare_surface(self,backdrop):
        """Shared real/preview renderer. No microphone or window capture here."""
        s=self.scale; w,h=self.width*s,self.height*s
        backdrop=backdrop.resize((w,h),Image.Resampling.BICUBIC)
        backdrop=Image.blend(backdrop,backdrop.filter(ImageFilter.GaussianBlur(13*s)),self.backdrop_blur_mix)
        pixels=np.asarray(backdrop)
        gx=np.arange(w,dtype=np.float32)[None,:]
        gy=np.arange(h,dtype=np.float32)[:,None]
        px,py=gx-w/2,gy-h/2
        dx=px-np.clip(px,-(w-h)/2,(w-h)/2)
        radius=np.maximum(np.hypot(dx,py),1)
        inset=np.maximum(0,h/2-radius)
        bevel=np.exp(-inset/(5.5*s))
        sx=np.clip(np.rint(gx-dx/radius*self.edge_refraction*s*bevel-px*.035).astype(int),0,w-1)
        sy=np.clip(np.rint(gy-py/radius*self.edge_refraction*s*bevel-py*.035).astype(int),0,h-1)
        lens=pixels[sy,sx].astype(np.float32)*.975+255*.025
        shine=np.exp(-((inset-2*s)/(1.3*s))**2)*np.clip(-py/radius*.65-dx/radius*.3+.2,0,1)*53
        # A brighter, broader reflection follows the upper curved surface.
        upper=np.clip(-py/radius,0,1)**2
        crown=np.exp(-((inset-3*s)/(2.5*s))**2)*upper*68
        soft_gloss=np.exp(-((inset-7*s)/(5*s))**2)*upper*13
        lens+=(shine+crown+soft_gloss)[:,:,None]
        mask_large=Image.new('L',(w*2,h*2)); d=ImageDraw.Draw(mask_large)
        d.rounded_rectangle((1,1,w*2-2,h*2-2),radius=h,fill=255)
        mask=mask_large.resize((w,h),Image.Resampling.LANCZOS)
        glass=Image.fromarray(np.uint8(np.clip(lens,0,255))).convert('RGBA')
        glass.putalpha(mask)
        d=ImageDraw.Draw(glass)
        d.rounded_rectangle((s,s,w-s-1,h-s-1),radius=h/2,outline=(245,251,255,150),width=s)
        # Cache everything static so higher FPS does not repeat glass/shadow work.
        self.wave_size=(self.scaled(self.width)*2,self.scaled(self.height)*2)
        self.wave_scale=self.display_scale*2
        wave_w,wave_h=self.wave_size
        self.v=np.linspace(0,1,wave_w,dtype=np.float32)
        self.sin_envelope=np.maximum(0,np.sin(np.pi*self.v))
        self.mask_values=np.asarray(mask.resize(self.wave_size,Image.Resampling.LANCZOS),dtype=np.float32)/255.
        self.wave_y=np.arange(wave_h,dtype=np.float32)[:,None]+.5
        self.wave_x=np.arange(wave_w,dtype=np.float32)+.5
        self.wave_envelope=self.sin_envelope**3.2*self.wave_gain
        self.blur_sigma=self.wave_scale*(self.width/280.)*(
            7.5*self.sin_envelope**2.2+3.*self.sin_envelope**.8+1.2*(1.-self.sin_envelope))
        self.blur_radii=np.array([0.,1.5,3.5,6.5,11.],dtype=np.float32)*self.wave_scale
        self.safe_band=np.zeros((wave_h,1),dtype=np.float32)
        padding=math.ceil(self.vertical_padding*self.wave_scale)
        self.safe_band[padding:wave_h-padding]=1.
        frame=Image.new('RGBA',((self.width+40)*s,(self.height+40)*s))
        shadow=Image.new('RGBA',frame.size)
        ImageDraw.Draw(shadow).rounded_rectangle((20*s,26*s,(20+self.width)*s,(26+self.height)*s),radius=h/2,fill=(0,0,0,55))
        frame.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9*s)))
        frame.alpha_composite(glass,(20*s,20*s))
        # Downsample the detailed glass/shadow once, rather than every wave frame.
        self.output_frame=frame.resize((self.scaled(self.width+40),self.scaled(self.height+40)),Image.Resampling.LANCZOS)

    def hide(self):
        if not self.visible:
            return
        self.visible=False
        self.exit_from=self.motion
        self.motion_started=time.perf_counter()
        self.motion_phase='exit'

    def begin_enter(self):
        self.amount=0.; self.level=0.
        self.started=self.last_tick=self.motion_started=time.perf_counter()
        self.motion_phase='enter'
        self.motion=CapsuleMotion(0.,self.travel,0.)

    def advance_motion(self, now):
        """Short flight, braking, then glass expansion; reverse order on dismissal."""
        if self.motion_phase=='enter':
            p=min(1.,max(0.,(now-self.motion_started)/self.enter_duration))
            flight=min(1.,p/.46)
            offset=self.travel*(1.-smootherstep(flight))
            # A small upward overshoot settles while the sphere becomes a capsule.
            offset-=1.8*math.sin(math.pi*smootherstep((p-.38)/.62))**2
            shape=smootherstep((p-.40)/.60)
            self.amount=p
            self.motion=CapsuleMotion(shape,offset,smootherstep(p/.18))
            if p==1.:
                self.motion_phase='idle'
                self.motion=CapsuleMotion()
        elif self.motion_phase=='exit':
            p=min(1.,max(0.,(now-self.motion_started)/self.exit_duration))
            start=self.exit_from
            shape=start.shape*(1.-smoothstep(p/.56))
            fall=smoothstep((p-.42)/.58)
            offset=start.offset*(1.-fall)+self.travel*fall*fall
            self.amount=1.-p
            self.motion=CapsuleMotion(shape,offset,start.opacity*(1.-smoothstep((p-.72)/.28)))
            if p==1.:self.motion_phase='hidden'
        return self.motion

    def blur_wave(self, alpha, amp):
        """Position-dependent Gaussian softness, also feathering the line ends."""
        if amp<.01:return alpha
        # Gaussian softness needs no subpixel detail: filter at physical size,
        # then combine with the separately supersampled droplets and glow.
        source=alpha.resize((self.wave_size[0]//2,self.wave_size[1]//2),Image.Resampling.BOX)
        sigma=self.blur_sigma[::2]*amp/2
        radii=self.blur_radii/2
        out=np.zeros((source.height,source.width),dtype=np.float32)
        lower=np.asarray(source)
        for low,high in zip(radii,radii[1:]):
            upper=np.asarray(source.filter(ImageFilter.GaussianBlur(float(high))))
            columns=np.flatnonzero((sigma>=low)&(sigma<=high))
            if columns.size:
                weight=(sigma[columns]-low)/(high-low)
                out[:,columns]=lower[:,columns]*(1.-weight)+upper[:,columns]*weight
            lower=upper
        return Image.fromarray(np.uint8(out)).resize(self.wave_size,Image.Resampling.BILINEAR)

    def wave_mask(self, t, amp):
        """Soft Gaussian wave with local metaballs and a faint glow."""
        s=self.wave_scale; w,h=self.wave_size
        v=self.v; env=self.wave_envelope
        ratio=self.width/280.
        center=h/2+amp*28*s*ratio*env*np.sin(2*np.pi*(v*1.2-t*.56))
        thick=(.65*s+amp*24*s*env*(.55+.45*np.sin(np.pi*v*1.65-t*.9)**2))*ratio
        # Fit the contour, droplets and glow together, rather than cutting peaks.
        extent=float(np.max(np.abs(center-h/2)+thick))+8.5*s
        fit=min(1.,(h/2-self.vertical_padding*s)/extent)
        center=h/2+(center-h/2)*fit
        thick*=fit
        distance=thick[None,:]-np.abs(self.wave_y-center[None,:])
        edge_width=(1.05+.85*amp)*s
        body=np.clip(.5+distance/edge_width,0.,1.)
        body*=body*(3.-2.*body)
        soft=np.asarray(self.blur_wave(Image.fromarray(np.uint8(body*255)),amp),dtype=np.float32)/255.
        activity=smoothstep((amp-.28)/.55)
        if activity:
            # Staggered droplets follow both moving edges. Nearby droplets merge
            # through a smooth union; the outer ones form a sparse dotted fringe.
            for index in range(34):
                fraction=.17+.66*((index/34+t*.025)%1.)
                x=min(w-1,round(fraction*(w-1)))
                strength=activity*float(self.sin_envelope[x])**2
                radius=s*(.65+1.0*(.5+.5*math.sin(index*2.4+t*2.1)))*strength
                if radius<.22*s:continue
                for side in (-1,1):
                    drift=.5+.5*math.sin(index*1.71+t*2.8+side)
                    cy=float(center[x]+side*(thick[x]+s*(.7+3.8*drift)*strength))
                    cx=x+s*.6*math.sin(index+t+side)
                    reach=radius+1.4*s
                    x0=max(0,math.floor(cx-reach));x1=min(w,math.ceil(cx+reach))
                    y0=max(0,math.floor(cy-reach));y1=min(h,math.ceil(cy+reach))
                    if x0>=x1 or y0>=y1:continue
                    blob=radius-np.hypot(self.wave_x[None,x0:x1]-cx,self.wave_y[y0:y1]-cy)
                    patch=distance[y0:y1,x0:x1]
                    bridge=np.maximum(.85*s-np.abs(patch-blob),0.)
                    distance[y0:y1,x0:x1]=np.maximum(patch,blob)+bridge*bridge/(3.4*s)
        # Round off the droplets as well as the wave body, preserving the fringe.
        core=np.clip(.5+distance/edge_width,0.,1.)
        core*=core*(3.-2.*core)
        glow=np.clip(1.+distance/(4.2*s),0.,1.)
        alpha=np.maximum(np.maximum(soft,core-body),glow*glow*(.10+.08*amp))
        return Image.fromarray(np.uint8(alpha*self.mask_values*self.safe_band*255))

    def render(self, t, amp):
        alpha=self.wave_mask(t,max(0.,min(1.,amp)))
        size=(self.scaled(self.width),self.scaled(self.height))
        alpha=alpha.resize(size,Image.Resampling.LANCZOS)
        white=Image.new('RGBA',size,'#FFFFFF'); white.putalpha(alpha)
        frame=self.output_frame.copy()
        frame.alpha_composite(white,(self.scaled(20),self.scaled(20)))
        return frame

    def morph_frame(self, image, shape):
        """Resize circular endcaps separately so the little orb stays round."""
        if shape>=1.:return image
        factor=(self.orb_diameter+(self.height-self.orb_diameter)*shape)/self.height
        split=round(image.width*(self.margin+self.height/2)/(self.width+2*self.margin))
        cap=max(1,round(split*factor))
        middle=max(0,round((image.width-2*split)*shape))
        height=max(1,round(image.height*factor))
        frame=Image.new('RGBA',(2*cap+middle,height))
        frame.paste(image.crop((0,0,split,image.height)).resize((cap,height),Image.Resampling.LANCZOS),(0,0))
        if middle:
            frame.paste(image.crop((split,0,image.width-split,image.height)).resize((middle,height),Image.Resampling.LANCZOS),(cap,0))
        frame.paste(image.crop((image.width-split,0,image.width,image.height)).resize((cap,height),Image.Resampling.LANCZOS),(cap+middle,0))
        return frame

    def frame_position(self, image):
        return (round(self.x+self.scaled(self.width)/2-image.width/2),
                round(self.y+self.scaled(self.height)/2-image.height/2+self.motion.offset*self.display_scale))

    def clip_to_work_area(self, image, position):
        """Let the orb emerge from behind any taskbar, including its shadow."""
        x,y=position;left,top,right,bottom=self.work_area
        x0=max(0,left-x);y0=max(0,top-y)
        x1=min(image.width,right-x);y1=min(image.height,bottom-y)
        if x0>=x1 or y0>=y1:return None
        if (x0,y0,x1,y1)==(0,0,image.width,image.height):return image
        clipped=Image.new('RGBA',image.size)
        clipped.paste(image.crop((x0,y0,x1,y1)),(x0,y0))
        return clipped

    @physical_pixels()
    def present(self, image, opacity):
        x,y=self.frame_position(image)
        image=self.clip_to_work_area(image,(x,y))
        if image is None:
            u.ShowWindow(self.hwnd,0)
            return
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
            position=W.POINT(x,y)
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
        motion=self.advance_motion(now)
        if self.motion_phase=='hidden':
            u.ShowWindow(self.hwnd,0); return
        desired=self.get_level() if self.visible else 0.
        desired=0. if desired<.015 else min(1.,desired*1.8)
        tau=.055 if desired>self.level else .12
        self.level+=(desired-self.level)*(1-math.exp(-dt/tau))
        if self.level<.008: self.level=0.
        try:
            image=self.render(now-self.started,self.level*motion.shape**2)
            self.present(self.morph_frame(image,motion.shape),motion.opacity)
        except Exception:
            self.visible=False; self.amount=0.; self.motion_phase='hidden'
            u.ShowWindow(self.hwnd,0); return
        elapsed=time.perf_counter()-now
        self.job=self.root.after(max(1,round(1000*(1/self.fps-elapsed))),self.tick)

    def close(self):
        self.closed=True
        if self.job is not None: self.root.after_cancel(self.job)
        u.DestroyWindow(self.hwnd)
