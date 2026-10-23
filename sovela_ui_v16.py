"""Sovela v1.6: non-deceptive startup readiness overlay, calm animated navigation,
compact settings with real dropdown controls, and accessible active-page state.

No malware scan is started by the visual preflight. Previously implemented Windows
Defender checks, cleaner confirmation and startup protections are inherited.
"""
from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox, ttk

from sovela_ui_v15 import (
    SovelaCareApp, SLATE_BG, SLATE_SIDE, SLATE_CARD, SLATE_TEXT,
    SLATE_MUTED, SLATE_GREEN, SLATE_GREEN_SOFT, SLATE_LINE,
    SLATE_FONT, SLATE_INK_SOFT, WHITE, DEEP, LITE, ACTIVE,
)
from sovela_preferences import (
    DEFAULTS, VALID_PAGES, MOTION_STYLES, MOTION_SPEEDS,
)

CARE_TIPS = (
    'Keep Windows and your browser updated to close known security gaps.',
    'Back up important files to a separate drive or trusted cloud account.',
    'Use a password manager and turn on two-factor authentication.',
    'Only install software from publishers and sources you trust.',
    'Leave real-time antivirus protection enabled while browsing.',
    'Review unfamiliar startup apps instead of disabling everything.',
    'Keep some free storage space so Windows can update and work smoothly.',
    'Check links and attachments carefully before you open them.',
    'Restart occasionally when Windows needs to finish installing updates.',
    'You do not need multiple real-time antivirus engines competing for control.',
)

