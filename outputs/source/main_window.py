"""Main dictation workspace with persistent sidebar navigation."""
import ctypes
import tkinter as tk
from tkinter import ttk
from ui_style import configure_styles,RoundedButton,RoundedPanel,icon_label,icon_image,dp
from recording_overlay import MonitorInfo,u


def build_main(app):
    root=app.root;root.app_ref=app
    ttk.Style(root).theme_use('clam')
    theme=configure_styles(root,app.store.settings.get('ui_theme','system'))
    root.configure(bg=theme.background);root.option_add('*Font',('Segoe UI',11))
    info=MonitorInfo();info.size=ctypes.sizeof(info)
    if u.GetMonitorInfoW(u.MonitorFromWindow(root.winfo_id(),2),ctypes.byref(info)):
        left,top,right,bottom=info.work.left,info.work.top,info.work.right,info.work.bottom
    else:left,top,right,bottom=0,0,root.winfo_screenwidth(),root.winfo_screenheight()
    width=min(dp(root,1100),right-left-40);height=min(dp(root,825),bottom-top-64)
    root.geometry(f'{width}x{height}+{left+(right-left-width)//2}+{top+(bottom-top-height)//2}')
    root.minsize(min(dp(root,850),width),min(dp(root,580),height))
    side=tk.Frame(root,bg=theme.secondary,width=dp(root,210));side.pack(side='left',fill='y');side.pack_propagate(False)
    brand=tk.Frame(side,bg=theme.secondary);brand.pack(fill='x',padx=dp(root,22),pady=(dp(root,30),dp(root,15)))
    tk.Label(brand,text='VoxPad',font=('Segoe UI',19,'bold'),bg=theme.secondary,fg=theme.text).pack(anchor='w')
    from app_features import VERSION
    tk.Label(brand,text=VERSION,font=('Segoe UI',11),bg=theme.secondary,fg=theme.muted).pack(anchor='w')
    app.main_nav={}
    for title,icon,callback in [('Dictation','mic',lambda:app.text.focus_set()),('History','history',app.open_history),
            ('Recording recovery','recovery',app.open_recovery),('File transcription','document',app.open_files),
            ('Statistics','statistics',app.open_statistics)]:
        b=RoundedButton(side,text=app.t(title),icon=icon,align='left',style='Nav.TButton',height=55,
                        command=callback,font=('Segoe UI',11))
        b.pack(fill='x',padx=dp(root,10),pady=dp(root,3));app.main_nav[title]=b
        if title=='Dictation':b.state(['pressed'])
    outer=ttk.Frame(root,style='Settings.TFrame',padding=(dp(root,26),dp(root,20),dp(root,18),dp(root,18)))
    outer.pack(side='left',fill='both',expand=True)
    tools=ttk.Frame(outer,style='Settings.TFrame');tools.pack(fill='x',pady=(0,dp(root,18)))
    RoundedButton(tools,text=app.t('Settings'),icon='settings',height=50,command=app.open_settings).pack(side='right')
    app.pause_button=RoundedButton(tools,text=app.t('Resume dictation') if app.paused else app.t('Pause dictation'),
                                  icon='play' if app.paused else 'pause',height=50,command=app.toggle_pause)
    app.pause_button.pack(side='left')
    panel=RoundedPanel(outer,padding=18);panel.pack(fill='x',pady=(0,dp(root,12)))
    state=panel.content
    app.status_icon=icon_label(state,'success',25,'#12b84a');app.status_icon.pack(side='left',anchor='n',padx=(0,dp(root,18)))
    status_icon=app.status_icon
    def status_changed(*args):
        value=app.status.get()
        if value in (app.t('Ready'),app.t('Done')):name,color='success','#12b84a'
        elif value==app.t('Error'):name,color='warning',theme.danger
        elif value==app.t('Paused'):name,color='pause',theme.muted
        else:name,color='mic',theme.accent
        status_icon.configure(image=icon_image(status_icon,name,25,color))
    trace=app.status.trace_add('write',status_changed)
    status_icon.bind('<Destroy>',lambda event:app.status.trace_remove('write',trace))
    status_changed()
    lines=tk.Frame(state,bg=theme.surface);lines.pack(fill='x',expand=True)
    ttk.Label(lines,textvariable=app.status,style='Card.TLabel',font=('Segoe UI',20,'bold')).pack(anchor='w')
    detail=ttk.Label(lines,textvariable=app.detail,style='Muted.TLabel',font=('Segoe UI',11),wraplength=600)
    detail.pack(anchor='w',pady=(dp(root,3),0))
    ttk.Label(lines,textvariable=app.metrics,style='Muted.TLabel',font=('Segoe UI',11)).pack(anchor='w',pady=(dp(root,12),0))
    lines.bind('<Configure>',lambda event:detail.configure(wraplength=max(150,event.width)))
    app.record_button=RoundedButton(outer,text=app.t('Loading model…'),font=('Segoe UI',18,'bold'),
                                   icon='mic',style='Primary.TButton',large=True,keycap='Ctrl')
    app.record_button.configure(state='disabled');app.record_button.pack(fill='x',pady=(0,dp(root,15)))
    app.record_button.bind('<ButtonPress-1>',app.mouse_press)
    if not getattr(app,'_mouse_release_bound',False):
        root.bind_all('<ButtonRelease-1>',app.mouse_release,add='+');app._mouse_release_bound=True
    editor=RoundedPanel(outer,padding=12);editor.pack(fill='both',expand=True)
    ttk.Label(editor.content,text=app.t('Recognised text'),style='Muted.TLabel').pack(anchor='w',pady=(0,dp(root,8)))
    text_frame=tk.Frame(editor.content,bg=theme.surface);text_frame.pack(fill='both',expand=True)
    scrollbar=ttk.Scrollbar(text_frame,orient='vertical');scrollbar.pack(side='right',fill='y')
    app.text=tk.Text(text_frame,wrap='word',bg=theme.surface,fg=theme.text,insertbackground=theme.accent,
                     selectbackground=theme.selection,relief='flat',bd=0,padx=4,pady=4,font=('Segoe UI',12),
                     undo=True,height=2,yscrollcommand=scrollbar.set)
    app.text.pack(fill='both',expand=True);scrollbar.configure(command=app.text.yview)
    app.device=ttk.Combobox(root,state='readonly')
