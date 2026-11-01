"""Shared, DPI-aware visual tokens and Tk styles for every application window."""
from dataclasses import dataclass
import winreg
import tkinter as tk
from tkinter import ttk,font as tkfont
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageTk

# 50% larger than the 0.5.1 interface; fonts and pixel dimensions share this scale.
UI_SCALE=.646875*1.5

def initialize_scale(window):
    """Set points and pixel units together, once per Tk interpreter."""
    root=window._root()
    if not hasattr(root,'_native_tk_scale'):
        root._native_tk_scale=float(root.tk.call('tk','scaling'))
        root.tk.call('tk','scaling',root._native_tk_scale*UI_SCALE)

@dataclass(frozen=True)
class Theme:
    background:str
    surface:str
    secondary:str
    text:str
    muted:str
    disabled:str
    border:str
    accent:str
    accent_hover:str
    accent_text:str
    selection:str
    danger:str

LIGHT=Theme('#f7f9fc','#ffffff','#e9eff6','#101117','#747c91','#969dab','#dfe4ed','#007aff','#006be5','#ffffff','#d8e9ff','#ef2929')
DARK=Theme('#111113','#1c1c1e','#2c2c2e','#f5f5f7','#98989d','#6b6b70','#38383a','#0a84ff','#409cff','#ffffff','#193a59','#ff453a')

def system_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize',0,
                            winreg.KEY_READ|winreg.KEY_WOW64_64KEY) as key:
            return int(winreg.QueryValueEx(key,'AppsUseLightTheme')[0])==0
    except OSError:return False

def theme_for(mode='system'):
    return DARK if mode=='dark' or (mode=='system' and system_dark()) else LIGHT

def configure_styles(window,mode='system'):
    initialize_scale(window)
    from branding import apply_icon
    apply_icon(window)
    theme=theme_for(mode);window.ui_theme=theme;window.theme_mode=mode
    from resize_support import attach
    attach(window)
    style=ttk.Style(window)
    style.configure('.',font=('Segoe UI',11),background=theme.background,foreground=theme.text)
    style.configure('Settings.TFrame',background=theme.background)
    style.configure('Card.TFrame',background=theme.surface,borderwidth=0,relief='flat')
    style.configure('Group.TFrame',background=theme.surface,relief='solid',borderwidth=1,bordercolor=theme.border,lightcolor=theme.border,darkcolor=theme.border)
    style.configure('TLabel',background=theme.background,foreground=theme.text)
    style.configure('Card.TLabel',background=theme.surface,foreground=theme.text)
    style.configure('Muted.TLabel',background=theme.surface,foreground=theme.muted,font=('Segoe UI',10))
    style.configure('PageMuted.TLabel',background=theme.background,foreground=theme.muted,font=('Segoe UI',12))
    style.configure('Divider.TFrame',background=theme.border)
    style.configure('Settings.Treeview',background=theme.surface,fieldbackground=theme.surface,foreground=theme.text,
                    borderwidth=0,relief='flat',rowheight=dp(window,54),font=('Segoe UI',16))
    style.map('Settings.Treeview',background=[('selected',theme.selection)],foreground=[('selected',theme.text)])
    style.layout('Settings.Treeview',[('Treeview.treearea',{'sticky':'nswe'})])
    style.configure('Settings.Treeview',padding=(dp(window,12),0))
    style.configure('Settings.Treeview.Heading',background=theme.background,foreground=theme.muted,relief='flat',padding=(dp(window,14),dp(window,10)),font=('Segoe UI',15))
    style.map('Settings.Treeview.Heading',background=[('active',theme.secondary)])
    style.configure('TEntry',fieldbackground=theme.surface,foreground=theme.text,bordercolor=theme.border,padding=(dp(window,8),dp(window,7)),insertcolor=theme.text)
    style.map('TEntry',bordercolor=[('focus',theme.accent)])
    style.configure('Settings.TCombobox',fieldbackground=theme.surface,background=theme.surface,foreground=theme.text,
                    arrowcolor=theme.muted,bordercolor=theme.border,padding=(dp(window,4),0))
    style.map('Settings.TCombobox',fieldbackground=[('readonly',theme.surface)],selectbackground=[('readonly',theme.surface)],
              selectforeground=[('readonly',theme.text)],bordercolor=[('focus',theme.accent)])
    # The rounded shell owns the field border. Keep Tk's editable popup and
    # keyboard behavior, with a larger system-library chevron.
    arrow='Vox.'+('Dark' if theme==DARK else 'Light')+'.Combo.downarrow'
    try:style.element_create(arrow,'image',icon_image(window,'chevron',14,theme.muted))
    except tk.TclError:pass
    style.layout('Settings.TCombobox',[('Combobox.padding',{'sticky':'nswe','children':[
        (arrow,{'side':'right','sticky':'e'}),('Combobox.textarea',{'sticky':'nswe'})]})])
    style.configure('Settings.TCheckbutton',background=theme.surface,foreground=theme.text,padding=4)
    style.configure('Settings.TButton',background=theme.surface,foreground=theme.text,bordercolor=theme.border,
                    lightcolor=theme.surface,darkcolor=theme.surface,padding=(16,9))
    style.map('Settings.TButton',background=[('pressed',theme.selection),('active',theme.secondary)],
              foreground=[('disabled',theme.disabled)],bordercolor=[('focus',theme.accent)])
    style.configure('Primary.TButton',background=theme.accent,foreground=theme.accent_text,bordercolor=theme.accent,
                    lightcolor=theme.accent,darkcolor=theme.accent,padding=(16,9))
    style.map('Primary.TButton',background=[('active',theme.accent_hover),('pressed',theme.accent_hover)],
              foreground=[('disabled',theme.disabled)])
    style.configure('Danger.TButton',background=theme.surface,foreground=theme.danger,bordercolor=theme.border,
                    lightcolor=theme.surface,darkcolor=theme.surface,padding=(16,9))
    style.map('Danger.TButton',background=[('active',theme.secondary),('pressed',theme.selection)])
    style.configure('Settings.Horizontal.TScale',background=theme.surface,troughcolor=theme.secondary)
    style.configure('TScrollbar',background=theme.secondary,troughcolor=theme.background)
    style.configure('Vertical.TScrollbar',background=theme.border,troughcolor=theme.surface,
                    arrowcolor=theme.muted,borderwidth=0,relief='flat',width=dp(window,11))
    return theme

