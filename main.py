"""Sovela v2.3: account gate followed by the existing PC-care loading screen."""
from pathlib import Path
import sys
import tkinter as tk
from sovela_launcher import AccountGate

if __name__ == '__main__':
    # Give Sovela one consistent Windows taskbar identity, including when
    # launched via the installer and when displaying its login screen.
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Sovela.PCCare.Desktop')
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    try:
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        icon = tk.PhotoImage(file=str(base / 'sovela.png'))
        root.iconphoto(True, icon)
        root._sovela_icon = icon
    except (OSError, tk.TclError):
        pass
    AccountGate(root)
    root.mainloop()
