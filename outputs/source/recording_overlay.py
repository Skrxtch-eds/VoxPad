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
    span: float = 1.
    glint: float = -1.
    glint_strength: float = 0.
    gap: float = 0.


def smootherstep(value):
    value = min(1., max(0., value))
    return min(1., max(0., value ** 3 * (value * (value * 6. - 15.) + 10.)))


def velocity_tail(elapsed, velocity, room, max_duration=.065):
    """Carry an interrupted edge's tangent briefly, then settle onto its new path."""
    if not velocity or room<=0.:
        return 0.,0.
    duration=min(max_duration,2.*room/abs(velocity))
    q=min(1.,max(0.,elapsed/duration))
    if q>=1.:
        return 0.,0.
    displacement=velocity*duration*(q-6*q**3+8*q**4-3*q**5)
    rate=velocity*(1.-18*q*q+32*q**3-15*q**4)
    return displacement,rate


class RecordingOverlay:
    # Design coordinates stay fixed: resizing must not alter the glass or wave.
    width, height, margin, scale = 234, 117, 20, 3
    size_multiplier = 1.10
    # Overall wave height grows 30%, including the capsule's own 10% increase.
    wave_gain = 1.30 / size_multiplier
    reference_size = (2880, 1920)
    display_scale = 1.
    fps = 120
    motion_speed = 1.56
    enter_duration, exit_duration = .560/motion_speed, .340/motion_speed
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
        self.motion = CapsuleMotion(0., 0., 0., span=.08)
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
        self._motion_geometry = None

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
        self.wave_envelope=self.sin_envelope**3.2*self.wave_gain
        self.blur_sigma=self.wave_scale*(self.width/280.)*(
            7.5*self.sin_envelope**2.2+3.*self.sin_envelope**.8+1.2*(1.-self.sin_envelope))
        self.blur_radii=np.array([0.,1.5,3.5,6.5,11.],dtype=np.float32)*self.wave_scale
        self.safe_band=np.zeros((wave_h,1),dtype=np.float32)
        padding=math.ceil(self.vertical_padding*self.wave_scale)
        self.safe_band[padding:wave_h-padding]=1.
        edge=np.minimum(self.wave_y-padding,wave_h-padding-self.wave_y)
        fade=np.clip(edge/(5.*self.wave_scale),0.,1.)
        self.glow_band=fade*fade*(3.-2.*fade)
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
        self.exit_velocity=getattr(self,'shape_velocity',0.)
        self.motion_started=time.perf_counter()
        self.motion_phase='exit'

    def begin_enter(self, motion=None, velocity=0.):
        self.amount=0.
        if motion is None:
            self.level=0.
            self.started=time.perf_counter()
        self.last_tick=self.motion_started=time.perf_counter()
        self.enter_from=motion or CapsuleMotion(0.,0.,0.,span=.08)
        self.enter_velocity=velocity
        self.opening_delay=0. if motion is not None else .25
        self.motion_phase='enter'
        self.shape_velocity=velocity
        self.motion=self.enter_from

    def advance_motion(self, now):
        """A hairline opens in place; a single reflection travels along its rim."""
        if self.motion_phase=='enter':
            p=min(1.,max(0.,(now-self.motion_started)/self.enter_duration))
            start=self.enter_from
            duration=(.84-self.opening_delay)*self.enter_duration
            q=min(1.,max(0.,(p-self.opening_delay)/(.84-self.opening_delay)))
            shape=start.shape+(1.-start.shape)*smootherstep(q)
            delta,rate=velocity_tail(now-self.motion_started,self.enter_velocity,start.shape,.065/self.motion_speed)
            shape=min(1.,max(0.,shape+delta))
            self.shape_velocity=(1.-start.shape)*30.*q*q*(1.-q)**2/duration+rate
            glint=min(1.,max(0.,(p-.40)/.60))
            strength=smootherstep(glint/.16)*(1.-smootherstep((glint-.76)/.24))
            blend=smootherstep(p/.12)
            strength=start.glint_strength*(1.-blend)+strength*blend
            glint=max(0.,start.glint)+(1.-max(0.,start.glint))*glint
            opacity=start.opacity+(1.-start.opacity)*smootherstep(p/.18)
            span=start.span+(1.-start.span)*smootherstep(p/.25)
            gap=start.gap*(1.-smootherstep(p/.25))
            self.amount=p
            self.motion=CapsuleMotion(shape,0.,opacity,span,glint,strength,gap)
            if p==1.:
                self.motion_phase='idle'
                self.motion=CapsuleMotion()
        elif self.motion_phase=='exit':
            p=min(1.,max(0.,(now-self.motion_started)/self.exit_duration))
            start=self.exit_from
            q=min(1.,p/.68)
            # Preserve velocity on early release, then brake before reversing.
            shape=start.shape*(1.-smootherstep(q))
            delta,rate=velocity_tail(now-self.motion_started,self.exit_velocity,1.-start.shape,.065/self.motion_speed)
            shape+=delta
            self.shape_velocity=-start.shape*30.*q*q*(1.-q)**2/(.68*self.exit_duration)+rate
            shape=min(1.,max(0.,shape))
            erasure=smootherstep((p-.66)/.34)
            # The two surviving strokes shorten from their outer AND inner
            # ends, rather than merely shrinking the whole line into its centre.
            meeting=(start.span+start.gap)/2
            span=start.span+(meeting-start.span)*erasure
            gap=start.gap+(meeting-start.gap)*erasure
            strength=start.glint_strength*(1.-smootherstep(p/.30))
            self.amount=1.-p
            self.motion=CapsuleMotion(shape,0.,start.opacity*(1.-smootherstep((p-.72)/.28)),
                                      span,start.glint,strength,gap)
            if p==1.:
                self.motion_phase='hidden'
                self.motion=CapsuleMotion(0.,0.,0.,span=0.)
        return self.motion

    @staticmethod
    def glow_profile(distance, scale):
        """The same soft white bloom for the opening line and the live wave."""
        return (np.exp(-.5*(distance/(2.6*scale))**2)*46.
                +np.exp(-.5*(distance/(7.2*scale))**2)*20.)

    def blur_wave(self, alpha, amp):
        """Position-dependent Gaussian softness, also feathering the line ends."""
        if amp<.01:return alpha
        # Filter at physical size, then combine with the supersampled glow.
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
        """One continuous wave, with Gaussian edges and a faint soft glow."""
        s=self.wave_scale; w,h=self.wave_size
        v=self.v; env=self.wave_envelope
        ratio=self.width/280.
        center=h/2+amp*28*s*ratio*env*np.sin(2*np.pi*(v*1.2-t*.56))
        thick=(.65*s+amp*24*s*env*(.55+.45*np.sin(np.pi*v*1.65-t*.9)**2))*ratio
        # Fit the contour and glow together, rather than cutting peaks.
        extent=float(np.max(np.abs(center-h/2)+thick))+8.5*s
        fit=min(1.,(h/2-self.vertical_padding*s)/extent)
        center=h/2+(center-h/2)*fit
        thick*=fit
        distance=thick[None,:]-np.abs(self.wave_y-center[None,:])
        edge_width=(1.05+.85*amp)*s
        body=np.clip(.5+distance/edge_width,0.,1.)
        body*=body*(3.-2.*body)
        soft=np.asarray(self.blur_wave(Image.fromarray(np.uint8(body*255)),amp),dtype=np.float32)/255.
        glow=self.glow_profile(np.maximum(0.,-distance),s)/255.
        # Fade only the outer bloom before the safe band, keeping the original
        # wave height and blurred body instead of clipping the new halo.
        alpha=np.maximum(soft,glow*self.glow_band)
        return Image.fromarray(np.uint8(alpha*self.mask_values*self.safe_band*255))

    def render(self, t, amp):
        alpha=self.wave_mask(t,max(0.,min(1.,amp)))
        size=(self.scaled(self.width),self.scaled(self.height))
        alpha=alpha.resize(size,Image.Resampling.LANCZOS)
        white=Image.new('RGBA',size,'#FFFFFF'); white.putalpha(alpha)
        frame=self.output_frame.copy()
        frame.alpha_composite(white,(self.scaled(20),self.scaled(20)))
        return frame

    def motion_geometry(self, size):
        """Small physical-pixel masks, reused throughout each appearance."""
        cached=getattr(self,'_motion_geometry',None)
        if cached is not None and cached[0]==size:
            return cached[1:]
        w,h=size;s=self.display_scale
        x=np.arange(w,dtype=np.float32)[None,:]+.5-w/2
        y=np.arange(h,dtype=np.float32)[:,None]+.5-h/2
        radius=self.scaled(self.height)/2
        straight=(self.scaled(self.width)-self.scaled(self.height))/2
        distance=np.hypot(np.maximum(np.abs(x)-straight,0.),y)-radius
        rim=np.exp(-.5*(distance/(.70*s))**2)
        halo=np.exp(-.5*(distance/(2.0*s))**2)
        # Keep the reflection on the upper-left arc and upper rim. The lower
        # edge must not light up in parallel with it.
        upper=np.clip(-y/radius,0.,1.)**1.5
        rim=(rim*220.+halo*18.)*upper
        # Integrate a subpixel Gaussian over each pixel. The thin initial line
        # stays equally bright even when its centre falls between pixel rows.
        sigma=.42*s
        erf=np.vectorize(math.erf,otypes=[np.float32])
        line=(erf((y+.5)/(math.sqrt(2)*sigma))-erf((y-.5)/(math.sqrt(2)*sigma)))*.5
        # Visible, soft white bloom around a fine core; the broad layer stays
        # faint rather than increasing the thickness of the bright line.
        line=line*220.+self.glow_profile(y,s)
        self._motion_geometry=(size,x,rim,line)
        return x,rim,line

    def morph_frame(self, image, motion):
        """Open a slit vertically on a fixed canvas, with no integer-size steps."""
        shape=motion.shape
        if shape>=1. and motion.glint_strength<=0. and motion.span>=1.:
            return image
        x,rim,line=self.motion_geometry(image.size)
        if shape<.20:
            half=self.scaled(self.width)*.49
            feather=4.*self.display_scale
            taper=np.clip((half*motion.span-np.abs(x))/feather,0.,1.)
            taper=taper*taper*(3.-2.*taper)
            centre=np.clip((np.abs(x)-half*motion.gap+feather)/feather,0.,1.)
            centre=centre*centre*(3.-2.*centre)
            line_mask=taper*centre
        frame=image
        if motion.glint_strength>0.:
            # One reflection starts on the upper-left curve and crosses the top.
            centre=(motion.glint*1.10-.55)*self.scaled(self.width)
            sweep=np.exp(-.5*((x-centre)/(15.*self.display_scale))**2)
            alpha=np.uint8(np.clip(rim*sweep*motion.glint_strength,0,255))
            light=Image.new('RGBA',image.size,(242,248,255,0))
            light.putalpha(Image.fromarray(alpha))
            frame=Image.alpha_composite(frame,light)
        if shape<1.:
            factor=(1.25+(self.height-1.25)*shape)/self.height
            cy=image.height/2
            # Premultiplied alpha avoids dark/coloured fringes. Fractional affine
            # sampling keeps the opening and centre stable at every DPI.
            frame=frame.convert('RGBa').transform(image.size,Image.Transform.AFFINE,
                    (1.,0.,0.,0.,1./factor,cy-cy/factor),Image.Resampling.BILINEAR).convert('RGBA')
            glass=smootherstep(shape/.09)
            if glass<1.:
                frame.putalpha(frame.getchannel('A').point(lambda a:round(a*glass)))
            strength=1.-smootherstep(shape/.20)
            if strength>0.:
                brightness=.82+.18*np.exp(-.5*(x/(half*.38))**2)
                alpha=np.uint8(np.clip(line*brightness*line_mask*strength,0,255))
                light=Image.new('RGBA',image.size,(255,255,255,0))
                light.putalpha(Image.fromarray(alpha))
                frame=Image.alpha_composite(frame,light)
        return frame

    def frame_position(self, image):
        return (round(self.x+self.scaled(self.width)/2-image.width/2),
                round(self.y+self.scaled(self.height)/2-image.height/2+self.motion.offset*self.display_scale))

    def clip_to_work_area(self, image, position):
        """Keep the capsule and its shadow within the monitor's work area."""
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
        if opacity<=0.:
            u.ShowWindow(self.hwnd,0)
            return
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
            self.present(self.morph_frame(image,motion),motion.opacity)
        except Exception:
            self.visible=False; self.amount=0.; self.motion_phase='hidden'
            u.ShowWindow(self.hwnd,0); return
        elapsed=time.perf_counter()-now
        self.job=self.root.after(max(1,round(1000*(1/self.fps-elapsed))),self.tick)

    def close(self):
        self.closed=True
        if self.job is not None: self.root.after_cancel(self.job)
        u.DestroyWindow(self.hwnd)