def dp(widget,value):
    return round(value*widget.winfo_fpixels('1i')/96.)

def rounded_surface(canvas,width,height,radius,fill,border,background):
    """Stretch solid regions; rasterize only the small antialiased corners."""
    if width<4 or height<4:return
    radius=max(1,min(radius,(min(width,height)-2)//2));patch=radius+1
    root=canvas._root();cache=getattr(root,'_round_corners',None)
    if cache is None:cache=root._round_corners={}
    key=(radius,fill,border,background)
    if key not in cache:
        side=2*patch;factor=3
        im=Image.new('RGB',(side*factor,side*factor),background)
        ImageDraw.Draw(im).rounded_rectangle((factor,factor,(side-2)*factor,(side-2)*factor),
            radius=radius*factor,fill=fill,outline=border or fill,width=factor)
        im=im.resize((side,side),Image.Resampling.LANCZOS)
        cache[key]=tuple(ImageTk.PhotoImage(im.crop(box),master=root) for box in
                         ((0,0,patch,patch),(side-patch,0,side,patch),
                          (0,side-patch,patch,side),(side-patch,side-patch,side,side)))
    canvas.create_rectangle(patch,1,width-patch,height-2,fill=fill,outline='')
    canvas.create_rectangle(1,patch,width-2,height-patch,fill=fill,outline='')
    if border:
        canvas.create_line(patch,1,width-patch,1,fill=border)
        canvas.create_line(patch,height-2,width-patch,height-2,fill=border)
        canvas.create_line(1,patch,1,height-patch,fill=border)
        canvas.create_line(width-2,patch,width-2,height-patch,fill=border)
    for im,(x,y) in zip(cache[key],((0,0),(width-patch,0),(0,height-patch),(width-patch,height-patch))):
        canvas.create_image(x,y,image=im,anchor='nw')

# The Windows system icon family is already installed and matches the thin,
# monochrome icon treatment of the reference. Rasterize at the display density.
ICONS={'mic':'\ue720','document':'\ue9f9','settings':'\ue713','history':'\ue9f9',
       'recovery':'\ue895','statistics':'\ue9e9','pause':'\ue769','play':'\ue768',
       'copy':'\ue8c8','export':'\ue898','delete':'\ue74d','folder':'\ue838',
       'add_file':'\ue8e5','search':'\ue721','check':'\ue73e','clock':'\ue823',
       'timer':'\ue916','characters':'\ue8e9','lightning':'\ue945','success':'\uec61',
       'wave':'\ue9e9','globe':'\ue774','archive':'\ue8f1','chevron':'\ue70d','warning':'\ue7ba'}

def icon_image(widget,name,size=24,color=None):
    color=color or widget.winfo_toplevel().ui_theme.muted
    pixels=dp(widget,size);root=widget._root()
    if not hasattr(root,'_ui_icons'):root._ui_icons={}
    key=(name,pixels,color)
    if key not in root._ui_icons:
        factor=3
        font=ImageFont.truetype(str(Path('C:/Windows/Fonts/segmdl2.ttf')),pixels*factor)
        im=Image.new('RGBA',(pixels*factor,pixels*factor))
        draw=ImageDraw.Draw(im);glyph=ICONS[name];box=draw.textbbox((0,0),glyph,font=font)
        draw.text(((pixels*factor-box[2]+box[0])/2-box[0],(pixels*factor-box[3]+box[1])/2-box[1]),glyph,font=font,fill=color)
        root._ui_icons[key]=ImageTk.PhotoImage(im.resize((pixels,pixels),Image.Resampling.LANCZOS),master=root)
    return root._ui_icons[key]

def icon_label(parent,name,size=24,color=None,background=None):
    im=icon_image(parent,name,size,color)
    return tk.Label(parent,image=im,bg=background or parent.winfo_toplevel().ui_theme.surface,bd=0)

class RoundedPanel(tk.Frame):
    """Resizable rounded native panel; children live in an inset content frame."""
    def __init__(self,parent,padding=14,radius=11,fill=None,border=True,**kwargs):
        t=parent.winfo_toplevel().ui_theme
        try:bg=parent.cget('background')
        except tk.TclError:bg=t.background
        if not bg:bg=t.background
        super().__init__(parent,bg=bg,bd=0,highlightthickness=0,**kwargs)
        self.fill=fill or t.surface;self.edge=t.border if border else self.fill;self.radius=dp(self,radius)
        self.back=tk.Canvas(self,width=1,height=1,bd=0,highlightthickness=0,bg=bg);self.back.place(x=0,y=0,relwidth=1,relheight=1)
        self.content=tk.Frame(self,bg=self.fill,bd=0)
        self.content.pack(fill='both',expand=True,padx=dp(self,padding),pady=dp(self,padding))
        self.bind('<Configure>',self._schedule_paint)
        self._size=None;self._paint_job=None
        self.bind('<Destroy>',self._cancel_paint)

    def _schedule_paint(self,event):
        if event.widget!=self:return
        if self._paint_job is None:self._paint_job=self.after(16,self._paint)

    def _cancel_paint(self,event):
        if event.widget==self and self._paint_job is not None:
            self.after_cancel(self._paint_job);self._paint_job=None

    def _paint(self):
        self._paint_job=None
        size=(self.winfo_width(),self.winfo_height())
        if min(size)<2 or size==self._size:return
        self._size=size;self.back.delete('all')
        rounded_surface(self.back,*size,self.radius,self.fill,self.edge,self.cget('bg'))

class ValueScale(tk.Canvas):
    """Continuous slider with a blue filled track and keyboard controls."""
    def __init__(self,parent,variable,from_=0,to=1,length=220,**kwargs):
        self.variable=variable;self.start=from_;self.end=to
        self.theme=parent.winfo_toplevel().ui_theme
        super().__init__(parent,width=dp(parent,length),height=dp(parent,26),bg=self.theme.surface,bd=0,highlightthickness=0,takefocus=1,**kwargs)
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Button-1>',self.move);self.bind('<B1-Motion>',self.move)
        for key,amount in (('<Left>',-1),('<Down>',-1),('<Right>',1),('<Up>',1)):
            self.bind(key,lambda e,a=amount:self.adjust(a))
        self.bind('<Home>',lambda e:self.variable.set(self.start));self.bind('<End>',lambda e:self.variable.set(self.end))
        self.bind('<FocusIn>',lambda e:self.draw());self.bind('<FocusOut>',lambda e:self.draw())
        self.trace=variable.trace_add('write',lambda *a:self.draw())
        self.bind('<Destroy>',self.destroy_trace)

    def destroy_trace(self,event):
        if event.widget==self:self.variable.trace_remove('write',self.trace)

    def move(self,event):
        self.focus_set();pad=dp(self,11);ratio=max(0,min(1,(event.x-pad)/max(1,self.winfo_width()-2*pad)))
        self.variable.set(self.start+ratio*(self.end-self.start))

    def adjust(self,amount):
        self.variable.set(max(self.start,min(self.end,self.variable.get()+amount*(self.end-self.start)/100)))
        return 'break'

    def draw(self):
        self.delete('all');w=self.winfo_width();h=self.winfo_height();p=dp(self,11)
        x=p+(w-2*p)*max(0,min(1,(self.variable.get()-self.start)/(self.end-self.start)))
        self.create_line(p,h/2,w-p,h/2,fill=self.theme.border,width=dp(self,6),capstyle='round')
        self.create_line(p,h/2,x,h/2,fill=self.theme.accent,width=dp(self,6),capstyle='round')
        r=dp(self,10);self.create_oval(x-r,h/2-r+1,x+r,h/2+r+1,fill='#ffffff',outline=self.theme.border)
        if self.focus_get()==self:self.create_rectangle(1,1,w-1,h-1,outline=self.theme.accent)

class AppSwitch(tk.Canvas):
    """Keyboard-operable compact switch sharing the current window palette."""
    def __init__(self,parent,variable,theme):
        scale=parent.winfo_fpixels('1i')/96.
        self.width=round(44*scale);self.height=round(28*scale)
        super().__init__(parent,width=self.width,height=self.height,highlightthickness=0,
                         bd=0,bg=theme.surface,cursor='hand2',takefocus=1)
        self.variable=variable;self.theme=theme
        self.knob=1. if variable.get() else 0.;self.animation=None
        self.bind('<Button-1>',self.toggle)
        self.bind('<space>',self.toggle)
        self.bind('<Return>',self.toggle)
        self.bind('<FocusIn>',lambda event:self.draw())
        self.bind('<FocusOut>',lambda event:self.draw())
        self.bind('<Destroy>',self._destroy)
        self.trace=variable.trace_add('write',lambda *args:self.animate())
        self.draw()

    def _destroy(self,event):
        if event.widget!=self:return
        if self.animation:self.after_cancel(self.animation)
        self.variable.trace_remove('write',self.trace)

    def toggle(self,event=None):
        self.variable.set(not self.variable.get())
        return 'break'

    def animate(self):
        target=1. if self.variable.get() else 0.
        if self.animation:self.after_cancel(self.animation);self.animation=None
        def step():
            if not self.winfo_exists():return
            self.knob+=(target-self.knob)*.38
            if abs(target-self.knob)<.015:self.knob=target
            self.draw()
            self.animation=self.after(16,step) if self.knob!=target else None
        step()

    def draw(self):
        self.delete('all');w=self.width;h=self.height;margin=round(h*.11)
        on=self.variable.get();s=3
        fill=self.theme.accent if on else ('#d1d1d6' if self.theme==LIGHT else '#525259')
        im=Image.new('RGB',(w*s,h*s),self.theme.surface);draw=ImageDraw.Draw(im)
        draw.rounded_rectangle((margin*s,margin*s,(w-margin)*s,(h-margin)*s),radius=h*s/2,fill=fill)
        diameter=round(h*.65);left=margin+(w-2*margin-diameter)*self.knob;top=(h-diameter)/2
        draw.ellipse((left*s,top*s,(left+diameter)*s,(top+diameter)*s),fill='#ffffff',outline='#e1e1e5',width=s)
        self._image=ImageTk.PhotoImage(im.resize((w,h),Image.Resampling.LANCZOS),master=self)
        self.create_image(0,0,image=self._image,anchor='nw')
        if self.focus_get()==self:
            self.create_rectangle(1,1,w-1,h-1,outline=self.theme.accent,width=1)


class RoundedButton(tk.Canvas):
    """Shared accessible button with a DPI-scaled rounded surface."""
    def __init__(self,parent,text='',command=None,style='Settings.TButton',font=None,
                 takefocus=True,large=False,icon=None,align='center',height=None,keycap='',**kwargs):
        self.theme=parent.winfo_toplevel().ui_theme
        self.text=text;self.command=command;self.variant=style
        self.font=tkfont.Font(root=parent,font=font or ('Segoe UI',16 if large else 11,'bold' if large else 'normal'))
        self.icon=icon;self.align=align;self.keycap=keycap
        self.scale=parent.winfo_fpixels('1i')/96.
        self.height=round((height or (84 if large else 36))*self.scale)
        self.pad=round(16*self.scale)
        self.disabled=False;self.hover=False;self.pressed=False;self.selected=False
        self.surface=self._parent_color(parent)
        requested=max(round((190 if large else 70)*self.scale),self.font.measure(text)+2*self.pad+(dp(parent,50 if large else 42) if icon else 4))
        super().__init__(parent,width=requested,height=self.height,bg=self.surface,bd=0,
                         highlightthickness=0,cursor='hand2',takefocus=takefocus,**kwargs)
        self.bind('<Configure>',lambda event:self.draw())
        self.bind('<Enter>',lambda event:self._set_hover(True))
        self.bind('<Leave>',lambda event:self._set_hover(False))
        self.bind('<ButtonPress-1>',lambda event:self._set_pressed(True))
        self.bind('<ButtonRelease-1>',self._release)
        self.bind('<space>',self._keyboard)
        self.bind('<Return>',self._keyboard)
        self.bind('<FocusIn>',lambda event:self.draw())
        self.bind('<FocusOut>',lambda event:self.draw())
        self.draw()

    def _parent_color(self,parent):
        try:
            if isinstance(parent,tk.Frame):return parent.cget('bg')
            return self.theme.surface if parent.cget('style') in ('Card.TFrame','Group.TFrame') else self.theme.background
        except (tk.TclError,AttributeError):return self.theme.background

    def _set_hover(self,value):
        self.hover=value;self.draw()

    def _set_pressed(self,value):
        self.pressed=value;self.draw()

    def _release(self,event):
        was_pressed=self.pressed;self.pressed=False;self.draw()
        if was_pressed and not self.disabled and 0<=event.x<self.winfo_width() and 0<=event.y<self.winfo_height():
            if self.command:self.command()

    def _keyboard(self,event):
        if not self.disabled and self.command:self.command()
        return 'break'

    def state(self,states=None):
        if states is None:return ('disabled',) if self.disabled else ()
        before=(self.selected,self.disabled)
        for value in states:
            if value=='pressed':self.selected=True
            elif value=='!pressed':self.selected=False
            elif value=='disabled':self.disabled=True
            elif value=='!disabled':self.disabled=False
        if before!=(self.selected,self.disabled):self.draw()

    def configure(self,cnf=None,**kwargs):
        if cnf:return super().configure(cnf,**kwargs)
        if not kwargs:return super().configure()
        before=(self.text,self.icon,self.keycap,self.disabled)
        if 'text' in kwargs:self.text=kwargs.pop('text')
        for key in ('icon','keycap'):
            if key in kwargs:setattr(self,key,kwargs.pop(key))
        if 'state' in kwargs:self.disabled=kwargs.pop('state')=='disabled'
        for key in ('bg','fg','activebackground','activeforeground'):
            kwargs.pop(key,None)
        if not kwargs and before==(self.text,self.icon,self.keycap,self.disabled):return
        if kwargs:super().configure(**kwargs)
        if hasattr(self,'font'):
            self.configure_width()
            self.draw()

    config=configure

    def cget(self,key):
        if key=='text':return self.text
        if key=='state':return 'disabled' if self.disabled else 'normal'
        return super().cget(key)

    def configure_width(self):
        width=max(round(70*self.scale),self.font.measure(self.text)+2*self.pad+(round(50*self.scale) if self.icon else 4))
        if width!=int(super().cget('width')):super().configure(width=width)

    def _rounded(self,x0,y0,x1,y1,r,fill,outline):
        self.create_rectangle(x0+r,y0,x1-r,y1,fill=fill,outline='')
        self.create_rectangle(x0,y0+r,x1,y1-r,fill=fill,outline='')
        for x,y,a in ((x0,y0,90),(x1-2*r,y0,0),(x1-2*r,y1-2*r,270),(x0,y1-2*r,180)):
            self.create_arc(x,y,x+2*r,y+2*r,start=a,extent=90,style='pieslice',fill=fill,outline='')
        if outline:
            self.create_arc(x0,y0,x0+2*r,y0+2*r,start=90,extent=90,style='arc',outline=outline)
            self.create_arc(x1-2*r,y0,x1,y0+2*r,start=0,extent=90,style='arc',outline=outline)
            self.create_arc(x1-2*r,y1-2*r,x1,y1,start=270,extent=90,style='arc',outline=outline)
            self.create_arc(x0,y1-2*r,x0+2*r,y1,start=180,extent=90,style='arc',outline=outline)
            self.create_line(x0+r,y0,x1-r,y0,fill=outline)
            self.create_line(x0+r,y1,x1-r,y1,fill=outline)
            self.create_line(x0,y0+r,x0,y1-r,fill=outline)
            self.create_line(x1,y0+r,x1,y1-r,fill=outline)

    def draw(self):
        self.delete('all');t=self.theme
        w=max(2,self.winfo_width());h=max(2,self.winfo_height())
        if w<5 or h<5:return
        if self.variant=='Nav.TButton':
            fill=t.accent if self.selected else (t.border if self.hover or self.pressed else self.surface)
            foreground=t.accent_text if self.selected else t.text;border=''
        elif self.variant=='Primary.TButton':
            fill=t.accent_hover if self.hover or self.pressed else t.accent;foreground=t.accent_text;border=''
        elif self.variant=='Danger.TButton':
            fill=t.secondary if self.hover or self.pressed else t.surface;foreground=t.danger;border=t.border
        else:
            fill=t.selection if self.selected else (t.secondary if self.hover or self.pressed else t.surface)
            foreground=t.text;border=t.border if not self.selected else t.accent
        if self.disabled:
            foreground='#ffffff' if self.variant=='Primary.TButton' else t.disabled
            fill=('#bbd5ff' if t==LIGHT else '#254b79') if self.variant=='Primary.TButton' else t.secondary
            if self.variant=='Danger.TButton':foreground='#ee9696'
        radius=min(round((12 if h>round(50*self.scale) else 9)*self.scale),h//2-1)
        rounded_surface(self,w,h,radius,fill,border,self.surface)
        icon_size=30 if self.height>60*self.scale else 22
        icon_space=round((icon_size+12)*self.scale) if self.icon else 0
        cap_space=round(78*self.scale) if self.keycap and w>680*self.scale else 0
        available=max(20,w-2*self.pad-icon_space-cap_space)
        text_width=min(self.font.measure(self.text),available)
        x=self.pad if self.align=='left' else max(self.pad,(w-icon_space-text_width-cap_space)/2)
        if self.icon:
            self._icon=icon_image(self,self.icon,icon_size,foreground)
            self.create_image(x+round(icon_size*self.scale)/2,h/2,image=self._icon)
        self.create_text(x+icon_space,h/2,text=self.text,font=self.font,fill=foreground,
                         width=available,anchor='w',justify='left' if self.align=='left' else 'center')
        if cap_space:
            cx=w-self.pad-round(54*self.scale)
            self._rounded(cx,h/2-round(23*self.scale),w-self.pad,h/2+round(23*self.scale),round(7*self.scale),fill,'#b8dcff')
            self.create_text((cx+w-self.pad)/2,h/2,text=self.keycap,font=('Segoe UI',13),fill=foreground)
        if self.focus_get()==self:self.create_rectangle(2,2,w-3,h-3,outline=t.accent)
