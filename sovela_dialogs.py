"""Sovela-owned confirmation/alert UI. Never use a remote dialog for privileged actions."""
import tkinter as tk
from tkinter import messagebox

DARK='#163D3B'; MINT='#65D1AD'; BG='#F5F8F7'; INK='#183B40'; SUB='#617975'
_INSTALLED=False

def show(kind,title,message,parent=None):
    root=parent or tk._default_root
    if root is None or not root.winfo_exists():
        return False if kind.startswith('ask') else 'ok'
    outcome={'choice':False}
    pop=tk.Toplevel(root)
    pop.title('Sovela')
    pop.configure(bg=BG)
    pop.resizable(False,False)
    pop.transient(root)
    pop.geometry('460x290')
    pop.update_idletasks()
    x=root.winfo_rootx()+max(0,(root.winfo_width()-460)//2)
    y=root.winfo_rooty()+max(0,(root.winfo_height()-290)//2)
    pop.geometry(f'+{x}+{y}')
    top=tk.Frame(pop,bg=DARK,height=73);top.pack(fill='x');top.pack_propagate(False)
    tk.Label(top,text='◈',bg=DARK,fg=MINT,font=('Segoe UI',28,'bold')).pack(side='left',padx=(24,14))
    tk.Label(top,text='SOVELA  /  '+('CONFIRM' if kind.startswith('ask') else 'NOTICE'),bg=DARK,fg='white',font=('Segoe UI',10,'bold')).pack(side='left')
    body=tk.Frame(pop,bg=BG,padx=25,pady=18);body.pack(fill='both',expand=True)
    tk.Label(body,text=str(title)[:90],bg=BG,fg=INK,font=('Segoe UI',16,'bold'),anchor='w').pack(fill='x')
    tk.Label(body,text=str(message)[:1200],bg=BG,fg=SUB,font=('Segoe UI',10),justify='left',anchor='nw',wraplength=390).pack(fill='both',expand=True,pady=(12,5))
    row=tk.Frame(body,bg=BG);row.pack(fill='x')
    def finish(value):
        outcome['choice']=value
        try:pop.grab_release()
        except tk.TclError:pass
        pop.destroy()
    def btn(text,yes=False):
        tk.Button(row,text=text,command=lambda:finish(yes),bg=DARK if yes else '#DFEBE7',
            fg='white' if yes else DARK,bd=0,padx=20,pady=10,font=('Segoe UI',10,'bold'),
            activebackground='#286D61',cursor='hand2').pack(side='right',padx=(9,0))
    if kind.startswith('ask'):
        btn('Confirm',True);btn('Cancel',False)
    else:btn('Got it',True)
    pop.protocol('WM_DELETE_WINDOW',lambda:finish(False))
    pop.bind('<Escape>',lambda _e:finish(False))
    pop.grab_set()
    pop.wait_window()
    return bool(outcome['choice'])

def install():
    global _INSTALLED
    if _INSTALLED:return
    # Existing modules import tkinter.messagebox, so one installation covers them.
    for action in ('showinfo','showwarning','showerror','askyesno','askokcancel','askretrycancel'):
        def handler(title=None,message=None,_kind=action,**kw):
            return show(_kind,title or 'Sovela',message or '',kw.get('parent'))
        setattr(messagebox,action,handler)
    _INSTALLED=True
