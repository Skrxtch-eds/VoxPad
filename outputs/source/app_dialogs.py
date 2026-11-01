"""Small application-themed confirmations and notices."""
import ctypes
import tkinter as tk
from tkinter import ttk
from ui_style import configure_styles,RoundedButton,UI_SCALE


def _dialog(title,message,kind='info',parent=None):
    parent=parent or tk._default_root
    if parent is None:return False
    root=parent.winfo_toplevel()
    mode=getattr(root,'theme_mode','system')
    window=tk.Toplevel(root)
    theme=configure_styles(window,mode)
    window.title(title)
    window.configure(bg=theme.background)
    window.resizable(False,False)
    window.transient(root)
    window.withdraw()
    result=tk.BooleanVar(master=window,value=False)
    unit=lambda value:round(value*UI_SCALE)
    card=ttk.Frame(window,style='Settings.TFrame',padding=unit(24))
    card.pack(fill='both',expand=True)
    ttk.Label(card,text=title,font=('Segoe UI',15,'bold'),wraplength=unit(480)).pack(anchor='w')
    ttk.Label(card,text=message,font=('Segoe UI',10),wraplength=unit(480)).pack(anchor='w',pady=(unit(12),unit(22)))
    bar=ttk.Frame(card,style='Settings.TFrame');bar.pack(fill='x')
    app=getattr(tk._default_root,'app_ref',None)
    ru=bool(app and app.store.settings.get('language')=='ru')
    def close(accepted=False):
        result.set(accepted);window.destroy()
    if kind=='question':
        RoundedButton(bar,text='Нет' if ru else 'No',command=lambda:close(False)).pack(side='right')
        RoundedButton(bar,text='Да' if ru else 'Yes',style='Primary.TButton',command=lambda:close(True)).pack(side='right',padx=(0,8))
    else:
        RoundedButton(bar,text='Понятно' if ru else 'OK',style='Primary.TButton',command=lambda:close(True)).pack(side='right')
    window.protocol('WM_DELETE_WINDOW',lambda:close(False))
    window.bind('<Escape>',lambda event:close(False))
    window.bind('<Return>',lambda event:close(True))
    window.update_idletasks()
    width=max(unit(380),min(unit(560),window.winfo_reqwidth()))
    height=window.winfo_reqheight()
    x=root.winfo_rootx()+max(0,(root.winfo_width()-width)//2)
    y=root.winfo_rooty()+max(0,(root.winfo_height()-height)//2)
    x=max(0,min(x,window.winfo_screenwidth()-width))
    y=max(0,min(y,window.winfo_screenheight()-height))
    window.geometry(f'{width}x{height}+{x}+{y}')
    try:
        preference=ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(window.winfo_id()),33,
                                                    ctypes.byref(preference),ctypes.sizeof(preference))
    except (OSError,AttributeError):pass
    window.deiconify();window.grab_set();window.focus_force();window.wait_window()
    return result.get()


class messagebox:
    @staticmethod
    def askyesno(title,message,**kwargs):return _dialog(title,message,'question',kwargs.get('parent'))
    @staticmethod
    def showinfo(title,message,**kwargs):return _dialog(title,message,'info',kwargs.get('parent'))
    @staticmethod
    def showerror(title,message,**kwargs):return _dialog(title,message,'error',kwargs.get('parent'))
