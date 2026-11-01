"""Three-section settings UI built on the application's existing Tkinter stack."""
import math
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, colorchooser
from PIL import Image, ImageTk
import numpy as np

from settings_help import Tooltip,Choice,HELP
from ui_style import configure_styles,AppSwitch,RoundedButton,RoundedPanel,ValueScale,icon_label,dp,UI_SCALE
from recording_overlay import RecordingOverlay,MonitorInfo,u
from model_manager import MODELS,installed
from platform_features import set_autostart
from text_processing import format_ending
from storage import DEFAULTS
from app_paths import BASE
import ctypes


class SettingsWindow:
    sections=('Dictation','Recognition','Application')
    def __init__(self,app):
        self.app=app; self.t=app.t; self.vars={}; self.pages={}; self.scrolls={}
        self.alive=True; self.jobs={}; self.preview_image=None; self.preview_dirty=True
        self.window=tk.Toplevel(app.root); app.settings_window=self.window
        w=self.window; w.title(self.t('Settings'))
        theme=configure_styles(w,app.store.settings.get('ui_theme','system'));self.theme=theme
        w.configure(bg=theme.background)
        info=MonitorInfo(); info.size=ctypes.sizeof(info)
        if u.GetMonitorInfoW(u.MonitorFromWindow(app.root.winfo_id(),2),ctypes.byref(info)):
            left,top,right,bottom=info.work.left,info.work.top,info.work.right,info.work.bottom
        else: left,top,right,bottom=0,0,w.winfo_screenwidth(),w.winfo_screenheight()
        dpi=w.winfo_fpixels('1i')/96.
        width=min(round(1100*dpi),right-left-32); height=min(round(825*dpi),bottom-top-64)
        w.geometry(f'{width}x{height}+{left+(right-left-width)//2}+{top+20}')
        w.minsize(min(dp(w,850),width),min(dp(w,600),height))
        outer=ttk.Frame(w,style='Settings.TFrame'); outer.pack(fill='both',expand=True)
        side_width=dp(w,220)
        side=tk.Frame(outer,bg=theme.secondary,width=side_width,padx=dp(w,10),pady=dp(w,45)); side.pack(side='left',fill='y'); side.pack_propagate(False)
        tk.Label(side,text=self.t('Settings'),bg=theme.secondary,fg=theme.text,font=('Segoe UI',18,'bold')).pack(anchor='w',padx=dp(w,8),pady=(0,dp(w,15)))
        self.nav={}
        for key,icon in zip(self.sections,('mic','document','settings')):
            button=self.button(side,text=self.t(key),icon=icon,align='left',height=48,style='Nav.TButton',command=lambda key=key:self.select(key))
            button.pack(fill='x',pady=dp(w,3)); self.nav[key]=button
        right=ttk.Frame(outer,style='Settings.TFrame'); right.pack(side='left',fill='both',expand=True)
        footer=ttk.Frame(right,padding=(dp(w,20),dp(w,10),dp(w,16),dp(w,16))); footer.pack(side='bottom',fill='x')
        self.notice=tk.StringVar()
        notice=ttk.Label(right,textvariable=self.notice,wraplength=600,foreground=theme.muted)
        def show_notice(*args):
            if self.notice.get():notice.pack(side='bottom',fill='x',padx=dp(w,24),before=footer)
            else:notice.pack_forget()
        self.notice.trace_add('write',show_notice)
        self.button(footer,text=self.t('Cancel'),command=self.close).pack(side='right',padx=(8,0))
        self.button(footer,text=self.t('Save'),command=self.save,style='Primary.TButton').pack(side='right')
        self.content=ttk.Frame(right,style='Settings.TFrame'); self.content.pack(fill='both',expand=True)
        descriptions=['Record your voice, choose keys and decide how text is inserted.','Choose a speech recognition model.','Appearance, background work and language.']
        for key,description in zip(self.sections,descriptions):
            page=ttk.Frame(self.content,style='Settings.TFrame'); self.pages[key]=page
            canvas=tk.Canvas(page,bg=theme.background,highlightthickness=0)
            scrollbar=ttk.Scrollbar(page,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set); scrollbar.pack(side='right',fill='y'); canvas.pack(side='left',fill='both',expand=True)
            inner=ttk.Frame(canvas,style='Settings.TFrame',padding=(dp(w,22),dp(w,14),dp(w,16),0));inner._section=key; handle=canvas.create_window((0,0),window=inner,anchor='nw')
            def update_layout(canvas=canvas,handle=handle,inner=inner,key=key):
                self.jobs.pop('layout_'+key,None)
                width=canvas.winfo_width()
                if int(float(canvas.itemcget(handle,'width')))!=width:canvas.itemconfigure(handle,width=width)
                region=canvas.bbox('all')
                if region!=getattr(canvas,'_last_region',None):
                    canvas.configure(scrollregion=region);canvas._last_region=region
            def layout(event,canvas=canvas,key=key,update_layout=update_layout):
                if 'layout_'+key not in self.jobs:self.jobs['layout_'+key]=canvas.after_idle(update_layout)
            # Reserve the scrollbar gutter, so its appearance cannot make a row
            # cross a wrapping breakpoint and start a geometry feedback loop.
            inner.bind('<Configure>',layout);canvas.bind('<Configure>',layout)
            ttk.Label(inner,text=self.t(key),font=('Segoe UI',23,'bold'),background=theme.background).pack(anchor='w',padx=dp(w,6),pady=(0,dp(w,3 if key=='Dictation' else 10)))
            self.tip(inner.winfo_children()[-1],description)
            if key=='Dictation':
                ttk.Label(inner,text=self.t('Voice becomes text.'),style='PageMuted.TLabel',font=('Segoe UI',10)).pack(anchor='w',padx=dp(w,6),pady=(0,dp(w,4)))
            self.scrolls[key]=canvas
            if key=='Dictation': self.build_dictation(inner)
            elif key=='Recognition': self.build_recognition(inner)
            else: self.build_application(inner)
        self.current=None; self.select('Dictation')
        w.bind('<MouseWheel>',lambda event:self.scrolls[self.current].yview_scroll(-int(event.delta/120),'units'))
        w.bind('<Escape>',lambda event:self.cancel_capture())
        w.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh(); self.animate()

    def call(self,callback):
        try: return callback()
        except Exception: self.notice.set(self.t('Could not complete this action. Please try again.'))

    def button(self,parent,**kwargs):
        kwargs.setdefault('style','Settings.TButton')
        return RoundedButton(parent,**kwargs)


    def select(self,key):
        if self.current: self.pages[self.current].pack_forget()
        self.current=key; self.pages[key].pack(fill='both',expand=True)
        for name,button in self.nav.items(): button.state(['pressed'] if name==key else ['!pressed'])

    def group(self,parent,title,description=''):
        panel=RoundedPanel(parent,padding=8);panel.pack(fill='x',pady=(0,dp(parent,10)))
        card=panel.content;card._panel=panel;card._rows=0;card._section=getattr(parent,'_section','')
        label=ttk.Label(card,text=self.t(title),font=('Segoe UI',14,'bold'),style='Card.TLabel'); label.pack(anchor='w',pady=(0,dp(parent,1)))
        if description:
            self.tip(label,description)
        return card

    def tip(self,widget,key):
        Tooltip(widget,self.t(key)); return widget

    def row(self,parent,title,description=''):
        help_key={'How to start recording':'Recording mode','Cue volume':'Sound volume','Background blur':'Glass blur','Start with Windows':'Start with Windows (in tray)'}.get(title,title)
        help_text=description or HELP.get(help_key,('',''))[0]
        if getattr(parent,'_rows',0):ttk.Frame(parent,style='Divider.TFrame',height=1).pack(fill='x')
        parent._rows=getattr(parent,'_rows',0)+1
        frame=ttk.Frame(parent,style='Card.TFrame'); frame.pack(fill='x',pady=dp(parent,6 if getattr(parent,'_section','')=='Application' else 3))
        frame.columnconfigure(0,weight=1)
        left=ttk.Frame(frame,style='Card.TFrame'); left.grid(row=0,column=0,sticky='ew',padx=(0,dp(parent,16)))
        label=ttk.Label(left,text=self.t(title),style='Card.TLabel',wraplength=dp(parent,380)); label.pack(anchor='w')
        if help_text:self.tip(label,help_text)
        controls=ttk.Frame(frame,style='Card.TFrame'); controls.grid(row=0,column=1,sticky='e')
        def update_row():
            self.jobs.pop('row_'+str(frame),None)
            width=frame.winfo_width()
            if width<dp(frame,100) or not self.window.winfo_viewable():return
            stacked=width<dp(frame,600)
            wrap=max(dp(frame,130),width-dp(frame,8)) if stacked else max(dp(frame,130),min(round(width*.55),width-controls.winfo_reqwidth()-dp(frame,25)))
            if int(label.cget('wraplength'))!=wrap:label.configure(wraplength=wrap)
            if getattr(controls,'_stacked',None)!=stacked:
                controls._stacked=stacked
                if stacked:controls.grid_configure(row=1,column=0,sticky='ew',pady=(dp(frame,7),0))
                else:controls.grid_configure(row=0,column=1,sticky='e',pady=0)
        def resize(event):
            key='row_'+str(frame)
            previous=self.jobs.pop(key,None)
            if previous:frame.after_cancel(previous)
            self.jobs[key]=frame.after(60,update_row)
        frame.bind('<Configure>',resize)
        return controls

    def boolean(self,parent,title,key,description=''):
        var=tk.BooleanVar(value=bool(self.app.store.settings.get(key,DEFAULTS.get(key,False)))); self.vars[key]=var
        controls=self.row(parent,title,description)
        button=AppSwitch(controls,var,self.theme)
        button.pack(anchor='e'); self.tip(button,description or title)
        return var

    def combo(self,parent,title,key,options,description='',labels=None):
        value=self.app.store.settings.get(key,options[0])
        if value not in options: value=options[0]
        choice=Choice(value,options,self.t); self.vars[key]=choice
        if labels:
            choice.labels=[self.t(labels.get(option,str(option))) for option in options]
            choice.variable.set(choice.labels[options.index(value)])
        controls=self.row(parent,title,description)
        shell=RoundedPanel(controls,padding=7,radius=8);shell.pack(fill='x')
        combo=ttk.Combobox(shell.content,textvariable=choice.variable,values=choice.labels,state='readonly',width=27,style='Settings.TCombobox')
        combo.pack(fill='x'); self.tip(combo,description or title)
        return choice,combo

    def slider(self,parent,title,key,start,end,description='',suffix='%'):
        var=tk.DoubleVar(value=float(self.app.store.settings[key])); self.vars[key]=var
        controls=self.row(parent,title,description)
        text=tk.StringVar(); label=ttk.Label(controls,textvariable=text,style='Card.TLabel',width=5,anchor='e'); label.pack(side='right',padx=(8,0))
        scale=ValueScale(controls,from_=start,to=end,variable=var,length=220); scale.pack(side='left'); self.tip(scale,description or title)
        def update(*args): text.set(f'{round(var.get()*(100 if end==1 else 1))}{suffix}')
        var.trace_add('write',update); update()
        return var,scale

    def build_dictation(self,parent):
        group=self.group(parent,'Recording')
        self.combo(group,'How to start recording','trigger_mode',['hold','toggle'],labels={'hold':'Hold the shortcut','toggle':'Press to start and finish'})
        self.app.pending_shortcuts={key:value for key,value in self.app.store.settings['shortcuts'].items() if key in ('dictate','history')}
        self.shortcut_row(group,'Recording shortcut','dictate','Choose the keys used to start and stop recording.')
        text=self.group(parent,'Text insertion')
        auto=self.boolean(text,'Paste automatically','auto_paste','After recognition, text appears in the field where your cursor was.')
        ending,ending_widget=self.combo(text,'What to add after text','ending',['space','period_space','period_enter'],
            'Enter can send a message in the active application.',labels={'space':'Space','period_space':'Punctuation and space','period_enter':'Punctuation and Enter'})
        self.ending_preview=tk.StringVar()
        ttk.Label(text,textvariable=self.ending_preview,style='Muted.TLabel',padding=(0,8)).pack(anchor='w')
        def insertion(*args):
            state='readonly' if auto.get() else 'disabled'
            ending_widget.configure(state=state)
            result,enter=format_ending(self.t('Hello world'),ending.get())
            self.ending_preview.set(self.t('Result preview')+': '+result+(' ↵' if enter else '␣'))
        auto.trace_add('write',insertion); ending.variable.trace_add('write',insertion); insertion()
        self.shortcut_row(group,'History shortcut','history')
        mic=self.group(parent,'Microphone')
        self.app.refresh_devices()
        names=list(self.app.device['values'])[1:]
        selected=self.app.store.settings.get('microphone','')
        if selected and selected not in names: names.append(selected)
        self.combo(mic,'Microphone','microphone',['']+names,labels={'':'Default microphone',**{name:name for name in names}})
        self.boolean(mic,'Automatically choose another microphone','microphone_fallback','If your microphone disconnects, switch to the default Windows microphone.')
        self.boolean(mic,'Lower other sounds','mute_recording','During recording, other computer sounds become quieter.')
        sound=self.group(parent,'Recording cues')
        self.boolean(sound,'Recording sounds','sounds','Play a sound when recording starts and finishes.')
        controls=self.row(sound,'Preview sound')
        for kind,title in [('start','Start recording sound'),('stop','End recording sound')]:
            self.button(controls,text=self.t(title),icon='play',font=('Segoe UI',10),height=32,command=lambda kind=kind:self.app.audio_cues.play(kind,self.vars['sound_volume'].get())).pack(side='left',padx=3)
        self.slider(sound,'Cue volume','sound_volume',0,100)

    def shortcut_row(self,parent,title,key,description=''):
        controls=self.row(parent,title,description or 'Press keys, release them, or press Esc to cancel.')
        var=tk.StringVar(value=self.app.chord_text(self.app.pending_shortcuts.get(key,[])) or self.t('Not assigned'))
        if not hasattr(self,'shortcut_labels'):self.shortcut_labels={}
        self.shortcut_labels[key]=var
        ttk.Label(controls,textvariable=var,background=self.theme.secondary,foreground=self.theme.text,padding=(dp(controls,10),dp(controls,7)),font=('Segoe UI',10)).pack(side='left',padx=(0,dp(controls,10)))
        buttons=ttk.Frame(controls,style='Card.TFrame'); buttons.pack(side='left')
        def capture():
            if self.app.recording or self.app.busy or self.app.loading_model:
                self.notice.set(self.t('Finish current work before applying settings.')); return
            if not self.app.hotkey.thread.is_alive():
                self.notice.set(self.t('Loading model…')); return
            self.app.capture_action=(key,var); self.app.hotkey.captured.clear(); self.app.hotkey.capture=True
            var.set(self.t('Capture')+'…'); self.notice.set(self.t('Press keys, release them, or press Esc to cancel.'))
        def reset():
            self.cancel_capture()
            self.app.pending_shortcuts[key]=list(DEFAULTS['shortcuts'].get(key,[]))
            var.set(self.app.chord_text(self.app.pending_shortcuts[key]) or self.t('Not assigned'))
        self.button(buttons,text=self.t('Change'),font=('Segoe UI',10),height=33,command=capture).pack(side='left',padx=3)
        self.button(buttons,text=self.t('Restore default'),font=('Segoe UI',10),height=33,command=reset).pack(side='left')

    def build_recognition(self,parent):
        group=self.group(parent,'Speech recognition model','Download a model once before using it. Recognition then runs locally on your computer.')
        self.combo(group,'Expected language','speech_language',['auto','ru','en'])
        self.model_rows={};self.model_checks={}
        for key,spec in MODELS.items():
            names={'parakeet':('Speed','Parakeet v3','lightning'),'whisper':('Accuracy','Whisper Small','wave'),'gigaam':('Russian speech','GigaAM v2','globe')}
            title,model,icon=names[key]
            controls=self.row(group,self.t(title)+' · '+model,f"{spec['size']/1e6:.0f} {self.t('MB')} · {self.t('One-time download; the size below is the download size.')}")
            controls.master.pack_configure(pady=dp(group,14))
            left=controls.master.winfo_children()[0];label=left.winfo_children()[0]
            label.pack_forget()
            badge=RoundedPanel(left,padding=8,radius=9,fill=self.theme.secondary,border=False);badge.pack(side='left',padx=(0,dp(group,16)))
            icon_label(badge.content,icon,28,background=self.theme.secondary).pack()
            label.pack(side='left',anchor='center')
            state=tk.StringVar(); ttk.Label(controls,textvariable=state,style='Muted.TLabel').pack(side='left',padx=(0,dp(group,15)))
            progress=ttk.Progressbar(group,length=200,maximum=100)
            buttons=ttk.Frame(controls,style='Card.TFrame'); buttons.pack(side='left')
            download=self.button(buttons,text=self.t('Download'),command=lambda key=key:self.call(lambda:self.app.download_model(key)))
            use=self.button(buttons,text=self.t('Use'),command=lambda key=key:self.call(lambda:self.app.switch_model(key)))
            remove=self.button(buttons,text=self.t('Remove'),command=lambda key=key:self.call(lambda:self.app.remove_model(key)))
            cancel=self.button(buttons,text=self.t('Cancel'),command=self.app.model_cancel.set)
            for button in (download,use,remove,cancel): button.pack(side='left',padx=2)
            check=icon_label(buttons,'success',27,self.theme.accent);self.model_checks[key]=check
            self.model_rows[key]=(state,progress,download,use,remove,cancel)
        self.app.model_progress=tk.StringVar()
        self.download_message=tk.StringVar(); ttk.Label(group,textvariable=self.download_message,style='Muted.TLabel',wraplength=640).pack(anchor='w')
    def build_application(self,parent):
        appearance=self.group(parent,'Appearance')
        self.combo(appearance,'Application theme','ui_theme',['system','light','dark'],
                   'Choose a light or dark appearance, or follow Windows.',
                   labels={'system':'System','light':'Light','dark':'Dark'})
        indicator=self.group(parent,'Recording indicator')
        self.boolean(indicator,'Show recording indicator','capsule_enabled','A small capsule with a sound wave appears while recording.')
        self.slider(indicator,'Background blur','glass_blur',0,1)
        ttk.Label(indicator,text=self.t('No blur')+'  —  '+self.t('Strong blur'),style='Muted.TLabel').pack(anchor='e')
        color=self.row(indicator,'Wave color')
        self.vars['wave_color']=tk.StringVar(value=self.app.store.settings['wave_color'].lower())
        for value in ('#ffffff','#93c5fd','#86efac','#f9a8d4'):
            tk.Button(color,bg=value,activebackground=value,width=3,relief='solid',borderwidth=1,
                      command=lambda value=value:self.vars['wave_color'].set(value),takefocus=True).pack(side='left',padx=3)
        self.button(color,text=self.t('Custom color'),command=self.choose_color).pack(side='left',padx=5)
        self.preview=ttk.Label(indicator,style='Card.TLabel'); self.preview.pack(anchor='center',pady=8)
        self.tip(self.preview,'Demo wave — the microphone is not used.')
        self.renderer=RecordingOverlay.__new__(RecordingOverlay)
        for key in ('wave_color','glass_blur'): self.vars[key].trace_add('write',lambda *args:setattr(self,'preview_dirty',True))
        behaviour=self.group(parent,'Application behaviour')
        self.boolean(behaviour,'Start with Windows','autostart')
        self.boolean(behaviour,'Keep working in the background','background_mode','Closing the window keeps dictation running. Reopen it from the icon near the Windows clock.')
        self.boolean(behaviour,'Pause dictation','paused','Temporarily disable recording shortcuts without closing the app.')
        language=self.group(parent,'Language')
        self.combo(language,'Language','language',['ru','en'],labels={'ru':'Russian','en':'English'})


    def choose_color(self):
        value=colorchooser.askcolor(self.vars['wave_color'].get(),parent=self.window,title=self.t('Wave color'))[1]
        if value:self.vars['wave_color'].set(value.lower())

    def refresh(self):
        if not self.alive:return
        previous=self.jobs.pop('refresh',None)
        if previous:self.window.after_cancel(previous)
        try:
            busy=self.app.busy or self.app.recording or self.app.loading_model
            for key,(state,bar,download,use,remove,cancel) in self.model_rows.items():
                downloaded=installed(BASE/'models',key); data=self.app.model_states.get(key,{})
                status='In use' if key==self.app.active_model and self.app.engine else ('Downloading model' if data.get('state')=='Downloading model' else ('Model ready' if downloaded else data.get('state','Not downloaded')))
                state.set(self.t(status))
                fetching=status=='Downloading model'
                if fetching:bar.pack(fill='x',pady=5,after=download.master.master.master)
                else:bar.pack_forget()
                check=self.model_checks[key]
                if status=='In use':check.pack(side='left',padx=dp(check,6))
                else:check.pack_forget()
                if fetching and data.get('stage')=='Extracting':
                    if str(bar.cget('mode'))!='indeterminate':bar.configure(mode='indeterminate'); bar.start(15)
                else:
                    bar.stop(); bar.configure(mode='determinate')
                    bar['value']=100*data.get('done',0)/max(1,data.get('total',1)) if fetching else (100 if downloaded else 0)
                actions=[(download,not downloaded and not fetching,not self.app.downloading),
                         (use,downloaded and (key!=self.app.active_model or not self.app.engine),not busy),
                         (remove,downloaded and key!=self.app.active_model,not busy and not self.app.downloading),
                         (cancel,fetching,True)]
                for button,visible,enabled in actions:
                    if visible and not button.winfo_manager():button.pack(side='left',padx=dp(button,2))
                    elif not visible and button.winfo_manager():button.pack_forget()
                    button.configure(state='normal' if enabled else 'disabled')
            self.download_message.set(self.app.model_progress.get() if getattr(self.app,'model_progress',None) else '')
        except Exception:self.notice.set(self.t('Could not complete this action. Please try again.'))
        self.jobs['refresh']=self.window.after(400,self.refresh)

    def animate(self):
        if not self.alive:return
        if self.current=='Application':
            if self.preview_dirty:
                w,h=RecordingOverlay.width,RecordingOverlay.height
                y=np.linspace(0,1,h)[:,None,None]
                backdrop=np.broadcast_to(np.array([32,48,72])[None,None,:]*(1-y)+np.array([98,114,133])[None,None,:]*y,(h,w,3)).copy()
                self.renderer.wave_color=self.vars['wave_color'].get()
                self.renderer.backdrop_blur_mix=self.vars['glass_blur'].get()
                self.renderer.prepare_surface(Image.fromarray(np.uint8(backdrop)))
                self.preview_dirty=False
            t=time.monotonic()
            image=self.renderer.render(t,.3+.23*math.sin(t*2))
            image=image.resize((round(image.width*UI_SCALE),round(image.height*UI_SCALE)),Image.Resampling.LANCZOS)
            self.preview_image=ImageTk.PhotoImage(image,master=self.window); self.preview.configure(image=self.preview_image)
        self.jobs['animate']=self.window.after(40 if self.current=='Application' else 200,self.animate)

    def cancel_capture(self):
        self.app.hotkey.capture=False; self.app.hotkey.captured.clear()
        self.app.handle_event('shortcut_cancel',None)

    def save(self):
        if self.app.busy or self.app.recording or self.app.loading_model:
            self.notice.set(self.t('Finish current work before applying settings.')); return
        changes={key:value.get() for key,value in self.vars.items()}
        valid={key:keys for key,keys in self.app.pending_shortcuts.items() if keys}
        if not valid.get('dictate'):
            self.notice.set(self.t('Assign a dictation shortcut.')); return
        values=[frozenset(keys) for keys in valid.values()]
        if len(values)!=len(set(values)):
            self.notice.set(self.t('This shortcut is already assigned to another action.')); return
        changes['shortcuts']=valid
        changes['sound_volume']=round(changes['sound_volume']); changes['wave_color']=changes['wave_color'].lower()
        previous=dict(self.app.store.settings)
        try:
            if changes['autostart']!=previous['autostart']:set_autostart(changes['autostart'],BASE.parent/'Launch.vbs')
            try:self.app.store.save(changes)
            except Exception:
                if changes['autostart']!=previous['autostart']:set_autostart(previous['autostart'],BASE.parent/'Launch.vbs')
                raise
        except Exception:
            self.notice.set(self.t('Could not save settings. Your previous settings are preserved.')); return
        app=self.app; language_changed=changes['language']!=previous['language'] or changes['ui_theme']!=previous.get('ui_theme','system')
        app.auto_paste.set(changes['auto_paste']); app.configure_bindings(); app.configure_overlay()
        if changes['paused']!=app.paused:app.toggle_pause()
        app.refresh_devices(); app.enable_controls(); app.update_hotkey()
        if app.tray:app.tray.set_language(changes['language'])
        if language_changed:
            app.rebuild_views(translate=changes['language']!=previous['language'])
        else:self.notice.set(self.t('Saved changes.'))
        if changes['speech_language']!=previous['speech_language'] and app.active_model=='whisper':app.switch_model('whisper')

    def close(self):
        if not self.alive:return
        self.alive=False; self.cancel_capture()
        for job in self.jobs.values():
            try:self.window.after_cancel(job)
            except tk.TclError:pass
        self.app.settings_window=None
        self.window.destroy()
        for value in self.vars.values():
            variable=value.variable if isinstance(value,Choice) else value
            for modes,callback in variable.trace_info():variable.trace_remove(modes,callback)
