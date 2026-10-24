"""Sovela v1.3 — ad-free Windows security companion (not an antivirus).

Built using the Python standard library only. This app never disables or
uninstalls antivirus software or silently uploads data. The optional PC Cleaner
recycles only specifically selected, eligible user-level files after confirmation.
A user-selected file can be hashed locally; a Microsoft Defender scan may be
requested separately and ONLY if Defender reports active protection.
"""

import ctypes
import hashlib
import json
import os
import sys
import queue
import shutil
import subprocess
import threading
import time
from sovela_brain import advanced_offline_reply, security_insights
from sovela_care import (CATEGORIES, scan_cleanup, clean_selected,
                           list_startups, disable_startup, restore_startup)
import urllib.request
import urllib.error
import webbrowser
from datetime import datetime
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

BG = '#0D1420'
PANEL = '#162236'
PANEL2 = '#1E2E45'
TEXT = '#F0F5FA'
MUTED = '#A7BAD0'
ACCENT = '#62DDB8'
ACCENT_DARK = '#357B78'
PURPLE = '#A9A0FF'
WARN = '#FFD082'
BORDER = '#2B3C54'
FONT = 'Segoe UI'

# Only reads status from Windows; no changes are made by these commands.
POWERSHELL = r'''
$ErrorActionPreference = 'Stop'
$result = [ordered]@{}
try {
  $result.antivirus = @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object -ExpandProperty displayName)
} catch {
  $result.antivirus = @()
  $result.antivirus_error = 'Could not read Windows antivirus registration.'
}
try {
  $result.firewall = @(Get-NetFirewallProfile -PolicyStore ActiveStore | Select-Object Name, Enabled)
} catch {
  $result.firewall = @()
  $result.firewall_error = 'Could not read Windows Firewall profiles.'
}
try {
  $mp = Get-MpComputerStatus
  $result.defender = [ordered]@{
    mode = [string]$mp.AMRunningMode
    antivirus_enabled = [bool]$mp.AntivirusEnabled
    realtime_enabled = [bool]$mp.RealTimeProtectionEnabled
  }
} catch {
  $result.defender_error = 'Microsoft Defender status was unavailable.'
}
ConvertTo-Json -InputObject $result -Depth 5 -Compress
'''

