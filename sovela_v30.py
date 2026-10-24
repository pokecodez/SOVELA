"""Sovela v3 early release: polished navigation, settings and account controls.

Premium automation here is consent-driven, local and read-only for cleanup.
Billing/admin authority must come from authenticated server functions.
"""
from __future__ import annotations
import os
import queue
import re
import time
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timezone
from tkinter import messagebox

from sovela_ui_v22 import SovelaAccountsApp
from sovela_ui_v15 import (SLATE_BG, SLATE_CARD, SLATE_SIDE, SLATE_TEXT, SLATE_MUTED,
    SLATE_GREEN, SLATE_GREEN_SOFT, SLATE_LINE, SLATE_FONT, WHITE, LITE)
from sovela_ui_v20 import pretty_estimate, AUTOMATIC
from sovela_care import scan_cleanup
from sovela_ai import open_windows_security
from sovela_auth import VERSION, valid_repo, update_info
from sovela_v3_core import (SUPPORT_EMAIL, PrivateGeminiKey, ask_gemini,
    load_local_settings, save_local_settings, reminder_due, premium_allowed)


class SovelaV3(SovelaAccountsApp):
    def __init__(self,root,session=None,account_client=None,updates_repo=''):
        self.local_options=load_local_settings()
        self.gemini_key=PrivateGeminiKey()
        self._maintenance_pending=False
        self._weekly_toast=None
        self._week_toast_job=None
        self._v3_login_status=''
        self._is_admin=False
        self._admin_accounts=[]
        self._account_section='Profile'
        super().__init__(root,session,account_client,
                         updates_repo or self.local_options.get('updates_repo',''))
        self.root.title('Sovela | PC Care v'+VERSION)
        # Check once after normal startup/preflight is complete.
        self.root.after(9500,self._weekly_maintenance)
        if self.sovela_session and self.account_client:
            self.run_job('admin_status',lambda:self.account_client.admin_status(self.sovela_session))

    def _replace_footer_version(self,widget):
        super()._replace_footer_version(widget)
        def update(w):
            try:
                if isinstance(w,tk.Label):
                    label=str(w.cget('text'))
                    if 'v2.3' in label or 'v2.2' in label:
                        w.configure(text=label.replace('v2.3','v3.0').replace('v2.2','v3.0'))
                for child in w.winfo_children():update(child)
            except tk.TclError:pass
        update(widget)

    def _entitled(self):
        return premium_allowed(self.sovela_session.entitlement if self.sovela_session else None)

    def make_nav(self):
        super().make_nav()
        rail=tk.Frame(self.sidebar,bg=SLATE_SIDE)
        # Insert the Premium shortcut before the sidebar's expanding spacer.
        place=None
        for child in self.sidebar.winfo_children():
            if isinstance(child,tk.Frame) and child.pack_info().get('fill')=='both':
                place=child;break
        rail.pack(fill='x',padx=10,pady=(5,0),before=place)
        self.premium_nav=self.text_button(rail,
               '✦    PREMIUM' if self._entitled() else '🔒    PREMIUM',
               self.open_premium,size=10,bg=SLATE_SIDE,
               fg=SLATE_GREEN if self._entitled() else SLATE_MUTED)
        self.premium_nav.configure(anchor='w',padx=15,pady=10)
        self.premium_nav.pack(fill='x')
        self.nav_buttons['Premium']=self.premium_nav

    def show_tab(self,tab):
        if tab=='Premium':
            self.open_premium();return
        result=super().show_tab(tab)
        if hasattr(self,'frame'):
            self._replace_footer_version(self.frame)
        return result

    def open_premium(self):
        if not self._entitled():
            self.account_sheet()
            return
        self._cancel_bounce()
        self.current_tab='Premium'
        self._account_open=False
        try:self.account_button.configure(state='normal')
        except tk.TclError:pass
        self.reset_body()
        self._root_view(25)
        self._sync_nav_state()
        self._premium_page()

    def _premium_page(self):
        self._page_header('✦  Premium maintenance',
                          'Optional conveniences. Your files are never deleted silently.')
        e,card=self._surface(self.view,padding=19);e.pack(fill='x',pady=(0,14))
        self._label(card,'AUTOMATIC REVIEW',10,True,color=SLATE_GREEN).pack(anchor='w')
        self._label(card,'Sovela can check maintenance needs once a week while the app is open.',
                    10,color=SLATE_MUTED).pack(anchor='w',pady=(5,12))
        for key,title,detail in [
            ('premium_clean_preview','Weekly cleanup review','Find eligible temporary/cache files. Never remove them automatically.'),
            ('premium_weekly_defender','Weekly antivirus quick scan','Request a Defender scan while Sovela is open, only if Defender is active.')]:
            row=tk.Frame(card,bg=WHITE);row.pack(fill='x',pady=(5,7))
            info=tk.Frame(row,bg=WHITE);info.pack(side='left',fill='x',expand=True)
            self._label(info,title,11,True).pack(anchor='w')
            self._label(info,detail,9,color=SLATE_MUTED,wraplength=415).pack(anchor='w',pady=(3,0))
            self._v3_switch(row,key).pack(side='right')
        e,c=self._surface(self.view,padding=16);e.pack(fill='x')
        self._label(c,'YOUR CONTROLS',10,True).pack(anchor='w',pady=(0,8))
        line=tk.Frame(c,bg=WHITE);line.pack(fill='x')
        self._button(line,'Review Cleaner',lambda:self.show_tab('Cleaner'),False,True).pack(side='left')
        self._button(line,'Run a scan',lambda:self.show_tab('Malware Scan'),False,True).pack(side='left',padx=7)
        self._label(c,'Automatic cleanup deletes nothing. Scans run only while Sovela is open and may take time.',
                    9,color=SLATE_MUTED,wraplength=630).pack(anchor='w',pady=(10,0))

    def _v3_switch(self,parent,key):
        btn=self._button(parent,'',lambda:self._toggle_local(key,btn),False,True)
        btn.configure(text='On  ●' if self.local_options.get(key) else 'Off  ○')
        return btn

    def _toggle_local(self,key,btn=None):
        self.local_options[key]=not self.local_options.get(key,False)
        save_local_settings(self.local_options)
        if btn and btn.winfo_exists():btn.configure(text='On  ●' if self.local_options[key] else 'Off  ○')

    def _weekly_maintenance(self):
        if not self.root.winfo_exists():return
        if not self.local_options.get('weekly_reminders',True):return
        if not self.local_options.get('last_weekly_reminder'):
            self.local_options['last_weekly_reminder']=datetime.now(timezone.utc).isoformat()
            save_local_settings(self.local_options)
            return
        if not reminder_due(self.local_options.get('last_weekly_reminder')):return
        self.local_options['last_weekly_reminder']=datetime.now(timezone.utc).isoformat()
        save_local_settings(self.local_options)
        self.record_activity('Weekly PC-care reminder shown')
        self._maintenance_notice()
        if self._entitled() and any(self.local_options.get(k) for k in
                                   ('premium_weekly_defender','premium_clean_preview')):
            self.root.after(2500,self._premium_maintenance)

    def _maintenance_notice(self):
        # Custom in-app notification; never Windows notifications. Visible only while running.
        if self._weekly_toast is not None:return
        popup=tk.Toplevel(self.root)
        self._weekly_toast=popup
        popup.overrideredirect(True)
        popup.attributes('-topmost',True)
        popup.configure(bg=SLATE_LINE)
        card=tk.Frame(popup,bg=WHITE,padx=20,pady=15)
        card.pack(fill='both',expand=True,padx=1,pady=1)
        self._label(card,'✦  SOVELA · WEEKLY PC CARE',10,True,color=SLATE_GREEN).pack(anchor='w')
        self._label(card,'A good time to review your antivirus scan and cleanable files.',10,
                    color=SLATE_TEXT,wraplength=315).pack(anchor='w',pady=(10,13))
        row=tk.Frame(card,bg=WHITE);row.pack(fill='x')
        self._button(row,'Open scanner →',lambda:self._close_weekly('Malware Scan'),True,True).pack(side='left')
        self._button(row,'Later',self._close_weekly,False,True).pack(side='right')
        left,top,right,bottom=self.work_area(self.root.winfo_x(),self.root.winfo_y())
        popup.geometry(f'380x165+{max(left,right-400)}+{top+18}')
        self._week_toast_job=self.root.after(14000,self._close_weekly)

    def _close_weekly(self,tab=None):
        if self._week_toast_job:
            try:self.root.after_cancel(self._week_toast_job)
            except tk.TclError:pass
            self._week_toast_job=None
        if self._weekly_toast:
            try:self._weekly_toast.destroy()
            except tk.TclError:pass
            self._weekly_toast=None
        if tab:self.show_tab(tab)

    def _premium_maintenance(self):
        # Premium never cleans/deletes unattended. It may refresh the safe preview.
        if not self._entitled() or not self.root.winfo_exists():return
        if not self.local_options.get('last_maintenance'):
            self.local_options['last_maintenance']=datetime.now(timezone.utc).isoformat()
            save_local_settings(self.local_options)
            return
        if not reminder_due(self.local_options.get('last_maintenance')):return
        self.local_options['last_maintenance']=datetime.now(timezone.utc).isoformat()
        save_local_settings(self.local_options)
        if self.local_options.get('premium_clean_preview') and not self.care_busy:
            self.care_busy=True
            self.run_job('care_preview',scan_cleanup)
            self.record_activity('Premium weekly cleanup preview requested')
        if self.local_options.get('premium_weekly_defender') and not self.device_scan_busy:
            # Runs a real Defender request, which will safely decline when inactive.
            self.start_device_scan('quick')

    def overview_page(self):
        self._page_header('Your computer','A calmer place to check, clean and keep things running.')
        e,c=self._surface(self.view,padding=18);e.pack(fill='x',pady=(0,16))
        line=tk.Frame(c,bg=WHITE);line.pack(fill='x')
        self._label(line,'◉  SECURITY OVERVIEW',10,True,color=SLATE_GREEN).pack(side='left')
        self._button(line,'Check protection →',self.check_protection_and_show,True,True).pack(side='right')
        self._label(c,str(self.status)[:120],14,True).pack(anchor='w',pady=(10,3))
        self._label(c,'Read from Windows settings · Not a malware scan result',9,color=SLATE_MUTED).pack(anchor='w')
        self._label(self.view,'QUICK ACTIONS',9,True,color=SLATE_MUTED).pack(anchor='w',pady=(0,8))
        grid=tk.Frame(self.view,bg=SLATE_BG);grid.pack(fill='x')
        actions=[('◈','Malware Scan','Quick or full scan','Malware Scan'),
                 ('✦','PC Cleaner','Review files safely','Cleaner'),
                 ('▦','Startup','Review launch programs','Startup'),
                 ('◉','PC Health','Actionable advice','PC Health'),
                 ('◇','File Inspector','Check a selected file','Downloads'),
                 ('✧','Assistant','Get troubleshooting help','Assistant')]
        for i,(ico,title,sub,tab) in enumerate(actions):
            edge,inside=self._surface(grid,padding=14)
            edge.grid(row=i//3,column=i%3,sticky='nsew',padx=(0,9 if i%3<2 else 0),pady=(0,9))
            grid.grid_columnconfigure(i%3,weight=1,uniform='actions')
            self._label(inside,ico,16,color=SLATE_GREEN).pack(anchor='w')
            self._label(inside,title,11,True).pack(anchor='w',pady=(5,0))
            self._label(inside,sub,8,color=SLATE_MUTED).pack(anchor='w')
            for widget in (edge,inside,*inside.winfo_children()):
                widget.configure(cursor='hand2')
                widget.bind('<Button-1>',lambda _event,target=tab:self.show_tab(target))
        row=tk.Frame(self.view,bg=SLATE_BG);row.pack(fill='x',pady=(9,0))
        self._button(row,'✦ Premium maintenance',self.open_premium,False,True).pack(side='left')
        self._button(row,'⚙  Windows Security',open_windows_security,False,True).pack(side='left',padx=8)

    def downloads_page(self):
        self._page_header('File inspector','Inspect a suspicious file without opening it.',('Choose file +',self.choose_file))
        e,c=self._surface(self.view,padding=18);e.pack(fill='x',pady=(0,12))
        self._label(c,'◈  FILE DETAILS',11,True,color=SLATE_GREEN).pack(anchor='w')
        if self.last_file:
            info=self.last_file
            for name,value in [('File',str(info.get('name','Unknown'))),
                               ('Size',self.human_bytes(info.get('size',0))),
                               ('Type',str(info.get('extension','Unknown'))),
                               ('Basic inspection',str(info.get('note','Unavailable'))[:180])]:
                line=tk.Frame(c,bg=WHITE);line.pack(fill='x',pady=(7,0))
                self._label(line,name,9,True).pack(side='left')
                self._label(line,value,9,color=SLATE_MUTED,wraplength=420).pack(side='right')
            line=tk.Frame(c,bg=WHITE);line.pack(fill='x',pady=(13,0))
            self._button(line,'Copy SHA-256',lambda:self.root.clipboard_clear() or self.root.clipboard_append(info.get('sha256','')),False,True).pack(side='left')
            self._button(line,'Search fingerprint ↗',lambda h=info.get('sha256',''):webbrowser.open('https://www.google.com/search?q='+__import__('urllib.parse',fromlist=['quote']).quote('"'+h+'"')),False,True).pack(side='left',padx=7)
            self._label(c,'Fingerprint searches share only the file hash, not its contents.',9,color=SLATE_MUTED).pack(anchor='w',pady=(10,0))
        else:
            self._label(c,'No file selected yet. Choose a downloaded file to check its metadata and fingerprint.',10,color=SLATE_MUTED,wraplength=620).pack(anchor='w',pady=(10,12))
            self._button(c,'Choose a file',self.choose_file).pack(anchor='w')
        e,c=self._surface(self.view,padding=17);e.pack(fill='x')
        self._label(c,'◎  ANTIVIRUS CHECK',11,True,color=SLATE_GREEN).pack(anchor='w')
        self._label(c,'Use Microsoft Defender for a real selected-file scan when Defender is active. If another antivirus is active, use its own scanner.',9,color=SLATE_MUTED,wraplength=610).pack(anchor='w',pady=(6,10))
        btn=self._button(c,'Request Defender file scan',self.defender_scan,True,True)
        btn.pack(anchor='w')
        if not self.selected_file or self.scanning or self.working_file:btn.configure(state='disabled')
        self._label(c,str(self.scan_message)[:280],9,color=SLATE_MUTED,wraplength=600).pack(anchor='w',pady=(10,0))

    def health_page(self):
        super().health_page()
        # Turn actionable recommendation text into actual safe shortcuts.
        def walk(w):
            try:
                if isinstance(w,tk.Label):
                    value=str(w.cget('text')).casefold()
                    target=None
                    if 'task manager' in value: target=self.open_task_manager
                    elif 'startup' in value: target=lambda:self.show_tab('Startup')
                    elif 'storage settings' in value: target=lambda:self.open_settings('ms-settings:storagesense','Storage')
                    if target:
                        w.configure(fg='#176EA4',cursor='hand2',font=(SLATE_FONT,9,'underline'))
                        w.bind('<Button-1>',lambda _e,cb=target:cb())
                for child in w.winfo_children():walk(child)
            except tk.TclError:pass
        walk(self.view)

    def startup_page(self):
        super().startup_page()
        if not self.startups:return
        items=self.startups.get('items',[])
        # Heuristics are recommendations for *review*, not claims of uselessness.
        optional=[]
        for item in items:
            name=str(item.get('name','')).lower()
            if not item.get('editable') or item.get('state')!='Enabled':continue
            if any(k in name for k in ('discord','spotify','steam','epic games','skype','teams','zoom','launcher')):
                optional.append(item)
        if optional:
            parent=tk.Frame(self.view,bg=SLATE_BG)
            target=next((w for w in self.view.winfo_children() if w is not parent and w.winfo_manager()=='pack' and str(w.pack_info().get('expand')) in ('1','True')),None)
            if target: parent.pack(fill='x',pady=(4,2),before=target)
            else:parent.pack(fill='x',pady=(4,2))
            self._label(parent,'✧  OPTIONAL STARTUP REVIEW',9,True,color=SLATE_GREEN).pack(anchor='w')
            self._label(parent,', '.join(x.get('name','App') for x in optional[:4])+'. If you rarely use these, consider disabling their auto-start above.',9,color=SLATE_MUTED,wraplength=670).pack(anchor='w',pady=(3,0))
        # No icon is not proof that an app is safe, unnecessary or malicious.

    def assistant_page(self):
        super().assistant_page()
        connected=bool(self.gemini_key.get()) if os.name=='nt' else False
        def relabel(w):
            try:
                if isinstance(w,tk.Label):
                    t=str(w.cget('text'))
                    if 'Online AI is not connected by the developer yet.' in t:
                        w.configure(text='Open Account → Personal AI to connect a Gemini API key. Guided help works offline.')
                    if t in ('○  Guided help','●  Online AI'):
                        w.configure(text='●  Personal Gemini' if connected else '○  Guided help')
                for child in w.winfo_children():relabel(child)
            except tk.TclError:pass
        relabel(self.body)

    def ask(self,text):
        value=text.strip()
        if not value:return
        if 'gemini' in value.lower() and ('key' in value.lower() or 'token' in value.lower()):
            self.messages.append(('you',value))
            self.messages.append(('sovela','You can create a Gemini API key at https://aistudio.google.com/apikey. Then open Account → Personal AI. Save your own key there. Only typed chat questions are sent to Google; scan results and files are not sent automatically. A free tier may have limits.'))
            self.show_tab('Assistant');return
        key=self.gemini_key.get() if os.name=='nt' else None
        if not key:
            return super().ask(text)
        if self.chat_waiting:return
        self.messages.append(('you',value))
        self.chat_waiting=True
        self.show_tab('Assistant')
        history=[(r,t) for r,t in self.messages if r=='you' or (r=='sovela' and len(t)<3000 and not t.startswith('Hello!'))]
        self.run_job('gemini_chat',lambda:ask_gemini(key,history))

    def poll_events(self):
        deferred=[]
        while True:
            try:kind,status,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='admin_status':
                self._is_admin=(status=='ok' and value is True)
                if self._is_admin and self._account_open:self._build_account_page()
            elif kind=='admin_list':
                if status=='ok' and isinstance(value,list):
                    self._admin_accounts=value[:100]
                    if self._account_open and self._account_section=='Admin':
                        self._admin_listbox.delete(0,'end')
                        for x in self._admin_accounts:
                            self._admin_listbox.insert('end',str(x.get('email','Unknown'))+'  ·  '+str(x.get('tier','')))
                elif self._account_open and self._account_section=='Admin':
                    messagebox.showerror('Admin','Account listing was unavailable.',parent=self.root)
            elif kind=='admin_grant':
                if self._account_open and self._account_section=='Admin':
                    messagebox.showinfo('Premium grant','Grant recorded by the server.' if status=='ok' else 'Grant failed. Check role and database setup.',parent=self.root)
            elif kind=='gemini_chat':
                self.chat_waiting=False
                self.messages.append(('sovela',value if status=='ok' else 'Gemini is unavailable: '+str(value)+'. Your offline assistant is still available.'))
                self.messages=self.messages[-30:]
                if self.current_tab=='Assistant':self.show_tab('Assistant')
            else:deferred.append((kind,status,value))
        for item in deferred:self.events.put(item)
        super().poll_events()

    def _build_account_page(self):
        """Compact, native account tabs: no nested popup or long scrolling page."""
        self._account_section=getattr(self,'_account_section','Profile')
        for old in self.view.winfo_children():old.destroy()
        head=tk.Frame(self.view,bg=SLATE_BG);head.pack(fill='x',pady=(0,12))
        left=tk.Frame(head,bg=SLATE_BG);left.pack(side='left',fill='x',expand=True)
        self._label(left,'Your account',22,True).pack(anchor='w')
        self._label(left,'Membership, help and updates in one place',9,color=SLATE_MUTED).pack(anchor='w',pady=(4,0))
        self._button(head,'Done  ✓',lambda:self.show_tab(self._account_return_tab),True,True).pack(side='right')
        tabs=tk.Frame(self.view,bg=SLATE_BG);tabs.pack(fill='x',pady=(0,13))
        sections=['Profile','Updates','Personal AI','Support']
        if self._is_admin:sections.append('Admin')
        for name in sections:
            btn=self._button(tabs,name,lambda n=name:self._change_account_section(n),False,True)
            btn.configure(bg=SLATE_GREEN_SOFT if name==self._account_section else LITE,
                          fg=SLATE_GREEN if name==self._account_section else SLATE_MUTED)
            btn.pack(side='left',padx=(0,7))
        e,c=self._surface(self.view,padding=20)
        e.pack(fill='both',expand=True)
        current=self._account_section
        if current=='Profile':
            email=self.sovela_session.email if self.sovela_session else 'Developer preview'
            self._label(c,'◈  SIGNED IN',9,True,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,email,15,True).pack(anchor='w',pady=(8,18))
            ent=(self.sovela_session.entitlement or {}) if self.sovela_session else {}
            tier=ent.get('tier','unknown')
            label={'trial':'Premium trial','premium':'Premium active','free':'Free plan'}.get(tier,'Membership unavailable')
            self._label(c,'✦  '+label,17,True,color=SLATE_GREEN).pack(anchor='w')
            if tier=='trial':
                self._label(c,str(ent.get('days_left','?'))+' days left · No automatic charges',10,color=SLATE_MUTED).pack(anchor='w',pady=(6,0))
            self._label(c,'Premium access is supplied by Supabase. Your Windows clock cannot extend a trial.',9,color=SLATE_MUTED,wraplength=590).pack(anchor='w',pady=(8,17))
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            self._button(row,'✦ Premium controls',self.open_premium,False,True).pack(side='left')
            if self.sovela_session and self.account_client:
                self._button(row,'Sign out',self._signout_account,False,True).pack(side='right')
            self._label(c,'Payment checkout is not enabled. No card details are requested.',9,color=SLATE_MUTED).pack(anchor='w',pady=(18,0))
        elif current=='Updates':
            self._label(c,'↻  APP UPDATES',11,True,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,'Connect a public GitHub Releases repository. Use owner/repository format.',9,color=SLATE_MUTED).pack(anchor='w',pady=(6,12))
            line=tk.Frame(c,bg=WHITE);line.pack(fill='x')
            entry=tk.Entry(line,bg='#F3F8F5',fg=SLATE_TEXT,bd=1,relief='solid',font=(SLATE_FONT,11))
            entry.insert(0,self.updates_repo)
            entry.pack(side='left',fill='x',expand=True,ipady=8)
            def save_repository():
                repo=valid_repo(entry.get())
                if not repo:
                    messagebox.showinfo('Repository','Enter owner/repository. Example: username/sovela-pc-care',parent=self.root);return
                self.updates_repo=repo
                self.local_options['updates_repo']=repo
                save_local_settings(self.local_options)
                self._latest_update=None
                self._check_updates_manual()
            self._button(line,'Assign',save_repository,True,True).pack(side='left',padx=(8,0))
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x',pady=(17,8))
            self._button(row,'Check for updates ↗',self._check_updates_manual,False,True).pack(side='left')
            self._account_status=tk.StringVar(value='')
            self._account_link=tk.Frame(c,bg=WHITE)
            self._account_link.pack(fill='x',pady=(5,0))
            self._label(c,'Published GitHub Releases only. Updates open in your browser; Sovela never silently downloads or runs installers.',9,color=SLATE_MUTED,wraplength=580).pack(anchor='w',pady=(17,0))
            self._update_account_info()
            tk.Label(c,textvariable=self._account_status,bg=WHITE,fg=SLATE_MUTED,
                     font=(SLATE_FONT,9),anchor='w').pack(fill='x',pady=(9,0))
        elif current=='Personal AI':
            self._label(c,'✧  GEMINI AI',11,True,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,'Optional real AI using your own Google AI Studio key. The key stays encrypted for your Windows user.',10,color=SLATE_MUTED,wraplength=590).pack(anchor='w',pady=(8,16))
            field=tk.Entry(c,show='●',font=(SLATE_FONT,11),bd=1,relief='solid',bg='#F3F8F5')
            field.pack(fill='x',ipady=8)
            status=self._label(c,'Connected' if self.gemini_key.get() else 'Not connected',10,color=SLATE_GREEN if self.gemini_key.get() else SLATE_MUTED)
            status.pack(anchor='w',pady=(10,12))
            def save_key():
                key=field.get().strip()
                try:
                    self.gemini_key.save(key)
                    if self.gemini_key.get()!=key:
                        raise OSError('Stored key could not be read back')
                except (ValueError,OSError):
                    messagebox.showerror('Sovela · Personal AI',
                        'Your key could not be saved and verified. Check that it is a valid Gemini API key '
                        'and that Windows permits Sovela to store encrypted settings.',parent=self.root)
                    return
                field.delete(0,'end');status.configure(text='Saved securely on this PC',fg=SLATE_GREEN)
            def delete_key():
                try:self.gemini_key.remove()
                except OSError:
                    messagebox.showerror('Sovela · Personal AI','Could not remove your saved key.',parent=self.root)
                    return
                status.configure(text='Not connected',fg=SLATE_MUTED)
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            self._button(row,'Connect',save_key,True,True).pack(side='left')
            self._button(row,'Disconnect',delete_key,False,True).pack(side='left',padx=8)
            self._button(row,'Get a free-tier key ↗',lambda:webbrowser.open('https://aistudio.google.com/apikey'),False,True).pack(side='left')
            self._label(c,'Only questions you type in Assistant go to Google. Files and security reports are not uploaded. Google usage limits and its privacy policy apply.',9,color=SLATE_MUTED,wraplength=585).pack(anchor='w',pady=(18,0))
        elif current=='Support':
            self._label(c,'✉  CONTACT & ACCOUNT HELP',11,True,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,'We can help with account issues, bugs and billing questions.',10,color=SLATE_MUTED).pack(anchor='w',pady=(8,16))
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            address=self._label(row,'Email hidden until you choose to reveal it',10,color=SLATE_MUTED)
            address.pack(side='left')
            self._button(row,'Reveal email',lambda:address.configure(text=SUPPORT_EMAIL),False,True).pack(side='right')
            self._button(c,'Open email program ↗',lambda:webbrowser.open('mailto:'+SUPPORT_EMAIL),True,True).pack(anchor='w',pady=(18,0))
            self._label(c,'Revealing an address is not CAPTCHA verification. Anti-spam verification must be provided by a trusted website or service.',9,color=SLATE_MUTED,wraplength=585).pack(anchor='w',pady=(18,0))
        elif current=='Admin':
            self._label(c,'⚙  ADMINISTRATOR',11,True,color=SLATE_GREEN).pack(anchor='w')
            self._label(c,'Server-verified role required. Grants are audited by Supabase.',9,color=SLATE_MUTED).pack(anchor='w',pady=(7,14))
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x')
            self._button(row,'Refresh accounts',self._load_admin_accounts,True,True).pack(side='left')
            self._admin_summary=tk.StringVar(value='Select Refresh accounts to load up to 100 accounts.')
            self._label(c,self._admin_summary.get(),10,color=SLATE_MUTED).pack(anchor='w',pady=(14,10))
            self._admin_listbox=tk.Listbox(c,height=7,font=(SLATE_FONT,9),bg='#F3F8F5',bd=0)
            self._admin_listbox.pack(fill='x')
            row=tk.Frame(c,bg=WHITE);row.pack(fill='x',pady=(11,0))
            self._label(row,'Grant days:',9,color=SLATE_MUTED).pack(side='left')
            self._grant_days=tk.StringVar(value='30')
            tk.OptionMenu(row,self._grant_days,'7','30','90').pack(side='left')
            self._button(row,'Grant selected account',self._grant_admin_premium,False,True).pack(side='right')

    def _change_account_section(self,name):
        self._account_section=name
        self._build_account_page()

    def _load_admin_accounts(self):
        if not self._is_admin:return
        self.run_job('admin_list',lambda:self.account_client.admin_accounts(self.sovela_session))

    def _grant_admin_premium(self):
        if not self._is_admin:return
        choice=self._admin_listbox.curselection()
        if not choice or choice[0]>=len(self._admin_accounts):return
        item=self._admin_accounts[choice[0]]
        days=int(self._grant_days.get())
        if not messagebox.askyesno('Grant Premium',f'Grant {days} days to {item.get("email", "this user")}? This will be audited.',parent=self.root):return
        self.run_job('admin_grant',lambda:self.account_client.admin_grant(self.sovela_session,item['id'],days))

    def _settings_dropdown(self,parent,title,key,options,helper,suffix=''):
        # Custom menu display; unlike an editable combo the user can only select.
        row=self._settings_row(parent,title,helper)
        choices={str(option)+suffix:option for option in options}
        holder=tk.Menubutton(row, text=str(self.preferences.get(key,options[0]))+suffix+'  ▾',
                   font=(SLATE_FONT,10),bg=SLATE_GREEN_SOFT,fg=SLATE_GREEN,
                   activebackground='#DCECE6',bd=0,relief='flat',cursor='hand2',
                   padx=10,pady=8)
        menu=tk.Menu(holder,tearoff=False,bg=WHITE,fg=SLATE_TEXT,activebackground=SLATE_GREEN_SOFT,
                     font=(SLATE_FONT,10))
        for label,value in choices.items():
            def choose(l=label,v=value):
                self._set_pref(key,v)
                holder.configure(text=l+'  ▾')
            menu.add_command(label=label,command=choose)
        holder.configure(menu=menu)
        holder.pack(side='right',padx=(8,0),pady=(8,0))

    def _settings_select_page(self,page):
        if page!='Maintenance':return super()._settings_select_page(page)
        self._settings_page_name=page
        for name,button in self._settings_tab_buttons.items():
            button.configure(bg=SLATE_GREEN_SOFT if name==page else LITE,
                             fg=SLATE_GREEN if name==page else SLATE_MUTED)
        for child in self._settings_area.winfo_children():child.destroy()
        area=self._settings_area
        row=self._settings_row(area,'Weekly PC-care reminder',
                  'An in-app reminder every 7 days, only when Sovela is open.')
        self._v3_switch(row,'weekly_reminders').pack(side='right')
        row=self._settings_row(area,'Premium automatic reviews',
                  'Only accessible during a verified Premium trial or membership.')
        self._button(row,'Open Premium',self.open_premium,False,True).pack(side='right')
        row=self._settings_row(area,'Contact support',
                  'Opens your email program; no hidden data is sent.')
        self._button(row,'Email support ↗',lambda:webbrowser.open('mailto:'+SUPPORT_EMAIL),False,True).pack(side='right')

    def open_settings_sheet(self):
        if getattr(self,'_settings_sheet',None) is not None:return
        super().open_settings_sheet()
        tabs=getattr(self,'_settings_tab_buttons',{})
        if 'Maintenance' not in tabs:
            holder=next(iter(tabs.values())).master
            button=self.text_button(holder,'Maintenance',lambda:self._settings_select_page('Maintenance'),
                      size=10,bg=LITE,fg=SLATE_MUTED)
            button.pack(side='left',padx=(0,5))
            tabs['Maintenance']=button