class SovelaPolishedApp(SovelaCareApp):
    """All security operations remain delegated to the existing, tested backend."""

    _WARM_PAGES = ('Protection', 'Malware Scan', 'Cleaner', 'Startup',
                   'Downloads', 'PC Health', 'Assistant', 'Activity', 'Tools')

    def __init__(self, root):
        self._booting = True
        self._boot_overlay = None
        self._boot_jobs = []
        self._boot_percent = None
        self._boot_spinner = None
        self._boot_tip = None
        self._boot_step = 0
        self._tip_index = 0
        self._transition_generation = 0
        self._transition_canvas = None
        self._last_transition = None
        self._settings_page_name = 'Appearance'
        self._settings_drop_vars = {}
        super().__init__(root)
        root.title('Sovela | Slate edition 1.6')
        self._replace_footer_version(self.frame)
        self._startup_overlay()
        self.root.after(80, self._warm_next_page)

    def _replace_footer_version(self, widget):
        try:
            if isinstance(widget, tk.Label):
                text=widget.cget('text')
                if 'v1.5' in text or 'v1.4' in text or 'v1.3' in text:
                    for old in ('v1.5','v1.4','v1.3'):
                        text=text.replace(old,'v1.6')
                    widget.configure(text=text)
            for child in widget.winfo_children():
                self._replace_footer_version(child)
        except tk.TclError:
            pass

    # --- Splash covers the MAIN area only. Window controls remain usable. ---
    def _startup_overlay(self):
        main = self.sidebar.master
        self.root.update_idletasks()
        overlay=tk.Frame(main,bg=SLATE_BG)
        overlay.place(x=0,y=0,relwidth=1,relheight=1)
        overlay.lift()
        self._boot_overlay=overlay
        try:self.settings_button.configure(state='disabled',cursor='arrow')
        except tk.TclError:pass
        # Keep content centered but do not allow a narrow monitor to clip it.
        center=tk.Frame(overlay,bg=SLATE_BG,width=540,height=385)
        center.place(relx=.5,rely=.48,anchor='center')
        center.pack_propagate(False)
        try:
            from pathlib import Path
            image = tk.PhotoImage(file=str(Path(__file__).resolve().with_name('sovela.png'))).subsample(4,4)
            self._sovela_splash_icon = image
            tk.Label(center,image=image,bg=SLATE_BG,bd=0).pack(pady=(1,5))
        except (OSError, tk.TclError):
            tk.Label(center,text='S',bg=SLATE_BG,fg=SLATE_GREEN,
                     font=(SLATE_FONT,31,'bold')).pack(pady=(1,5))
        tk.Label(center,text='sovela',bg=SLATE_BG,fg=SLATE_TEXT,
                 font=(SLATE_FONT,28,'bold')).pack()
        tk.Label(center,text='Preparing your workspace',bg=SLATE_BG,fg=SLATE_MUTED,
                 font=(SLATE_FONT,11)).pack(pady=(3,13))
        self._boot_spinner=tk.Canvas(center,width=66,height=66,bg=SLATE_BG,highlightthickness=0)
        self._boot_spinner.pack()
        self._boot_percent=tk.StringVar(value='0%')
        tk.Label(center,textvariable=self._boot_percent,bg=SLATE_BG,fg=SLATE_GREEN,
                 font=(SLATE_FONT,17,'bold')).pack(pady=(10,3))
        self._boot_stage=tk.StringVar(value='Getting everything ready…')
        tk.Label(center,textvariable=self._boot_stage,bg=SLATE_BG,fg=SLATE_MUTED,
                 font=(SLATE_FONT,10)).pack()
        line=tk.Canvas(center,width=360,height=5,bg=SLATE_LINE,highlightthickness=0)
        line.pack(pady=(14,19))
        self._boot_progress=line
        line.create_rectangle(0,0,0,5,fill=SLATE_GREEN,outline='',tags='fill')
        tk.Label(center,text='A LITTLE PC-CARE TIP',bg=SLATE_BG,fg=SLATE_GREEN,
                 font=(SLATE_FONT,9,'bold')).pack()
        self._boot_tip=tk.StringVar(value=CARE_TIPS[0])
        tk.Label(center,textvariable=self._boot_tip,bg=SLATE_BG,fg=SLATE_INK_SOFT,
                 font=(SLATE_FONT,10),wraplength=440,justify='center').pack(pady=(8,0))
        self._animate_spinner(0)
        self._advance_tip()

    def _animate_spinner(self,frame):
        canvas=self._boot_spinner
        if canvas is None or not canvas.winfo_exists():return
        canvas.delete('all')
        # Rotating segmented ring. No simulated scan progress.
        import math
        for i in range(12):
            theta=2*math.pi*(i+frame%12)/12
            x=33+23*math.cos(theta)
            y=33+23*math.sin(theta)
            fill=SLATE_GREEN if i>=8 else ('#8EBAAC' if i>=5 else '#D6E4DD')
            canvas.create_oval(x-3.8,y-3.8,x+3.8,y+3.8,fill=fill,outline='')
        self.root.after(70,lambda:self._animate_spinner(frame+1))

    def _advance_tip(self):
        if self._boot_overlay is None or not self._boot_overlay.winfo_exists():return
        self._tip_index=(self._tip_index+1)%len(CARE_TIPS)
        self._boot_tip.set(CARE_TIPS[self._tip_index])
        self.root.after(5000,self._advance_tip)

    def _warm_next_page(self):
        """Precreate each page once so basic Tk layout/font issues surface at launch.
        Percent is completed readiness stages, NOT a virus scan or security score.
        """
        if not self.root.winfo_exists():return
        page_count=len(self._WARM_PAGES)
        if self._boot_step<page_count:
            page=self._WARM_PAGES[self._boot_step]
            self._boot_stage.set(f'Preparing {page.lower()}…')
            try:
                super().show_tab(page)
                self.root.update_idletasks()
            except Exception as exc:
                # Keep launch usable even if a noncritical page can't pre-render.
                self.record_activity(f'UI preflight for {page} encountered {type(exc).__name__}')
            self._boot_step+=1
            percent=round(93*self._boot_step/page_count)
            self._set_boot_percent(percent)
            self.root.after(65,self._warm_next_page)
            return
        self._boot_stage.set('Finishing your workspace…')
        try:
            super().show_tab(self.preferences.get('start_page','Overview'))
            self.root.update_idletasks()
        except Exception:
            super().show_tab('Overview')
        self._set_boot_percent(100)
        self.root.after(120,self._finish_boot)

    def _set_boot_percent(self,value):
        if self._boot_percent is None:return
        self._boot_percent.set(f'{value}%')
        self._boot_progress.coords('fill',0,0,int(360*value/100),5)

    def _finish_boot(self):
        if self._boot_overlay is not None:
            self._boot_overlay.destroy()
            self._boot_overlay=None
            self._boot_spinner=None
        self._booting=False
        try:self.settings_button.configure(state='normal',cursor='hand2')
        except tk.TclError:pass
        self._sync_nav_state()

    # --- Page selection: no work or animation when already selected. ---
    def make_nav(self):
        super().make_nav()
        # User click on the selected category is inert, but internal refreshes
        # (scan results, cleanup previews, startup inspection) must still work.
        for name,button in self.nav_buttons.items():
            button.configure(command=lambda page=name:self._navigate_to(page))

    def _navigate_to(self,tab):
        if tab!=self.current_tab:
            self.show_tab(tab)

    def _sync_nav_state(self):
        for name,button in self.nav_buttons.items():
            active=name==self.current_tab
            try:
                button.configure(state='disabled' if active else 'normal',
                    cursor='arrow' if active else 'hand2',
                    disabledforeground=SLATE_GREEN if active else SLATE_MUTED,
                    bg=SLATE_CARD if active else SLATE_SIDE,
                    fg=SLATE_GREEN if active else SLATE_MUTED)
            except tk.TclError:pass

    def show_tab(self,tab):
        if tab=='Settings':
            self.open_settings_sheet();return
        previous=getattr(self,'current_tab','')
        self._transition_generation+=1
        gen=self._transition_generation
        super().show_tab(tab)
        if not self._booting:
            self._sync_nav_state()
            if previous and previous!=tab and self.preferences.get('smooth_motion',True):
                self._page_transition(gen)

    def _animate_current_page(self,tab):
        # Replaced v1.5's slight 17px padding motion with a visible mask reveal.
        return

    def _chosen_transition(self):
        configured=self.preferences.get('motion_style','Variety')
        if configured!='Variety':return configured
        options=[item for item in MOTION_STYLES if item!='Variety' and item!=self._last_transition]
        result=random.choice(options)
        self._last_transition=result
        return result

    def _page_transition(self,gen):
        # Drawing over NEW widgets prevents the in-between layout from flashing.
        body=self.body
        if not body.winfo_exists():return
        self.root.update_idletasks()
        w=max(30,body.winfo_width());h=max(30,body.winfo_height())
        if self._transition_canvas is not None:
            try:self._transition_canvas.destroy()
            except tk.TclError:pass
        veil=tk.Canvas(body,bg=SLATE_BG,highlightthickness=0,bd=0)
        veil.place(x=0,y=0,relwidth=1,relheight=1)
        # Canvas.lift() means raise *canvas item*, not raise window.
        # place() already stacks this newly created cover above page children.
        self._transition_canvas=veil
        style=self._chosen_transition()
        count={'Snappy':13,'Balanced':21,'Relaxed':30}.get(self.preferences.get('motion_speed'),21)
        # Grouped masks are independently animated to create distinct reveals.
        if style=='Blinds':
            strips=8
            ids=[veil.create_rectangle(i*w/strips,0,(i+1)*w/strips+1,h,
                                       fill=SLATE_BG,outline='') for i in range(strips)]
        elif style=='Split':
            ids=[veil.create_rectangle(0,0,w,h/2+1,fill=SLATE_BG,outline=''),
                 veil.create_rectangle(0,h/2,w,h,fill=SLATE_BG,outline='')]
        else:
            ids=[veil.create_rectangle(0,0,w,h,fill=SLATE_BG,outline='')]
        # Accent changes the character of each screen reveal.
        accent=veil.create_rectangle(0,0,0,0,fill=SLATE_GREEN,outline='')
        def step(n):
            if gen!=self._transition_generation or not veil.winfo_exists():return
            t=min(1,n/count)
            eased=1-(1-t)**3
            if style=='Sweep':
                x=w*eased
                veil.coords(ids[0],x,0,w,h)
                veil.coords(accent,max(0,x-4),0,x,h)
            elif style=='Lift':
                y=h*eased
                veil.coords(ids[0],0,0,w,max(0,h-y))
                veil.coords(accent,0,max(0,h-y),w,max(0,h-y+3))
            elif style=='Split':
                d=h*.5*eased
                veil.coords(ids[0],0,0,w,max(0,h/2-d))
                veil.coords(ids[1],0,min(h,h/2+d),w,h)
                veil.coords(accent,0,max(0,h/2-d),w,max(0,h/2-d+2))
            else: # Blinds
                for i,ident in enumerate(ids):
                    local=max(0,min(1,(t-i*.047)/(1-i*.047)))
                    veil.coords(ident,i*w/8,h*local,(i+1)*w/8+1,h)
                veil.coords(accent,0,0,0,0)
            if n<count:
                self.root.after(16,lambda:step(n+1))
            else:
                veil.destroy()
                if self._transition_canvas is veil:self._transition_canvas=None
        self.root.after(10,lambda:step(0))

    # --- Settings: two compact screens, sticky footer, and actual dropdowns. ---
    def open_settings_sheet(self):
        if self._settings_sheet is not None:
            self.close_settings_sheet();return
        self._settings_page_name='Appearance'
        self._settings_generation+=1
        generation=self._settings_generation
        sheet=tk.Frame(self.content,bg=SLATE_LINE)
        self._settings_sheet=sheet
        sheet.place(relx=1.0,x=0,y=0,width=475,relheight=1)
        inner=tk.Frame(sheet,bg=WHITE,padx=17,pady=14)
        inner.pack(fill='both',expand=True,padx=(1,0))
        heading=tk.Frame(inner,bg=WHITE);heading.pack(fill='x',pady=(0,9))
        txt=tk.Frame(heading,bg=WHITE);txt.pack(side='left',fill='x',expand=True)
        self._label(txt,'Settings',19,True).pack(anchor='w')
        self._label(txt,'Customise your workspace',9,color=SLATE_MUTED).pack(anchor='w',pady=(3,0))
        self._button(heading,'×',self.close_settings_sheet,False,True).pack(side='right')
        tabs=tk.Frame(inner,bg=WHITE);tabs.pack(fill='x',pady=(4,13))
        self._settings_tab_buttons={}
        for title in ('Appearance','Scans & alerts'):
            btn=self.text_button(tabs,title,lambda x=title:self._settings_select_page(x),
                                 size=10,bg=LITE,fg=SLATE_MUTED)
            btn.pack(side='left',padx=(0,8),ipadx=4)
            self._settings_tab_buttons[title]=btn
        self._settings_area=tk.Frame(inner,bg=WHITE)
        self._settings_area.pack(fill='both',expand=True)
        footer=tk.Frame(inner,bg=WHITE)
        footer.pack(side='bottom',fill='x',pady=(8,0))
        tk.Frame(footer,bg=SLATE_LINE,height=1).pack(fill='x',pady=(0,9))
        tk.Label(footer,text='Saved automatically on this computer',bg=WHITE,
                 fg=SLATE_MUTED,font=(SLATE_FONT,9)).pack(anchor='w',pady=(0,9))
        bottom=tk.Frame(footer,bg=WHITE);bottom.pack(fill='x')
        self._button(bottom,'Reset',self._reset_settings,False,True).pack(side='left')
        self._button(bottom,'Done  ✓',self.close_settings_sheet,True,True).pack(side='right')
        self._settings_select_page('Appearance')
        def slide(i):
            if self._settings_sheet is not sheet or generation!=self._settings_generation:return
            t=1-(1-min(i,16)/16)**3
            sheet.place_configure(x=-round(475*t))
            if i<16:self.root.after(14,lambda:slide(i+1))
        if self.preferences.get('smooth_motion',True):
            self.root.after(10,lambda:slide(1))
        else:sheet.place_configure(x=-475)
        sheet.lift()

    def _settings_select_page(self,page):
        self._settings_page_name=page
        for name,button in self._settings_tab_buttons.items():
            button.configure(bg=SLATE_GREEN_SOFT if name==page else LITE,
                             fg=SLATE_GREEN if name==page else SLATE_MUTED,
                             state='disabled' if name==page else 'normal',
                             disabledforeground=SLATE_GREEN)
        for child in self._settings_area.winfo_children():child.destroy()
        area=self._settings_area
        if page=='Appearance':
            self._settings_dropdown(area,'Transition style','motion_style',MOTION_STYLES,
                                    'Choose a reveal effect or mix them automatically.')
            self._settings_dropdown(area,'Animation speed','motion_speed',MOTION_SPEEDS,
                                    'Set the pace of screen transitions.')
            self._settings_switch(area,'smooth_motion','Animated interface',
                                  'Disable animations when you want less motion.')
            self._settings_switch(area,'always_on_top','Keep Sovela on top',
                                  'Show Sovela above normal windows.')
            self._settings_switch(area,'hover_hints','Show hover explanations',
                                  'Reveal concise tips beside tools.')
            self._settings_dropdown(area,'Opening page','start_page',VALID_PAGES,
                                    'The first category displayed after loading.')
        else:
            self._settings_switch(area,'show_scan_timer','Elapsed scan timer',
                                  'Show minutes and seconds during Defender scans.')
            self._settings_switch(area,'scan_opens_page','Open scanner when started',
                                  'Jump to Malware Scan when a scan is requested.')
            self._settings_switch(area,'check_at_launch','Check protection at launch',
                                  'Read Windows security status without scanning files.')
            self._settings_switch(area,'scan_notifications','In-app scan alerts',
                                  'Show completion cards above normal windows.')
            self._settings_switch(area,'scan_error_notifications','Show scan issues',
                                  'Also alert when a result needs review.')
            self._settings_dropdown(area,'Alert display time','notification_seconds',(6,10,15),
                                    'How long scan result cards remain visible.',suffix=' sec')
        self.root.update_idletasks()

    def _settings_row(self,parent,title,helper,height=68):
        row=tk.Frame(parent,bg=WHITE,height=height)
        row.pack(fill='x',pady=(0,5))
        row.pack_propagate(False)
        info=tk.Frame(row,bg=WHITE)
        info.pack(side='left',fill='both',expand=True)
        self._label(info,title,10,True).pack(anchor='w',pady=(6,1))
        self._label(info,helper,8,color=SLATE_MUTED,wraplength=250).pack(anchor='w')
        return row

    def _settings_dropdown(self,parent,title,key,options,helper,suffix=''):
        row=self._settings_row(parent,title,helper)
        style=ttk.Style(self.root)
        style.configure('Sovela.TCombobox', fieldbackground=SLATE_GREEN_SOFT,
                        foreground=SLATE_TEXT, background=SLATE_GREEN_SOFT,
                        borderwidth=0, padding=(7,5), arrowsize=14)
        style.map('Sovela.TCombobox', fieldbackground=[('readonly',SLATE_GREEN_SOFT)],
                  foreground=[('readonly',SLATE_TEXT)])
        mapping={str(value)+suffix:value for value in options}
        current=str(self.preferences.get(key,options[0]))+suffix
        variable=tk.StringVar(value=current)
        box=ttk.Combobox(row,textvariable=variable,values=tuple(mapping),
                         width=17,state='readonly',font=(SLATE_FONT,10),justify='left',
                         style='Sovela.TCombobox')
        box.pack(side='right',padx=(9,0),pady=(9,0))
        def changed(_event):
            choice=mapping.get(variable.get())
            if choice is not None:self._set_pref(key,choice)
        box.bind('<<ComboboxSelected>>',changed)
        self._settings_drop_vars[key]=variable

    def _settings_switch(self,parent,key,title,helper):
        row=self._settings_row(parent,title,helper)
        button=tk.Button(row,bd=0,relief='flat',cursor='hand2',
                         font=(SLATE_FONT,10,'bold'),padx=15,pady=7)
        button.pack(side='right',pady=(7,0))
        def repaint():
            on=bool(self.preferences[key])
            button.configure(text='On  ●' if on else 'Off  ○',
                             bg=SLATE_GREEN_SOFT if on else LITE,
                             fg=SLATE_GREEN if on else SLATE_MUTED,
                             activebackground=ACTIVE)
        def change():
            self._set_pref(key,not self.preferences[key]);repaint()
        button.configure(command=change)
        repaint()

    def _reset_settings(self):
        if not messagebox.askyesno('Reset Sovela settings',
               'Restore the default appearance and notification settings?',parent=self.root):return
        self.preferences=DEFAULTS.copy()
        self._save_prefs()
        if self.pinned!=self.preferences['always_on_top']:
            self.toggle_pin()
        self._settings_select_page(self._settings_page_name)
        self._scan_needs_refresh=self.current_tab=='Malware Scan'

    def close_settings_sheet(self,animate=True):
        # v1.5 implementation assumes 444 px. This version's sheet is 475.
        sheet=self._settings_sheet
        if sheet is None:return
        self._settings_generation+=1
        generation=self._settings_generation
        self._settings_sheet=None
        if not animate or not self.preferences.get('smooth_motion',True):
            sheet.destroy()
            if self._scan_needs_refresh:
                self._scan_needs_refresh=False
                # Invalidate current-tab no-op, since timer label changed.
                super().show_tab(self.current_tab)
                self._sync_nav_state()
            return
        def slide(i):
            if generation!=self._settings_generation or not sheet.winfo_exists():return
            t=1-(1-min(i,12)/12)**3
            sheet.place_configure(x=-round(475*(1-t)))
            if i<12:self.root.after(14,lambda:slide(i+1))
            else:
                sheet.destroy()
                if self._scan_needs_refresh:
                    self._scan_needs_refresh=False
                    super(SovelaPolishedApp,self).show_tab(self.current_tab)
                    self._sync_nav_state()
        slide(0)
