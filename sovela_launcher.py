"""Show email/password sign-in before Sovela's existing loading animation."""
import threading
import queue
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

from sovela_auth import (AccountError, SupabaseAccounts, TokenStore, read_cloud_config,
                         VERSION)
from sovela_v31 import SovelaV31
from sovela_window import schedule_chrome, begin_windows_titlebar_drag
from sovela_ai import windows_work_area, clamp_to_area

BG='#F3F6F5'
CARD='#FFFFFF'
INK='#24383A'
MUTED='#788B8B'
SAGE='#286F65'
PALE='#E5F2ED'
FONT='Segoe UI'


class AccountGate:
    def __init__(self, root):
        self.root=root
        self.config=read_cloud_config()
        self.client=(SupabaseAccounts(self.config) if self.config.get('supabase_url') else None)
        self.busy=False
        self.mode='signup'
        self.pending_email = None
        self.generation=0
        self.completed=queue.Queue()
        root.title('Sovela · Welcome')
        root.overrideredirect(False)
        root.resizable(False, False)
        root.configure(bg=BG)
        root.geometry('740x680')
        self.center()
        schedule_chrome(root)
        self._has_saved_session=bool(self.client and TokenStore().load())
        if self._has_saved_session:
            self._show_resume_splash()
        else:
            self.draw()
        root.after(75, self.poll_completed)
        if self.client:
            self.mode='signin'
            if not self._has_saved_session:
                self.set_mode('signin')
                self.set_status('Checking for your saved sign-in…')
            self.async_job(self.client.resume, self.handle_resume)

    def _show_resume_splash(self):
        """Neutral launch splash, no flashing login before saved session refresh."""
        self.root.configure(bg=BG)
        self._auth_titlebar()
        panel=tk.Frame(self.root,bg=BG)
        panel.pack(fill='both',expand=True)
        tk.Label(panel,text='◈',font=(FONT,48),bg=BG,fg=SAGE).pack(pady=(180,14))
        tk.Label(panel,text='sovela.',font=(FONT,26,'bold'),bg=BG,fg=INK).pack()
        tk.Label(panel,text='Checking your saved sign-in…',font=(FONT,11),bg=BG,fg=MUTED).pack(pady=(15,0))

    def center(self):
        self.root.update_idletasks()
        width,height=740,680
        self.root.geometry('%dx%d+%d+%d' % (width,height,
                    max(0,(self.root.winfo_screenwidth()-width)//2),
                    max(0,(self.root.winfo_screenheight()-height)//2)))

    def draw(self):
        for w in self.root.winfo_children():w.destroy()
        self._auth_titlebar()
        surface=tk.Frame(self.root,bg=BG)
        surface.pack(fill='both', expand=True)
        # Tiny left brand rail + simple authentication card.
        rail=tk.Frame(surface,bg='#213D3A',width=250)
        rail.pack(side='left',fill='y')
        rail.pack_propagate(False)
        tk.Label(rail,text='◈',font=(FONT,36),fg='#BEE8D5',bg='#213D3A').pack(anchor='w',padx=26,pady=(62,6))
        tk.Label(rail,text='sovela.',font=(FONT,27,'bold'),fg='white',bg='#213D3A').pack(anchor='w',padx=26)
        tk.Label(rail,text='A healthier PC.\nA quieter mind.',font=(FONT,13),
                 fg='#CBDED7',bg='#213D3A',justify='left').pack(anchor='w',padx=27,pady=(16,0))
        tk.Label(rail,text='Quiet PC care and security assistance.\nNo adverts. No scare tactics.',
                 fg='#9DBDB2',bg='#213D3A',font=(FONT,9),justify='left',
                 wraplength=194).pack(side='bottom',anchor='w',padx=27,pady=31)
        content=tk.Frame(surface,bg=BG,padx=34,pady=32)
        content.pack(side='left',expand=True,fill='both')
        tk.Label(content,text='Welcome to Sovela',fg=INK,bg=BG,
                 font=(FONT,23,'bold')).pack(anchor='w',pady=(7,0))
        tk.Label(content,text='Your security and PC care, all in one place.',
                 fg=MUTED,bg=BG,font=(FONT,10)).pack(anchor='w',pady=(5,8))
        tk.Label(content,text=('Trial availability is shown before you confirm your account' if self.client
                               else 'Creator setup required for real accounts'),
                 fg=SAGE,bg=BG,font=(FONT,9,'bold')).pack(anchor='w',pady=(0,15))
        self.form_area=tk.Frame(content,bg=BG)
        self.form_area.pack(fill='x')
        switch=tk.Frame(self.form_area,bg=BG)
        switch.pack(fill='x')
        self.signup_btn=self.button(switch,'Create account',lambda:self.set_mode('signup'),False)
        self.signup_btn.pack(side='left',fill='x',expand=True,padx=(0,4))
        self.signin_btn=self.button(switch,'Sign in',lambda:self.set_mode('signin'),False)
        self.signin_btn.pack(side='left',fill='x',expand=True,padx=(4,0))
        tk.Label(self.form_area,text='EMAIL ADDRESS',fg=MUTED,bg=BG,
                 font=(FONT,9,'bold')).pack(anchor='w',pady=(22,7))
        self.email_entry=tk.Entry(self.form_area,bg=CARD,fg=INK,insertbackground=INK,
               font=(FONT,11),bd=0,highlightbackground='#CBD8D4',highlightcolor=SAGE,
               highlightthickness=1,relief='flat')
        self.email_entry.pack(fill='x',ipady=10)
        tk.Label(self.form_area,text='PASSWORD',fg=MUTED,bg=BG,
                 font=(FONT,9,'bold')).pack(anchor='w',pady=(17,7))
        self.password_entry=tk.Entry(self.form_area,show='•',bg=CARD,fg=INK,insertbackground=INK,
               font=(FONT,11),bd=0,highlightbackground='#CBD8D4',highlightcolor=SAGE,
               highlightthickness=1,relief='flat')
        self.password_entry.pack(fill='x',ipady=10)
        self.password_entry.bind('<Return>', lambda _e:self.submit())
        self.show_pw=tk.BooleanVar(value=False)
        tk.Checkbutton(self.form_area,text='Show password',variable=self.show_pw,
                       command=lambda:self.password_entry.configure(show='' if self.show_pw.get() else '•'),
                       bg=BG,fg=MUTED,selectcolor=BG,activebackground=BG,
                       font=(FONT,9)).pack(anchor='w',pady=(6,8))
        self.submit_btn=self.button(self.form_area,'Create account →',self.submit,True)
        self.submit_btn.pack(fill='x',ipady=4)
        self.status=tk.StringVar(value='')
        self.status_label=tk.Label(content,textvariable=self.status,bg=BG,fg=SAGE,font=(FONT,9),
                 wraplength=384,justify='left')
        self.status_label.pack(anchor='w',pady=(13,4))
        extra=tk.Frame(self.form_area,bg=BG)
        extra.pack(fill='x',pady=(2,0))
        self.reset_btn=self.button(extra,'Forgot password?',self.reset_password,False)
        self.reset_btn.pack(side='left')
        self.have_code_btn=self.button(extra,'I have a confirmation code',self.have_code,False)
        self.have_code_btn.pack(side='right')
        # Confirmation never leaves the app; the user types an emailed OTP.
        self.verification_area = tk.Frame(content,bg=BG)
        tk.Label(self.verification_area,text='Check your email', fg=INK, bg=BG,
                 font=(FONT,17,'bold')).pack(anchor='w',pady=(18,6))
        self.verify_info = tk.StringVar(value='Enter the code from your confirmation email.')
        tk.Label(self.verification_area,textvariable=self.verify_info,
                 fg=MUTED,bg=BG,font=(FONT,10),wraplength=373,
                 justify='left').pack(anchor='w',pady=(0,17))
        self.code_heading=tk.Label(self.verification_area,text='EMAIL CONFIRMATION CODE',
                 fg=MUTED,bg=BG,font=(FONT,9,'bold'))
        self.code_heading.pack(anchor='w',pady=(0,8))
        self.code_entry=tk.Entry(self.verification_area,bg=CARD,fg=INK,
                 insertbackground=INK,font=(FONT,17,'bold'),bd=0,
                 highlightbackground='#CBD8D4',highlightcolor=SAGE,
                 highlightthickness=1,justify='center')
        self.code_entry.pack(fill='x',ipady=10)
        self.code_entry.bind('<Return>',lambda _e:self.verify_code())
        self.recovery_password=tk.Entry(self.verification_area,show='•',bg=CARD,fg=INK,
              font=(FONT,11),bd=0,highlightbackground='#CBD8D4',highlightthickness=1)
        self.confirm_btn=self.button(self.verification_area,'Confirm email →',self.verify_code,True)
        self.confirm_btn.pack(fill='x',pady=(15,7),ipady=4)
        self.resend_btn=self.button(self.verification_area,'Send another code',self.resend_code,False)
        self.resend_btn.pack(fill='x',pady=(2,7))
        self.back_btn=self.button(self.verification_area,'Back to sign in',lambda:self.set_mode('signin'),False)
        self.back_btn.pack(fill='x',pady=(0,3))
        if not self.client:
            self.set_status('Creator setup required. Accounts are not connected yet.')
            self.submit_btn.configure(state='disabled')
            self.reset_btn.configure(state='disabled')
            self.button(content,'Continue in developer preview →',
                        lambda:self.start_app(None,None),False).pack(fill='x',pady=(14,0))
            tk.Label(content,text='Developer preview only — not a customer sign-in.',
                     font=(FONT,8),fg=MUTED,bg=BG).pack(anchor='w')
        self.set_mode('signin' if self.client else 'signup')

    def _auth_titlebar(self):
        """Sovela's own minimise/close controls while Windows keeps the taskbar."""
        bar=tk.Frame(self.root,bg=CARD,height=40)
        bar.pack(fill='x')
        bar.pack_propagate(False)
        left=tk.Label(bar,text='  ◈   sovela.',bg=CARD,fg=INK,font=(FONT,12,'bold'))
        left.pack(side='left',padx=(10,0))
        close=tk.Button(bar,text='×',command=self.root.destroy,bd=0,relief='flat',
                        bg=CARD,fg=MUTED,activebackground='#F7E6E6',
                        font=(FONT,16),cursor='hand2',width=3)
        close.pack(side='right',padx=(0,8))
        mini=tk.Button(bar,text='—',command=self.root.iconify,bd=0,relief='flat',
                       bg=CARD,fg=MUTED,activebackground=PALE,
                       font=(FONT,12),cursor='hand2',width=4)
        mini.pack(side='right')
        for item in (bar,left):
            item.bind('<ButtonPress-1>',self._start_auth_drag)
            item.bind('<B1-Motion>',self._move_auth_drag)
        tk.Frame(self.root,height=1,bg='#E1EAE6').pack(fill='x')

    def _start_auth_drag(self,event):
        self._auth_drag_native=begin_windows_titlebar_drag(self.root)
        if self._auth_drag_native:
            return
        self._auth_dx=event.x_root-self.root.winfo_x()
        self._auth_dy=event.y_root-self.root.winfo_y()

    def _move_auth_drag(self,event):
        if getattr(self,'_auth_drag_native',False):
            return
        x=event.x_root-getattr(self,'_auth_dx',0)
        y=event.y_root-getattr(self,'_auth_dy',0)
        area=(windows_work_area(event.x_root,event.y_root)
              or (0,0,self.root.winfo_screenwidth(),self.root.winfo_screenheight()))
        x,y=clamp_to_area(x,y,self.root.winfo_width(),self.root.winfo_height(),area)
        self.root.geometry(f'+{x}+{y}')

    def button(self,parent,text,cmd,primary):
        return tk.Button(parent,text=text,command=cmd,cursor='hand2',bd=0,relief='flat',
              highlightthickness=0,font=(FONT,10,'bold'),padx=12,pady=10,
              bg=SAGE if primary else PALE,fg='white' if primary else SAGE,
              activebackground='#1E5750' if primary else '#D8E8E2',
              activeforeground='white' if primary else SAGE)

    def set_status(self,s):
        self.status.set(s)

    def set_mode(self,mode):
        if self.busy:return
        self.mode=mode
        if mode=='verify_link':
            self.form_area.pack_forget()
            self.verification_area.pack(fill='x',before=self.status_label)
            self.verify_info.set('Check the confirmation LINK sent to your email.\n\n'
                'Your account is created when you register, but you must verify the email '
                'before signing in. If the link shows a localhost error, confirmation may '
                'still have succeeded. Close that tab, come back to Sovela and sign in.')
            self.code_heading.pack_forget()
            self.code_entry.pack_forget()
            self.recovery_password.pack_forget()
            self.confirm_btn.configure(text='I opened the link — Sign in →',
                                       command=lambda:self.set_mode('signin'))
            self.resend_btn.configure(text='Resend confirmation email')
            self.set_status('Never share your confirmation link. Sovela does not need a verification code.')
            return
        if mode in ('verify','recover'):
            self.form_area.pack_forget()
            self.verification_area.pack(fill='x',before=self.status_label)
            self.code_heading.pack(anchor='w',pady=(0,8))
            self.code_entry.pack(fill='x',ipady=10)
            self.verify_info.set(('Enter the recovery code for ' if mode=='recover' else 'Enter the confirmation code for ')+str(self.pending_email or 'your email')+'.')
            self.confirm_btn.configure(text='Reset password →' if mode=='recover' else 'Confirm email →',
                                       command=self.confirm_recovery if mode=='recover' else self.verify_code)
            if mode=='recover':
                self.recovery_password.pack(fill='x',ipady=10,pady=(10,4),before=self.confirm_btn)
                self.recovery_password.delete(0,'end')
                self.set_status('Enter the emailed code and a NEW password (8+ characters).')
            else:
                self.recovery_password.pack_forget()
                self.set_status('Enter the code from your Sovela confirmation email.')
            self.code_entry.focus_set()
            return
        self.verification_area.pack_forget()
        self.form_area.pack(fill='x',before=self.status_label)
        self.signup_btn.configure(bg=PALE if mode=='signup' else BG)
        self.signin_btn.configure(bg=PALE if mode=='signin' else BG)
        self.submit_btn.configure(text=('Create account →' if mode=='signup' else 'Sign in →'))

    def async_job(self, operation, callback):
        if self.busy:return
        self.busy=True
        self.generation+=1
        generation=self.generation
        if self.client and not self._has_saved_session:
            self.submit_btn.configure(state='disabled')
            self.confirm_btn.configure(state='disabled')
            self.resend_btn.configure(state='disabled')
        def run():
            try: result,err=operation(),None
            except AccountError as e:result,err=None,str(e)
            except Exception:result,err=None,'Something went wrong. Please try again.'
            self.completed.put((generation,callback,result,err))
        threading.Thread(target=run,daemon=True).start()

    def poll_completed(self):
        try:
            while True:
                generation,callback,result,error=self.completed.get_nowait()
                self.deliver(generation,callback,result,error)
        except queue.Empty:
            pass
        try:
            if self.root.winfo_exists() and not self.root.overrideredirect():
                self.root.after(75,self.poll_completed)
        except tk.TclError:
            pass

    def deliver(self,generation,callback,result,error):
        if generation!=self.generation or not self.root.winfo_exists():return
        self.busy=False
        if self.client and not self._has_saved_session:
            self.submit_btn.configure(state='normal')
            self.confirm_btn.configure(state='normal')
            self.resend_btn.configure(state='normal')
        callback(result,error)

    def submit(self):
        if not self.client or self.busy:return
        email=self.email_entry.get().strip()
        password=self.password_entry.get()
        mode=self.mode
        self.set_status('Creating your account…' if mode=='signup' else 'Signing in…')
        operation=(lambda:self.client.signup(email,password) if mode=='signup'
                   else self.client.signin(email,password))
        self.async_job(operation,lambda result,error:self.handle_auth(mode,result,error))

    def handle_auth(self,mode,session,error):
        self.password_entry.delete(0,'end')
        if error:
            self.set_status(error)
        elif session:
            self.start_app(session,self.client)
        elif mode=='signup':
            self.pending_email = self.email_entry.get().strip().lower()
            self.set_mode('verify_link')
        else:
            self.set_status('Sign in was not completed. Check your email verification.')

    def have_code(self):
        if self.busy:return
        email=self.email_entry.get().strip().lower()
        import re
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            self.set_status('Enter the email address you signed up with first.')
            return
        self.pending_email=email
        self.set_mode('verify')

    def verify_code(self):
        if self.busy or not self.client or not self.pending_email:return
        code=self.code_entry.get().strip()
        self.set_status('Verifying your confirmation code…')
        self.async_job(lambda:self.client.verify_email_code(self.pending_email,code),
                       self.handle_verification)

    def handle_verification(self,session,error):
        if error:
            self.set_status(error)
        elif session:
            self.code_entry.delete(0,'end')
            self.start_app(session,self.client)
        else:
            self.set_status('We could not verify that code. Please try again.')

    def resend_code(self):
        if self.busy or not self.client or not self.pending_email:return
        self.set_status('Requesting another code…')
        self.async_job(lambda:self.client.resend_confirmation(self.pending_email),
                       lambda _result,error:self.set_status(error or 'A new confirmation code was requested. Check your inbox and spam folder.'))

    def handle_resume(self,session,error):
        if self._has_saved_session and not session:
            self._has_saved_session=False
            self.draw()
            self.set_mode('signin')
        if session:
            self.start_app(session,self.client)
        elif error:
            self.set_status(error+' Your PC care data remains on this computer.')
        else:
            self.set_status('Sign in or create your free account. Your account will show the current Premium trial offer.')

    def reset_password(self):
        if not self.client:return
        email=self.email_entry.get().strip().lower()
        self.pending_email=email
        self.set_status('Requesting a password reset code…')
        self.async_job(lambda:self.client.password_reset(email),
            lambda _r,error:self.set_status(error) if error else self.set_mode('recover'))

    def confirm_recovery(self):
        if not self.client or self.busy:return
        email=self.pending_email
        code=self.code_entry.get().strip()
        new_password=self.recovery_password.get()
        if len(new_password)<8:
            self.set_status('Your new password must be at least 8 characters.');return
        def recover():
            sess=self.client.verify_recovery_code(email,code)
            self.client.change_password(sess,new_password)
            return sess
        self.set_status('Checking the recovery code…')
        self.async_job(recover,self.handle_recovery)

    def handle_recovery(self,session,error):
        self.recovery_password.delete(0,'end')
        if error:self.set_status(error)
        else:self.start_app(session,self.client)

    def start_app(self,session,client):
        self.generation+=1
        # Do not start the regular startup loader until login has completed.
        for w in self.root.winfo_children():w.destroy()
        SovelaV31(self.root,session,client,self.config.get('updates_repo',''))
