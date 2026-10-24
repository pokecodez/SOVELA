"""Sovela 3.1: Aurora UI, safe server-verified owner controls and Credits.

This module adds no hidden remote execution, file deletion or automatic installers.
It uses the existing trusted Windows malware tooling unchanged.
"""
from __future__ import annotations
import re
import math
from datetime import datetime, timezone
import tkinter as tk
import webbrowser
from tkinter import messagebox
from sovela_window import begin_windows_titlebar_drag
from sovela_preferences import save as save_preferences
from sovela_v30 import SovelaV3
from sovela_ui_v15 import (SLATE_BG, SLATE_SIDE, SLATE_CARD, SLATE_GREEN, SLATE_GREEN_SOFT,
    SLATE_MUTED, SLATE_FONT, SLATE_TEXT, WHITE)
from sovela_auth import VERSION

DEEP='#163D3B'; DEEP2='#235C58'; MINT='#8BDBC0'; SKY='#C1EAED'; INK='#1B3940'; WARM='#FFF1DD'
REPO='pokecodez/SOVELA'


def version_tuple(version):
    hit=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)',str(version or ''))
    return tuple(map(int,hit.groups())) if hit else (0,0,0)


def safe_text(value,length=800):
    # Avoid unbounded labels and control characters from remotely editable text.
    return ''.join(ch for ch in str(value or '') if ch == '\n' or ord(ch)>=32)[:length]


