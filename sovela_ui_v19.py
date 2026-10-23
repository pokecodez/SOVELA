"""Sovela v1.9: one subtle, reliable page bounce; clear protection results.

The effect intentionally does not rely on video masks or hundreds of widgets.
A same-page data refresh must never animate. Antivirus and cleanup functions are
unchanged and delegated to the established read-only / consent-gated backends.
"""
from __future__ import annotations

import time
import tkinter as tk
from datetime import datetime

from sovela_ai import SovelaApp
from sovela_ui_v16 import SovelaPolishedApp
from sovela_ui_v15 import SovelaCareApp, SLATE_BG, SLATE_MUTED, SLATE_GREEN, SLATE_FONT


class SovelaBounceApp(SovelaPolishedApp):
    BOUNCE_MS = {'Snappy': 130, 'Balanced': 175, 'Relaxed': 215}

    def __init__(self, root):
        self._bounce_widget = None
        self._bounce_pack = None
        self._bounce_job = None
        self._bounce_generation = 0
        self._protection_check_time = None
        super().__init__(root)
        root.title('Sovela | Slate v1.9')
        self._replace_footer_version(self.frame)

    def _replace_footer_version(self, widget):
        """Update version labels from previous releases without replacing UI."""
        super()._replace_footer_version(widget)
        def visit(w):
            try:
                if isinstance(w, tk.Label):
                    s=w.cget('text')
                    for version in ('v1.8','v1.7','v1.6','v1.5','v1.4','v1.3'):
                        s=s.replace(version,'v1.9')
                    w.configure(text=s)
                for child in w.winfo_children():
                    visit(child)
            except tk.TclError:
                return
        visit(widget)

    def _animate_current_page(self, tab):
        """Disable inherited padding slide. Navigation uses bounce only."""
        return

    def _page_transition(self, gen):
        """Disable inherited cinematic masks unconditionally."""
        return

    def _cancel_bounce(self):
        self._bounce_generation+=1
        if self._bounce_job is not None:
            try:self.root.after_cancel(self._bounce_job)
            except (ValueError, tk.TclError):pass
            self._bounce_job=None
        widget=self._bounce_widget
        pack=self._bounce_pack
        self._bounce_widget=None
        self._bounce_pack=None
        if widget is None:
            return
        try:
            if widget.winfo_exists() and widget.winfo_manager()=='place':
                widget.place_forget()
                widget.pack(**pack)
        except tk.TclError:
            pass

    def show_tab(self, tab):
        if tab=='Settings':
            self.open_settings_sheet()
            return
        old=getattr(self,'current_tab','')
        # Make sure a rapid click never leaves a previous page floating.
        self._cancel_bounce()
        # Skip v1.6's cinematic transition code while retaining its header,
        # navigation, spinner and settings infrastructure.
        SovelaCareApp.show_tab(self,tab)
        if not getattr(self,'_booting',True):
            self._sync_nav_state()
            if old and old!=tab and self.preferences.get('smooth_motion',True):
                self._begin_bounce()

    @staticmethod
    def bounce_offset(progress):
        """Slight lift, gentle overshoot and settle; values in screen pixels."""
        progress=max(0.,min(1.,float(progress)))
        if progress<0.34:
            t=progress/0.34
            return round(-9*(1-(1-t)**3))
        if progress<0.69:
            t=(progress-0.34)/0.35
            return round(-9+(11*(t*t*(3-2*t))))
        t=(progress-0.69)/0.31
        return round(2*(1-(t*t*(3-2*t))))

    def _begin_bounce(self):
        try:
            children=self.body.winfo_children()
            if len(children)!=1:
                return
            widget=children[0]
            if widget.winfo_manager()!='pack':
                return
            self.root.update_idletasks()
            info=widget.pack_info().copy()
            self._bounce_widget=widget
            self._bounce_pack=info
            widget.place(x=0,y=0,relwidth=1,relheight=1)
            gen=self._bounce_generation
            elapsed_ms=self.BOUNCE_MS.get(self.preferences.get('motion_speed','Balanced'),175)
            start=time.perf_counter()
            def frame():
                if gen!=self._bounce_generation or self._bounce_widget is not widget:
                    return
                try:
                    if not widget.winfo_exists():return
                    fraction=min(1.,(time.perf_counter()-start)*1000/elapsed_ms)
                    widget.place_configure(y=self.bounce_offset(fraction))
                    if fraction>=1:
                        self._cancel_bounce()
                        return
                    self._bounce_job=self.root.after(15,frame)
                except tk.TclError:
                    self._cancel_bounce()
            self._bounce_job=self.root.after(15,frame)
        except tk.TclError:
            self._cancel_bounce()

    def _settings_select_page(self, page):
        # Keep the real speed dropdown, but hide the retired video-editing
        # effects. There is now one simple, consistent bounce style.
        super()._settings_select_page(page)
        if page!='Appearance':
            return
        rows=self._settings_area.winfo_children()
        if rows:
            rows[0].destroy()  # old Transition style chooser
        self._settings_drop_vars.pop('motion_style',None)
        labels={
            'Animation speed': 'Bounce speed',
            'Animated interface': 'Page bounce',
            'Set the pace of screen transitions.': 'Choose how quickly panels lift and settle.',
            'Disable animations when you want less motion.': 'Turn off the small bounce when changing categories.',
        }
        def relabel(parent):
            for child in parent.winfo_children():
                if isinstance(child,tk.Label):
                    current=child.cget('text')
                    if current in labels:
                        child.configure(text=labels[current])
                relabel(child)
        relabel(self._settings_area)

    def overview_page(self):
        super().overview_page()
        # The dashboard used to re-render itself for Check Protection. Route
        # both dashboard check buttons to the dedicated results page instead.
        def visit(w):
            for child in w.winfo_children():
                if isinstance(child,tk.Button) and child.cget('text') in ('Check protection','Refresh ↻'):
                    child.configure(command=self.check_protection_and_show)
                visit(child)
        visit(self.view)

    def check_protection_and_show(self):
        self.show_tab('Protection')
        # A manual user action is never confused with the optional startup check.
        self._initial_check_skipped=True
        SovelaApp.check(self)

    def receive_security(self,data):
        super().receive_security(data)
        self._protection_check_time=datetime.now().strftime('%H:%M:%S')
        self.status='Windows security settings checked'

    def protection_page(self):
        super().protection_page()
        # Show honest feedback close to the results, not just 'information ready'.
        if self.checking:
            notice='Checking your Windows protection settings…'
        elif self._protection_check_time:
            notice='Last checked at '+self._protection_check_time+'  ·  From Windows settings, not a malware scan.'
        else:
            notice='Press Refresh to check the latest protection information.'
        status=tk.Label(self.view,text=notice,bg=SLATE_BG,
                        fg=SLATE_GREEN if self._protection_check_time else SLATE_MUTED,
                        font=(SLATE_FONT,10),anchor='w',justify='left')
        status.pack(fill='x',pady=(0,10),before=self.view.winfo_children()[1]
                    if len(self.view.winfo_children())>1 else None)

    def close(self):
        self._cancel_bounce()
        return super().close()
