"""Sovela 1.5 — motion, live scan status, private in-app toasts and settings sheet.

Uses the existing PC-care engine and Microsoft Defender rather than claiming
Sovela independently detects malware. All UI changes happen on the Tk thread.
"""
from __future__ import annotations
import os
import queue
import time
import tkinter as tk
from tkinter import messagebox

from sovela_ui_v14 import (SovelaPCApp, WHITE, LITE, ACTIVE, DEEP, SOFT,
    SLATE_BG, SLATE_SIDE, SLATE_CARD, SLATE_TEXT, SLATE_MUTED, SLATE_GREEN,
    SLATE_GREEN_SOFT, SLATE_LINE, SLATE_ORANGE, SLATE_FONT, SLATE_INK_SOFT,
    open_windows_security)
from sovela_preferences import DEFAULTS, VALID_PAGES, load, save
from sovela_scans import run_defender_scan


def elapsed_display(seconds):
    seconds=max(0,int(seconds))
    minutes, seconds=divmod(seconds,60)
    if minutes >= 60:
        hours, minutes = divmod(minutes,60)
        return f'{hours:d}:{minutes:02d}:{seconds:02d}'
    return f'{minutes:02d}:{seconds:02d}'


def blend(c1,c2,t):
    """Interpolate two literal hex colours. Used only for light UI transitions."""
    t=max(0.,min(1.,float(t)))
    return '#'+''.join(f'{round(int(c1[i:i+2],16)*(1-t)+int(c2[i:i+2],16)*t):02x}'
                        for i in (1,3,5))