class SovelaV31(SovelaV3):
    def __init__(self,root,session=None,account_client=None,updates_repo=''):
        self.global_config={}
        self._admin_section='Members'
        self._global_config_pending=False
        self._remote_minimum=(0,0,0)
        self._update_gate=False
        self._admin_config={}
        self._native_titlebar_drag=False
        super().__init__(root,session,account_client,updates_repo or REPO)
        self.root.title('Sovela | PC Care '+VERSION)
        if self.account_client:
            self.run_job('public_config',self.account_client.public_config)
        self.root.after(150,self.ensure_visible)

    def make_nav(self):
        super().make_nav()
        self._restyle_navigation()

    def _replace_footer_version(self,widget):
        super()._replace_footer_version(widget)
        def change(w):
            if isinstance(w,tk.Label):
                value=str(w.cget('text'))
                updated=re.sub(r'v3\.(?:0|1)(?:\.\d+)?', 'v'+VERSION, value)
                if value!=updated:w.configure(text=updated)
            for ch in w.winfo_children():change(ch)
        try:change(widget)
        except tk.TclError:pass

    def _restyle_navigation(self):
        # Deep evergreen sidebar: much stronger visual identity than generic grey panels.
        try:
            self.sidebar.configure(bg=DEEP)
            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child,(tk.Frame,tk.Label)):
                        try:
                            child.configure(bg=DEEP)
                            if isinstance(child,tk.Label):child.configure(fg='#A5D0C8')
                        except tk.TclError:pass
                    walk(child)
            walk(self.sidebar)
            self._sync_nav_state()
        except (AttributeError,tk.TclError):pass

    def _nav_hover(self, widget, name, entering):
        """v3.1.1: one hover only; never use the old light-theme animation."""
        try:
            if not widget.winfo_exists():
                return
            # Cancel previously scheduled legacy hover animation frames.
            widget._sovela_motion = getattr(widget, '_sovela_motion', 0) + 1
            active = name == getattr(self, 'current_tab', '')
            widget.configure(bg='#2C625A' if active else ('#24574F' if entering else DEEP),
                             fg='#F2FFFB' if active else '#B5D7CD',
                             activebackground='#24574F', activeforeground='#F2FFFB')
        except tk.TclError:
            pass

    def _sync_nav_state(self):
        for name,button in getattr(self,'nav_buttons',{}).items():
            active=name==getattr(self,'current_tab','')
            try:
                button._sovela_motion=getattr(button,'_sovela_motion',0)+1
                button.configure(bg='#2C625A' if active else DEEP,
                    fg='#F2FFFB' if active else '#B5D7CD',
                    disabledforeground='#F2FFFB',
                    state='disabled' if active else 'normal',
                    cursor='arrow' if active else 'hand2',
                    activebackground='#24574F',activeforeground='#F2FFFB')
            except tk.TclError:pass

    def start_drag(self, event):
        """Let the Windows compositor move our custom-chrome window natively.

        Calling Tk geometry repeatedly during motion makes some GPUs paint a
        temporary black client area. Fall back to Tk positioning on other OSs.
        """
        self._native_titlebar_drag = begin_windows_titlebar_drag(self.root)
        if self._native_titlebar_drag:
            self.root.after(70, self.ensure_visible)
        else:
            super().start_drag(event)

    def drag(self, event):
        if not self._native_titlebar_drag:
            super().drag(event)

    def draw_titlebar(self):
        super().draw_titlebar()
        # No extra native bar is drawn here. Windows caption masking is handled by
        # sovela_window.py, which retains taskbar/Alt-Tab functionality.
        try:
            bar=self.pin_button.master
            bar.configure(bg='#F6FAF8')
            for child in bar.winfo_children():
                if isinstance(child,(tk.Label,tk.Button)):
                    try:child.configure(bg='#F6FAF8')
                    except tk.TclError:pass
        except (tk.TclError,AttributeError):pass

    def show_tab(self,tab):
        if getattr(self,'_update_gate',False) and tab not in ('Account','Updates'):
            return self._required_update_page()
        result=super().show_tab(tab)
        self._sync_nav_state()
        return result

    def _required_update_page(self):
        self.current_tab='Update required'
        self.reset_body()
        self._root_view(30)
        box=tk.Frame(self.view,bg=WHITE,padx=28,pady=28);box.pack(fill='both',expand=True)
        self._label(box,'◈  A newer Sovela is required',23,True,color=DEEP).pack(anchor='w',pady=(8,16))
        self._label(box,'This version is below the supported minimum set by Sovela. '
            'For security and compatibility, please install the latest verified release.',11,
            color=SLATE_MUTED,wraplength=610).pack(anchor='w',pady=(0,24))
        self._button(box,'View verified GitHub release ↗',
            lambda:webbrowser.open('https://github.com/'+REPO+'/releases/latest'),True,False).pack(anchor='w')
        self._label(box,'Sovela never silently downloads or runs installers. Confirm the publisher before installing.',9,
            color=SLATE_MUTED,wraplength=610).pack(anchor='w',pady=(22,0))
        self._sync_nav_state()

    def poll_events(self):
        retained=[]
        while True:
            try:kind,status,value=self.events.get_nowait()
            except __import__('queue').Empty:break
            if kind=='public_config':
                if status=='ok' and isinstance(value,dict):
                    self.global_config=value
                    self._remote_minimum=version_tuple(value.get('min_supported_version'))
                    if self._remote_minimum>version_tuple(VERSION):
                        self._update_gate=True
                        self._required_update_page()
                    elif self.current_tab=='Overview':
                        SovelaV3.show_tab(self,'Overview')
                        self._sync_nav_state()
            elif kind=='admin_config':
                if status=='ok' and isinstance(value,dict):
                    self._admin_config=value
                    if getattr(self,'_account_open',False) and self._account_section=='Admin':
                        self._build_account_page()
            elif kind=='admin_set_config':
                if status=='ok' and isinstance(value,dict):
                    self._admin_config=value;self.global_config=value
                    self._build_account_page() if self._account_open else None
                    messagebox.showinfo('Changes saved','The global setting was saved on the account server. It will appear on clients when they next refresh.')
                else:
                    messagebox.showerror('Unable to save',str(value)[:300])
            elif kind=='checkout':
                if status=='ok' and isinstance(value,str) and value.startswith('https://checkout.stripe.com/'):
                    webbrowser.open(value)
                else:messagebox.showerror('Checkout unavailable','Premium billing is not available yet. No payment was taken.')
            elif kind=='admin_find':
                if status=='ok' and isinstance(value,dict) and value.get('id'):
                    self._admin_accounts=[value]
                    self._populate_admin_list()
                else:
                    messagebox.showinfo('No account found','No matching account was found, or the account service could not complete the search.')
            elif kind in ('admin_grant','admin_revoke','admin_end_trial'):
                messagebox.showinfo('Premium access',
                    ('The server recorded the change. Refreshing membership now.' if status=='ok'
                     else 'Could not update Premium: '+safe_text(value,180)), parent=self.root)
                if status=='ok':
                    self._load_admin_accounts()
                    self._refresh_membership()
            elif kind=='refresh_entitlement':
                if status=='ok' and isinstance(value,dict) and 'tier' in value:
                    if self.sovela_session:
                        self.sovela_session.entitlement=value
                    if getattr(self,'_account_open',False) and self._account_section=='Profile':
                        self._build_account_page()
                    try:self.premium_nav.configure(text='✦    PREMIUM' if self._entitled() else '🔒    PREMIUM')
                    except (tk.TclError,AttributeError):pass
                else:
                    messagebox.showwarning('Membership refresh',
                        'Could not refresh your membership. Check your connection, then try again.', parent=self.root)
            else:retained.append((kind,status,value))
        for item in retained:self.events.put(item)
        super().poll_events()

    def overview_page(self):
        # Branded aurora hero, warm accent cards and genuinely useful actions.
        intro=tk.Frame(self.view,bg=SLATE_BG)
        intro.pack(fill='x',pady=(0,10))
        self._label(intro,'Your PC, made simple',21,True,color=INK).pack(anchor='w')
        self._label(intro,'Security and performance without the clutter.',9,color=SLATE_MUTED).pack(anchor='w',pady=(4,0))
        hero=tk.Canvas(self.view,height=169,bg=DEEP,highlightthickness=0,bd=0)
        hero.pack(fill='x',pady=(0,12))
        # Raster-like custom ink palette, not a generic flat card.
        for y in range(170):
            amount=y/169
            r=round(22+12*amount);g=round(57+42*amount);b=round(58+32*amount)
            hero.create_line(0,y,900,y,fill=f'#{r:02x}{g:02x}{b:02x}')
        for x in range(500,910,55):
            hero.create_oval(x-96,14,x+85,194,outline='#467F72',width=1)
        for x,y,size in [(642,43,6),(724,107,4),(816,54,6),(565,131,4)]:
            hero.create_oval(x,y,x+size,y+size,fill=MINT,outline='')
        title=safe_text(self.global_config.get('headline','Quiet protection. Clear answers.'),72)
        subtitle=safe_text(self.global_config.get('subline','A little less noise. A lot more confidence.'),150)
        hero.create_text(27,29,anchor='nw',text='◈  SOVELA  /  COMPUTER CARE',
            fill=MINT,font=(SLATE_FONT,10,'bold'))
        hero.create_text(27,63,anchor='nw',text=title,fill='white',font=(SLATE_FONT,18,'bold'),width=510)
        hero.create_text(28,119,anchor='nw',text=subtitle,fill='#D3EBE4',font=(SLATE_FONT,10),width=490)
        announcement=safe_text(self.global_config.get('announcement',''),350)
        if announcement:
            banner=tk.Frame(self.view,bg=WARM,padx=13,pady=9);banner.pack(fill='x',pady=(0,10))
            self._label(banner,'✦  SOVELA UPDATE',9,True,color='#84602D').pack(anchor='w')
            self._label(banner,announcement,9,color='#654F32',wraplength=660).pack(anchor='w',pady=(3,0))
        top=tk.Frame(self.view,bg=SLATE_BG);top.pack(fill='x',pady=(0,10))
        self._label(top,'YOUR ESSENTIALS',10,True,color=DEEP).pack(side='left')
        self._button(top,'Check protection →',self.check_protection_and_show,False,True).pack(side='right')
        action_frame=tk.Frame(self.view,bg=SLATE_BG);action_frame.pack(fill='both',expand=True)
        actions=[
            ('◈','Malware scan','Quick or full scan','Malware Scan','#DBEFE7'),
            ('✧','Cleaner','Review potential savings','Cleaner','#FCEAD9'),
            ('▦','Startup','Inspect launch programs','Startup','#E6EDFA'),
            ('◉','PC Health','Find worthwhile improvements','PC Health','#E2F0F1'),
            ('◇','File Inspector','Examine unknown downloads','Downloads','#F3EAF2'),
            ('☼','Assistant','Troubleshoot problems','Assistant','#EDF2DB')]
        for i,(symbol,title,subtitle,destination,tint) in enumerate(actions):
            col=i%3;row=i//3
            action_frame.grid_columnconfigure(col,weight=1,uniform='action')
            outer=tk.Frame(action_frame,bg='#D6E3DF',padx=1,pady=1)
            outer.grid(row=row,column=col,sticky='nsew',padx=(0,8 if col!=2 else 0),pady=(0,8))
            inner=tk.Frame(outer,bg=WHITE,padx=14,pady=10);inner.pack(fill='both',expand=True)
            icon=tk.Label(inner,text=symbol,bg=tint,fg=DEEP,font=(SLATE_FONT,20),width=3,height=1)
            icon.pack(anchor='w')
            self._label(inner,title,11,True,color=INK).pack(anchor='w',pady=(7,1))
            self._label(inner,subtitle,8,color=SLATE_MUTED).pack(anchor='w')
            for w in (outer,inner,icon,*inner.winfo_children()):
                try:
                    w.configure(cursor='hand2')
                    w.bind('<Button-1>',lambda _e,d=destination:self.show_tab(d))
                except tk.TclError:pass

    def _settings_select_page(self,page):
        if page=='Account':
            return self._open_account_from_settings()
        if page!='Credits':
            result=super()._settings_select_page(page)
            if page=='Appearance':
                row=self._settings_row(self._settings_area,'Window rendering',
                       'If the window flashes black when dragged, use native Windows rendering. Restart Sovela to apply.')
                enabled=bool(self.preferences.get('safe_window_frame',False))
                self._button(row,'Windows fallback: '+('On' if enabled else 'Off'),
                    self._toggle_window_rendering,False,True).pack(side='right')
            return result
        self._settings_page_name='Credits'
        for name,button in self._settings_tab_buttons.items():
            button.configure(bg='#D8ECE5' if name=='Credits' else '#F4F6F5',
                             fg=DEEP if name=='Credits' else SLATE_MUTED)
        for widget in self._settings_area.winfo_children():widget.destroy()
        area=self._settings_area
        for title,detail in [
            ('SOVELA · PC CARE','Design and development: Sovela independent project.'),
            ('CREATOR','Created by the Sovela project owner.'),
            ('SOFTWARE','Python and Tkinter power the desktop interface.'),
            ('SECURITY','Sovela works with Windows Security and Microsoft Defender when available. It is not an independent antivirus engine.'),
            ('ACCOUNT SERVICES','Supabase provides optional sign-in and subscriptions data. GitHub hosts public release files.'),
            ('PRIVACY','Sovela does not sell user data; review the full Privacy document before public release.')]:
            row=tk.Frame(area,bg=WHITE);row.pack(fill='x',pady=(0,9))
            self._label(row,title,9,True,color=DEEP).pack(anchor='w')
            self._label(row,detail,9,color=SLATE_MUTED,wraplength=650).pack(anchor='w',pady=(3,0))

    def open_settings_sheet(self):
        if getattr(self,'_settings_sheet',None) is not None:
            self.close_settings_sheet()
            return
        super().open_settings_sheet()
        tabs=getattr(self,'_settings_tab_buttons',{})
        if 'Credits' not in tabs and tabs:
            holder=next(iter(tabs.values())).master
            button=self.text_button(holder,'Credits',lambda:self._settings_select_page('Credits'),
                size=10,bg='#F4F6F5',fg=SLATE_MUTED)
            button.pack(side='left',padx=(0,5))
            tabs['Credits']=button
        # Account is a header shortcut, not a fifth tab that gets clipped at
        # standard 990px window widths.
        try:
            sheet=self._settings_sheet
            inner=sheet.winfo_children()[0]
            heading=inner.winfo_children()[0]
            btn=self.text_button(heading,'Account ↗',self._open_account_from_settings,
                size=9,bg='#E3F2EB',fg=DEEP)
            btn.pack(side='right',padx=(0,7))
        except (IndexError,AttributeError,tk.TclError):
            pass

    def _toggle_window_rendering(self):
        self.preferences['safe_window_frame']=not bool(self.preferences.get('safe_window_frame',False))
        save_preferences(self.preferences)
        messagebox.showinfo('Restart Sovela',
            'Window rendering preference saved. Restart Sovela to apply it. '
            'The Windows fallback shows a native title bar for compatibility.',
            parent=self.root)
        self._settings_select_page('Appearance')

    def _open_account_from_settings(self):
        if getattr(self,'_settings_sheet',None) is not None:
            self.close_settings_sheet(animate=False)
        self.account_sheet()

    def _refresh_membership(self):
        if self.sovela_session and self.account_client:
            self.run_job('refresh_entitlement',
                         lambda:self.account_client.entitlement(self.sovela_session))

    def account_sheet(self):
        was_open=getattr(self,'_account_open',False)
        super().account_sheet()
        if not was_open and getattr(self,'_account_open',False):
            # Accounts can be changed from another device; never trust the
            # sign-in-time membership snapshot indefinitely.
            self._refresh_membership()

    def _build_account_page(self):
        super()._build_account_page()
        if self._account_section=='Profile':
            try:
                # The old v3.0 text said checkout was always disabled.
                # Do not contradict the server-controlled current status.
                def update_legacy_text(widget):
                    if isinstance(widget,tk.Label):
                        if 'Payment checkout is not enabled' in str(widget.cget('text')):
                            widget.configure(text='Payment availability is shown below.')
                    for child in widget.winfo_children():update_legacy_text(child)
                update_legacy_text(self.view)
                ent=(self.sovela_session.entitlement or {}) if self.sovela_session else {}
                if ent.get('tier')=='premium' and ent.get('premium_until'):
                    raw=str(ent['premium_until'])
                    try:
                        end=datetime.fromisoformat(raw.replace('Z','+00:00'))
                        days=max(0,math.ceil((end-datetime.now(timezone.utc)).total_seconds()/86400))
                        explanation=' · approximately '+str(days)+' day(s) left'
                    except (ValueError,TypeError):
                        explanation=''
                    self._label(self.view,'Premium access through '+raw[:10]+explanation,
                                9,color=SLATE_MUTED).pack(anchor='w',pady=(1,8))
                if ent.get('tier')=='trial' and ent.get('trial_ends_at'):
                    self._label(self.view,'Your original trial ends: '+str(ent['trial_ends_at'])[:10]+
                                ' (an existing trial is not shortened by new-user promotions)',
                                9,color=SLATE_MUTED).pack(anchor='w',pady=(1,8))
                # Make billing visible while keeping purchase disabled until
                # checkout + webhook have been end-to-end verified by the owner.
                payment=tk.Frame(self.view,bg=WHITE,padx=16,pady=12,
                                 highlightbackground='#C5DCD1',highlightthickness=1)
                payment.pack(fill='x',pady=(6,0))
                self._label(payment,'✦  PREMIUM PLANS',11,True,color=DEEP).pack(anchor='w')
                self._label(payment,'Sovela Premium · £3.99/month (sandbox example price)',9,
                            color=SLATE_MUTED).pack(anchor='w',pady=(5,5))
                enabled=bool(self.global_config.get('payment_ready'))
                if enabled and self.account_client and self.sovela_session:
                    self._button(payment,'Subscribe securely with Stripe ↗',
                        lambda:self.run_job('checkout',lambda:self.account_client.start_checkout(self.sovela_session)),
                        True,True).pack(anchor='w',pady=(5,0))
                else:
                    disabled=tk.Button(payment,text='Subscribe · Not available yet',
                        bg='#E4EAE7',fg='#6A7772',disabledforeground='#6A7772',
                        state='disabled',relief='flat',font=(SLATE_FONT,10,'bold'),padx=12,pady=8)
                    disabled.pack(anchor='w',pady=(5,4))
                    self._label(payment,'Purchases are disabled while Stripe billing is tested. '
                        'No card details are requested and nothing is charged.',9,
                        color=SLATE_MUTED,wraplength=600).pack(anchor='w',pady=(5,0))
                if self.sovela_session and self.account_client:
                    self._button(payment,'↻ Refresh my membership',self._refresh_membership,
                                False,True).pack(anchor='w',pady=(9,0))
            except tk.TclError:
                pass
        if self._account_section!='Admin':return
        # Replace the old simplistic admin list with an owner studio.
        try:
            edge=self.view.winfo_children()[2]
            card=edge.winfo_children()[0]
            for w in card.winfo_children():w.destroy()
            self._admin_content(card)
        except (IndexError,tk.TclError):pass

    def _admin_content(self,holder):
        self._label(holder,'OWNER STUDIO',11,True,color=DEEP).pack(anchor='w')
        self._label(holder,'Server-verified permissions • changes are recorded in Supabase.',9,color=SLATE_MUTED).pack(anchor='w',pady=(3,11))
        bar=tk.Frame(holder,bg=WHITE);bar.pack(fill='x',pady=(0,11))
        for part in ('Members','Broadcast','Promotions','Brand','Releases'):
            b=self._button(bar,part,lambda x=part:self._switch_admin(x),False,True)
            b.configure(bg='#D5EDE2' if part==self._admin_section else '#F0F5F2')
            b.pack(side='left',padx=(0,5))
        section=self._admin_section
        if section=='Members':
            row=tk.Frame(holder,bg=WHITE);row.pack(fill='x')
            self._button(row,'↻ Refresh accounts',self._load_admin_accounts,True,True).pack(side='left')
            searchrow=tk.Frame(holder,bg=WHITE);searchrow.pack(fill='x',pady=(11,0))
            self._admin_search=tk.Entry(searchrow,font=(SLATE_FONT,10),bg='#F2F8F5',fg=INK,bd=1,relief='solid')
            self._admin_search.pack(side='left',fill='x',expand=True,ipady=6)
            def find():
                email=self._admin_search.get().strip()
                self.run_job('admin_find',lambda:self.account_client.admin_find(self.sovela_session,email))
            self._button(searchrow,'Find exact email',find,False,True).pack(side='right',padx=(9,0))
            self._label(holder,'Select an account. Grants and revocations are recorded in the audit log.',9,color=SLATE_MUTED,wraplength=610).pack(anchor='w',pady=(8,8))
            self._admin_listbox=tk.Listbox(holder,height=6,font=(SLATE_FONT,10),bg='#F2F8F5',fg=INK,bd=0,highlightthickness=1,highlightbackground='#DAE7E1')
            self._admin_listbox.pack(fill='x')
            self._populate_admin_list()
            row=tk.Frame(holder,bg=WHITE);row.pack(fill='x',pady=(10,0))
            self._label(row,'Grant days',10,color=SLATE_MUTED).pack(side='left')
            self._admin_days=tk.Spinbox(row,from_=1,to=365,width=6,font=(SLATE_FONT,11),bd=1)
            self._admin_days.delete(0,'end');self._admin_days.insert(0,'30')
            self._admin_days.pack(side='left',padx=(9,14))
            self._button(row,'Give Premium',self._grant_verified,True,True).pack(side='left')
            self._button(row,'Revoke manual grant',self._revoke_verified,False,True).pack(side='left',padx=(8,0))
            self._button(holder,'End free trial (separate action)',self._end_trial_verified,
                         False,True).pack(anchor='w',pady=(10,0))
            self._label(holder,'Manual grants, free trials and paid subscriptions are separate. '
                        'Ending a trial is permanent and does not cancel Stripe billing.',9,
                        color=SLATE_MUTED,wraplength=610).pack(anchor='w',pady=(7,0))
        else:
            mapping={
                'Broadcast':('Global announcement','announcement',800,'This message appears on customer dashboards.'),
                'Promotions':('Free trial for FUTURE signups (days)','trial_days',2,'7 by default; 0–90 days. Current accounts keep their existing end dates.'),
                'Brand':('Home headline','headline',72,'The title customers see on their overview.'),
                'Releases':('Minimum supported version','min_supported_version',32,'Requires an update to keep using current clients; does NOT download anything automatically.')}
            title,key,limit,note=mapping[section]
            self._label(holder,title,15,True,color=INK).pack(anchor='w',pady=(7,7))
            self._label(holder,note,9,color=SLATE_MUTED,wraplength=580).pack(anchor='w',pady=(0,11))
            if key=='announcement':
                field=tk.Text(holder,height=5,wrap='word',font=(SLATE_FONT,11),bg='#F3F7F6',fg=INK,bd=1,relief='solid')
                field.pack(fill='x')
                field.insert('1.0',self._admin_config.get(key,self.global_config.get(key,'')))
                read=lambda:field.get('1.0','end-1c')
            else:
                field=tk.Entry(holder,font=(SLATE_FONT,12),bg='#F3F7F6',fg=INK,bd=1,relief='solid')
                field.insert(0,str(self._admin_config.get(key,self.global_config.get(key,'7' if key=='trial_days' else ''))))
                field.pack(fill='x',ipady=8)
                read=field.get
            def save():
                value=read().strip()
                if len(value)>limit:
                    messagebox.showwarning('Value too long','Keep this setting to '+str(limit)+' characters.');return
                if key=='min_supported_version' and not messagebox.askyesno('Require an update',
                    'This can block older versions of Sovela until users install an update. Continue?'):return
                self.run_job('admin_set_config',lambda:self.account_client.admin_set_config(self.sovela_session,key,value))
            self._button(holder,'Save global change',save,True,True).pack(anchor='w',pady=(13,0))
            if section=='Brand':
                self._label(holder,'Subheading',10,True,color=INK).pack(anchor='w',pady=(19,4))
                sub=tk.Entry(holder,font=(SLATE_FONT,10),bg='#F3F7F6',fg=INK,bd=1,relief='solid')
                sub.insert(0,self._admin_config.get('subline',self.global_config.get('subline','')))
                sub.pack(fill='x',ipady=5)
                self._button(holder,'Save subheading',lambda:self.run_job('admin_set_config',
                    lambda:self.account_client.admin_set_config(self.sovela_session,'subline',sub.get())),False,True).pack(anchor='w',pady=(7,0))
            if section=='Releases':
                self._label(holder,'Public releases: github.com/'+REPO,9,color=SLATE_MUTED).pack(anchor='w',pady=(17,3))
                self._label(holder,'Important: old offline clients cannot be remotely controlled. Publishing an update is always safer than running remote code.',9,color=SLATE_MUTED,wraplength=560).pack(anchor='w')
            if section=='Promotions':
                self._label(holder,'Paid subscriptions are NOT live yet. A verified checkout and payment webhook are required before selling Premium.',9,color='#8D5D36',wraplength=550).pack(anchor='w',pady=(20,0))

    def _populate_admin_list(self):
        box=getattr(self,'_admin_listbox',None)
        if box is None or not box.winfo_exists():return
        box.delete(0,'end')
        for record in self._admin_accounts[:100]:
            box.insert('end',safe_text(record.get('email','Unknown'),70)+'   •   '+safe_text(record.get('tier','unknown'),12))

    def _switch_admin(self,name):
        self._admin_section=name
        self._build_account_page()
        if name in ('Broadcast','Promotions','Brand','Releases') and self.account_client:
            self.run_job('admin_config',lambda:self.account_client.admin_config(self.sovela_session))

    def _selected_admin_user(self):
        box=getattr(self,'_admin_listbox',None)
        if box is None or not box.winfo_exists():return None
        selection=box.curselection()
        if not selection or selection[0]>=len(self._admin_accounts):
            messagebox.showinfo('Choose a customer','Select an account from the list first.')
            return None
        return self._admin_accounts[selection[0]]

    def _grant_verified(self):
        user=self._selected_admin_user()
        if not user:return
        try:days=int(self._admin_days.get())
        except (ValueError,TypeError):days=0
        if not 1<=days<=365:
            messagebox.showwarning('Check the duration','Choose between 1 and 365 days.');return
        if not messagebox.askyesno('Grant Premium',f'Give {days} days of Premium to {user.get("email","this account")}?'):
            return
        self.run_job('admin_grant',lambda:self.account_client.admin_grant(self.sovela_session,user['id'],days))

    def _revoke_verified(self):
        user=self._selected_admin_user()
        if not user:return
        if not messagebox.askyesno('Revoke Premium',
            'Remove the manually assigned Premium grant from '+str(user.get('email','this account'))+'? Paid subscriptions must be cancelled in Stripe separately. Existing free trials stay unchanged.'):
            return
        self.run_job('admin_revoke',lambda:self.account_client.admin_revoke(self.sovela_session,user['id']))

    def _end_trial_verified(self):
        user=self._selected_admin_user()
        if not user:return
        if not messagebox.askyesno('End free trial',
                'Permanently end the free Premium trial for '+str(user.get('email','this account'))+'? '
                'This is separate from manual grants and paid subscriptions. This cannot be undone automatically.',
                parent=self.root):
            return
        self.run_job('admin_end_trial',
            lambda:self.account_client.admin_end_trial(self.sovela_session,user['id']))