# We deliberately check active Defender mode immediately before the user-requested
# scan, because another installed antivirus may leave Defender in passive mode.
DEFENDER_SCAN_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
try {
  $mp = Get-MpComputerStatus -ErrorAction Stop
  if ($mp.AMRunningMode -ne 'Normal' -or !$mp.AntivirusEnabled -or !$mp.RealTimeProtectionEnabled) {
    Write-Output 'DEFENDER_NOT_ACTIVE'
    exit 3
  }
  if (![System.IO.File]::Exists($env:SOVELA_SCAN_PATH)) {
    Write-Output 'FILE_NOT_FOUND'
    exit 4
  }
  Start-MpScan -ScanType CustomScan -ScanPath $env:SOVELA_SCAN_PATH -ErrorAction Stop
  Write-Output 'SCAN_COMMAND_FINISHED'
} catch {
  Write-Output 'SCAN_FAILED'
  exit 5
}
'''


def powershell_run(script, *, timeout=35, env=None):
    if os.name != 'nt':
        raise RuntimeError('Sovela works on Windows 10 or 11 only.')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return subprocess.run(
        ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, text=True, timeout=timeout, creationflags=flags,
        encoding='utf-8', errors='replace', env=env,
    )


def powershell_check():
    result = powershell_run(POWERSHELL)
    if result.returncode != 0:
        raise RuntimeError('Windows could not provide security details. Open Windows Security to check directly.')
    try:
        data = json.loads(result.stdout.lstrip('\ufeff').strip())
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        return data
    except (ValueError, TypeError) as error:
        raise RuntimeError('Windows returned security details Sovela could not understand.') from error


def defender_is_active(data):
    mp = data.get('defender') if isinstance(data, dict) else None
    return (isinstance(mp, dict) and str(mp.get('mode', '')).lower() == 'normal'
            and mp.get('antivirus_enabled') is True
            and mp.get('realtime_enabled') is True)


def request_defender_scan(file_path):
    env = os.environ.copy()
    # File path goes in an environment variable, not into executable PS code.
    env['SOVELA_SCAN_PATH'] = str(file_path)
    try:
        result = powershell_run(DEFENDER_SCAN_SCRIPT, timeout=240, env=env)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Defender did not finish within four minutes. Review its status in Windows Security.') from error
    if result.returncode == 3 or 'DEFENDER_NOT_ACTIVE' in result.stdout:
        raise RuntimeError('Microsoft Defender is not the active antivirus. Use your currently active antivirus to scan this file instead.')
    if result.returncode == 4:
        raise RuntimeError('That file has moved or was deleted. Choose it again.')
    if result.returncode != 0 or 'SCAN_COMMAND_FINISHED' not in result.stdout:
        raise RuntimeError('Windows did not confirm the scan command. Open Windows Security to review scan results.')
    return 'Defender completed the scan command. Check Windows Security > Protection history for findings. Sovela cannot declare this file safe.'


def inspect_file(file_path):
    """Local file metadata and streaming SHA-256; no malware verdict."""
    path = Path(file_path)
    if not path.is_file():
        raise RuntimeError('That file no longer exists. Choose it again.')
    length = path.stat().st_size
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    executable = {'.exe', '.msi', '.bat', '.cmd', '.ps1', '.vbs', '.vbe',
                  '.js', '.jse', '.scr', '.com', '.pif', '.hta', '.lnk', '.jar'}
    caution = {'.zip', '.rar', '.7z', '.iso', '.docm', '.xlsm', '.pptm', '.html', '.htm'}
    suffix = path.suffix.lower()
    suffixes = [s.lower() for s in path.suffixes]
    double_ext = (len(suffixes) >= 2 and suffix in executable
                  and suffixes[-2] in {'.pdf', '.jpg', '.jpeg', '.png', '.txt', '.docx', '.xlsx'})
    if double_ext:
        note = 'Warning: the filename disguises an executable/script behind a document or image-looking extension. Do not open it unless you know its source.'
    elif suffix in executable:
        note = 'Caution: this type of file can run code. Only open it if you trust its source and it has been checked by your active antivirus.'
    elif suffix in caution:
        note = 'Caution: archives, macro documents, and web files may contain risky content. Use your active antivirus before opening unknown downloads.'
    else:
        note = 'No risky extension pattern was flagged. This does NOT mean the file is safe or malware-free.'
    return {
        'name': path.name,
        'size': length,
        'extension': suffix or '(none)',
        'sha256': digest.hexdigest(),
        'note': note,
    }


def computer_health():
    if os.name != 'nt':
        raise RuntimeError('The PC Health check runs on Windows only.')
    drive = os.environ.get('SystemDrive', 'C:') + '\\'
    disk = shutil.disk_usage(drive)

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]

    memory = MemoryStatus()
    memory.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise RuntimeError('Windows could not provide memory information.')

    startup_count = 0
    startup_complete = True
    try:
        import winreg
        subkey = r'Software\Microsoft\Windows\CurrentVersion\Run'
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    startup_count += winreg.QueryInfoKey(key)[1]
            except FileNotFoundError:
                pass
            except OSError:
                startup_complete = False
    except ImportError:
        startup_complete = False
    for folder in (
        os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'),
        os.path.join(os.environ.get('ProgramData', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'),
    ):
        try:
            if os.path.isdir(folder):
                startup_count += sum(1 for item in os.scandir(folder) if item.is_file())
        except OSError:
            startup_complete = False
    return {
        'disk_total': disk.total, 'disk_free': disk.free,
        'ram_total': memory.ullTotalPhys, 'ram_free': memory.ullAvailPhys,
        'startup_count': startup_count, 'startup_complete': startup_complete,
    }



def enumerate_startup_items():
    """Read-only inventory of common startup locations (not a malware scan)."""
    if os.name != 'nt':
        raise RuntimeError('Startup Explorer only works on Windows.')
    import winreg
    items, notes = [], []
    key_name = r'Software\Microsoft\Windows\CurrentVersion\Run'
    for hive, label in ((winreg.HKEY_CURRENT_USER, 'Current user'),
                        (winreg.HKEY_LOCAL_MACHINE, 'All users')):
        try:
            with winreg.OpenKey(hive, key_name) as key:
                count = winreg.QueryInfoKey(key)[1]
                for index in range(min(count, 150)):
                    try:
                        name, command, _kind = winreg.EnumValue(key, index)
                        items.append({'name': str(name), 'source': label + ' registry',
                                      'detail': str(command)})
                    except OSError:
                        notes.append('Some registry entries could not be read.')
                if count > 150:
                    notes.append('A registry location had more entries than the display limit.')
        except FileNotFoundError:
            pass
        except OSError:
            notes.append('Could not read some registry startup entries.')
    for root_env, label, postfix in (
        ('APPDATA', 'Current user', ('Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')),
        ('ProgramData', 'All users', ('Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')),
    ):
        base = os.environ.get(root_env)
        if not base:
            notes.append('A startup folder location is unavailable.')
            continue
        folder = Path(base).joinpath(*postfix)
        try:
            if folder.is_dir():
                for child in folder.iterdir():
                    if child.is_file():
                        items.append({'name': child.name, 'source': label + ' startup folder',
                                      'detail': str(child)})
        except OSError:
            notes.append('Could not read a startup folder.')
    items.sort(key=lambda item: (item['name'].casefold(), item['source']))
    return {'items': items[:100], 'total': len(items),
            'notes': sorted(set(notes + (['Only the first 100 entries are displayed.'] if len(items)>100 else [])))}


def explain_question(question, security=None):
    """Compatibility helper; uses the same neutral topic catalogue as chat."""
    return advanced_offline_reply(question, security)


def gb(number):
    return f'{number / (1024 ** 3):.1f} GB'


def open_windows_security():
    try:
        if os.name != 'nt':
            raise OSError('Windows required')
        os.startfile('windowsdefender:')
    except OSError:
        messagebox.showinfo('Windows Security', 'Press the Windows key, search for "Windows Security", and open that app.')



def clamp_to_area(x, y, width, height, area):
    """Keep the entire window inside the rectangle (left, top, right, bottom)."""
    left, top, right, bottom = area
    return (min(max(int(x), left), max(left, right - width)),
            min(max(int(y), top), max(top, bottom - height)))


def windows_work_area(point_x=None, point_y=None):
    """Usable area of the nearest monitor, excluding its taskbar if possible.

    A fallback is provided for non-Windows/simulated displays, so developing
    and testing the interface never changes Windows security settings.
    """
    if os.name == 'nt':
        try:
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD),
                            ('rcMonitor', wintypes.RECT),
                            ('rcWork', wintypes.RECT),
                            ('dwFlags', wintypes.DWORD)]

            user32 = ctypes.windll.user32
            get_monitor = user32.MonitorFromPoint
            get_monitor.argtypes = [wintypes.POINT, wintypes.DWORD]
            get_monitor.restype = wintypes.HMONITOR if hasattr(wintypes, 'HMONITOR') else ctypes.c_void_p
            get_info = user32.GetMonitorInfoW
            get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
            get_info.restype = wintypes.BOOL
            if point_x is None or point_y is None:
                pos = wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(pos)):
                    raise OSError('Cannot locate pointer')
            else:
                pos = wintypes.POINT(int(point_x), int(point_y))
            monitor = get_monitor(pos, 2)  # MONITOR_DEFAULTTONEAREST
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(info)
            if monitor and get_info(monitor, ctypes.byref(info)):
                r = info.rcWork
                if r.right > r.left and r.bottom > r.top:
                    return (r.left, r.top, r.right, r.bottom)
        except (AttributeError, OSError, ValueError, TypeError):
            pass
    return None




# ── Sovela 0.7 / Slate edition ─────────────────────────────────────
# Design: a calm desktop utility, not an alarm dashboard.
# The app does not replace an antivirus or submit system information.
# Selected cleanup moves supported old files into the Windows Recycle Bin. All optional cloud chat is opt-in.

SLATE_BG = '#F3F5F4'
SLATE_SIDE = '#E9EEEC'
SLATE_CARD = '#FFFFFF'
SLATE_TEXT = '#20332E'
SLATE_MUTED = '#6D817A'
SLATE_LINE = '#DCE5E0'
SLATE_GREEN = '#326C60'
SLATE_GREEN_SOFT = '#E4F1EC'
SLATE_ORANGE = '#9A6D30'
SLATE_ORANGE_SOFT = '#FAF3E5'
SLATE_INK_SOFT = '#526962'
SLATE_INPUT = '#F6F8F7'
SLATE_FONT = 'Segoe UI'


def assistant_offline(question, security=None):
    """Compatibility helper; no antivirus brand preference."""
    return advanced_offline_reply(question, security)


class SovelaCloudUnavailable(RuntimeError):
    """Hosted AI temporarily unreachable or at its allowed usage limit."""


def load_cloud_endpoint():
    """Creator configures this ONCE before release; customers never enter a key.

    The empty starter value is intentional: no hosted server has been deployed.
    """
    home=(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent)
    path=home / 'sovela_config.json'
    try:
        config=json.loads(path.read_text(encoding='utf-8'))
        url=config.get('assistant_url','').strip().rstrip('/')
        if not url:
            return ''
        if not url.startswith('https://') and not url.startswith('http://127.0.0.1:'):
            return ''
        return url
    except (OSError,ValueError,TypeError,AttributeError):
        return ''


def ask_sovela_cloud(endpoint, messages):
    """Requests go to a creator-owned backend; no secret is shipped to clients.

    Does not attach files, file hashes, security reports or machine identifiers.
    User-written chat and earlier chat replies are sent ONLY when configured.
    """
    if not endpoint:
        raise SovelaCloudUnavailable('Cloud AI is not configured.')
    history=[{'role':'user' if r=='you' else 'assistant','content':t[:2200]}
             for r,t in messages[-8:] if r in ('you','sovela')]
    payload=json.dumps({'messages':history}).encode('utf-8')
    req=urllib.request.Request(endpoint+'/chat',data=payload,method='POST',headers={
        'Content-Type':'application/json','Accept':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=24) as response:
            data=json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (429,503):
            raise SovelaCloudUnavailable('Cloud AI has reached its usage limit.') from None
        raise SovelaCloudUnavailable('Cloud AI could not answer at the moment.') from None
    except (urllib.error.URLError,TimeoutError,OSError,ValueError):
        raise SovelaCloudUnavailable('Cloud AI is offline or unreachable.') from None
    reply=data.get('reply','') if isinstance(data,dict) else ''
    if not isinstance(reply,str) or not reply.strip():
        raise SovelaCloudUnavailable('Cloud AI returned no answer.')
    return reply.strip()[:4500]


class CalmScrollbar(tk.Canvas):
    """A slim, quiet custom scrollbar with click and drag support."""
    def __init__(self, parent, command, background=SLATE_BG):
        super().__init__(parent, bg=background, bd=0, highlightthickness=0,
                         width=16, cursor='hand2')
        self.command = command
        self.first, self.last = 0., 1.
        self.pressed_at = None
        self.start = 0.
        self.bind('<Configure>', lambda _e: self.paint())
        self.bind('<Button-1>', self.press)
        self.bind('<B1-Motion>', self.motion)
        self.bind('<ButtonRelease-1>', self.release)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.paint()

    def measure(self):
        h = max(1, self.winfo_height()-24)
        extent = max(42, round(h * (self.last-self.first)))
        extent = min(extent, h)
        track_range = max(0, h-extent)
        pos = round(track_range * self.first / max(0.00001, 1. - (self.last-self.first)))
        return 12+pos, extent, track_range

    def paint(self):
        self.delete('all')
        if self.winfo_height() < 25:
            return
        self.create_line(8, 12, 8, self.winfo_height()-12, fill=SLATE_LINE,
                         width=4, capstyle='round')
        if self.last - self.first >= .999:
            return
        y, span, _r = self.measure()
        self.create_line(8, y, 8, y+span, fill='#A5BAB1', width=5, capstyle='round')

    def press(self, event):
        if self.last-self.first >= .999:
            return
        y, span, _range = self.measure()
        if not y <= event.y <= y+span:
            goal = (event.y-12-span/2) / max(1, self.winfo_height()-24-span)
            self.command('moveto', max(0., min(1., goal)))
        self.pressed_at, self.start = event.y, self.first

    def motion(self, event):
        if self.pressed_at is None:
            return
        _y, _span, travel = self.measure()
        if travel:
            self.command('moveto', max(0., min(1., self.start + (event.y-self.pressed_at) / travel * (1-(self.last-self.first)))))

    def release(self, _event):
        self.pressed_at = None


class SovelaApp:
    WIDTH, HEIGHT = 940, 674
    MENU = ('Overview', 'Protection', 'Downloads', 'PC Health', 'Cleaner', 'Startup', 'Assistant', 'Activity', 'Tools')

    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.last_data = None
        self.last_health = None
        self.last_file = None
        self.selected_file = None
        self.startups = None
        self.checking = False
        self.working_file = False
        self.working_health = False
        self.working_startups = False
        self.care_busy = False
        self.clean_preview = None
        self.clean_notice = ''
        self.clean_choices = {cat:tk.BooleanVar(value=False) for cat,_,_,_ in CATEGORIES}
        self.startup_busy = False
        self.startup_notice = ''
        self.scanning = False
        self.scan_message = 'No scan requested.'
        self.report_notice = ''
        self.status = 'Not checked'
        self.security_details = {k:'Not checked yet' for k in ('antivirus', 'defender', 'firewall')}
        self.activity = []
        self.messages = [('sovela', 'Hello! I’m Sovela. Ask me about Windows, security alerts, privacy, suspicious links, startup programs or PC performance. No setup needed.\n\nWhen Sovela’s online AI service is connected, I can have open conversations. Otherwise I’ll clearly provide guided offline help.')]
        self.cloud_endpoint=load_cloud_endpoint()
        self.cloud_available=bool(self.cloud_endpoint)
        self.cloud_limit_notice=False
        self.chat_waiting = False
        self.pinned = False
        self._restoring_from_minimize = False
        self._minimize_phase = None
        self._position_check_id = None
        self.nav_buttons = {}
        self.current_tab = ''
        self.composer = None
        self.thread_view = None

        root.title('Sovela · Slate edition 1.3')
        root.configure(bg=SLATE_LINE)
        # Keep the normal Windows-managed app window. Override-redirect causes
        # Windows to treat Sovela as a floating tool instead of a taskbar app.
        root.overrideredirect(False)
        root.resizable(False, False)
        from sovela_window import schedule_chrome
        schedule_chrome(root)
        self.center_window()
        root.bind('<Control-w>', lambda _e: root.destroy())
        root.bind('<Control-m>', lambda _e: self.minimize_window())
        root.bind('<Control-p>', lambda _e: self.toggle_pin())
        root.bind('<Map>', self.on_map)
        root.bind('<Configure>', self.schedule_position_check)
        root.bind_all('<MouseWheel>', self.on_global_wheel)
        # Do not leave credentials behind after app closes.
        root.protocol('WM_DELETE_WINDOW', self.close)

        self.frame = tk.Frame(root, bg=SLATE_BG, highlightthickness=1,
                              highlightbackground=SLATE_LINE)
        self.frame.pack(fill='both', expand=True)
        self.draw_titlebar()
        main = tk.Frame(self.frame, bg=SLATE_BG)
        main.pack(fill='both', expand=True)
        self.sidebar = tk.Frame(main, bg=SLATE_SIDE, width=200)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        self.make_nav()
        self.content = tk.Frame(main, bg=SLATE_BG)
        self.content.pack(side='left', fill='both', expand=True)
        self.body = tk.Frame(self.content, bg=SLATE_BG)
        self.body.pack(fill='both', expand=True)
        bottom = tk.Frame(self.content, bg=SLATE_BG, height=38)
        bottom.pack(fill='x', side='bottom')
        bottom.pack_propagate(False)
        tk.Label(bottom, text='Quiet security & PC care   •   Nothing cleans without your permission   •   v1.3',
                 bg=SLATE_BG, fg=SLATE_MUTED, font=(SLATE_FONT, 9)).pack(side='left', padx=27)
        self.show_tab('Overview')
        root.after(110, self.poll_events)
        # Read-only status check at startup; no scans or changes to security settings.
        if os.name == 'nt':
            root.after(650, self.check)

    def close(self):
        self.root.destroy()

    def work_area(self, x=None, y=None):
        return windows_work_area(x, y) or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def center_window(self):
        self.root.update_idletasks()
        left, top, right, bottom = self.work_area()
        w = min(self.WIDTH, max(300, right-left-12))
        h = min(self.HEIGHT, max(300, bottom-top-12))
        x,y = clamp_to_area(left+(right-left-w)//2, top+(bottom-top-h)//2,w,h,(left,top,right,bottom))
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    def schedule_position_check(self, event):
        if event.widget != self.root or self._restoring_from_minimize:
            return
        if self._position_check_id is not None:
            self.root.after_cancel(self._position_check_id)
        self._position_check_id = self.root.after(160, self.ensure_visible)

    def ensure_visible(self):
        self._position_check_id = None
        if self.root.state() != 'normal':
            return
        x,y,w,h = self.root.winfo_x(),self.root.winfo_y(),self.root.winfo_width(),self.root.winfo_height()
        area = self.work_area(x+w//2,y+22)
        nx,ny = clamp_to_area(x,y,w,h,area)
        if (nx,ny)!=(x,y):
            self.root.geometry(f'+{nx}+{ny}')

    def start_drag(self, event):
        self.drag_dx = event.x_root-self.root.winfo_x()
        self.drag_dy = event.y_root-self.root.winfo_y()

    def drag(self, event):
        x,y=event.x_root-self.drag_dx,event.y_root-self.drag_dy
        x,y=clamp_to_area(x,y,self.root.winfo_width(),self.root.winfo_height(),self.work_area(event.x_root,event.y_root))
        self.root.geometry(f'+{x}+{y}')

    def minimize_window(self):
        """Use native minimise, preserving Sovela's Windows taskbar presence."""
        try:
            self.root.iconify()
        except tk.TclError:
            pass

    def on_map(self, event):
        """Tk handles restoring the normal application window."""
        if event.widget is self.root:
            self._restoring_from_minimize = False
            self._minimize_phase = None

    def restore_after_minimize(self):
        """Open the main app from an in-app scan notification."""
        try:
            if self.root.state() == 'iconic':
                self.root.deiconify()
            self.root.lift()
            self.root.attributes('-topmost', self.pinned)
            self.ensure_visible()
        except tk.TclError:
            pass

    def toggle_pin(self):
        self.pinned=not self.pinned
        self.root.attributes('-topmost',self.pinned)
        self.pin_button.configure(text='Pinned  ●' if self.pinned else 'Pin  ○',
                                  fg=SLATE_GREEN if self.pinned else SLATE_MUTED)

    def draw_titlebar(self):
        bar=tk.Frame(self.frame,bg=SLATE_CARD,height=67)
        bar.pack(fill='x')
        bar.pack_propagate(False)
        try:
            # App icon is shipped locally; no external image dependency or network call.
            icon_path = Path(__file__).resolve().with_name('sovela.png')
            brand_icon = tk.PhotoImage(file=str(icon_path)).subsample(8, 8)
            self._sovela_header_icon = brand_icon  # Tk images need a strong reference.
            logo = tk.Label(bar, image=brand_icon, bg=SLATE_CARD, bd=0)
        except (OSError, tk.TclError):
            logo = tk.Canvas(bar, width=35, height=35, bg=SLATE_CARD, highlightthickness=0)
            logo.create_oval(2,2,32,32,fill=SLATE_GREEN_SOFT,outline='')
            logo.create_text(17,17,text='S',fill=SLATE_GREEN,font=(SLATE_FONT,16,'bold'))
        logo.pack(side='left',padx=(19,9),pady=15)
        name=tk.Label(bar,text='sovela',bg=SLATE_CARD,fg=SLATE_TEXT,font=(SLATE_FONT,17,'bold'))
        name.pack(side='left')
        subtitle=tk.Label(bar,text=' /  pc care',bg=SLATE_CARD,fg=SLATE_MUTED,font=(SLATE_FONT,10))
        subtitle.pack(side='left',padx=(4,0),pady=(4,0))
        # Custom window controls; the underlying window stays Windows-managed,
        # so it still appears on the taskbar and restores from minimised state.
        close = self.text_button(bar,'×',self.close,size=18,bg=SLATE_CARD,
                                 fg=SLATE_MUTED,width=3)
        close.pack(side='right',padx=(0,10),pady=8)
        minimize = self.text_button(bar,'—',self.minimize_window,size=13,
                                    bg=SLATE_CARD,fg=SLATE_MUTED,width=3)
        minimize.pack(side='right')
        self.pin_button=self.text_button(bar,'Pin  ○',self.toggle_pin,size=10,bg=SLATE_CARD,fg=SLATE_MUTED)
        self.pin_button.pack(side='right',padx=(3,13))
        for w in (bar,logo,name,subtitle):
            w.configure(cursor='fleur')
            w.bind('<ButtonPress-1>',self.start_drag)
            w.bind('<B1-Motion>',self.drag)
        tk.Frame(self.frame,height=1,bg=SLATE_LINE).pack(fill='x')

    def text_button(self,parent,text,command,size=10,bg=SLATE_CARD,fg=SLATE_GREEN,width=None):
        return tk.Button(parent,text=text,command=command,bg=bg,fg=fg,
                         activebackground=SLATE_GREEN_SOFT,activeforeground=SLATE_GREEN,
                         font=(SLATE_FONT,size,'bold'),bd=0,relief='flat',highlightthickness=0,
                         cursor='hand2',padx=12,pady=7,width=width)

    def make_nav(self):
        tk.Label(self.sidebar,text='WORKSPACE',bg=SLATE_SIDE,fg=SLATE_MUTED,
                 font=(SLATE_FONT,9,'bold')).pack(anchor='w',padx=24,pady=(30,17))
        for name,glyph in [('Overview','⌂'),('Protection','◇'),('Downloads','↓'),
                           ('PC Health','◌'),('Cleaner','✧'),('Startup','≡'),('Assistant','☼'),
                           ('Activity','◷'),('Tools','⚙')]:
            row=tk.Frame(self.sidebar,bg=SLATE_SIDE)
            row.pack(fill='x',padx=11,pady=2)
            b=self.text_button(row,f'{glyph}    {name}',lambda x=name:self.show_tab(x),
                               bg=SLATE_SIDE,fg=SLATE_MUTED,size=11)
            b.configure(anchor='w',padx=16,pady=8)
            b.pack(fill='x')
            self.nav_buttons[name]=b
        tk.Frame(self.sidebar,bg=SLATE_SIDE).pack(fill='both',expand=True)
        note=tk.Frame(self.sidebar,bg='#DDE8E2',padx=14,pady=14)
        note.pack(fill='x',padx=13,pady=(0,17))
        tk.Label(note,text='●  QUIET BY DESIGN',bg='#DDE8E2',fg=SLATE_GREEN,
                 font=(SLATE_FONT,9,'bold'),anchor='w').pack(fill='x')
        tk.Label(note,text='No adverts or scare tactics.\nYou stay in control.',
                 bg='#DDE8E2',fg=SLATE_INK_SOFT,justify='left',
                 font=(SLATE_FONT,9)).pack(fill='x',anchor='w',pady=(8,0))

    def reset_body(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.composer=None
        self.thread_view=None

    def show_tab(self,tab):
        self.current_tab=tab
        for name,btn in self.nav_buttons.items():
            btn.configure(bg=SLATE_CARD if tab==name else SLATE_SIDE,
                          fg=SLATE_GREEN if tab==name else SLATE_MUTED)
        self.reset_body()
        if tab=='Assistant':
            self.assistant_page()
            return
        # Standard scrollable pages with a softly styled custom track.
        wrap=tk.Frame(self.body,bg=SLATE_BG)
        wrap.pack(fill='both',expand=True)
        canvas=tk.Canvas(wrap,bg=SLATE_BG,bd=0,highlightthickness=0)
        bar=CalmScrollbar(wrap,canvas.yview,SLATE_BG)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y',padx=(0,8))
        canvas.pack(side='left',fill='both',expand=True)
        view=tk.Frame(canvas,bg=SLATE_BG,padx=27,pady=24)
        window=canvas.create_window(0,0,window=view,anchor='nw')
        view.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        def wheel(event):
            canvas.yview_scroll(-int(event.delta/120) if event.delta else 0,'units')
        self._wheel_target=canvas
        self._wheel_handler=wheel
        self.view=view
        getattr(self,{'Overview':'overview_page','Protection':'protection_page',
                      'Downloads':'downloads_page','PC Health':'health_page','Cleaner':'cleaner_page','Startup':'startup_page',
                      'Activity':'activity_page','Tools':'tools_page'}[tab])()

    def on_global_wheel(self,event):
        if self.current_tab=='Assistant':
            if self.thread_view and self.thread_view.winfo_exists():
                self.thread_view.yview_scroll(-int(event.delta/120) if event.delta else 0,'units')
        elif hasattr(self,'_wheel_handler'):
            self._wheel_handler(event)

    def title(self,heading,sub):
        tk.Label(self.view,text=heading,bg=SLATE_BG,fg=SLATE_TEXT,
                 font=(SLATE_FONT,22,'bold'),anchor='w').pack(fill='x')
        tk.Label(self.view,text=sub,bg=SLATE_BG,fg=SLATE_MUTED,font=(SLATE_FONT,10),
                 anchor='w').pack(fill='x',pady=(6,23))

    def label(self,parent,text,*,size=10,fg=SLATE_TEXT,bold=False,wrap=None,pady=(0,0)):
        lbl=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=fg,
                     font=(SLATE_FONT,size,'bold' if bold else 'normal'),
                     anchor='w',justify='left',wraplength=wrap or 480)
        lbl.pack(fill='x',anchor='w',pady=pady)
        return lbl

    def card(self,pad=19):
        border=tk.Frame(self.view,bg=SLATE_LINE,padx=1,pady=1)
        border.pack(fill='x',pady=(0,14))
        inner=tk.Frame(border,bg=SLATE_CARD,padx=pad,pady=pad)
        inner.pack(fill='both',expand=True)
        return inner

    def action(self,parent,text,fn,primary=False,side=None):
        b=tk.Button(parent,text=text,command=fn,
                    bg=SLATE_GREEN if primary else SLATE_GREEN_SOFT,
                    fg='#FFFFFF' if primary else SLATE_GREEN,
                    activebackground='#28584E' if primary else '#D7EBE3',
                    activeforeground='#FFFFFF' if primary else SLATE_GREEN,
                    font=(SLATE_FONT,10,'bold'),relief='flat',bd=0,highlightthickness=0,
                    padx=19,pady=11,cursor='hand2')
        if side:
            b.pack(side=side,padx=(0,9))
        else:
            b.pack(anchor='w',pady=(10,0))
        return b

    def tag(self,parent,text,soft=SLATE_GREEN_SOFT,ink=SLATE_GREEN):
        tk.Label(parent,text=text,bg=soft,fg=ink,font=(SLATE_FONT,9,'bold'),
                 padx=12,pady=6).pack(anchor='w')

    def info_row(self,parent,title,detail):
        row=tk.Frame(parent,bg=SLATE_CARD)
        row.pack(fill='x',pady=(12,0))
        tk.Label(row,text=title,bg=SLATE_CARD,fg=SLATE_INK_SOFT,
                 font=(SLATE_FONT,10,'bold'),anchor='w',width=14).pack(side='left')
        tk.Label(row,text=detail,bg=SLATE_CARD,fg=SLATE_TEXT,
                 font=(SLATE_FONT,10),wraplength=365,justify='left',anchor='w').pack(side='left',fill='x',expand=True)

    def overview_page(self):
        self.title('A calmer way to feel secure.', 'Everything important, without the noise.')
        c=self.card(23)
        self.tag(c,'SECURITY OVERVIEW')
        self.label(c,self.status,size=21,bold=True,pady=(17,9))
        self.label(c,'Sovela reads Windows security settings. It does not replace your antivirus.',
                   fg=SLATE_MUTED,pady=(0,13))
        bar=tk.Frame(c,bg=SLATE_CARD)
        bar.pack(fill='x')
        self.action(bar,'Run a security check',self.check,primary=True,side='left')
        self.action(bar,'Windows Security ↗',open_windows_security,side='left')
        c=self.card()
        self.label(c,'At a glance',size=13,bold=True,pady=(0,6))
        for title,field in [('Antivirus','antivirus'),('Microsoft Defender','defender'),('Windows Firewall','firewall')]:
            self.info_row(c,title,self.security_details[field])
        c=self.card()
        self.label(c,'Good to know',size=13,bold=True,pady=(0,7))
        self.label(c,'No alarming risk scores. No upgrade banners. No hidden scans. '
                   'You decide what to inspect and when.',fg=SLATE_MUTED)
        self.action(c,'Ask Sovela a question  →',lambda:self.show_tab('Assistant'))

    def protection_page(self):
        self.title('Protection','A clear look at what Windows is reporting.')
        for title,key in [('Registered antivirus','antivirus'),('Microsoft Defender','defender'),
                          ('Windows Firewall','firewall')]:
            c=self.card()
            self.label(c,title,size=11,bold=True,pady=(0,8))
            self.label(c,self.security_details[key],fg=SLATE_INK_SOFT)
        actions=tk.Frame(self.view,bg=SLATE_BG)
        actions.pack(fill='x',pady=(3,10))
        self.action(actions,'Refresh status',self.check,primary=True,side='left')
        self.action(actions,'Copy summary',self.copy_summary,side='left')
        if self.report_notice:
            self.label(self.view,self.report_notice,fg=SLATE_GREEN)
        self.label(self.view,'Registration information is not proof of active protection or a malware-free device.',
                   fg=SLATE_MUTED,pady=(9,0))

    def downloads_page(self):
        self.title('Downloads','Get useful details about a file, without opening it.')
        c=self.card()
        self.label(c,'Choose a file to inspect',size=13,bold=True)
        self.label(c,'Files are read locally. Sovela cannot declare files safe.',
                   fg=SLATE_MUTED,pady=(8,0))
        self.action(c,'Choose a file',self.choose_file,primary=True)
        if self.selected_file:
            self.label(c,'Selected: '+self.selected_file.name,fg=SLATE_INK_SOFT,pady=(12,0))
        if self.last_file:
            c=self.card()
            self.label(c,self.last_file['name'],size=13,bold=True,pady=(0,9))
            self.info_row(c,'Size',self.human_bytes(self.last_file['size']))
            self.info_row(c,'Extension',self.last_file['extension'])
            self.label(c,self.last_file['note'],fg=SLATE_ORANGE,pady=(15,11))
            self.label(c,'SHA-256 fingerprint:',fg=SLATE_MUTED,pady=(5,4))
            e=tk.Entry(c,relief='flat',bg=SLATE_INPUT,fg=SLATE_TEXT,readonlybackground=SLATE_INPUT,
                       font=('Consolas',9))
            e.insert(0,self.last_file['sha256'])
            e.configure(state='readonly')
            e.pack(fill='x',ipady=8)
        c=self.card()
        self.label(c,'Optional Defender scan',size=13,bold=True)
        self.label(c,'Only works when Microsoft Defender is the active antivirus. '
                   'If another antivirus is active, use its own scanning tools instead.',fg=SLATE_MUTED,pady=(7,0))
        b=self.action(c,'Request Defender scan',self.defender_scan)
        if not self.selected_file or self.scanning or self.working_file:
            b.configure(state='disabled')
        self.label(c,self.scan_message,fg=SLATE_MUTED,pady=(10,0))

    def health_page(self):
        self.title('PC Health','A quick, friendly picture of your computer.')
        controls=tk.Frame(self.view,bg=SLATE_BG)
        controls.pack(fill='x',pady=(0,16))
        self.action(controls,'Check PC health',self.health_check,primary=True,side='left')
        self.action(controls,'Open startup settings',lambda:self.open_settings('ms-settings:startupapps','Startup Apps'),side='left')
        if not self.last_health:
            c=self.card()
            self.label(c,'No health information yet',size=14,bold=True,pady=(0,6))
            self.label(c,'Click Check PC health to see storage, memory and common startup entries.',fg=SLATE_MUTED)
            return
        h=self.last_health
        disk=int(100*(h['disk_total']-h['disk_free'])/max(1,h['disk_total']))
        ram=int(100*(h['ram_total']-h['ram_free'])/max(1,h['ram_total']))
        for title,pct,caption in [('Storage used',disk,gb(h['disk_free'])+' free space'),
                                  ('Memory used',ram,gb(h['ram_total'])+' total memory')]:
            c=self.card()
            self.label(c,title,size=11,bold=True,pady=(0,5))
            self.label(c,f'{pct}%',size=19,bold=True,pady=(0,7))
            self.label(c,caption,fg=SLATE_MUTED,pady=(0,12))
            track=tk.Frame(c,bg=SLATE_LINE,height=7)
            track.pack(fill='x')
            track.pack_propagate(False)
            tk.Frame(track,bg=SLATE_GREEN if pct<90 else SLATE_ORANGE).place(relx=0,rely=0,relwidth=max(0,min(1,pct/100)),relheight=1)
        c=self.card()
        self.label(c,str(h['startup_count'])+' common startup entries',size=13,bold=True,pady=(0,4))
        self.label(c,'This count is approximate. Not all background software is included.',fg=SLATE_MUTED)
        self.action(c,'Preview safe cleanup  →',lambda:self.show_tab('Cleaner'))

    def cleaner_page(self):
        self.title('PC Cleaner','Six separate categories. Preview first, choose exactly what to clean.')
        head=self.card()
        self.label(head,'Clean without the drama',size=13,bold=True,pady=(0,7))
        self.label(head,'Nothing is selected by default. Eligible old cache and diagnostic files move to your Windows Recycle Bin; they may still occupy disk space until you empty it. Cookies and Recycle Bin use official controls.',fg=SLATE_MUTED,wrap=590)
        row=tk.Frame(head,bg=SLATE_CARD);row.pack(fill='x',pady=(12,0))
        scan_button=self.action(row,'Preview categories',self.preview_cleanup,primary=True,side='left')
        if self.care_busy: scan_button.configure(state='disabled')
        self.action(row,'Windows Storage settings ↗',lambda:self.open_settings('ms-settings:storagesense','Storage settings'),side='left')
        if self.clean_notice:
            self.label(self.view,self.clean_notice,fg=SLATE_INK_SOFT,wrap=590,pady=(0,12))
        for key,title,detail,mode in CATEGORIES:
            card=self.card(15)
            row=tk.Frame(card,bg=SLATE_CARD);row.pack(fill='x')
            cb=tk.Checkbutton(row,variable=self.clean_choices[key],text='  '+title,
                font=(SLATE_FONT,12,'bold'),bg=SLATE_CARD,fg=SLATE_TEXT,
                activebackground=SLATE_CARD,selectcolor=SLATE_GREEN_SOFT,
                activeforeground=SLATE_GREEN,highlightthickness=0,bd=0,cursor='hand2')
            cb.pack(side='left')
            if mode=='guided':
                self.tag(row,'MANUAL REVIEW',soft=SLATE_ORANGE_SOFT,ink=SLATE_ORANGE)
            elif self.clean_preview is not None:
                matched=self.clean_preview.get(key,{})
                count=len(matched.get('files',[])); bytes_found=matched.get('bytes',0)
                self.label(card, f'{count} eligible files   •   {self.human_bytes(bytes_found)}',size=10,bold=True,fg=SLATE_GREEN,pady=(8,0))
                if matched.get('limited'):
                    self.label(card,'Preview limited to the first 2,500 eligible files.',fg=SLATE_ORANGE)
            self.label(card,detail,fg=SLATE_MUTED,pady=(7,0),wrap=580)
        footer=self.card()
        self.label(footer,'Apply only what you selected',size=13,bold=True,pady=(0,8))
        self.label(footer,'Old files are rechecked before recycling; busy or changed files are skipped. No registry cleaning, Downloads folder deletion or unprompted changes.',fg=SLATE_MUTED,wrap=575)
        run=self.action(footer,'Clean selected categories',self.run_cleanup,primary=True)
        if self.care_busy or self.clean_preview is None:
            run.configure(state='disabled')
        if self.clean_preview is not None:
            self.label(footer,'To clean cookies or empty Recycle Bin, select the category and use the review buttons below; those actions are never performed automatically.',fg=SLATE_MUTED,pady=(10,0),wrap=575)
        review=tk.Frame(footer,bg=SLATE_CARD);review.pack(fill='x',pady=(6,0))
        self.action(review,'Review browser cookies ↗',self.browser_cookie_help,side='left')
        self.action(review,'Open Recycle Bin ↗',self.open_recycle,side='left')

    def preview_cleanup(self):
        if self.care_busy:
            return
        self.care_busy=True
        self.clean_notice='Looking only in supported personal cache and diagnostic folders…'
        self.show_tab('Cleaner')
        self.run_job('care_preview',scan_cleanup)

    def browser_cookie_help(self):
        messagebox.showinfo('Cookies & site data',
          'For your safety, Sovela never silently deletes browser sign-in cookies.\n\n'
          'Chrome: Settings → Privacy and security → Delete browsing data.\n'
          'Edge: Settings → Privacy, search and services → Clear browsing data.\n'
          'Firefox: Settings → Privacy & Security → Cookies and Site Data.\n\n'
          'Select only Cookies & site data. Clearing them can sign you out of websites.',parent=self.root)

    def open_recycle(self):
        try:
            os.startfile('shell:RecycleBinFolder')
        except (OSError,AttributeError):
            messagebox.showinfo('Recycle Bin','Open Recycle Bin from your desktop or File Explorer. Review its contents before emptying it.',parent=self.root)

    def run_cleanup(self):
        if self.care_busy or self.clean_preview is None:
            return
        selected=[k for k,value in self.clean_choices.items() if value.get()]
        if not selected:
            messagebox.showinfo('Nothing selected','Tick one or more categories first. Nothing was changed.',parent=self.root)
            return
        automatic=[k for k in selected if k not in ('cookies','recycle')]
        count=sum(len(self.clean_preview.get(k,{}).get('files',[])) for k in automatic)
        total=sum(self.clean_preview.get(k,{}).get('bytes',0) for k in automatic)
        if not automatic or count==0:
            messagebox.showinfo('Nothing to recycle',
              'No eligible files were found in your selected automatic categories. '
              'For Cookies or Recycle Bin, use the review buttons. Nothing was deleted.',parent=self.root)
            return
        selected_names=', '.join(next(n for key,n,_,_ in CATEGORIES if key==k) for k in automatic)
        if not messagebox.askyesno('Confirm chosen cleanup',
          f'ONLY these categories:\n{selected_names}\n\n'
          f'{count} eligible files • {self.human_bytes(total)}\n\n'
          'Sovela will attempt to move these old files to the Windows Recycle Bin, '
          'where you may restore them. Closing affected apps is recommended. '
          'Disk space may not be recovered until you empty the bin.\n\n'
          'Do you want to continue?',parent=self.root):
            return
        self.care_busy=True; self.clean_notice='Cleaning only selected categories…'
        self.show_tab('Cleaner')
        self.run_job('care_clean',lambda:clean_selected(self.clean_preview,automatic))

    def startup_page(self):
        self.title('Startup Manager','Review, disable and restore optional applications for your account.')
        self.label(self.view,'Only your personal Run entries and Startup folder items are editable. All-users and security-related entries are read-only. No services or scheduled tasks are changed.',fg=SLATE_MUTED,pady=(0,12),wrap=565)
        refresh=self.action(self.view,'Inspect startup programs',self.inspect_startups,primary=True)
        if self.working_startups or self.startup_busy: refresh.configure(state='disabled')
        if self.startup_notice:
            self.label(self.view,self.startup_notice,fg=SLATE_GREEN,pady=(12,5),wrap=565)
        if self.startups is None:
            c=self.card()
            self.label(c,'Not inspected yet',size=13,bold=True)
            self.label(c,'Press Inspect startup programs to view supported entries.',fg=SLATE_MUTED,pady=(8,0))
        else:
            c=self.card()
            self.label(c,f'{self.startups["total"]} entries listed',size=13,bold=True)
            for note in self.startups['notes']:
                self.label(c,note,fg=SLATE_ORANGE,pady=(6,0))
            for item in self.startups['items']:
                c=self.card(12)
                head=tk.Frame(c,bg=SLATE_CARD);head.pack(fill='x')
                self.label(head,str(item['name'])[:90],size=11,bold=True,wrap=400)
                self.label(c,item['source']+'  •  '+item['state'],fg=SLATE_GREEN,pady=(5,4),wrap=555)
                self.label(c,str(item['detail'])[:270],size=9,fg=SLATE_MUTED,wrap=555)
                if item.get('editable'):
                    if item['state']=='Enabled':
                        self.action(c,'Disable (reversible)',lambda i=item:self.change_startup(i,False))
                    else:
                        self.action(c,'Restore startup',lambda i=item:self.change_startup(i,True))
                else:
                    self.label(c,'Read-only: manage this through Windows or its own application.',fg=SLATE_MUTED,pady=(8,0))
        self.action(self.view,'Windows Startup settings ↗',lambda:self.open_settings('ms-settings:startupapps','Startup Apps'))

    def change_startup(self,item,restore):
        if self.startup_busy:
            return
        verb='restore' if restore else 'disable'
        if not messagebox.askyesno('Confirm startup change',
            f'Do you want to {verb} “{item["name"]}” for your Windows account?\n\n'
            'Sovela will save a recovery record. This does not stop running programs, services or security tools.',parent=self.root):
            return
        self.startup_busy=True
        self.startup_notice='Applying your chosen startup change…'
        self.show_tab('Startup')
        self.run_job('startup_change',lambda:(restore_startup(item) if restore else disable_startup(item)))

    def activity_page(self):
        self.title('Activity','Only what you’ve chosen to do in this session.')
        c=self.card()
        self.tag(c,'LOCAL & TEMPORARY')
        self.label(c,'This history disappears when you close Sovela.',fg=SLATE_MUTED,pady=(12,2))
        if not self.activity:
            self.label(c,'Nothing to show yet. Your activity will appear here as you use the tools.',pady=(15,0))
        for item in reversed(self.activity[-25:]):
            self.label(c,item,size=10,pady=(10,0))
        self.action(c,'Clear history',self.clear_activity)

    def tools_page(self):
        self.title('Tools','Trusted Windows shortcuts. Nothing extra to install.')
        for heading,body,link,fn in [
            ('Windows Security','Your antivirus, virus and threat protection, and firewall overview.',
             'Open Windows Security  ↗',open_windows_security),
            ('Windows Update','Check security patches and pending restarts in official Windows settings.',
             'Open Windows Update  ↗',lambda:self.open_settings('ms-settings:windowsupdate','Windows Update')),
            ('Startup Apps','Review Windows startup entries and boot behaviour.',
             'Open Startup Apps  ↗',lambda:self.open_settings('ms-settings:startupapps','Startup Apps')),
            ('Windows Storage','Use Storage Sense for system files, thumbnails and cleanup recommendations.',
             'Open Storage settings  ↗',lambda:self.open_settings('ms-settings:storagesense','Storage settings')),
        ]:
            c=self.card()
            self.label(c,heading,size=12,bold=True)
            self.label(c,body,fg=SLATE_MUTED,pady=(6,0))
            self.action(c,link,fn)

    def assistant_page(self):
        """One assistant. No model switcher, API key or configuration for customers."""
        shell=tk.Frame(self.body,bg=SLATE_BG,padx=26,pady=18)
        shell.pack(fill='both',expand=True)
        header=tk.Frame(shell,bg=SLATE_BG)
        header.pack(fill='x')
        tk.Label(header,text='Ask Sovela',bg=SLATE_BG,fg=SLATE_TEXT,
                 font=(SLATE_FONT,21,'bold')).pack(side='left')
        label='●  Online AI' if self.cloud_available else '○  Guided help'
        status_color=SLATE_GREEN if self.cloud_available else SLATE_MUTED
        tk.Label(header,text=label,bg=SLATE_GREEN_SOFT if self.cloud_available else SLATE_SIDE,
                 fg=status_color,font=(SLATE_FONT,10,'bold'),padx=11,pady=8).pack(side='right')
        description=('Your typed chats go to the hosted AI provider. Never share passwords or codes.'
                     if self.cloud_available else
                     'Built-in security guidance is available. Online AI is not connected by the developer yet.')
        tk.Label(shell,text=description,bg=SLATE_BG,fg=SLATE_MUTED,
                 font=(SLATE_FONT,9),anchor='w').pack(fill='x',pady=(4,11))
        chat_shell=tk.Frame(shell,bg=SLATE_CARD,highlightbackground=SLATE_LINE,highlightthickness=1)
        chat_canvas=tk.Canvas(chat_shell,bg=SLATE_CARD,highlightthickness=0,bd=0)
        scroll=CalmScrollbar(chat_shell,chat_canvas.yview,SLATE_CARD)
        scroll.pack(side='right',fill='y')
        chat_canvas.pack(side='left',fill='both',expand=True)
        self.thread_view=chat_canvas
        self.messages_frame=tk.Frame(chat_canvas,bg=SLATE_CARD,padx=15,pady=13)
        chat_window=chat_canvas.create_window(0,0,window=self.messages_frame,anchor='nw')
        self.messages_frame.bind('<Configure>',lambda _e:chat_canvas.configure(scrollregion=chat_canvas.bbox('all')))
        chat_canvas.bind('<Configure>',lambda e:chat_canvas.itemconfigure(chat_window,width=e.width))
        for role,content in self.messages:
            self.draw_bubble(role,content)
        if self.chat_waiting:
            self.draw_bubble('sovela','Thinking…')
        compose=tk.Frame(shell,bg=SLATE_CARD,highlightbackground=SLATE_LINE,highlightthickness=1,padx=9,pady=8)
        compose.pack(side='bottom',fill='x')
        self.composer=tk.Entry(compose,bg=SLATE_CARD,fg=SLATE_TEXT,insertbackground=SLATE_GREEN,
                               relief='flat',bd=0,font=(SLATE_FONT,11))
        self.composer.pack(side='left',fill='x',expand=True,ipady=8,padx=(6,3))
        self.composer.bind('<Return>',lambda _e:(self.send_from_entry(), 'break')[1])
        send=self.text_button(compose,'Send  ↗',self.send_from_entry,size=10,bg=SLATE_GREEN,fg='#FFFFFF')
        send.configure(activebackground='#28584E',activeforeground='#FFFFFF')
        send.pack(side='right')
        actions=tk.Frame(shell,bg=SLATE_BG)
        for title,q in [('Check my protection','Review my protection and PC health'),
                        ('Why is my PC slow?','My computer is running slowly'),
                        ('Suspicious email','I received a suspicious email')]:
            self.text_button(actions,title,lambda question=q:self.ask(question),size=9,
                bg=SLATE_GREEN_SOFT,fg=SLATE_GREEN).pack(side='left',padx=(0,7))
        actions.pack(side='bottom',fill='x',pady=(8,8))
        chat_shell.pack(fill='both',expand=True)
        self.composer.focus_set()
        self.root.after_idle(self.scroll_chat_to_bottom)
        self.root.after(80,self.scroll_chat_to_bottom)
        self.root.after(180,self.scroll_chat_to_bottom)

    def scroll_chat_to_bottom(self):
        canvas = self.thread_view
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists() or not self.messages_frame.winfo_exists():
                return
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox('all'))
            canvas.yview_moveto(1.0)
        except tk.TclError:
            pass

    def draw_bubble(self,role,message):
        mine=role=='you'
        container=tk.Frame(self.messages_frame,bg=SLATE_CARD)
        container.pack(fill='x',pady=8)
        align='e' if mine else 'w'
        lbl=tk.Label(container,text='YOU' if mine else 'SOVELA',fg=SLATE_MUTED,bg=SLATE_CARD,
                     font=(SLATE_FONT,8,'bold'))
        lbl.pack(anchor=align,pady=(0,4))
        cell=tk.Frame(container,bg=SLATE_GREEN_SOFT if mine else SLATE_INPUT,padx=13,pady=11)
        cell.pack(anchor=align)
        tk.Label(cell,text=message,bg=cell.cget('bg'),fg=SLATE_TEXT,
                 justify='left',font=(SLATE_FONT,10),wraplength=385).pack()

    def send_from_entry(self):
        if self.composer is None:
            return
        text=self.composer.get().strip()
        self.ask(text)

    def ask(self,text):
        text=text.strip()
        if not text or self.chat_waiting:
            return
        if len(text)>3000:
            messagebox.showinfo('Sovela','Please keep questions under 3,000 characters.',parent=self.root)
            return
        self.messages.append(('you',text))
        if self.cloud_available:
            self.chat_waiting=True
            # User-typed chat only: never automatically upload device scans or selected files.
            previous=[(r,t) for r,t in self.messages if r=='you' or (r=='sovela' and not t.startswith('Hello! I’m Sovela.'))]
            self.show_tab('Assistant')
            self.run_job('cloud_chat',lambda:ask_sovela_cloud(self.cloud_endpoint,previous))
        else:
            answer=advanced_offline_reply(text,self.last_data,self.last_health,self.last_file,
                                          self.startups,self.messages[:-1])
            self.messages.append(('sovela','GUIDED HELP (not generative AI)\n'+answer))
            self.messages=self.messages[-30:]
            self.show_tab('Assistant')

    def record_activity(self,message):
        self.activity.append(datetime.now().strftime('%H:%M')+'   '+message)
        self.activity=self.activity[-100:]

    def clear_activity(self):
        self.activity.clear()
        self.show_tab('Activity')

    def run_job(self,kind,fn):
        def work():
            try:
                result=fn()
                self.events.put((kind,'ok',result))
            except SovelaCloudUnavailable as exc:
                self.events.put((kind,'unavailable',str(exc)))
            except Exception as exc:
                self.events.put((kind,'error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def poll_events(self):
        while True:
            try:
                kind,state,value=self.events.get_nowait()
            except queue.Empty:
                break
            if kind=='cloud_chat':
                self.chat_waiting=False
                if state=='ok':
                    self.messages.append(('sovela',value))
                else:
                    # For the current session, stop retrying a failing hosted service
                    # on every message. Guided help remains available instantly.
                    self.cloud_available=False
                    original=next((t for r,t in reversed(self.messages) if r=='you'),'')
                    fallback=advanced_offline_reply(original,self.last_data,self.last_health,
                                                    self.last_file,self.startups,self.messages[:-1])
                    self.messages.append(('sovela',
                        'Online AI is unavailable right now. ' +
                        'Sovela has switched to guided help automatically.\n\n'+
                        'GUIDED HELP (not generative AI)\n'+fallback))
                self.messages=self.messages[-30:]
            elif kind=='security':
                self.checking=False
                if state=='ok':
                    self.receive_security(value)
                else:
                    self.status='Windows status unavailable'
            elif kind=='health':
                self.working_health=False
                if state=='ok':
                    self.last_health=value
            elif kind=='file':
                self.working_file=False
                if state=='ok':
                    self.last_file=value
            elif kind=='startups':
                self.working_startups=False
                if state=='ok':
                    self.startups=value
            elif kind=='care_preview':
                self.care_busy=False
                if state=='ok':
                    self.clean_preview=value
                    count=sum(len(item.get('files',[])) for item in value.values())
                    self.clean_notice=f'Preview ready: {count} eligible old files across automatic categories. Nothing changed.'
                else:
                    self.clean_notice='Could not preview folders: '+value
            elif kind=='care_clean':
                self.care_busy=False
                if state=='ok':
                    self.clean_notice=(f'Moved {value["recycled"]} files to Windows Recycle Bin '
                                       f'({self.human_bytes(value["bytes"])}). '
                                       f'{value["skipped"]} skipped. Empty the bin only after reviewing it.')
                    self.clean_preview=None
                else:
                    self.clean_notice='Cleanup stopped: '+value
            elif kind=='startup_change':
                self.startup_busy=False
                self.startup_notice=value if state=='ok' else 'Could not change startup: '+value
                self.startups=None
                self.inspect_startups()
            elif kind=='defender_scan':
                self.scanning=False
                self.scan_message=value if state=='ok' else 'Scan not confirmed: '+value
            if kind != 'cloud_chat':
                self.record_activity({
                    'security':'Windows protection reviewed',
                    'health':'PC health reviewed',
                    'file':'Chosen file inspected',
                    'startups':'Startup entries inspected',
                    'defender_scan':'Defender scan requested',
                    'care_preview':'Cleanup preview created',
                    'care_clean':'Selected cleanup reviewed',
                    'startup_change':'User-level startup option changed',
                }.get(kind,'Task completed')+(' · done' if state=='ok' else ' · unavailable'))
                if state=='error' and kind not in ('care_preview','care_clean','startup_change'):
                    messagebox.showwarning('Sovela',value,parent=self.root)
            if self.current_tab=='Assistant' or kind != 'cloud_chat':
                self.show_tab(self.current_tab)
        try:
            self.root.after(120,self.poll_events)
        except tk.TclError:
            pass

    def check(self):
        if self.checking:
            return
        self.checking=True
        self.status='Checking Windows…'
        self.show_tab(self.current_tab)
        self.run_job('security',powershell_check)

    def receive_security(self,data):
        self.last_data=data
        self.status='Security information ready'
        av=data.get('antivirus',[])
        if isinstance(av,str):
            av=[av]
        names=[str(s) for s in av if s]
        self.security_details['antivirus']=', '.join(names) if names else 'None registered or unavailable — verify in Windows Security'
        mp=data.get('defender')
        if defender_is_active(data):
            self.security_details['defender']='Real-time protection reported on'
        elif isinstance(mp,dict) and 'passive' in str(mp.get('mode','')).lower():
            self.security_details['defender']='Passive mode (another antivirus may be active)'
        else:
            self.security_details['defender']='Protection not confirmed — review Windows Security'
        fw=data.get('firewall',[])
        if isinstance(fw,dict):
            fw=[fw]
        if data.get('firewall_error') or not fw:
            self.security_details['firewall']='Status unavailable — review Windows Security'
        else:
            entries=[str(p.get('Name','Profile'))+': '+('On' if p.get('Enabled') is True else 'Off' if p.get('Enabled') is False else 'Unknown') for p in fw if isinstance(p,dict)]
            self.security_details['firewall']='  ·  '.join(entries) or 'Unavailable'
        self.messages.append(('sovela','I’ve received your latest Windows security check. Ask “Am I protected?” and I’ll explain what Windows reported — without claiming your PC is virus-free.'))
        self.messages=self.messages[-30:]

    def copy_summary(self):
        if not self.last_data:
            self.report_notice='Run a check before copying a summary.'
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(['Sovela security information (not a malware scan)']+
                                                      [f'{k}: {v}' for k,v in self.security_details.items()]))
            self.report_notice='Copied. You can paste it wherever you choose.'
        self.show_tab('Protection')

    def choose_file(self):
        folder=Path.home()/'Downloads'
        path=filedialog.askopenfilename(title='Choose a file',initialdir=str(folder if folder.exists() else Path.home()),parent=self.root)
        if not path:
            return
        self.selected_file=Path(path)
        self.last_file=None
        self.working_file=True
        self.scan_message='No scan requested.'
        self.show_tab('Downloads')
        self.run_job('file',lambda:inspect_file(path))

    def defender_scan(self):
        if self.scanning or not self.selected_file or self.working_file:
            return
        if not messagebox.askyesno('Microsoft Defender scan',
                                 'This uses Microsoft Defender, only if it is active. A real antivirus may '
                                 'quarantine a detected threat. Sovela will not scan files itself. Proceed?',parent=self.root):
            return
        self.scanning=True
        self.scan_message='Waiting for Defender…'
        self.show_tab('Downloads')
        self.run_job('defender_scan',lambda:request_defender_scan(str(self.selected_file)))

    def health_check(self):
        if self.working_health:
            return
        self.working_health=True
        self.show_tab('PC Health')
        self.run_job('health',computer_health)

    def inspect_startups(self):
        if self.working_startups:
            return
        self.working_startups=True
        self.show_tab('Startup')
        self.run_job('startups',list_startups)

    def open_settings(self,uri,friendly):
        try:
            os.startfile(uri)
        except (OSError,AttributeError):
            messagebox.showinfo('Windows settings','Press the Windows key and search for '+friendly+'.',parent=self.root)

    @staticmethod
    def human_bytes(num):
        if num>=1024**3:return gb(num)
        if num>=1024**2:return f'{num/1024**2:.1f} MB'
        if num>=1024:return f'{num/1024:.1f} KB'
        return f'{num} bytes'


if __name__=='__main__':
    root=tk.Tk()
    SovelaApp(root)
    root.mainloop()
