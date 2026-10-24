"""Sovela custom frame for Windows, without losing a normal taskbar window.

Only adjusts the *visual* native caption. The Tk toplevel remains managed by
Windows (overrideredirect(False)), preserving taskbar, Alt+Tab and native
minimise/restore. No admin rights required. Other OSs use native frames.
"""
from __future__ import annotations
import sys


def apply_custom_chrome(root):
    """Hide Windows' caption safely. Returns True on success."""
    if sys.platform != 'win32':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        root.update_idletasks()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos.restype = wintypes.BOOL
        hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
        if not hwnd:
            return False
        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_CAPTION, WS_SYSMENU, WS_MINIMIZEBOX = 0x00C00000, 0x00080000, 0x00020000
        WS_EX_APPWINDOW, WS_EX_TOOLWINDOW = 0x00040000, 0x00000080
        style = int(user32.GetWindowLongW(hwnd, GWL_STYLE))
        target = (style & ~WS_CAPTION) | WS_SYSMENU | WS_MINIMIZEBOX
        ext = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
        ext_target = (ext | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        if style != target:
            user32.SetWindowLongW(hwnd, GWL_STYLE, target)
        if ext != ext_target:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ext_target)
        if style != target or ext != ext_target:
            flags = 0x0001 | 0x0002 | 0x0004 | 0x0020  # no size/move/z-order; frame changed
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, flags)
        return True
    except (OSError, AttributeError, ValueError):
        return False


def schedule_chrome(root):
    """Set the Windows style after Tk creates the HWND and after taskbar restores."""
    def safe_apply():
        try:
            if root.winfo_exists() and root.state() == 'normal' and not root.overrideredirect():
                apply_custom_chrome(root)
        except Exception:
            pass
    root.after(100, safe_apply)
    def on_map(event):
        if event.widget is root:
            root.after(65, safe_apply)
    root.bind('<Map>', on_map, add='+')
