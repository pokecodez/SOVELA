"""Sovela Quick Access: compact, task-first GUI atop the existing safeguarded engine.

All destructive operations continue to be delegated to sovela_ai/sovela_care,
including explicit confirmation, personal-folder allowlists, age / stat checks,
and Win32 Recycle Bin recycling only. UI never performs file deletions itself.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from sovela_ai import (SovelaApp, CalmScrollbar, SLATE_BG, SLATE_SIDE,
                         SLATE_CARD, SLATE_TEXT, SLATE_MUTED, SLATE_GREEN,
                         SLATE_GREEN_SOFT, SLATE_LINE, SLATE_ORANGE,
                         SLATE_ORANGE_SOFT, SLATE_FONT, SLATE_INPUT,
                         SLATE_INK_SOFT, open_windows_security, gb)
from sovela_care import CATEGORIES

WHITE = '#FFFFFF'
LITE = '#F7FAF8'
ACTIVE = '#E1F0E9'
DEEP = '#254A40'
SOFT = '#84978E'


class MouseFollowTip:
    """Short delay, mouse-following tooltip; absolutely no modal interaction."""
    def __init__(self, root, widget, heading, description):
        self.root = root
        self.widget = widget
        self.heading = heading
        self.description = description
        self.pop = None
        self.timer = None
        self.px = 0
        self.py = 0
        widget.bind('<Enter>', self.enter, add='+')
        widget.bind('<Motion>', self.motion, add='+')
        widget.bind('<Leave>', self.leave, add='+')
        widget.bind('<Destroy>', self.leave, add='+')

    def enter(self, e):
        self.px, self.py = e.x_root, e.y_root
        self.cancel_timer()
        self.timer = self.root.after(240, self.open)

    def motion(self, e):
        self.px, self.py = e.x_root, e.y_root
        if self.pop is not None:
            self.place()

    def cancel_timer(self):
        if self.timer:
            try: self.root.after_cancel(self.timer)
            except tk.TclError: pass
            self.timer = None

    def open(self):
        self.timer = None
        if not self.widget.winfo_exists():
            return
        if self.pop is not None:
            return
        self.pop = tk.Toplevel(self.root)
        self.pop.withdraw()
        self.pop.overrideredirect(True)
        try: self.pop.attributes('-topmost', True)
        except tk.TclError: pass
        edge = tk.Frame(self.pop, bg=SLATE_LINE, padx=1, pady=1)
        edge.pack()
        body = tk.Frame(edge, bg=WHITE, padx=13, pady=11)
        body.pack()
        tk.Label(body, text=self.heading, bg=WHITE, fg=SLATE_TEXT,
                 font=(SLATE_FONT,10,'bold'), anchor='w').pack(anchor='w')
        tk.Label(body, text=self.description, bg=WHITE, fg=SLATE_INK_SOFT,
                 font=(SLATE_FONT,9), wraplength=250, justify='left',
                 anchor='w').pack(anchor='w',pady=(5,0))
        self.pop.update_idletasks()
        self.place()
        self.pop.deiconify()

    def place(self):
        if self.pop is None:
            return
        w, h = self.pop.winfo_reqwidth(), self.pop.winfo_reqheight()
        try:
            x0, y0, x1, y1 = self.root.winfo_screenwidth()*0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            x = min(max(x0+4, self.px + 22), max(x0+4, x1-w-8))
            y = min(max(y0+4, self.py + 19), max(y0+4, y1-h-8))
            self.pop.geometry(f'+{int(x)}+{int(y)}')
        except tk.TclError:
            pass

    def leave(self, _e=None):
        self.cancel_timer()
        if self.pop is not None:
            try: self.pop.destroy()
            except tk.TclError: pass
            self.pop = None


class SovelaQuickApp(SovelaApp):
    WIDTH, HEIGHT = 960, 690

    def __init__(self, root):
        self._tips = []
        self._quick_clean_widgets = {}
        self._clean_btn = None
        self._clean_hint = None
        super().__init__(root)
        root.title('Sovela | Quick Access v1.3')

    def reset_body(self):
        for tip in self._tips:
            tip.leave()
        self._tips = []
        self._quick_clean_widgets = {}
        self._clean_btn = None
        self._clean_hint = None
        super().reset_body()

    def tip(self, widget, heading, description):
        self._tips.append(MouseFollowTip(self.root, widget, heading, description))

    def make_nav(self):
        """Structured navigation with the common tasks near the top."""
        self.nav_buttons = {}
        for heading, items in [
            ('ESSENTIALS', [('Overview','⌂'),('Protection','◇'),('Cleaner','✧'),('Startup','≡')]),
            ('YOUR DEVICE', [('Downloads','↓'),('PC Health','◌')]),
            ('SUPPORT', [('Assistant','☼'),('Activity','◷'),('Tools','⚙')]),
        ]:
            tk.Label(self.sidebar,text=heading,bg=SLATE_SIDE,fg=SLATE_MUTED,
                     font=(SLATE_FONT,8,'bold')).pack(anchor='w',padx=23,pady=(21 if heading=='ESSENTIALS' else 15,7))
            for name,icon in items:
                line=tk.Frame(self.sidebar,bg=SLATE_SIDE)
                line.pack(fill='x',padx=10,pady=1)
                btn=self.text_button(line,f'{icon}    {name}',lambda n=name:self.show_tab(n),
                                     size=10,bg=SLATE_SIDE,fg=SLATE_MUTED)
                btn.configure(anchor='w',padx=15,pady=8)
                btn.pack(fill='x')
                self.nav_buttons[name]=btn
        tk.Frame(self.sidebar,bg=SLATE_SIDE).pack(fill='both',expand=True)
        tk.Label(self.sidebar,text='No ads. No surprise changes.',bg=SLATE_SIDE,
                 fg=SLATE_MUTED,font=(SLATE_FONT,9),justify='center').pack(pady=(0,22))

    def on_global_wheel(self,event):
        # Most quick-access screens intentionally have no page-level scrolling.
        if self.current_tab in ('Assistant','Activity'):
            return super().on_global_wheel(event)
        if self.current_tab=='Startup':
            canvas=getattr(self,'_startup_canvas',None)
            if canvas is not None:
                try:
                    if canvas.winfo_exists():
                        x,y=canvas.winfo_rootx(),canvas.winfo_rooty()
                        if x <= event.x_root <= x+canvas.winfo_width() and y <= event.y_root <= y+canvas.winfo_height():
                            canvas.yview_scroll(-int(event.delta/120) if event.delta else 0,'units')
                except tk.TclError:
                    pass

    def _root_view(self, pad=24):
        self.view=tk.Frame(self.body,bg=SLATE_BG,padx=pad,pady=19)
        self.view.pack(fill='both',expand=True)

    def show_tab(self,tab):
        """Important pages are fixed-height; only long lists get an inner scrollbar."""
        self.current_tab=tab
        for name,btn in self.nav_buttons.items():
            btn.configure(bg=SLATE_CARD if tab==name else SLATE_SIDE,
                          fg=SLATE_GREEN if tab==name else SLATE_MUTED)
        self.reset_body()
        if tab=='Assistant':
            self.assistant_page()
            return
        direct={
            'Overview':self.overview_page,
            'Protection':self.protection_page,
            'Cleaner':self.cleaner_page,
            'Startup':self.startup_page,
            'Downloads':self.downloads_page,
            'PC Health':self.health_page,
            'Tools':self.tools_page,
        }
        if tab in direct:
            self._root_view(24)
            direct[tab]()
            return
        # Activity (potentially long) retains the previous custom scrollbar.
        super().show_tab(tab)

    def _label(self,parent,text, size=10, strong=False,color=SLATE_TEXT,**kwargs):
        l=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,
                   font=(SLATE_FONT,size,'bold' if strong else 'normal'),
                   anchor='w',justify='left',**kwargs)
        return l

    def _page_header(self, title, subtitle, action=None):
        top=tk.Frame(self.view,bg=SLATE_BG)
        top.pack(fill='x',pady=(0,16))
        left=tk.Frame(top,bg=SLATE_BG);left.pack(side='left',fill='x',expand=True)
        self._label(left,title,21,True).pack(anchor='w')
        self._label(left,subtitle,9,color=SLATE_MUTED).pack(anchor='w',pady=(5,0))
        if action:
            label,fn=action
            b=self._button(top,label,fn,primary=False)
            b.pack(side='right',pady=(9,0))
        return top

    def _button(self,parent,label,fn,primary=True,compact=False):
        return tk.Button(parent,text=label,command=fn,bg=SLATE_GREEN if primary else SLATE_GREEN_SOFT,
                         fg=WHITE if primary else DEEP,activebackground=DEEP if primary else ACTIVE,
                         activeforeground=WHITE if primary else DEEP,
                         font=(SLATE_FONT,10,'bold'),bd=0,relief='flat',highlightthickness=0,
                         cursor='hand2',padx=17 if not compact else 10,pady=10 if not compact else 7)

    def _surface(self,parent, padding=17, bg=SLATE_CARD):
        edge=tk.Frame(parent,bg=SLATE_LINE,padx=1,pady=1)
        inner=tk.Frame(edge,bg=bg,padx=padding,pady=padding)
        inner.pack(fill='both',expand=True)
        return edge,inner

    def _metric(self,parent,label,value,extra=''):
        edge,inner=self._surface(parent,padding=15)
        self._label(inner,label,9,color=SLATE_MUTED).pack(anchor='w')
        self._label(inner,value,13,True,wraplength=180).pack(anchor='w',pady=(10,0))
        if extra:
            self._label(inner,extra,9,color=SLATE_MUTED,wraplength=186).pack(anchor='w',pady=(5,0))
        return edge

    def overview_page(self):
        self._page_header('Your PC, at a glance','Everything you need within one or two clicks.',('Refresh ↻',self.check))
        edge,hero=self._surface(self.view,padding=20)
        edge.pack(fill='x',pady=(0,14))
        top=tk.Frame(hero,bg=WHITE);top.pack(fill='x')
        tk.Label(top,text='●',bg=WHITE,fg=SLATE_GREEN,font=(SLATE_FONT,18)).pack(side='left',padx=(0,8))
        self._label(top,'SECURITY STATUS',10,True,color=SLATE_GREEN).pack(side='left')
        self._label(hero,self.status,17,True,wraplength=610).pack(anchor='w',pady=(8,5))
        self._label(hero,'Status from Windows — not a malware scan or safety guarantee.',9,color=SLATE_MUTED).pack(anchor='w')
        row=tk.Frame(hero,bg=WHITE);row.pack(fill='x',pady=(15,0))
        self._button(row,'Check protection',self.check).pack(side='left')
        self._button(row,'Windows Security ↗',open_windows_security,False).pack(side='left',padx=(9,0))
        self._label(self.view,'QUICK ACTIONS',9,True,color=SLATE_MUTED).pack(anchor='w',pady=(5,9))
        quick=tk.Frame(self.view,bg=SLATE_BG);quick.pack(fill='x')
        for i,(ico,title,sub,tab) in enumerate([
            ('✧','PC Cleaner','Free up storage','Cleaner'),
            ('≡','Startup apps','Control launch apps','Startup'),
            ('◌','PC Health','Storage & memory','PC Health'),
            ('☼','Ask Sovela','Guided support','Assistant'),
        ]):
            e,c=self._surface(quick,padding=13)
            e.grid(row=0,column=i,sticky='nsew',padx=(0,9 if i<3 else 0))
            quick.grid_columnconfigure(i,weight=1,uniform='quick')
            self._label(c,ico,22,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,title,11,True).pack(anchor='w',pady=(6,1))
            self._label(c,sub,8,color=SLATE_MUTED).pack(anchor='w')
            for w in (e,c,*c.winfo_children()):
                w.configure(cursor='hand2')
                w.bind('<Button-1>',lambda _evt,t=tab:self.show_tab(t))
        bottom=tk.Frame(self.view,bg=SLATE_BG);bottom.pack(fill='x',pady=(14,0))
        for i,(name,key) in enumerate([('Antivirus','antivirus'),('Defender','defender'),('Firewall','firewall')]):
            e=self._metric(bottom,name,str(self.security_details[key])[:60])
            e.grid(row=0,column=i,sticky='nsew',padx=(0,10 if i<2 else 0))
            bottom.grid_columnconfigure(i,weight=1,uniform='stat')

    def protection_page(self):
        self._page_header('Protection','Your Windows protection at a glance.',('Refresh ↻',self.check))
        for title,key in [('Registered antivirus','antivirus'),('Microsoft Defender','defender'),('Windows Firewall','firewall')]:
            e,c=self._surface(self.view,padding=14)
            e.pack(fill='x',pady=(0,10))
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            self._label(row,title,10,True).pack(side='left')
            self._label(row,str(self.security_details[key]),10,color=SLATE_INK_SOFT,wraplength=410).pack(side='right')
        row=tk.Frame(self.view,bg=SLATE_BG);row.pack(fill='x',pady=(5,0))
        self._button(row,'Open Windows Security ↗',open_windows_security).pack(side='left')
        self._button(row,'Copy report',self.copy_summary,False).pack(side='left',padx=(9,0))
        if self.report_notice: self._label(self.view,self.report_notice,9,color=SLATE_GREEN).pack(anchor='w',pady=(8,0))
        self._label(self.view,'Sovela reads Windows settings. Keep your current antivirus enabled.',9,color=SLATE_MUTED).pack(anchor='w',pady=(14,0))

    def _selection_changed(self):
        for key,(edge,inner,headline,marker,detail) in self._quick_clean_widgets.items():
            active=self.clean_choices[key].get()
            bg=ACTIVE if active else WHITE
            edge.configure(bg=SLATE_GREEN if active else SLATE_LINE)
            inner.configure(bg=bg)
            for widget in inner.winfo_children():
                if isinstance(widget,tk.Frame):
                    widget.configure(bg=bg)
                    for child in widget.winfo_children():
                        if isinstance(child,tk.Label) and child is not marker:
                            child.configure(bg=bg)
                elif isinstance(widget,tk.Label) and widget is not marker:
                    widget.configure(bg=bg)
            marker.configure(text='✓' if active else '+',bg=SLATE_GREEN if active else SLATE_GREEN_SOFT,
                             fg=WHITE if active else SLATE_GREEN)
        sel=[key for key,_,_,mode in CATEGORIES if mode=='clean' and self.clean_choices[key].get()]
        if self._clean_btn is not None:
            ready=bool(sel and self.clean_preview is not None and not self.care_busy
                       and sum(len(self.clean_preview.get(k,{}).get('files',[])) for k in sel)>0)
            self._clean_btn.configure(state='normal' if ready else 'disabled',
                                      cursor='hand2' if ready else 'arrow')
        if self._clean_hint is not None:
            if not sel:
                text='Select one or more categories above.'
            elif self.clean_preview is None:
                text=f'{len(sel)} selected  ·  Scan to see eligible files.'
            else:
                total=sum(self.clean_preview.get(k,{}).get('bytes',0) for k in sel)
                count=sum(len(self.clean_preview.get(k,{}).get('files',[])) for k in sel)
                text=f'{len(sel)} selected  ·  {count} files  ·  {self.human_bytes(total)} eligible'
            self._clean_hint.configure(text=text)

    def _toggle_tile(self,key):
        self.clean_choices[key].set(not self.clean_choices[key].get())
        self._selection_changed()

    def cleaner_page(self):
        self._page_header('PC Cleaner','Select what to clean, scan, then confirm.',('Windows Storage ↗',lambda:self.open_settings('ms-settings:storagesense','Storage settings')))
        row=tk.Frame(self.view,bg=SLATE_BG);row.pack(fill='x',pady=(0,8))
        self._label(row,'AUTOMATIC CLEANUP',9,True,color=SLATE_MUTED).pack(side='left')
        self._label(row,'Select multiple',9,color=SLATE_MUTED).pack(side='right')
        tiles=tk.Frame(self.view,bg=SLATE_BG)
        tiles.pack(fill='x')
        icons={'temp':'◇','cache':'◎','reports':'▤','dumps':'▦'}
        subtitles={'temp':'Old temporary items','cache':'Browser cache only',
                   'reports':'Archived error logs','dumps':'Old app crash files'}
        for col,(key,name,desc,mode) in enumerate([c for c in CATEGORIES if c[3]=='clean']):
            edge,inside=self._surface(tiles,padding=13)
            edge.grid(row=0,column=col,sticky='nsew',padx=(0,9 if col<3 else 0))
            tiles.grid_columnconfigure(col,weight=1,uniform='tiles')
            tile_row=tk.Frame(inside,bg=WHITE)
            tile_row.pack(fill='x')
            symbol=self._label(tile_row,icons[key],19,color=SLATE_GREEN)
            symbol.pack(side='left')
            mark=tk.Label(tile_row,text='+',bg=SLATE_GREEN_SOFT,fg=SLATE_GREEN,
                          font=(SLATE_FONT,12,'bold'),width=2)
            mark.pack(side='right')
            title=self._label(inside,name,10,True)
            title.pack(anchor='w',pady=(12,2))
            caption=self._label(inside,subtitles[key],8,color=SLATE_MUTED)
            caption.pack(anchor='w')
            count=tk.Label(inside,text='Hover for details  ↗',bg=WHITE,fg=SLATE_MUTED,
                           font=(SLATE_FONT,8),anchor='w')
            count.pack(anchor='w',pady=(7,0))
            self._quick_clean_widgets[key]=(edge,inside,title,mark,count)
            for w in (edge,inside,tile_row,symbol,mark,title,caption,count):
                w.configure(cursor='hand2')
                w.bind('<Button-1>',lambda _e,k=key:self._toggle_tile(k))
                self.tip(w,name,desc + (' Preview and confirmation required before recycling.' if key!='cache' else ' Close browsers before cleaning; cached images and files may need to download again.'))
            if self.clean_preview is not None:
                matched=self.clean_preview.get(key,{})
                count.configure(text=f'{len(matched.get("files",[]))} files  ·  {self.human_bytes(matched.get("bytes",0))}')
        self._selection_changed()
        actions_edge,actions=self._surface(self.view,padding=14,bg=LITE)
        actions_edge.pack(fill='x',pady=(12,0))
        self._clean_btn=self._button(actions,'Clean selected',self.run_cleanup,primary=True)
        self._clean_btn.pack(side='right')
        scan=self._button(actions,'①  Scan files',self.preview_cleanup,primary=False)
        scan.pack(side='right',padx=(0,9))
        if self.care_busy: scan.configure(state='disabled')
        self._clean_hint=self._label(actions,'Select categories above',10,color=SLATE_INK_SOFT)
        self._clean_hint.pack(side='left',fill='x',expand=True,pady=(9,0))
        self._selection_changed()
        notice=self.clean_notice or ('Nothing has been cleaned.' if self.clean_preview is None else 'Scan finished. Review your selections before cleaning.')
        notice_color=SLATE_ORANGE if ('Could not' in notice or 'stopped' in notice) else SLATE_INK_SOFT
        self._label(self.view,notice,9,color=notice_color,wraplength=660).pack(anchor='w',pady=(9,0))
        sep=tk.Frame(self.view,bg=SLATE_LINE,height=1);sep.pack(fill='x',pady=(17,12))
        self._label(self.view,'MANUAL CLEANUP',9,True,color=SLATE_MUTED).pack(anchor='w',pady=(0,8))
        manual=tk.Frame(self.view,bg=SLATE_BG);manual.pack(fill='x')
        for col,(key,name,desc,_mode) in enumerate([c for c in CATEGORIES if c[3]=='guided']):
            e,c=self._surface(manual,padding=13)
            e.grid(row=0,column=col,sticky='nsew',padx=(0,9 if col==0 else 0))
            manual.grid_columnconfigure(col,weight=1,uniform='manual')
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            self._label(row,('◉  ' if key=='cookies' else '♻  ')+name,10,True).pack(side='left')
            fn=self.browser_cookie_help if key=='cookies' else self.open_recycle
            b=self._button(row,'Manage ↗',fn,primary=False,compact=True)
            b.pack(side='right')
            self.tip(b,name,desc)
            self._label(c,'Controlled in your browser' if key=='cookies' else 'Controlled by Windows',8,color=SLATE_MUTED).pack(anchor='w',pady=(6,0))
        self._label(self.view,'Only selected eligible old files are sent to Recycle Bin. Cookies are never cleared by Sovela.',
                    8,color=SLATE_MUTED,wraplength=670).pack(anchor='w',pady=(14,0))

    def startup_page(self):
        self._page_header('Startup Manager','Control supported personal startup entries.',('Refresh ↻',self.inspect_startups))
        top=tk.Frame(self.view,bg=SLATE_BG)
        top.pack(fill='x',pady=(0,12))
        if self.startups is None:
            self._label(top,'No startup list yet.',10,color=SLATE_MUTED).pack(side='left',pady=8)
            self._button(top,'Inspect startup programs',self.inspect_startups).pack(side='right')
            return
        items=self.startups.get('items',[])
        editable=sum(1 for item in items if item.get('editable'))
        self._label(top,f'{len(items)} entries  ·  {editable} manageable  ·  others read-only',10,color=SLATE_INK_SOFT).pack(side='left',pady=7)
        self._button(top,'Windows startup ↗',lambda:self.open_settings('ms-settings:startupapps','Startup Apps'),False,True).pack(side='right')
        if self.startup_notice:
            self._label(self.view,self.startup_notice,9,color=SLATE_GREEN).pack(anchor='w',pady=(0,7))
        e, card=self._surface(self.view,padding=0)
        e.pack(fill='both',expand=True)
        head=tk.Frame(card,bg=LITE,height=35);head.pack(fill='x');head.pack_propagate(False)
        self._label(head,'APPLICATION',9,True,color=SLATE_MUTED).pack(side='left',padx=17,pady=8)
        self._label(head,'ACTION',9,True,color=SLATE_MUTED).pack(side='right',padx=35,pady=8)
        body=tk.Frame(card,bg=WHITE);body.pack(fill='both',expand=True)
        canvas=tk.Canvas(body,bg=WHITE,highlightthickness=0,bd=0)
        bar=CalmScrollbar(body,canvas.yview,WHITE);bar.pack(side='right',fill='y')
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side='left',fill='both',expand=True)
        list_frame=tk.Frame(canvas,bg=WHITE)
        wid=canvas.create_window(0,0,window=list_frame,anchor='nw')
        list_frame.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda ev:canvas.itemconfigure(wid,width=ev.width))
        def wheel(ev):
            canvas.yview_scroll(-int(ev.delta/120) if ev.delta else 0,'units')
        self._startup_canvas=canvas
        # Avoid hijacking global mouse wheel when the cursor is outside the list.
        canvas.bind('<MouseWheel>',wheel)
        list_frame.bind('<MouseWheel>',wheel)
        for i,item in enumerate(items):
            row=tk.Frame(list_frame,bg=WHITE,padx=14,pady=8)
            row.pack(fill='x')
            block=tk.Frame(row,bg=WHITE);block.pack(side='left',fill='x',expand=True)
            name=str(item.get('name','Unknown'))
            self._label(block,name[:56],10,True).pack(anchor='w')
            caption=str(item.get('source',''))+'  ·  '+str(item.get('state',''))
            self._label(block,caption[:82],8,color=SLATE_MUTED).pack(anchor='w',pady=(3,0))
            detail=str(item.get('detail',''))
            if detail:
                for w in (row,block):self.tip(w,name,detail[:420])
            if item.get('editable'):
                active=item.get('state')=='Enabled'
                b=self._button(row,'Disable' if active else 'Restore',
                    lambda x=item,a=active:self.change_startup(x,not a),primary=False,compact=True)
                b.pack(side='right',padx=(9,0))
                self.tip(b,'Reversible setting','Controls this supported current-user startup entry only. Sovela stores information needed to restore it.')
            else:
                self._label(row,'Read-only',9,color=SLATE_MUTED).pack(side='right',padx=(10,8))
            if i<len(items)-1:
                tk.Frame(list_frame,bg=SLATE_LINE,height=1).pack(fill='x')
        self._label(self.view,'Only eligible per-user entries can be changed. Services, scheduled tasks and security tools are left alone.',8,color=SLATE_MUTED,wraplength=660).pack(anchor='w',pady=(10,0))

    def downloads_page(self):
        self._page_header('File Inspector','Inspect a selected file without opening it.')
        e,c=self._surface(self.view,padding=18)
        e.pack(fill='x',pady=(0,13))
        row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
        self._label(row,'Choose a file to inspect',13,True).pack(side='left')
        self._button(row,'Choose file ↗',self.choose_file).pack(side='right')
        if self.selected_file:self._label(c,self.selected_file.name,10,color=SLATE_INK_SOFT).pack(anchor='w',pady=(9,0))
        if self.last_file:
            e,c=self._surface(self.view,padding=15);e.pack(fill='x',pady=(0,13))
            self._label(c,self.last_file['name'],12,True).pack(anchor='w')
            self._label(c,f'{self.human_bytes(self.last_file["size"])}  ·  {self.last_file["extension"]}',10,color=SLATE_MUTED).pack(anchor='w',pady=(6,0))
            self._label(c,self.last_file['note'],9,color=SLATE_ORANGE,wraplength=630).pack(anchor='w',pady=(8,0))
            self._label(c,'SHA-256: '+str(self.last_file['sha256']),8,color=SLATE_MUTED,wraplength=650).pack(anchor='w',pady=(7,0))
        e,c=self._surface(self.view,padding=15);e.pack(fill='x')
        row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
        self._label(row,'Microsoft Defender scan',11,True).pack(side='left')
        b=self._button(row,'Request scan',self.defender_scan,primary=False,compact=True)
        b.pack(side='right')
        if not self.selected_file or self.scanning or self.working_file: b.configure(state='disabled')
        self._label(c,self.scan_message,9,color=SLATE_MUTED,wraplength=620).pack(anchor='w',pady=(7,0))
        self._label(self.view,'Sovela shows file information. It does not determine whether a file is safe.',9,color=SLATE_MUTED).pack(anchor='w',pady=(15,0))

    def health_page(self):
        self._page_header('PC Health','A simple overview of device resources.',('Refresh ↻',self.health_check))
        if not self.last_health:
            e,c=self._surface(self.view,padding=22);e.pack(fill='x')
            self._label(c,'No health report yet',15,True).pack(anchor='w')
            self._label(c,'Click below to check storage and memory use.',10,color=SLATE_MUTED).pack(anchor='w',pady=(9,0))
            b=self._button(c,'Check PC health',self.health_check)
            b.pack(anchor='w',pady=(16,0))
            return
        h=self.last_health
        row=tk.Frame(self.view,bg=SLATE_BG);row.pack(fill='x')
        for i,(name,used,total,free) in enumerate([
            ('Storage',h['disk_total']-h['disk_free'],h['disk_total'],h['disk_free']),
            ('Memory',h['ram_total']-h['ram_free'],h['ram_total'],h['ram_free'])]):
            e,c=self._surface(row,padding=19);e.grid(row=0,column=i,sticky='nsew',padx=(0,11 if i==0 else 0))
            row.grid_columnconfigure(i,weight=1)
            pct=max(0,min(100,round(100*used/max(total,1))))
            self._label(c,name,11,True).pack(anchor='w')
            self._label(c,f'{pct}% used',23,True).pack(anchor='w',pady=(14,4))
            self._label(c,f'{gb(free)} available',9,color=SLATE_MUTED).pack(anchor='w')
            track=tk.Frame(c,bg=SLATE_LINE,height=9);track.pack(fill='x',pady=(19,2))
            tk.Frame(track,bg=SLATE_GREEN if pct<90 else SLATE_ORANGE).place(relwidth=pct/100,relheight=1)
        e,c=self._surface(self.view,padding=17);e.pack(fill='x',pady=(14,0))
        self._label(c,f'{h.get("startup_count",0)} detected startup entries',12,True).pack(anchor='w')
        r=tk.Frame(c,bg=WHITE);r.pack(fill='x',pady=(11,0))
        self._button(r,'Manage startup',lambda:self.show_tab('Startup')).pack(side='left')
        self._button(r,'Clean PC',lambda:self.show_tab('Cleaner'),primary=False).pack(side='left',padx=(9,0))

    def tools_page(self):
        self._page_header('Tools','Common Windows actions, without hunting through menus.')
        tools=[('◇','Windows Security','Protection settings',open_windows_security),
               ('↻','Windows Update','Updates and patches',lambda:self.open_settings('ms-settings:windowsupdate','Windows Update')),
               ('≡','Startup Apps','Windows startup settings',lambda:self.open_settings('ms-settings:startupapps','Startup Apps')),
               ('✧','Storage','Windows storage settings',lambda:self.open_settings('ms-settings:storagesense','Storage settings'))]
        grid=tk.Frame(self.view,bg=SLATE_BG);grid.pack(fill='x')
        for i,(icon,title,desc,fn) in enumerate(tools):
            e,c=self._surface(grid,padding=17)
            e.grid(row=i//2,column=i%2,sticky='nsew',padx=(0,11 if i%2==0 else 0),pady=(0,12))
            grid.grid_columnconfigure(i%2,weight=1)
            self._label(c,icon,21,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,title,12,True).pack(anchor='w',pady=(11,3))
            self._label(c,desc,9,color=SLATE_MUTED).pack(anchor='w')
            self._button(c,'Open ↗',fn,primary=False,compact=True).pack(anchor='w',pady=(12,0))
