"""Real Tk/Windows regression checks for resize, density and system theme."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import json,sys,tempfile,time,statistics
from unittest.mock import Mock,patch
import tkinter as tk

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/source'))
try:C.windll.shcore.SetProcessDpiAwareness(1)
except Exception:pass
import app as application,app_features,settings_window,activity_window,settings_actions
from app import App
from storage import Store
from ui_style import UI_SCALE,dp,LIGHT,DARK,system_dark
from resize_support import u,WM_ENTERSIZEMOVE,WM_EXITSIZEMOVE
u.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.SendMessageW.restype=C.c_ssize_t
u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT];u.SetWindowPos.restype=W.BOOL
u.GetWindowRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.GetWindowRect.restype=W.BOOL
u.GetClientRect.argtypes=[W.HWND,C.POINTER(W.RECT)];u.GetClientRect.restype=W.BOOL


def pump(root,seconds=.15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:root.update();time.sleep(.002)


def run():
    report={'scale':UI_SCALE,'resize':{},'checks':[]}
    with tempfile.TemporaryDirectory(prefix='.tmp-',dir=Path(__file__).resolve().parent) as temporary:
        directory=Path(temporary)
        for module in (application,app_features,settings_window,activity_window,settings_actions):module.BASE=directory
        store=Store(directory);store.save({'language':'ru','ui_theme':'light','sounds':False})
        store.add('Сохранённый текст для поиска',2,.1)
        root=tk.Tk();root.withdraw();native_dpi=root.winfo_fpixels('1i')/96;errors=[]
        root.report_callback_exception=lambda cls,value,trace:errors.append(str(value))
        with patch('app_features.Store',return_value=store),patch('app_features.Engine',return_value=Mock()):
            app=App(root,smoke=True);app.close=lambda:None
            deadline=time.monotonic()+10
            while (not app.engine or app.loading_model) and time.monotonic()<deadline:root.update();time.sleep(.01)
        root.deiconify();pump(root)
        from recording_overlay import MonitorInfo
        info=MonitorInfo();info.size=C.sizeof(info)
        assert u.GetMonitorInfoW(u.MonitorFromWindow(root.winfo_id(),2),C.byref(info))
        work_width=info.work.right-info.work.left;work_height=info.work.bottom-info.work.top
        assert abs(root.winfo_width()-min(round(1100*native_dpi*UI_SCALE),work_width-40))<4
        assert abs(root.winfo_height()-min(round(825*native_dpi*UI_SCALE),work_height-64))<4
        scaling=float(root.tk.call('tk','scaling'))
        app.open_settings();ui=app.settings_ui;pump(root)
        assert float(root.tk.call('tk','scaling'))==scaling,'Toplevel scaled the interpreter twice'
        assert abs(UI_SCALE/.646875-1.5)<1e-9
        assert abs(dp(root,100)-round(100*native_dpi*UI_SCALE))<=1
        report['checks'].append('Interface enlarged by 50%, matching fonts and geometry, work-area limits, no repeated scaling')
        for section in ui.sections:
            ui.select(section);pump(root)
            assert not ui.notice.get(),ui.notice.get()
        targets={'Main':root,'Settings':ui.window}
        for kind in ('History','File transcription','Recording recovery','Statistics'):
            app.open_activity(kind);targets[kind]=app.activity_windows[kind].window
        pump(root)
        for kind,window in targets.items():
            for other in targets.values():
                if other!=window:other.withdraw()
            window.deiconify();pump(root)
            handler=window._resize_handler
            bounds=W.RECT();client=W.RECT();u.GetWindowRect(handler.hwnd,C.byref(bounds));u.GetClientRect(handler.hwnd,C.byref(client))
            border_w=bounds.right-bounds.left-client.right;border_h=bounds.bottom-bounds.top-client.bottom
            timings=[];deferred_before=handler.deferred_count
            u.SendMessageW(handler.hwnd,WM_ENTERSIZEMOVE,0,0)
            frozen={child:(child.winfo_width(),child.winfo_height()) for child,_ in handler.frozen}
            try:
                for width,height in [(900,650),(1200,860),(850,620),(1100,825)]*4:
                    started=time.perf_counter()
                    assert u.SetWindowPos(handler.hwnd,None,0,0,dp(root,width)+border_w,dp(root,height)+border_h,0x0002|0x0004|0x0010)
                    root.update();timings.append((time.perf_counter()-started)*1000)
                    assert all((child.winfo_width(),child.winfo_height())==size for child,size in frozen.items())
            finally:u.SendMessageW(handler.hwnd,WM_EXITSIZEMOVE,0,0)
            pump(root)
            assert handler.deferred_count>deferred_before,(kind,'Native sizing messages were not deferred')
            assert abs(window.winfo_width()-dp(root,1100))<4,(kind,window.winfo_width())
            assert abs(window.winfo_height()-dp(root,825))<4,(kind,window.winfo_height())
            report['resize'][kind]={'mean_ms':round(statistics.mean(timings),2),'max_ms':round(max(timings),2),'deferred_sizes':handler.deferred_count-deferred_before}
            print(kind,report['resize'][kind],flush=True)
        report['checks'].append('Native drag loop stays responsive and commits the final size for every window')
        for view in list(app.activity_windows.values()):view.close()
        root.deiconify();ui.window.deiconify()
        # Selecting "As in Windows" and saving follows the application theme,
        # irrespective of the previous explicitly selected theme.
        ui=app.settings_ui;ui.select('Application')
        choice=ui.vars['ui_theme'];choice.variable.set(choice.labels[choice.options.index('system')])
        with patch('ui_style.system_dark',return_value=True):ui.save();pump(root)
        assert store.settings['ui_theme']=='system' and root.ui_theme==DARK
        ui=app.settings_ui;ui.vars['sound_volume'].set(37);app.pending_shortcuts['dictate']=[0x71]
        app.text.insert('1.0','Незавершённый текст');geometry=root.geometry()
        app.text.mark_set('insert','1.5');app.text.tag_add('sel','1.0','1.3')
        app.open_history();history=app.activity_windows['History'];history.query.set('Сохранённый')
        app.file_jobs.append({'id':'fixture-job','path':str(directory/'test.wav'),'state':'Completed',
            'text':'Результат файла','error':'','duration':2,'output':'','cancel':Mock()})
        app.open_files();files=app.activity_windows['File transcription'];files.refresh()
        files.file_tree.selection_set('fixture-job');files.view_file()
        old_ui=ui
        with patch('ui_style.system_dark',return_value=False):
            app.smoke=False;app._request_checked=0
            app.on_poll();app.smoke=True;pump(root)
        assert root.ui_theme==LIGHT and app.settings_ui is not old_ui
        assert root.geometry()==geometry
        assert app.settings_ui.vars['sound_volume'].get()==37 and store.settings['sound_volume']!=37
        assert app.pending_shortcuts['dictate']==[0x71]
        assert app.text.get('1.0','end-1c')=='Незавершённый текст'
        assert app.text.index('insert')=='1.5' and tuple(map(str,app.text.tag_ranges('sel')))==('1.0','1.3')
        assert app.activity_windows['History'].query.get()=='Сохранённый'
        assert app.activity_windows['File transcription'].file_tree.selection()==('fixture-job',)
        assert app.activity_windows['File transcription'].file_result.get('1.0','end-1c')=='Результат файла'
        assert not app.settings_ui.notice.get(),app.settings_ui.notice.get()
        report['checks'].append('System theme: save, live OS change, unsaved settings/text/shortcuts and window geometry retained')
        old_ui=app.settings_ui;app.busy=True
        with patch('ui_style.system_dark',return_value=True):app.check_system_theme()
        assert app.settings_ui is old_ui and root.ui_theme==LIGHT
        app.busy=False
        store.save({'ui_theme':'light'})
        with patch('ui_style.system_dark',return_value=True):app.check_system_theme()
        assert root.ui_theme==LIGHT
        report['checks'].append('Theme changes deferred during work; explicit light theme remains light')
        with patch('ui_style.winreg.OpenKey') as key,patch('ui_style.winreg.QueryValueEx',return_value=(0,4)):
            assert system_dark()
        with patch('ui_style.winreg.OpenKey') as key,patch('ui_style.winreg.QueryValueEx',return_value=(1,4)):
            assert not system_dark()
        report['checks'].append('Reads AppsUseLightTheme from the 64-bit Windows personalization key')
        extra=tk.Toplevel(root)
        from ui_style import configure_styles
        configure_styles(extra,'light');tk.Label(extra,text='Resize cleanup').pack();pump(root)
        u.SendMessageW(extra._resize_handler.hwnd,WM_ENTERSIZEMOVE,0,0)
        extra.destroy();pump(root)
        report['checks'].append('Closing a sizing window cleans up native hooks and pending callbacks')
        app.quit_app();assert not errors,errors
        report['callback_errors']=errors
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    return report


if __name__=='__main__':
    result=run()
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
