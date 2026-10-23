"""Sovela PC Care v1.4: accurate scans, compact health advice, app icons and clean flow."""
from __future__ import annotations
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from sovela_ui_v13 import (SovelaQuickApp, MouseFollowTip, WHITE, LITE, ACTIVE, DEEP,
                              SOFT, SLATE_BG, SLATE_SIDE, SLATE_CARD, SLATE_TEXT,
                              SLATE_MUTED, SLATE_GREEN, SLATE_GREEN_SOFT, SLATE_LINE,
                              SLATE_ORANGE, SLATE_ORANGE_SOFT, SLATE_FONT,
                              SLATE_INK_SOFT, CalmScrollbar, open_windows_security)
from sovela_care import CATEGORIES
from sovela_icons import extract_icons, extract_path
from sovela_scans import run_defender_scan
from sovela_health_plus import suggest, older_large_downloads

class SovelaPCApp(SovelaQuickApp):
    MENU = ('Overview', 'Malware Scan', 'Protection', 'Cleaner', 'Startup',
            'Downloads', 'PC Health', 'Assistant', 'Activity', 'Tools')
    WIDTH, HEIGHT = 980, 710

    def __init__(self, root):
        self._clean_on_preview=False
        self.device_scan_busy=False
        self.device_scan_mode=None
        self.device_scan_started=None
        self.device_scan_message='Choose a scan to check for malware using your active Microsoft Defender.'
        self._icons={}
        self._images=[]
        self._icon_queue=queue.Queue()
        self._requested_icon_signature=None
        super().__init__(root)
        root.title('Sovela | PC Care v1.4')
        self._replace_footer_version(self.frame)
        self.root.after(30000,self._scan_tick)

    def _scan_tick(self):
        if self.device_scan_busy and self.current_tab=='Malware Scan':
            self.show_tab('Malware Scan')
        try:self.root.after(30000,self._scan_tick)
        except tk.TclError:pass

    def _replace_footer_version(self,widget):
        try:
            if isinstance(widget,tk.Label) and 'v1.3' in widget.cget('text'):
                widget.configure(text=widget.cget('text').replace('v1.3','v1.4'))
            for child in widget.winfo_children():self._replace_footer_version(child)
        except tk.TclError:pass

    def make_nav(self):
        self.nav_buttons={}
        groups=[('ESSENTIALS',[('Overview','⌂'),('Malware Scan','⛨'),('Protection','◇'),('Cleaner','✧'),('Startup','≡')]),
                ('YOUR DEVICE',[('Downloads','↓'),('PC Health','◌')]),
                ('SUPPORT',[('Assistant','☼'),('Activity','◷'),('Tools','⚙')])]
        for heading,items in groups:
            tk.Label(self.sidebar,text=heading,bg=SLATE_SIDE,fg=SLATE_MUTED,
                     font=(SLATE_FONT,8,'bold')).pack(anchor='w',padx=23,pady=(16 if heading=='ESSENTIALS' else 10,5))
            for name,symbol in items:
                row=tk.Frame(self.sidebar,bg=SLATE_SIDE)
                row.pack(fill='x',padx=10,pady=1)
                btn=self.text_button(row,f'{symbol}    {name}',lambda n=name:self.show_tab(n),
                                     size=10,bg=SLATE_SIDE,fg=SLATE_MUTED)
                btn.configure(anchor='w',padx=14,pady=7)
                btn.pack(fill='x')
                self.nav_buttons[name]=btn
        tk.Frame(self.sidebar,bg=SLATE_SIDE).pack(fill='both',expand=True)
        tk.Label(self.sidebar,text='Local checks · No popups',bg=SLATE_SIDE,
                 fg=SLATE_MUTED,font=(SLATE_FONT,9)).pack(pady=(0,13))

    def show_tab(self,tab):
        if tab=='Malware Scan':
            self.current_tab=tab
            for name,btn in self.nav_buttons.items():
                btn.configure(bg=SLATE_CARD if tab==name else SLATE_SIDE,
                              fg=SLATE_GREEN if tab==name else SLATE_MUTED)
            self.reset_body()
            self._root_view(24)
            self.malware_page()
            return
        super().show_tab(tab)

    def overview_page(self):
        super().overview_page()

    def malware_page(self):
        self._page_header('Malware Scan','A real scan from Microsoft Defender, not guesses from Sovela.',
                          ('Protection history ↗',open_windows_security))
        heading=tk.Frame(self.view,bg=SLATE_BG);heading.pack(fill='x',pady=(0,10))
        self._label(heading,'CHOOSE A SCAN',9,True,color=SLATE_MUTED).pack(side='left')
        self._label(heading,'Runs only when Defender is active',9,color=SLATE_MUTED).pack(side='right')
        tiles=tk.Frame(self.view,bg=SLATE_BG);tiles.pack(fill='x')
        for i,(icon,name,desc,detail,mode) in enumerate([
            ('⚡','Quick scan','Common infection locations','Often takes minutes; a 5-minute finish is not guaranteed.','quick'),
            ('◎','Deep dive','Full computer scan','Checks all files Defender can access. Duration depends on PC and disk size.','full'),
        ]):
            edge,inside=self._surface(tiles,padding=18)
            edge.grid(row=0,column=i,sticky='nsew',padx=(0,12 if i==0 else 0))
            tiles.grid_columnconfigure(i,weight=1,uniform='scan')
            self._label(inside,icon,22,color=SLATE_GREEN).pack(anchor='w')
            self._label(inside,name,15,True).pack(anchor='w',pady=(10,4))
            self._label(inside,desc,10,color=SLATE_INK_SOFT).pack(anchor='w')
            self._label(inside,detail,9,color=SLATE_MUTED,wraplength=250).pack(anchor='w',pady=(5,10))
            b=self._button(inside,'Run '+name,lambda m=mode:self.start_device_scan(m),True)
            b.pack(anchor='w')
            if self.device_scan_busy:b.configure(state='disabled',cursor='arrow')
            self.tip(b,name,detail+' Sovela never disables your antivirus.')
        edge,panel=self._surface(self.view,padding=17,bg=LITE)
        edge.pack(fill='x',pady=(15,0))
        color=SLATE_ORANGE if self.device_scan_busy else SLATE_TEXT
        display=self.device_scan_message
        if self.device_scan_busy and self.device_scan_started:
            minutes=int((time.monotonic()-self.device_scan_started)//60)
            display=f'{self.device_scan_mode.title()} scan running · {minutes} min elapsed. Do not close Sovela while it monitors the command.'
        self._label(panel,'SCAN STATUS',9,True,color=SLATE_MUTED).pack(anchor='w')
        self._label(panel,display,11,strong=False,color=color,wraplength=625).pack(anchor='w',pady=(9,4))
        row=tk.Frame(panel,bg=LITE);row.pack(fill='x',pady=(11,0))
        self._button(row,'Open Windows Security ↗',open_windows_security,primary=False).pack(side='left')
        self._label(row,'No independent antivirus engine',9,color=SLATE_MUTED).pack(side='right',pady=(8,0))
        self._label(self.view,'If another antivirus is active, run its own scan. Sovela will not force Defender on or interfere with security settings.',
                    9,color=SLATE_MUTED,wraplength=650).pack(anchor='w',pady=(14,0))

    def start_device_scan(self,mode):
        if self.device_scan_busy:return
        if mode not in ('quick','full'):return
        if os.name!='nt':
            self.device_scan_message='Malware scans require Windows and an active Microsoft Defender installation.'
            self.show_tab('Malware Scan');return
        if mode=='full' and not messagebox.askyesno('Full scan',
                'A deep scan can take a long time and temporarily use significant CPU and disk activity.\n\nStart a full Microsoft Defender scan?',parent=self.root):
            return
        self.device_scan_busy=True
        self.device_scan_started=time.monotonic()
        self.device_scan_mode=mode
        self.device_scan_message='Starting Defender scan…'
        self.show_tab('Malware Scan')
        self.run_job('device_scan',lambda:run_defender_scan(mode))

    def _selection_changed(self):
        super()._selection_changed()
        selected=[key for key,name,description,mode in CATEGORIES if mode=='clean' and self.clean_choices[key].get()]
        if self._clean_btn is not None:
            enabled=bool(selected) and not self.care_busy
            self._clean_btn.configure(state='normal' if enabled else 'disabled',
                                      cursor='hand2' if enabled else 'arrow')
            self._clean_btn.configure(text='Clean selected' if self.clean_preview is not None else 'Scan & clean selected')
        if self._clean_hint is not None and selected and self.clean_preview is None:
            self._clean_hint.configure(text=f'{len(selected)} selected · Review before any cleanup')

    def cleaner_page(self):
        super().cleaner_page()
        if self._clean_btn is not None:
            self._clean_btn.configure(command=self.clean_click)
        self._selection_changed()

    def clean_click(self):
        if self.care_busy:return
        selected=[key for key,name,desc,mode in CATEGORIES if mode=='clean' and self.clean_choices[key].get()]
        if not selected:
            messagebox.showinfo('Select a category','Select a cleaning tile first.',parent=self.root)
            return
        if self.clean_preview is None:
            self._clean_on_preview=True
            self.preview_cleanup()
        else:
            self.run_cleanup()  # Existing preview totals and confirmation are preserved.

    def startup_page(self):
        self._page_header('Startup Manager','Choose apps by name and icon. Only safe per-user entries can be changed.',('Refresh ↻',self.inspect_startups))
        top=tk.Frame(self.view,bg=SLATE_BG);top.pack(fill='x',pady=(0,11))
        if self.startups is None:
            self._label(top,'No startup entries inspected yet.',10,color=SLATE_MUTED).pack(side='left',pady=8)
            self._button(top,'Inspect startup apps',self.inspect_startups).pack(side='right')
            return
        items=self.startups.get('items',[])
        editable=sum(1 for item in items if item.get('editable'))
        self._label(top,f'{len(items)} entries · {editable} manageable · others read-only',10,color=SLATE_INK_SOFT).pack(side='left',pady=7)
        self._button(top,'Windows startup ↗',lambda:self.open_settings('ms-settings:startupapps','Startup Apps'),False,True).pack(side='right')
        if self.startup_notice:
            self._label(self.view,self.startup_notice,9,color=SLATE_GREEN).pack(anchor='w',pady=(0,7))
        edge,card=self._surface(self.view,padding=0);edge.pack(fill='both',expand=True)
        header=tk.Frame(card,bg=LITE,height=35);header.pack(fill='x');header.pack_propagate(False)
        self._label(header,'PROGRAM',9,True,color=SLATE_MUTED).pack(side='left',padx=17,pady=8)
        self._label(header,'STARTUP',9,True,color=SLATE_MUTED).pack(side='right',padx=36,pady=8)
        area=tk.Frame(card,bg=WHITE);area.pack(fill='both',expand=True)
        canvas=tk.Canvas(area,bg=WHITE,highlightthickness=0,bd=0)
        bar=CalmScrollbar(area,canvas.yview,WHITE);bar.pack(side='right',fill='y')
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side='left',fill='both',expand=True)
        listing=tk.Frame(canvas,bg=WHITE)
        identifier=canvas.create_window(0,0,window=listing,anchor='nw')
        listing.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda ev:canvas.itemconfigure(identifier,width=ev.width))
        canvas.bind('<MouseWheel>',lambda ev:canvas.yview_scroll(-int(ev.delta/120) if ev.delta else 0,'units'))
        self._startup_canvas=canvas
        self._images=[]  # Keep Tk icon instances alive until the list redraws.
        for i,item in enumerate(items):
            row=tk.Frame(listing,bg=WHITE,padx=14,pady=8)
            row.pack(fill='x')
            icon_box=tk.Frame(row,bg=LITE,width=39,height=39)
            icon_box.pack(side='left',padx=(0,11));icon_box.pack_propagate(False)
            path=extract_path(str(item.get('detail','')))
            encoded=self._icons.get(path)
            picture=None
            if encoded:
                try:
                    picture=tk.PhotoImage(data=encoded,format='png')
                    if picture.width()>40:
                        picture=picture.subsample(max(1,(picture.width()+31)//32))
                    self._images.append(picture)
                except tk.TclError:picture=None
            if picture is not None:
                tk.Label(icon_box,image=picture,bg=LITE).pack(expand=True)
            else:
                name=str(item.get('name','App'))
                tk.Label(icon_box,text=name[:1].upper() or '•',bg=LITE,fg=SLATE_GREEN,
                         font=(SLATE_FONT,17,'bold')).pack(expand=True)
            block=tk.Frame(row,bg=WHITE);block.pack(side='left',fill='x',expand=True)
            name=str(item.get('name','Unknown'))
            self._label(block,name[:47],10,True).pack(anchor='w')
            caption=str(item.get('source',''))+'  ·  '+str(item.get('state',''))
            self._label(block,caption[:75],8,color=SLATE_MUTED).pack(anchor='w',pady=(3,0))
            detail=str(item.get('detail',''))
            if detail:self.tip(block,name,detail[:400])
            if item.get('editable'):
                active=item.get('state')=='Enabled'
                button=self._button(row,'Disable' if active else 'Restore',
                  lambda x=item,a=active:self.change_startup(x,not a),primary=False,compact=True)
                button.pack(side='right',padx=(8,0))
                self.tip(button,'Startup switch','Changes only a supported personal startup item. Restore is available later.')
            else:
                self._label(row,'Read-only',9,color=SLATE_MUTED).pack(side='right',padx=(8,4))
            if i<len(items)-1:tk.Frame(listing,bg=SLATE_LINE,height=1).pack(fill='x')
        self._label(self.view,'Icons are shown when Windows provides a readable program icon. Unknown apps stay read-only when appropriate.',
                    8,color=SLATE_MUTED).pack(anchor='w',pady=(9,0))

    def health_page(self):
        self._page_header('PC Health','Live resource checks with specific, evidence-based recommendations.',('Refresh ↻',self.health_check))
        if not self.last_health:
            edge,c=self._surface(self.view,padding=21);edge.pack(fill='x')
            self._label(c,'Your health report is ready in one click',14,True).pack(anchor='w')
            self._label(c,'Checks disk space, RAM and common startup locations. Never removes applications.',10,color=SLATE_MUTED).pack(anchor='w',pady=(7,13))
            self._button(c,'Check PC health',self.health_check).pack(anchor='w')
            return
        h=self.last_health
        metrics=tk.Frame(self.view,bg=SLATE_BG);metrics.pack(fill='x',pady=(0,12))
        for i,(name,free,total) in enumerate((('Storage',h['disk_free'],h['disk_total']),('Memory',h['ram_free'],h['ram_total']))):
            e,c=self._surface(metrics,padding=13);e.grid(row=0,column=i,sticky='nsew',padx=(0,10 if i==0 else 0))
            metrics.grid_columnconfigure(i,weight=1)
            used=max(0,min(100,int(100*(total-free)/max(1,total))))
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            self._label(row,name,11,True).pack(side='left')
            self._label(row,f'{used}% used',11,True,color=SLATE_ORANGE if used>=90 else SLATE_GREEN).pack(side='right')
            bar=tk.Frame(c,bg=SLATE_LINE,height=7);bar.pack(fill='x',pady=(10,6))
            tk.Frame(bar,bg=SLATE_ORANGE if used>=90 else SLATE_GREEN).place(relwidth=used/100,relheight=1)
            self._label(c,f'{self.human_bytes(free)} free',9,color=SLATE_MUTED).pack(anchor='w')
        self._label(self.view,'PERSONALISED SUGGESTIONS',9,True,color=SLATE_MUTED).pack(anchor='w',pady=(0,8))
        recommendations=suggest(h,self.startups)
        for title,explanation,level in recommendations[:3]:
            edge,c=self._surface(self.view,padding=10)
            edge.pack(fill='x',pady=(0,7))
            line=tk.Frame(c,bg=WHITE);line.pack(fill='x')
            self._label(line,'●',12,color=SLATE_ORANGE if level=='high' else SLATE_GREEN).pack(side='left',padx=(0,7))
            self._label(line,title,10,True).pack(side='left')
            note=self._label(c,explanation,9,color=SLATE_MUTED,wraplength=610)
            note.pack(anchor='w',pady=(3,0))
        downloads=older_large_downloads(limit=5)
        box=tk.Frame(self.view,bg=SLATE_BG);box.pack(fill='x',pady=(7,0))
        if downloads:
            e,c=self._surface(box,padding=10);e.pack(fill='x')
            names=', '.join(d['name'][:20] for d in downloads[:2])
            self._label(c,'Older large downloads (review only)',10,True).pack(anchor='w')
            self._label(c,f'{len(downloads)} installers/archives over 200 MB and 90 days old. Examples: {names}',9,
                        color=SLATE_MUTED,wraplength=610).pack(anchor='w',pady=(4,0))
            self.tip(c,'Old download candidates','These are not necessarily unwanted. Sovela has not checked whether games or programs are still used, and will never uninstall them automatically.')
        buttons=tk.Frame(self.view,bg=SLATE_BG);buttons.pack(fill='x',pady=(11,0))
        self._button(buttons,'Manage startup',lambda:self.show_tab('Startup'),False,True).pack(side='left')
        self._button(buttons,'Storage settings ↗',lambda:self.open_settings('ms-settings:storagesense','Storage settings'),False,True).pack(side='left',padx=(8,0))
        self._button(buttons,'Task Manager ↗',self.open_task_manager,False,True).pack(side='left',padx=(8,0))

    def open_task_manager(self):
        if os.name!='nt':return
        try:
            import subprocess
            subprocess.Popen(['taskmgr.exe'],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            messagebox.showinfo('Task Manager','Press Ctrl + Shift + Esc to open Task Manager.',parent=self.root)

    def _maybe_fetch_icons(self):
        if not self.startups:return
        items=self.startups.get('items',[])
        signature=tuple((x.get('name'),x.get('detail'),x.get('state')) for x in items)
        if not signature or signature==self._requested_icon_signature:return
        self._requested_icon_signature=signature
        def task():
            icons=extract_icons(items)
            self._icon_queue.put(icons)
        threading.Thread(target=task,daemon=True).start()

    def poll_events(self):
        # Intercept the new scan event before inherited events are processed.
        remaining=[]
        while True:
            try:kind,state,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='device_scan':
                self.device_scan_busy=False
                self.device_scan_started=None
                if state=='ok':
                    self.device_scan_message=value['message']
                    self.record_activity('Microsoft Defender '+value['mode']+' scan command finished')
                else:
                    self.device_scan_message='Scan unavailable: '+str(value)
                    self.record_activity('Defender scan unavailable')
            else:
                remaining.append((kind,state,value))
        for item in remaining:self.events.put(item)
        super().poll_events()
        # Inherited event processing may deliver an updated startup list.
        self._maybe_fetch_icons()
        changed=False
        while True:
            try:icons=self._icon_queue.get_nowait()
            except queue.Empty:break
            self._icons.update(icons)
            changed=True
        if changed and self.current_tab=='Startup':self.show_tab('Startup')
        # After scanning for cleaner files, prompt *once* through the existing
        # review/confirmation flow; never clean just because a preview completed.
        if self._clean_on_preview and not self.care_busy:
            self._clean_on_preview=False
            if self.clean_preview is not None:
                self.root.after(40,self.run_cleanup)
        if not self.device_scan_busy and self.current_tab=='Malware Scan':
            # Only redraw on state change or when an event was received.
            if hasattr(self,'_last_scan_render'):
                current=(self.device_scan_busy,self.device_scan_message)
                if current!=self._last_scan_render:
                    self.show_tab('Malware Scan')
                    self._last_scan_render=current
            else:self._last_scan_render=(self.device_scan_busy,self.device_scan_message)
