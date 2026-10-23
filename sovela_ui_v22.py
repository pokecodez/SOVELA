"""Sovela v2.3: native full-page Account experience, no separate account window.

This file retains the legacy filename as an import-compatible module; Account
is implemented inside the existing body, not as a Toplevel or modal sheet.
"""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

from sovela_ui_v20 import SovelaCarePlusApp
from sovela_auth import VERSION, update_info
from sovela_ui_v15 import (SLATE_BG, SLATE_CARD, SLATE_TEXT, SLATE_MUTED,
                           SLATE_GREEN, SLATE_GREEN_SOFT, SLATE_LINE,
                           SLATE_FONT, SLATE_INK_SOFT)

WHITE = '#FFFFFF'

class SovelaAccountsApp(SovelaCarePlusApp):
    """The unchanged PC-care screens plus an ordinary, non-modal Account page."""

    def __init__(self, root, session=None, account_client=None, updates_repo=''):
        self.sovela_session = session
        self.account_client = account_client
        self.updates_repo = updates_repo
        self._latest_update = None
        self._account_return_tab = 'Overview'
        self._account_open = False
        self._account_status = None
        self._account_link = None
        super().__init__(root)
        root.title('Sovela | PC Care v' + VERSION)
        self._replace_footer_version(self.frame)
        if self.updates_repo:
            self.root.after(2500, self._check_updates_at_launch)

    def _replace_footer_version(self, widget):
        super()._replace_footer_version(widget)
        def visit(w):
            try:
                if isinstance(w, tk.Label):
                    value=str(w.cget('text'))
                    if 'v2.1' in value or 'v2.2' in value:
                        w.configure(text=value.replace('v2.1','v2.3').replace('v2.2','v2.3'))
                for child in w.winfo_children():visit(child)
            except tk.TclError:
                pass
        visit(widget)

    def draw_titlebar(self):
        super().draw_titlebar()
        header = self.frame.winfo_children()[0]
        self.account_button = self.text_button(header, 'Account', self.account_sheet,
                             size=9, bg=SLATE_CARD, fg=SLATE_GREEN)
        self.account_button.pack(side='right', padx=(2,9))

    def _check_updates_at_launch(self):
        def work():
            info=update_info(self.updates_repo)
            try:self.root.after(0,lambda:self._update_badge(info))
            except tk.TclError:pass
        threading.Thread(target=work,daemon=True).start()

    def _update_badge(self, info):
        self._latest_update=info
        try:
            self.account_button.configure(text='Account  •' if info and info.get('available') else 'Account')
        except tk.TclError:pass
        if self._account_open:
            self._update_account_info()

    def show_tab(self, tab):
        if tab=='Account':
            self.account_sheet()
            return
        if self._account_open:
            self._account_open=False
            try:self.account_button.configure(state='normal',cursor='hand2')
            except tk.TclError:pass
        super().show_tab(tab)

    def account_sheet(self):
        """Keep existing top-right Account button; draw Account inside app."""
        if self._account_open or getattr(self,'_booting',False):
            return
        if self.current_tab in self.nav_buttons:
            self._account_return_tab=self.current_tab
        else:
            self._account_return_tab='Overview'
        self._account_open=True
        self._cancel_bounce()
        if getattr(self,'_settings_sheet',None) is not None:
            self.close_settings_sheet(animate=False)
        self.current_tab='Account'
        self.reset_body()
        self._root_view(27)
        self._sync_nav_state()  # no sidebar selection while Account is showing
        self.account_button.configure(state='disabled',cursor='arrow',disabledforeground=SLATE_GREEN)
        self._build_account_page()

    def _account_label(self,parent,text,size=10,bold=False,color=SLATE_TEXT,wrap=None,**pack):
        label=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,
                       font=(SLATE_FONT,size,'bold' if bold else 'normal'),
                       justify='left',anchor='w',wraplength=wrap or 675)
        pack.setdefault('anchor','w')
        label.pack(**pack)
        return label

    def _account_card(self,parent,bg=WHITE,pad=19):
        edge=tk.Frame(parent,bg=SLATE_LINE,padx=1,pady=1)
        edge.pack(fill='x',pady=(0,12))
        card=tk.Frame(edge,bg=bg,padx=pad,pady=pad)
        card.pack(fill='both',expand=True)
        return card

    def _account_button(self,parent,title,command,primary=False):
        return tk.Button(parent,text=title,command=command,
            bg=SLATE_GREEN if primary else SLATE_GREEN_SOFT,
            fg=WHITE if primary else SLATE_GREEN,
            activebackground='#27564B' if primary else '#D6E9E0',
            activeforeground=WHITE if primary else SLATE_GREEN,
            font=(SLATE_FONT,10,'bold'),bd=0,relief='flat',
            highlightthickness=0,padx=18,pady=10,cursor='hand2')

    def _build_account_page(self):
        page=self.view
        header=tk.Frame(page,bg=SLATE_BG)
        header.pack(fill='x',pady=(0,16))
        left=tk.Frame(header,bg=SLATE_BG)
        left.pack(side='left',fill='x',expand=True)
        self._account_label(left,'Your account',23,True,**{'anchor':'w'})
        self._account_label(left,'Membership, account details and application updates',
                            10,False,SLATE_MUTED,pady=(3,0))
        self._account_button(header,'Done  ✓',
             lambda:self.show_tab(self._account_return_tab),primary=True).pack(side='right',padx=(8,0))

        identity=self._account_card(page,pad=17)
        line=tk.Frame(identity,bg=WHITE)
        line.pack(fill='x')
        avatar=tk.Label(line,text='S',bg=SLATE_GREEN_SOFT,fg=SLATE_GREEN,
                        font=(SLATE_FONT,20,'bold'),width=3,height=2)
        avatar.pack(side='left',padx=(0,16))
        idcol=tk.Frame(line,bg=WHITE)
        idcol.pack(side='left',fill='x',expand=True)
        self._account_label(idcol,'SIGNED IN AS',8,True,SLATE_MUTED)
        email=self.sovela_session.email if self.sovela_session else 'Creator preview'
        self._account_label(idcol,email,13,True,SLATE_TEXT,pady=(5,0))
        tk.Label(line,text='Verified account' if self.sovela_session else 'Preview',
                 bg=SLATE_GREEN_SOFT,fg=SLATE_GREEN,
                 font=(SLATE_FONT,9,'bold'),padx=11,pady=8).pack(side='right')

        plan=self._account_card(page,bg='#E7F2ED',pad=20)
        self._account_label(plan,'YOUR MEMBERSHIP',9,True,SLATE_GREEN)
        entitlement=(self.sovela_session.entitlement or {}) if self.sovela_session else {}
        tier=entitlement.get('tier','unavailable')
        if tier=='trial':
            try:days=max(0,int(entitlement.get('days_left',0)))
            except (TypeError,ValueError):days=0
            heading='Premium trial'
            description=f'{days} day'+('' if days==1 else 's')+' remaining'
        elif tier=='premium':
            heading='Premium membership'
            description='Your membership is active'
        elif tier=='free':
            heading='Free membership'
            description='Core PC-care features remain available'
        else:
            heading='Membership not available'
            description='Unable to verify your plan right now'
        row=tk.Frame(plan,bg='#E7F2ED');row.pack(fill='x',pady=(7,2))
        tk.Label(row,text=heading,bg='#E7F2ED',fg=SLATE_TEXT,
                 font=(SLATE_FONT,19,'bold')).pack(side='left')
        tk.Label(row,text=description,bg='#E7F2ED',fg=SLATE_GREEN,
                 font=(SLATE_FONT,10,'bold')).pack(side='right',pady=(5,0))
        expiry=str(entitlement.get('trial_ends_at') or '')[:10] if tier=='trial' else ''
        note=('Trial ends '+expiry+' · No automatic charges' if expiry else
              'You stay in control. No payment method is required to use the free app.')
        self._account_label(plan,note,9,False,SLATE_INK_SOFT,pady=(8,0))

        updates=self._account_card(page,pad=16)
        top=tk.Frame(updates,bg=WHITE);top.pack(fill='x')
        text=tk.Frame(top,bg=WHITE);text.pack(side='left',fill='x',expand=True)
        self._account_label(text,'App updates',13,True)
        self._account_label(text,'Find new versions without installing anything silently.',
                            9,False,SLATE_MUTED,pady=(5,0))
        self._account_button(top,'Check updates ↗',self._check_updates_manual).pack(side='right',padx=(14,0))
        self._account_status=tk.StringVar(value='')
        tk.Label(updates,textvariable=self._account_status,fg=SLATE_MUTED,bg=WHITE,
                 font=(SLATE_FONT,9),anchor='w',justify='left',
                 wraplength=610).pack(fill='x',pady=(12,0))
        self._account_link=tk.Frame(updates,bg=WHITE)
        self._account_link.pack(anchor='w',pady=(3,0))
        self._update_account_info()

        bottom=tk.Frame(page,bg=SLATE_BG);bottom.pack(fill='x',pady=(2,0))
        self._account_label(bottom,'Sovela v'+VERSION+'  ·  Your security tools remain available without leaving this page.',
                            9,False,SLATE_MUTED,pady=(0,10))
        if self.sovela_session and self.account_client:
            self._account_button(bottom,'Sign out',self._signout_account).pack(side='left')
        elif not self.sovela_session:
            self._account_label(bottom,'Development preview: customer accounts are not connected.',
                                9,False,SLATE_MUTED)

    def _update_account_info(self):
        if not self._account_open or self._account_status is None:return
        if self._latest_update is None:
            status='Version '+VERSION+' · Release checking is not configured yet.' if not self.updates_repo else 'Version '+VERSION+' · Check for newer releases.'
        elif self._latest_update.get('available'):
            status='New version available: '+str(self._latest_update.get('tag',''))
        else:
            status='Version '+VERSION+' · No newer published release found.'
        self._account_status.set(status)
        if self._account_link and self._account_link.winfo_exists():
            for child in self._account_link.winfo_children():child.destroy()
            if self._latest_update and self._latest_update.get('available'):
                link=self._latest_update.get('url','')
                self._account_button(self._account_link,'View release ↗',
                    lambda:webbrowser.open(link)).pack(anchor='w')

    def _check_updates_manual(self):
        if not self.updates_repo:
            if self._account_status:self._account_status.set('The creator has not configured a public GitHub Releases repository yet.')
            return
        if self._account_status:self._account_status.set('Checking for updates…')
        def work():
            result=update_info(self.updates_repo)
            def done():
                self._latest_update=result
                if result is None and self._account_status:
                    self._account_status.set('Could not check releases. Try again later.')
                else:self._update_badge(result)
            try:self.root.after(0,done)
            except tk.TclError:pass
        threading.Thread(target=work,daemon=True).start()

    def _signout_account(self):
        if not messagebox.askyesno('Sign out','Sign out of Sovela on this computer? You will need to sign in again.',parent=self.root):
            return
        if self._account_status:self._account_status.set('Signing out…')
        sess=self.sovela_session
        def work():
            self.account_client.signout(sess)
            try:self.root.after(0,self.root.destroy)
            except tk.TclError:pass
        threading.Thread(target=work,daemon=True).start()
