"""Dedicated history, recovery, file transcription and statistics workspaces."""
from pathlib import Path
import ctypes
import tkinter as tk
from tkinter import ttk,filedialog
from tkinter import font as tkfont
from app_dialogs import messagebox
from settings_window import SettingsWindow,BASE
from settings_actions import pending_records
from ui_style import configure_styles,RoundedPanel,icon_label,dp
from recording_overlay import MonitorInfo,u
from storage import local_recording_time

class ActivityWindow(SettingsWindow):
    def __init__(self,app,kind):
        self.app=app;self.t=app.t;self.kind=kind;self.vars={};self.alive=True;self.jobs={}
        self.history_signature=self.job_signature=self.recovery_signature=None
        self.window=tk.Toplevel(app.root);w=self.window;w.title(self.t(kind))
        self.theme=configure_styles(w,app.store.settings.get('ui_theme','system'));w.configure(bg=self.theme.background)
        info=MonitorInfo();info.size=ctypes.sizeof(info)
        if u.GetMonitorInfoW(u.MonitorFromWindow(app.root.winfo_id(),2),ctypes.byref(info)):
            self.work_area=(info.work.left,info.work.top,info.work.right,info.work.bottom)
        else:self.work_area=(0,0,w.winfo_screenwidth(),w.winfo_screenheight())
        left,top,right,bottom=self.work_area
        sizes={'History':(1050,860),'Recording recovery':(1100,780),'File transcription':(1025,885),'Statistics':(1060,850)}
        dw,dh=sizes[kind];width=min(dp(w,dw),right-left-40);height=min(dp(w,dh),bottom-top-64)
        w.geometry(f'{width}x{height}+{left+(right-left-width)//2}+{top+(bottom-top-height)//2}')
        w.minsize(min(dp(w,800),width),min(dp(w,620),height))
        self.notice=tk.StringVar()
        self.notice_label=ttk.Label(w,textvariable=self.notice,style='PageMuted.TLabel',wraplength=700,padding=12)
        self.notice.trace_add('write',self.show_notice)
        self.body=ttk.Frame(w,style='Settings.TFrame',padding=(dp(w,28),dp(w,32),dp(w,28),dp(w,28)))
        if kind=='File transcription':self.body.configure(padding=(dp(w,22),dp(w,67),dp(w,22),dp(w,14)))
        elif kind=='Recording recovery':self.body.configure(padding=(dp(w,28),dp(w,50),dp(w,28),dp(w,28)))
        self.body.pack(fill='both',expand=True)
        if kind=='History':self.build_history(self.body)
        elif kind=='File transcription':self.build_files(self.body)
        elif kind=='Statistics':self.build_stats(self.body)
        else:self.build_recovery(self.body)
        w.protocol('WM_DELETE_WINDOW',self.close);self.refresh()

    def show_notice(self,*args):
        if self.notice.get():self.notice_label.pack(side='bottom',fill='x',before=self.body)
        else:self.notice_label.pack_forget()


    def button(self,parent,**kwargs):
        kwargs.setdefault('font',('Segoe UI',15))
        return super().button(parent,**kwargs)

    def heading(self,parent,title):
        label=ttk.Label(parent,text=self.t(title),font=('Segoe UI',28,'bold'))
        label.pack(anchor='w',pady=(0,dp(parent,4)))
        return label

    def table(self,parent,columns,height=3):
        panel=RoundedPanel(parent,padding=8);panel.pack(fill='both',expand=True,pady=(dp(parent,10),0))
        area=panel.content
        scroll=ttk.Scrollbar(area,orient='vertical')
        tree=ttk.Treeview(area,columns=[c[0] for c in columns],show='headings',height=height,selectmode='browse',style='Settings.Treeview',yscrollcommand=scroll.set)
        minimums=[]
        heading_font=tkfont.Font(root=self.window,font=('Segoe UI',15))
        row_font=tkfont.Font(root=self.window,font=('Segoe UI',16))
        for name,title,width in columns:
            tree.heading(name,text=self.t(title),anchor='w')
            minimum=max(dp(parent,80),heading_font.measure(self.t(title))+dp(parent,40))
            if name=='date':minimum=max(minimum,row_font.measure('2026-10-30 16:05:55')+dp(parent,18))
            minimums.append(minimum)
            tree.column(name,width=dp(parent,width),minwidth=minimum,anchor='w',stretch=True)
        tree.pack(side='left',fill='both',expand=True)
        scroll.configure(command=tree.yview)
        scroll.pack(side='right',fill='y')
        def scroll_state(first,last):
            scroll.set(first,last)
        tree.configure(yscrollcommand=scroll_state)
        def update_columns():
            self.jobs.pop('columns_'+str(tree),None)
            available=max(1,area.winfo_width()-dp(parent,24)-scroll.winfo_width())
            if available==getattr(tree,'_last_column_width',None):return
            tree._last_column_width=available
            flexible=list(range(len(columns)));widths={};remaining=available
            while flexible:
                weight=sum(columns[i][2] for i in flexible)
                constrained=[i for i in flexible if remaining*columns[i][2]/weight<minimums[i]]
                if not constrained:
                    for i in flexible:widths[i]=round(remaining*columns[i][2]/weight)
                    break
                for i in constrained:
                    widths[i]=minimums[i];remaining-=minimums[i];flexible.remove(i)
            for i,(name,_,_) in enumerate(columns):
                if tree.column(name,'width')!=widths[i]:tree.column(name,width=widths[i])
        def fit_columns(event):
            key='columns_'+str(tree)
            if key not in self.jobs:self.jobs[key]=area.after_idle(update_columns)
        area.bind('<Configure>',fit_columns)
        return tree,panel

    def build_history(self,parent):
        heading=self.heading(parent,'History');heading.configure(font=('Segoe UI',34,'bold'))
        self.history_count=tk.StringVar();counter=ttk.Label(parent,textvariable=self.history_count,style='PageMuted.TLabel',font=('Segoe UI',16));counter.pack(anchor='w',pady=(0,dp(parent,16)))
        preview=RoundedPanel(parent,padding=14);preview.pack(fill='x',pady=(0,dp(parent,16)))
        self.history_result=tk.Text(preview.content,width=1,height=4,wrap='word',relief='flat',bd=0,font=('Segoe UI',16),bg=self.theme.surface,fg=self.theme.text,selectbackground=self.theme.selection)
        self.history_result.pack(fill='x');self.history_result.configure(state='disabled')
        self.history_recent=tk.StringVar()
        search=RoundedPanel(parent,padding=12);search.pack(fill='x',pady=(0,dp(parent,6)))
        icon_label(search.content,'search',23).pack(side='left',padx=(dp(parent,7),dp(parent,12)))
        self.query=tk.StringVar()
        field=tk.Entry(search.content,textvariable=self.query,font=('Segoe UI',16),bg=self.theme.surface,fg=self.theme.text,insertbackground=self.theme.accent,relief='flat',bd=0)
        field.pack(side='left',fill='x',expand=True)
        placeholder=tk.Label(field,text=self.t('Search'),font=('Segoe UI',16),bg=self.theme.surface,fg=self.theme.muted,bd=0)
        placeholder.place(x=1,y=0);placeholder.bind('<Button-1>',lambda e:field.focus_set())
        def query_changed(*args):
            if self.query.get() or field.focus_get()==field:placeholder.place_forget()
            else:placeholder.place(x=1,y=0)
            self.refresh_history()
        self.query.trace_add('write',query_changed)
        field.bind('<FocusIn>',lambda e:placeholder.place_forget());field.bind('<FocusOut>',lambda e:query_changed())
        bar=ttk.Frame(parent,style='Settings.TFrame');bar.pack(side='bottom',fill='x',pady=(dp(parent,20),0))
        buttons=[]
        for name,icon,callback,side in [('Copy','copy',self.copy_history,'left'),('Export TXT','export',self.export_history,'left'),('Clear history','delete',self.clear_history,'right'),('Delete','delete',self.delete_history,'right')]:
            button=self.button(bar,text=self.t(name),icon=icon,height=56,command=lambda c=callback:self.call(c),style='Danger.TButton' if name in ('Delete','Clear history') else 'Settings.TButton')
            button.pack(side=side,padx=(0,dp(parent,8)));buttons.append(button)
        self.history_tree,_=self.table(parent,[('date','Date',290),('text','Text',660)],height=3)
        self.history_tree.bind('<<TreeviewSelect>>',lambda e:self.view_history())
        previous=[]
        def responsive(event):
            compact=event.width<dp(parent,900) or event.height<dp(parent,720)
            if previous==[compact]:return
            previous[:]=[compact]
            heading.configure(font=('Segoe UI',28 if compact else 34,'bold'))
            counter.configure(font=('Segoe UI',14 if compact else 16))
            self.history_result.configure(font=('Segoe UI',14 if compact else 16),height=3 if compact else 4)
            for button in buttons:
                button.pad=dp(parent,12 if compact else 16);button.font.configure(size=11 if compact else 15)
                button.configure(height=dp(parent,46 if compact else 56))
        parent.bind('<Configure>',responsive)

    def build_recovery(self,parent):
        self.heading(parent,'Recording recovery')
        self.recovery_count=tk.StringVar();ttk.Label(parent,textvariable=self.recovery_count,style='PageMuted.TLabel',font=('Segoe UI',16)).pack(anchor='w',pady=(dp(parent,6),dp(parent,12)))
        bar=ttk.Frame(parent,style='Settings.TFrame');bar.pack(side='bottom',fill='x',pady=(dp(parent,20),0))
        ttk.Frame(bar,style='Divider.TFrame',height=1).pack(fill='x',pady=(0,dp(parent,14)))
        self.recovery_buttons={}
        for name,callback,style in [('Recover',self.recover,'Primary.TButton'),('Recognise again',self.recover,'Settings.TButton'),('Delete',self.delete_recovery,'Danger.TButton')]:
            button=self.button(bar,text=self.t(name),height=48,command=lambda c=callback:self.call(c),style=style)
            button.pack(side='left',padx=(0,dp(parent,12)));self.recovery_buttons[name]=button
        self.recovery_info=tk.StringVar()
        self.recovery_info_label=ttk.Label(parent,textvariable=self.recovery_info,style='PageMuted.TLabel')
        self.recovery_tree,self.recovery_panel=self.table(parent,[('name','Recording information',490),('duration','Duration',280),('state','State',260)],height=3)
        self.recovery_empty=tk.Frame(self.recovery_panel.content,bg=self.theme.surface)
        icon_label(self.recovery_empty,'recovery',76,self.theme.disabled).pack(pady=(0,dp(parent,20)))
        tk.Label(self.recovery_empty,text=self.t('No recordings to recover.'),font=('Segoe UI',15),fg=self.theme.muted,bg=self.theme.surface).pack()
        self.recovery_tree.bind('<<TreeviewSelect>>',lambda e:self.show_recovery_info())

    def build_files(self,parent):
        outer=RoundedPanel(parent,padding=16);outer.pack(fill='both',expand=True);parent=outer.content
        self.heading(parent,'File transcription').configure(font=('Segoe UI',31,'bold'),background=self.theme.surface)
        panel=RoundedPanel(parent,padding=18);panel.pack(fill='both',expand=True,pady=(dp(parent,12),0));files=panel.content
        choose=self.button(files,text=self.t('Choose files'),icon='add_file',height=66,font=('Segoe UI',17),command=lambda:self.call(self.choose_files),style='Primary.TButton');choose.pack(anchor='w',pady=(0,dp(parent,14)))
        export=tk.Frame(files,bg=self.theme.surface);export.pack(fill='x',pady=(0,dp(parent,18)))
        export.columnconfigure(1,weight=1)
        ttk.Label(export,text=self.t('Export folder'),style='Card.TLabel',font=('Segoe UI',16)).grid(row=0,column=0,sticky='w',padx=(0,dp(parent,28)))
        self.vars['export_folder']=tk.StringVar(value=self.app.store.settings.get('export_folder',''))
        field=RoundedPanel(export,padding=10,radius=8);field.grid(row=0,column=1,sticky='ew')
        entry=tk.Entry(field.content,textvariable=self.vars['export_folder'],width=10,font=('Segoe UI',15),bg=self.theme.surface,fg=self.theme.text,insertbackground=self.theme.accent,relief='flat',bd=0);entry.pack(fill='x')
        entry.bind('<FocusOut>',lambda e:self.commit_export());entry.bind('<Return>',lambda e:self.commit_export())
        folder_button=self.button(export,text=self.t('Choose folder'),icon='folder',height=52,command=self.choose_folder);folder_button.grid(row=0,column=2,padx=(dp(parent,12),0))
        ttk.Frame(files,style='Divider.TFrame',height=1).pack(fill='x')
        self.file_empty=ttk.Label(files,text=self.t('No files added yet.'),style='Muted.TLabel',font=('Segoe UI',15));self.file_empty.pack(anchor='w',pady=(dp(parent,18),dp(parent,5)))
        bar=tk.Frame(files,bg=self.theme.surface);bar.pack(side='bottom',fill='x',pady=(dp(parent,16),0));self.file_actions=bar
        ttk.Frame(bar,style='Divider.TFrame',height=1).grid(row=0,column=0,columnspan=2,sticky='ew',pady=(0,dp(parent,12)))
        self.file_buttons={}
        for index,(name,callback) in enumerate([('Cancel selected',self.cancel_file),('View result',self.view_file),('Copy',self.copy_file),('Save as TXT',self.save_file)]):
            button=self.button(bar,text=self.t(name),height=56,command=lambda c=callback:self.call(c))
            button.grid(row=1+index//2,column=index%2,sticky='w',padx=(0,dp(parent,10)),pady=dp(parent,4));self.file_buttons[name]=button
        self.file_tree,_=self.table(files,[('name','File',460),('state','State',300),('time','Duration',180)],height=3)
        self.file_tree.bind('<<TreeviewSelect>>',lambda e:self.update_file_actions())
        self.file_result=tk.Text(files,width=1,height=4,wrap='word',relief='flat',bd=0,padx=12,pady=8,font=('Segoe UI',11),bg=self.theme.surface,fg=self.theme.text,insertbackground=self.theme.accent)
        self.file_result.configure(state='disabled')
        previous=[]
        def responsive(event):
            compact=self.window.winfo_height()<dp(parent,780)
            if previous==[compact]:return
            previous[:]=[compact]
            self.body.configure(padding=(dp(parent,18 if compact else 22),dp(parent,16 if compact else 67),dp(parent,18 if compact else 22),dp(parent,12 if compact else 14)))
            for button,size,height in [(choose,14 if compact else 17,48 if compact else 66),(folder_button,11 if compact else 15,38 if compact else 52)]+[(b,12 if compact else 15,40 if compact else 56) for b in self.file_buttons.values()]:
                button.font.configure(size=size);button.configure(height=dp(parent,height))
            entry.configure(font=('Segoe UI',11 if compact else 15))
            field.content.pack_configure(pady=dp(parent,6 if compact else 10))
        self.body.bind('<Configure>',responsive)

    def commit_export(self):
        if not self.alive:return False
        value=self.vars['export_folder'].get().strip()
        if value and not Path(value).expanduser().is_dir():
            self.notice.set(self.t('Choose an existing export folder.'));return False
        value=str(Path(value).expanduser()) if value else ''
        if value!=self.app.store.settings.get('export_folder',''):self.app.store.save({'export_folder':value})
        self.notice.set('');return True

    def choose_files(self):
        if self.commit_export():self.app.open_file()

    def build_stats(self,parent):
        heading=self.heading(parent,'Statistics');heading.configure(font=('Segoe UI',36,'bold'));heading.pack_configure(pady=(dp(parent,70),dp(parent,12)))
        self.stats={};cells=ttk.Frame(parent,style='Settings.TFrame');cells.pack(fill='both',expand=True,pady=(0,dp(parent,65)))
        for col in range(6):cells.columnconfigure(col,weight=1,uniform='metrics')
        cells.rowconfigure(0,weight=12);cells.rowconfigure(1,weight=13)
        metrics=[('dictations','Recordings','mic'),('words','Recognised words','document'),('characters','Recognised characters','characters'),('audio_seconds','Total recording time','clock'),('average_processing_seconds','Average recognition time','timer')]
        widgets=[]
        for i,(key,title,icon) in enumerate(metrics):
            panel=RoundedPanel(cells,padding=28,radius=16,width=1,height=1);panel.pack_propagate(False)
            panel.grid(row=0 if i<3 else 1,column=i*2 if i<3 else (i-3)*3,columnspan=2 if i<3 else 3,sticky='nsew',padx=(0,dp(parent,16)) if i not in (2,4) else 0,pady=(0,dp(parent,18)) if i<3 else 0)
            box=panel.content;symbol=icon_label(box,icon,42,self.theme.accent);symbol.pack(anchor='w',pady=(0,dp(parent,18)))
            caption=self.t(title)
            if i==3:caption+='\n'
            elif i==4:caption='\n'.join(caption.rsplit(' ',1))
            label=ttk.Label(box,text=caption,style='Muted.TLabel',font=('Segoe UI',17),wraplength=dp(parent,270));label.pack(anchor='w')
            panel.bind('<Configure>',lambda event,label=label:label.configure(wraplength=max(dp(parent,100),min(dp(parent,270),event.width-dp(parent,56 if parent.winfo_height()>=dp(parent,730) else 36)))),add='+')
            if key=='average_processing_seconds':self.tip(label,'Average time to process one dictation, including enabled text processing.')
            var=tk.StringVar();self.stats[key]=var
            value=ttk.Label(box,textvariable=var,font=('Segoe UI',48,'bold'),style='Card.TLabel');value.pack(anchor='w',pady=(dp(parent,12),0))
            widgets.append((panel,symbol,label,value,icon))
        current=[]
        def responsive(event):
            compact=event.height<dp(parent,730)
            if current==[compact]:return
            current[:]=[compact]
            heading.configure(font=('Segoe UI',28 if compact else 36,'bold'))
            heading.pack_configure(pady=(dp(parent,8 if compact else 70),dp(parent,20 if compact else 12)))
            cells.pack_configure(pady=(0,dp(parent,16 if compact else 100)))
            from ui_style import icon_image
            for panel,symbol,label,value,icon in widgets:
                panel.content.pack_configure(padx=dp(parent,18 if compact else 28),pady=dp(parent,18 if compact else 28))
                symbol.configure(image=icon_image(symbol,icon,32 if compact else 42,self.theme.accent))
                symbol.pack_configure(pady=(0,dp(parent,10 if compact else 18)))
                label.configure(font=('Segoe UI',13 if compact else 17))
                value.configure(font=('Segoe UI',34 if compact else 48,'bold'))
                value.pack_configure(pady=(dp(parent,8 if compact else 12),0))
        parent.bind('<Configure>',responsive)

    def chosen_file(self):
        ids=self.file_tree.selection()
        return next((job for job in self.app.file_jobs if ids and job['id']==ids[0]),None)

    def update_file_actions(self):
        job=self.chosen_file()
        for name,button in self.file_buttons.items():
            enabled=bool(job and (job['state'] in ('Waiting','Recognising') if name=='Cancel selected' else job.get('text')))
            button.configure(state='normal' if enabled else 'disabled')

    def cancel_file(self):
        job=self.chosen_file()
        if job and job['state'] in ('Waiting','Recognising'):
            job['cancel'].set()
            if job['state']=='Waiting':job['state']='Cancelled'

    def put_text(self,widget,text):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('1.0',text); widget.configure(state='disabled')

    def view_file(self):
        job=self.chosen_file()
        if job:
            self.file_result.pack(side='bottom',fill='x',pady=6,before=self.file_actions)
            self.put_text(self.file_result,job['text'] or self.t(job['error'] or job['state']))

    def copy_file(self):
        job=self.chosen_file()
        if job and job['text']:
            from windows_input import copy_text
            copy_text(job['text'],self.window.winfo_id())

    def save_text(self,text):
        if not text:return
        target=filedialog.asksaveasfilename(parent=self.window,title=self.t('Save as TXT'),defaultextension='.txt',filetypes=[(self.t('Text'),'*.txt')])
        if target:Path(target).write_text(text+'\n','utf-8')

    def save_file(self):
        job=self.chosen_file()
        if job:self.save_text(job['text'])

    def refresh_history(self):
        rows=self.app.store.history(self.query.get()); self.history_rows={str(row['id']):row for row in rows}
        selected=self.history_tree.selection()
        self.history_tree.delete(*self.history_tree.get_children())
        for key,row in self.history_rows.items():self.history_tree.insert('', 'end',iid=key,values=(local_recording_time(row['created']),row['text'].replace('\n',' ')[:100]))
        if selected and self.history_tree.exists(selected[0]):
            self.history_tree.selection_set(selected[0]);self.view_history()
        else:self.put_text(self.history_result,self.history_recent.get())

    def chosen_history(self):
        selection=self.history_tree.selection(); return self.history_rows.get(selection[0]) if selection else None

    def view_history(self):
        row=self.chosen_history()
        if row:
            self.put_text(self.history_result,row['text'])
        else:self.put_text(self.history_result,self.history_recent.get())

    def copy_history(self):
        row=self.chosen_history()
        if row:
            from windows_input import copy_text
            copy_text(row['text'],self.window.winfo_id())

    def export_history(self):
        row=self.chosen_history()
        if row:self.save_text(row['text'])

    def delete_history(self):
        row=self.chosen_history()
        if row:self.app.store.delete(row['id']); self.history_signature=None

    def clear_history(self):
        if messagebox.askyesno(self.t('Clear history'),self.t('Clear history')+'?',parent=self.window):
            self.app.store.clear_history(); self.history_signature=None

    def selected_recovery(self):
        ids=self.recovery_tree.selection(); return next((r for r in self.pending if ids and r['id']==ids[0]),None)

    def show_recovery_info(self):
        record=self.selected_recovery()
        if record:
            self.recovery_info.set(f"{self.t('Duration')}: {record['seconds']:.1f} {self.t('s')} · {self.t('Size')}: {record['size']/1024:.1f} KB")
            self.recovery_info_label.pack(side='bottom',anchor='w',pady=(dp(self.window,6),0))
        else:self.recovery_info.set('');self.recovery_info_label.pack_forget()
        self.update_recovery_actions()

    def update_recovery_actions(self):
        record=self.selected_recovery()
        available=bool(record and not (self.app.busy or self.app.recording or self.app.loading_model))
        for name,button in self.recovery_buttons.items():
            enabled=available and (name=='Delete' or record['valid'])
            button.configure(state='normal' if enabled else 'disabled')

    def recover(self):
        record=self.selected_recovery()
        if record:self.app.recover_record(record)

    def delete_recovery(self):
        record=self.selected_recovery()
        if record and not self.app.busy and messagebox.askyesno(self.t('Delete'),self.t('Delete this saved recording? This cannot be undone.'),parent=self.window):
            record['raw'].unlink(missing_ok=True); record['meta'].unlink(missing_ok=True); self.recovery_signature=None

    def refresh(self):
        if not self.alive:return
        previous=self.jobs.pop('refresh',None)
        if previous:self.window.after_cancel(previous)
        try:
            if self.kind=='File transcription':
                signature=tuple((job['id'],job['state'],job['duration']) for job in self.app.file_jobs)
                if signature!=self.job_signature:
                    selected=self.file_tree.selection(); self.file_tree.delete(*self.file_tree.get_children())
                    for job in self.app.file_jobs:self.file_tree.insert('', 'end',iid=job['id'],values=(Path(job['path']).name,self.t(job['state']),f"{job['duration']:.0f} {self.t('s')}"))
                    if selected and self.file_tree.exists(selected[0]):self.file_tree.selection_set(selected[0])
                    self.file_empty.configure(text='' if signature else self.t('No files added yet.')); self.job_signature=signature
                self.update_file_actions()
            elif self.kind=='History':
                history=self.app.store.history(); signature=tuple((r['id'],r['text'],local_recording_time(r['created'])) for r in history)
                if signature!=self.history_signature:
                    self.history_count.set(self.t('Saved: {count} / 100').format(count=len(history)))
                    self.history_recent.set('\n'.join(r['text'].replace('\n',' ')[:110] for r in history[:3]) or self.t('No transcripts yet.'))
                    self.refresh_history(); self.history_signature=signature
            elif self.kind=='Statistics':
                stats=self.app.store.statistics()
                for key,var in self.stats.items():
                    if key=='audio_seconds':var.set(f"{stats[key]/60:.1f} {self.t('min')}")
                    elif key=='average_processing_seconds':var.set(f"{stats[key]:.2f} {self.t('s')}")
                    else:var.set(str(stats[key]))
            elif self.kind=='Recording recovery':
                self.pending=pending_records(BASE/'data/pending')
                signature=tuple((r['id'],r['valid'],r['size'],local_recording_time(r['created']) if r.get('created') else '') for r in self.pending)
                if signature!=self.recovery_signature:
                    selected=self.recovery_tree.selection()
                    self.recovery_tree.delete(*self.recovery_tree.get_children())
                    for record in self.pending:
                        name=local_recording_time(record['created']) if record.get('created') else record['id'][:10]
                        self.recovery_tree.insert('', 'end',iid=record['id'],values=(name,f"{record['seconds']:.1f} {self.t('s')}",self.t('Model ready') if record['valid'] else self.t('Damaged recording')))
                    self.recovery_count.set(self.t('Available for recovery: {count}').format(count=len(self.pending))); self.recovery_signature=signature
                    if selected and self.recovery_tree.exists(selected[0]):self.recovery_tree.selection_set(selected[0])
                    if self.pending:self.recovery_empty.place_forget()
                    else:self.recovery_empty.place(relx=.5,rely=.53,anchor='center')
                    self.show_recovery_info()
                self.update_recovery_actions()
        except Exception:self.notice.set(self.t('Could not complete this action. Please try again.'))
        self.jobs['refresh']=self.window.after(400,self.refresh)

    def choose_folder(self):
        value=filedialog.askdirectory(parent=self.window,title=self.t('Export folder'))
        if value:
            self.app.store.save({'export_folder':value});self.vars['export_folder'].set(value)

    def close(self):
        if not self.alive:return
        self.alive=False
        for job in self.jobs.values():
            try:self.window.after_cancel(job)
            except tk.TclError:pass
        self.app.activity_windows.pop(self.kind,None)
        self.window.destroy()