class SovelaCareApp(SovelaPCApp):
    WIDTH, HEIGHT=990, 722

    def __init__(self,root):
        self.preferences=load()
        self._settings_sheet=None
        self._settings_generation=0
        self._motion_generation=0
        self._toast=None
        self._toast_generation=0
        self._toast_after=[]
        self._scan_last=None
        self._scan_status_label=None
        self._scan_elapsed_var=None
        self._scan_indicator=None
        self._scan_pulse=0
        self._clock_last=-1
        self._initial_check_skipped=False
        self._startup_icon_ready=False
        self._scan_needs_refresh=False
        self._file_scan_started=None
        self._toast_target_tab="Malware Scan"
        super().__init__(root)
        root.title('Sovela | Calm PC Care 1.5')
        self._replace_footer_version(self.frame)
        if self.preferences['always_on_top'] and not self.pinned:
            self.toggle_pin()
        start=self.preferences['start_page']
        if start!='Overview':
            root.after(100,lambda:self.show_tab(start))
        self.root.after(100,self._live_tick)

    def _replace_footer_version(self,widget):
        try:
            if isinstance(widget,tk.Label):
                text=widget.cget('text')
                if 'v1.3' in text or 'v1.4' in text:
                    widget.configure(text=text.replace('v1.3','v1.5').replace('v1.4','v1.5'))
            for child in widget.winfo_children():self._replace_footer_version(child)
        except tk.TclError:
            pass

    def draw_titlebar(self):
        super().draw_titlebar()
        bar=self.pin_button.master
        gear=self.text_button(bar,'⚙  Settings',self.open_settings_sheet,
                              size=10,bg=SLATE_CARD,fg=SLATE_MUTED)
        gear.pack(side='right',before=self.pin_button,padx=(0,5))
        self.settings_button=gear

    def make_nav(self):
        super().make_nav()
        for label in self.sidebar.winfo_children():
            if isinstance(label,tk.Label) and 'No popups' in label.cget('text'):
                label.configure(text='Quiet care · In-app scan alerts')
        for name,button in self.nav_buttons.items():
            button.configure(cursor='hand2')
            button.bind('<Enter>',lambda _e,b=button,n=name:self._nav_hover(b,n,True),add='+')
            button.bind('<Leave>',lambda _e,b=button,n=name:self._nav_hover(b,n,False),add='+')
        # Drawer shortcut is prominent at the bottom of the navigation.
        # The header button also remains visible from every page.

    def _nav_hover(self,widget,name,entering):
        if not widget.winfo_exists() or name==self.current_tab:return
        self._animate_bg(widget,SLATE_SIDE,SLATE_CARD if entering else SLATE_SIDE)

    def _animate_bg(self, widget, initial, destination, frames=7):
        if not self.preferences['smooth_motion']:
            try:widget.configure(bg=destination)
            except tk.TclError:pass
            return
        generation=getattr(widget,'_sovela_motion',0)+1
        widget._sovela_motion=generation
        try:initial=widget.cget('bg')
        except tk.TclError:return
        def frame(i):
            if not widget.winfo_exists() or widget._sovela_motion!=generation:return
            # Ease-out cubic for calm, short interactions.
            t=1-(1-i/frames)**3
            try:widget.configure(bg=blend(initial,destination,t))
            except (tk.TclError, ValueError):return
            if i<frames:self.root.after(16,lambda:frame(i+1))
        frame(0)

    def _button(self,parent,label,fn,primary=True,compact=False):
        button=super()._button(parent,label,fn,primary,compact)
        if self.preferences['smooth_motion']:
            resting=SLATE_GREEN if primary else SLATE_GREEN_SOFT
            hover=DEEP if primary else ACTIVE
            button.bind('<Enter>',lambda _e,b=button,a=resting,z=hover:self._animate_bg(b,a,z),add='+')
            button.bind('<Leave>',lambda _e,b=button,a=hover,z=resting:self._animate_bg(b,a,z),add='+')
        return button

    def tip(self,widget,heading,description):
        if self.preferences['hover_hints']:
            super().tip(widget,heading,description)

    def check(self):
        # The inherited startup timer is the first scheduled check. A manual
        # check always works and is never blocked by this preference.
        if not self.preferences['check_at_launch'] and not self._initial_check_skipped:
            self._initial_check_skipped=True
            return
        self._initial_check_skipped=True
        super().check()

    def show_tab(self,tab):
        if tab=='Settings':
            self.open_settings_sheet();return
        was=getattr(self,'current_tab','')
        if self._settings_sheet is not None:
            self.close_settings_sheet(animate=False)
        super().show_tab(tab)
        if was!=tab:
            self._animate_current_page(tab)

    def _animate_current_page(self,tab):
        self._motion_generation+=1
        gen=self._motion_generation
        if not self.preferences['smooth_motion'] or not hasattr(self,'view') or tab in ('Assistant','Activity'):
            return
        panel=self.view
        if not panel.winfo_exists() or panel.winfo_manager()!='pack':return
        try:panel.pack_configure(padx=(17,0))
        except tk.TclError:return
        def step(i):
            if gen!=self._motion_generation or not panel.winfo_exists():return
            movement=round(17*(1-(1-(1-i/9)**3)))
            try:panel.pack_configure(padx=(movement,0))
            except tk.TclError:return
            if i<9:self.root.after(18,lambda:step(i+1))
        self.root.after(18,lambda:step(1))

    def _scan_tick(self):
        # v1.4 scheduled a 30-second full-page redraw. The new timer updates
        # labels instead, leaving focus and animated controls undisturbed.
        return

    def malware_page(self):
        self._page_header('Malware Scan','Windows Defender scans, presented clearly and accurately.',
                          ('Windows Security ↗',open_windows_security))
        head=tk.Frame(self.view,bg=SLATE_BG);head.pack(fill='x',pady=(0,10))
        self._label(head,'CHOOSE A SCAN',9,True,color=SLATE_MUTED).pack(side='left')
        self._label(head,'Requires active Microsoft Defender',9,color=SLATE_MUTED).pack(side='right')
        tiles=tk.Frame(self.view,bg=SLATE_BG);tiles.pack(fill='x')
        for i,(icon,title,sub,desc,mode) in enumerate([
            ('↗','Quick Scan','Common malware locations','Usually shorter; duration varies by computer.','quick'),
            ('◎','Deep Dive','Full device scan','May run for hours on devices with many files.','full'),
        ]):
            edge,card=self._surface(tiles,padding=17)
            edge.grid(row=0,column=i,sticky='nsew',padx=(0,11 if i==0 else 0))
            tiles.grid_columnconfigure(i,weight=1,uniform='scan')
            self._label(card,icon,21,color=SLATE_GREEN).pack(anchor='w')
            self._label(card,title,14,True).pack(anchor='w',pady=(6,1))
            self._label(card,sub,10,color=SLATE_INK_SOFT).pack(anchor='w')
            self._label(card,desc,9,color=SLATE_MUTED,wraplength=245).pack(anchor='w',pady=(3,10))
            b=self._button(card,'Start '+title,lambda x=mode:self.start_device_scan(x))
            b.pack(anchor='w')
            if self.device_scan_busy:b.configure(state='disabled',cursor='arrow')
            self.tip(b,title,desc+' Your existing antivirus is never turned off.')
        edge,card=self._surface(self.view,padding=17,bg=LITE)
        edge.pack(fill='x',pady=(15,0))
        topline=tk.Frame(card,bg=LITE);topline.pack(fill='x')
        self._label(topline,'LIVE SCAN STATUS',9,True,color=SLATE_MUTED).pack(side='left')
        self._scan_elapsed_var=tk.StringVar(value=self._live_time())
        if self.preferences['show_scan_timer']:
            self._label(topline,'ELAPSED',9,color=SLATE_MUTED).pack(side='right',padx=(0,6))
            tk.Label(topline,textvariable=self._scan_elapsed_var,bg=LITE,fg=SLATE_GREEN,
                     font=(SLATE_FONT,12,'bold')).pack(side='right')
        if self.device_scan_busy:
            status='Defender is scanning. Keep Sovela open to monitor this request.'
        elif self._scan_last:
            status=self._scan_last['headline']
        else:
            status='No scan has been run in this session.'
        self._scan_status_label=self._label(card,status,12,True,color=SLATE_TEXT,wraplength=610)
        self._scan_status_label.pack(anchor='w',pady=(8,4))
        if self.device_scan_busy:
            self._label(card,'Working… exact percent is not available from this scan interface.',9,color=SLATE_MUTED).pack(anchor='w')
            self._scan_indicator=tk.Canvas(card,bg=SLATE_LINE,height=5,highlightthickness=0)
            self._scan_indicator.pack(fill='x',pady=(11,8))
            self._scan_pulse=self._scan_indicator.create_rectangle(0,0,100,6,fill=SLATE_GREEN,outline='')
        else:
            self._scan_indicator=None
        if self._scan_last:
            result=self._scan_last
            detail=f'{result["type"]}  ·  {elapsed_display(result["elapsed"])}  ·  {result["clock"]}'
            self._label(card,detail,10,True,color=SLATE_GREEN if result['outcome']=='complete' else SLATE_ORANGE).pack(anchor='w',pady=(5,0))
            self._label(card,result['message'],9,color=SLATE_INK_SOFT,wraplength=635).pack(anchor='w',pady=(5,0))
        elif not self.device_scan_busy:
            self._label(card,'Scan results will appear here. Sovela never labels a device malware-free.',9,
                        color=SLATE_MUTED).pack(anchor='w',pady=(5,0))
        row=tk.Frame(card,bg=LITE);row.pack(fill='x',pady=(12,0))
        self._button(row,'Open Windows Security ↗',open_windows_security,False,True).pack(side='left')
        self._label(row,'No automatic removals or changes',9,color=SLATE_MUTED).pack(side='right',pady=(7,0))
        if not self.device_scan_busy:
            self._label(self.view,'If another antivirus is active, open its app to perform the scan. Defender stays in passive mode.',
                        9,color=SLATE_MUTED,wraplength=650).pack(anchor='w',pady=(12,0))

    def _live_time(self):
        if self.device_scan_busy and self.device_scan_started is not None:
            return elapsed_display(time.monotonic()-self.device_scan_started)
        return elapsed_display(self._scan_last['elapsed']) if self._scan_last else '00:00'

    def _live_tick(self):
        try:
            if self.device_scan_busy and self.current_tab=='Malware Scan':
                if self._scan_elapsed_var is not None:
                    self._scan_elapsed_var.set(self._live_time())
                if self._scan_indicator is not None and self._scan_indicator.winfo_exists():
                    canvas=self._scan_indicator
                    w=max(100,canvas.winfo_width())
                    if self.preferences['smooth_motion']:
                        self._scan_pulse=(self._scan_pulse if isinstance(self._scan_pulse,int) else 0)
                        span=115
                        # An indeterminate moving accent, NOT a fabricated scan percentage.
                        elapsed=time.monotonic()-self.device_scan_started
                        x=((elapsed*125)%(w+span))-span
                        canvas.coords(self._scan_pulse,x,0,x+span,6)
                    else:
                        canvas.coords(self._scan_pulse,0,0,w,6)
            self.root.after(100 if self.device_scan_busy else 280,self._live_tick)
        except tk.TclError:
            return

    def start_device_scan(self,mode):
        if self.device_scan_busy:return
        if mode not in ('quick','full'):return
        if os.name!='nt':
            self._scan_last={'type':mode.title()+' scan','outcome':'error','elapsed':0,
               'clock':time.strftime('%H:%M'),'headline':'Scan unavailable on this device',
               'message':'Sovela requires Windows and active Microsoft Defender for malware scans.'}
            self.show_tab('Malware Scan');return
        if mode=='full' and not messagebox.askyesno('Start deep scan?',
            'A full Defender scan can run for a long time and use CPU and disk resources.\n\nStart the full scan now?',parent=self.root):
            return
        current=self.current_tab
        self.device_scan_busy=True
        self.device_scan_started=time.monotonic()
        self.device_scan_mode=mode
        self.device_scan_message='Requesting Microsoft Defender scan…'
        self._scan_last=None
        if self.preferences['scan_opens_page'] or current=='Malware Scan':
            self.show_tab('Malware Scan')
        self.run_job('device_scan',lambda:run_defender_scan(mode))

    def poll_events(self):
        # Intercept *only* scan results so the inherited read-only health,
        # startup, cleaner, file and chat workflows remain untouched.
        remaining=[]
        completed=[]
        while True:
            try:kind,state,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='device_scan':
                elapsed=int(time.monotonic()-self.device_scan_started) if self.device_scan_started else 0
                mode=self.device_scan_mode or 'quick'
                self.device_scan_busy=False
                self.device_scan_started=None
                outcome=value.get('outcome','unverified') if state=='ok' and isinstance(value,dict) else 'error'
                message=(value.get('message','Windows did not provide a verified result.')
                         if state=='ok' and isinstance(value,dict)
                         else str(value))
                if outcome=='complete':
                    heading='Scan completed and verified'
                elif outcome=='unverified':
                    heading='Scan needs review'
                else:
                    heading='Scan could not be confirmed'
                self.device_scan_message=message
                self._scan_last={'type':'Quick scan' if mode=='quick' else 'Deep dive',
                                 'outcome':outcome,'elapsed':elapsed,
                                 'clock':time.strftime('%H:%M'),
                                 'headline':heading,'message':message}
                self.record_activity('Defender '+mode+' scan · '+outcome)
                completed.append(self._scan_last.copy())
                if self.current_tab=='Malware Scan':
                    self.show_tab('Malware Scan')
            elif kind=='defender_scan':
                # The selected-file scan API reports command return, not a
                # verified threat-free verdict. Never use a green success toast.
                runtime=max(0,int(time.monotonic()-self._file_scan_started)) if self._file_scan_started else 0
                result={'type':'Selected file scan','outcome':'unverified' if state=='ok' else 'error',
                        'elapsed':runtime,'clock':time.strftime('%H:%M'),
                        'headline':'File scan: review results' if state=='ok' else 'File scan needs attention',
                        'message': ('Defender returned from the selected-file scan. Review Windows Security for any detections; Sovela does not certify files as safe.'
                                    if state=='ok' else str(value)), 'target_tab':'Downloads'}
                completed.append(result)
                self._file_scan_started=None
                remaining.append((kind,state,value))
            else:
                remaining.append((kind,state,value))
        for event in remaining:self.events.put(event)
        super().poll_events()
        for item in completed:
            self.root.after(70,lambda x=item:self._notify_scan(x))

    def defender_scan(self):
        was=self.scanning
        super().defender_scan()
        if not was and self.scanning:
            self._file_scan_started=time.monotonic()

    def _notify_scan(self,result):
        if not self.preferences['scan_notifications']:return
        if result['outcome']!='complete' and not self.preferences['scan_error_notifications']:return
        self.dismiss_toast()
        self._toast_target_tab=result.get('target_tab','Malware Scan')
        toast=tk.Toplevel(self.root)
        self._toast=toast
        self._toast_generation+=1
        gen=self._toast_generation
        toast.overrideredirect(True)
        toast.configure(bg=SLATE_LINE)
        toast.attributes('-topmost',True)
        try:toast.attributes('-alpha',0 if self.preferences['smooth_motion'] else .98)
        except tk.TclError:pass
        panel=tk.Frame(toast,bg=WHITE,padx=17,pady=14)
        panel.pack(fill='both',expand=True,padx=1,pady=1)
        top=tk.Frame(panel,bg=WHITE);top.pack(fill='x')
        signal='●' if result['outcome']=='complete' else '◐'
        color=SLATE_GREEN if result['outcome']=='complete' else SLATE_ORANGE
        tk.Label(top,text=signal,bg=WHITE,fg=color,font=(SLATE_FONT,16,'bold')).pack(side='left',padx=(0,7))
        tk.Label(top,text='SOVELA · SCAN UPDATE',bg=WHITE,fg=SLATE_MUTED,
                 font=(SLATE_FONT,9,'bold')).pack(side='left')
        tk.Button(top,text='×',command=self.dismiss_toast,bd=0,bg=WHITE,fg=SLATE_MUTED,
                  activebackground=WHITE,font=(SLATE_FONT,15),cursor='hand2').pack(side='right')
        tk.Label(panel,text=result['headline'],bg=WHITE,fg=SLATE_TEXT,
                 font=(SLATE_FONT,13,'bold'),anchor='w').pack(fill='x',pady=(8,3))
        tk.Label(panel,text=f'{result["type"]} · {elapsed_display(result["elapsed"])} elapsed',
                 bg=WHITE,fg=SLATE_INK_SOFT,font=(SLATE_FONT,10),anchor='w').pack(fill='x')
        tk.Label(panel,text=('View Defender information and next steps.' if result['outcome']=='complete' else
                             'Review the status in Windows Security.'),
                 bg=WHITE,fg=SLATE_MUTED,font=(SLATE_FONT,9),anchor='w').pack(fill='x',pady=(3,11))
        actions=tk.Frame(panel,bg=WHITE);actions.pack(fill='x')
        self._button(actions,'View results  →',self._open_scan_from_toast,True,True).pack(side='left')
        self._button(actions,'Dismiss',self.dismiss_toast,False,True).pack(side='right')
        width,height=355,198
        area=self.work_area(self.root.winfo_x(),self.root.winfo_y())
        left,top,right,bottom=area
        target_x=max(left+8,right-width-18)
        target_y=top+18
        toast.geometry(f'{width}x{height}+{target_x+29}+{target_y}')
        toast.deiconify()
        def tween(i):
            if self._toast is not toast or gen!=self._toast_generation:return
            t=1-(1-min(i,12)/12)**3
            toast.geometry(f'+{int(target_x+29*(1-t))}+{target_y}')
            try:toast.attributes('-alpha',.98*t)
            except tk.TclError:pass
            if i<12:self.root.after(17,lambda:tween(i+1))
        if self.preferences['smooth_motion']:
            self.root.after(12,lambda:tween(1))
        else:
            toast.geometry(f'+{target_x}+{target_y}')
        duration=int(self.preferences['notification_seconds'])*1000
        self._toast_after.append(self.root.after(duration,lambda:self._dismiss_if_current(gen)))

    def _dismiss_if_current(self,generation):
        if self._toast_generation==generation:self.dismiss_toast()

    def dismiss_toast(self):
        self._toast_generation+=1
        for handle in self._toast_after:
            try:self.root.after_cancel(handle)
            except tk.TclError:pass
        self._toast_after=[]
        pop=self._toast
        self._toast=None
        if pop is not None:
            try:pop.destroy()
            except tk.TclError:pass

    def _open_scan_from_toast(self):
        self.dismiss_toast()
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.after(100,self.restore_after_minimize)
            self.show_tab(self._toast_target_tab)
            if not self.pinned:
                self.root.attributes('-topmost',True)
                self.root.after(850,lambda:self.root.attributes('-topmost',False)
                                if self.root.winfo_exists() and not self.pinned else None)
        except tk.TclError:pass

    # ---- A slide-in Settings sheet, not a separate settings window ----
    def open_settings_sheet(self):
        if self._settings_sheet is not None:
            self.close_settings_sheet();return
        self._settings_generation+=1
        generation=self._settings_generation
        sheet=tk.Frame(self.content,bg=SLATE_LINE)
        self._settings_sheet=sheet
        sheet.place(relx=1.0,x=0,y=0,width=444,relheight=1)
        inner=tk.Frame(sheet,bg=WHITE,padx=19,pady=16)
        inner.pack(fill='both',expand=True,padx=(1,0),pady=(0,0))
        header=tk.Frame(inner,bg=WHITE);header.pack(fill='x',pady=(0,4))
        title=tk.Frame(header,bg=WHITE);title.pack(side='left',fill='x',expand=True)
        self._label(title,'Settings',18,True).pack(anchor='w')
        self._label(title,'Personalise Sovela. Changes save on this PC.',9,color=SLATE_MUTED).pack(anchor='w',pady=(3,0))
        self._button(header,'Close  ×',self.close_settings_sheet,False,True).pack(side='right')
        self._settings_section(inner,'APPEARANCE')
        self._settings_toggle(inner,'smooth_motion','Smooth animations','Subtle sliding and hover transitions.')
        self._settings_toggle(inner,'always_on_top','Keep Sovela on top','Show the main widget above normal windows.')
        self._settings_toggle(inner,'hover_hints','Helpful hover tips','Show short explanations when pointing at tools.')
        self._settings_section(inner,'SCANNING')
        self._settings_toggle(inner,'show_scan_timer','Live scan timer','Show elapsed minutes and seconds.')
        self._settings_toggle(inner,'scan_opens_page','Open scanner when started','Stay in your current page when switched off.')
        self._settings_toggle(inner,'check_at_launch','Check security at launch','Read Windows protection status at startup.')
        self._settings_section(inner,'IN-APP ALERTS')
        self._settings_toggle(inner,'scan_notifications','Scan-complete popup','Sovela alert over other open windows.')
        self._settings_toggle(inner,'scan_error_notifications','Include scan problems','Show alerts when Defender cannot confirm a scan.')
        control=tk.Frame(inner,bg=WHITE);control.pack(fill='x',pady=(3,0))
        self._label(control,'Popup duration',10,True).pack(side='left')
        duration=self._button(control,f'{self.preferences["notification_seconds"]} seconds   ↻',
                              lambda:self._cycle_setting('notification_seconds',(6,10,15)),False,True)
        duration.pack(side='right');self._setting_duration_btn=duration
        control2=tk.Frame(inner,bg=WHITE);control2.pack(fill='x',pady=(4,0))
        self._label(control2,'Opening page',10,True).pack(side='left')
        opening=self._button(control2,self.preferences['start_page']+'   ↻',
                             lambda:self._cycle_setting('start_page',VALID_PAGES),False,True)
        opening.pack(side='right');self._setting_start_btn=opening
        bottom=tk.Frame(inner,bg=WHITE);bottom.pack(side='bottom',fill='x',pady=(6,0))
        tk.Frame(bottom,bg=SLATE_LINE,height=1).pack(fill='x',pady=(0,10))
        self._label(bottom,'Settings are stored locally. No accounts, adverts or telemetry.',
                    8,color=SLATE_MUTED,wraplength=380).pack(anchor='w')
        row=tk.Frame(bottom,bg=WHITE);row.pack(fill='x',pady=(8,0))
        self._button(row,'Reset to defaults',self._reset_settings,False,True).pack(side='left')
        self._button(row,'Done',self.close_settings_sheet,True,True).pack(side='right')
        def slide(i):
            if self._settings_sheet is not sheet or self._settings_generation!=generation:return
            t=1-(1-min(i,13)/13)**3
            sheet.place_configure(x=-round(444*t))
            if i<13:self.root.after(15,lambda:slide(i+1))
        if self.preferences['smooth_motion']:
            self.root.after(10,lambda:slide(1))
        else:
            sheet.place_configure(x=-444)
        sheet.lift()

    def _settings_section(self,body,name):
        self._label(body,name,9,True,color=SLATE_GREEN).pack(anchor='w',pady=(8,3))

    def _settings_toggle(self,parent,key,heading,description):
        row=tk.Frame(parent,bg=WHITE,height=39)
        row.pack(fill='x',pady=1)
        row.pack_propagate(False)
        text=tk.Frame(row,bg=WHITE);text.pack(side='left',fill='both',expand=True)
        self._label(text,heading,10,True).pack(anchor='w')
        self._label(text,description,8,color=SLATE_MUTED,wraplength=290).pack(anchor='w',pady=(2,0))
        b=tk.Button(row,bd=0,relief='flat',cursor='hand2',font=(SLATE_FONT,10,'bold'),
                    padx=12,pady=5)
        b.pack(side='right',padx=(8,0))
        def change():
            self._set_pref(key,not self.preferences[key])
            update()
        def update():
            active=bool(self.preferences[key])
            b.configure(text='On  ●' if active else 'Off  ○',command=change,
                        bg=SLATE_GREEN_SOFT if active else LITE,
                        fg=SLATE_GREEN if active else SLATE_MUTED,
                        activebackground=ACTIVE)
        update()

    def _cycle_setting(self,key,options):
        current=self.preferences[key]
        target=options[(options.index(current)+1)%len(options)]
        self._set_pref(key,target)
        if key=='notification_seconds' and self._settings_sheet is not None:
            self._setting_duration_btn.configure(text=f'{target} seconds   ↻')
        if key=='start_page' and self._settings_sheet is not None:
            self._setting_start_btn.configure(text=f'{target}   ↻')

    def _set_pref(self,key,value):
        self.preferences[key]=value
        self._save_prefs()
        if key=='always_on_top' and self.pinned!=bool(value):
            self.toggle_pin()
        elif key=='hover_hints' and not value:
            for tip in self._tips:tip.leave()
        elif key in ('show_scan_timer','smooth_motion') and self.current_tab=='Malware Scan':
            self._scan_needs_refresh=True

    def toggle_pin(self):
        super().toggle_pin()
        if hasattr(self,'preferences'):
            self.preferences['always_on_top']=self.pinned
            self._save_prefs()

    def _save_prefs(self):
        try:save(self.preferences)
        except OSError:pass

    def _reset_settings(self):
        if not messagebox.askyesno('Reset preferences','Reset Sovela appearance and alert preferences to their defaults?',parent=self.root):
            return
        self.preferences=DEFAULTS.copy()
        self._save_prefs()
        if self.pinned:self.toggle_pin()
        self.close_settings_sheet(animate=False)
        if self.current_tab=='Malware Scan':self.show_tab('Malware Scan')
        self.open_settings_sheet()

    def close_settings_sheet(self,animate=True):
        sheet=self._settings_sheet
        if sheet is None:return
        self._settings_generation+=1
        gen=self._settings_generation
        self._settings_sheet=None
        # Disable the sheet immediately: no stale settings panel should trap input.
        if not animate or not self.preferences['smooth_motion']:
            try:sheet.destroy()
            except tk.TclError:pass
            if self._scan_needs_refresh:
                self._scan_needs_refresh=False
                self.show_tab(self.current_tab)
            return
        sheet.lift()
        def dismiss(i):
            if self._settings_generation!=gen or not sheet.winfo_exists():return
            t=1-(1-min(i,9)/9)**3
            sheet.place_configure(x=-round(444*(1-t)))
            if i<9:self.root.after(16,lambda:dismiss(i+1))
            else:
                sheet.destroy()
                if self._scan_needs_refresh:
                    self._scan_needs_refresh=False
                    self.show_tab(self.current_tab)
        dismiss(0)

    def close(self):
        self.dismiss_toast()
        if self.device_scan_busy:
            answer=messagebox.askyesno('Scan in progress',
                'Sovela is monitoring a Defender scan. Closing Sovela stops this live timer and completion alert. '
                'Windows Security may continue the scan.\n\nClose Sovela anyway?',parent=self.root)
            if not answer:return
        super().close()
