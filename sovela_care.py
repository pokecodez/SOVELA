"""Sovela PC Care: conservative Windows-only user-level maintenance.

No privilege elevation, no system registry/service changes, no Downloads deletion,
no silent browser cookie removal, no registry cleaning or antivirus interference.
Preview only enumerates explicit allowlist roots; cleanup revalidates each path.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

# Preserve existing disabled-startup records from earlier versions without
# changing startup programs at launch. If the new file doesn't yet exist,
# read the old file for Restore; write new changes only under Sovela.
DATA_HOME = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
STATE_DIR = DATA_HOME / 'Sovela' / 'state'
LEGACY_STARTUP_SAVE = DATA_HOME / 'GuardianAI' / 'state' / 'disabled_startup.json'
STARTUP_SAVE = STATE_DIR / 'disabled_startup.json'
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
MAX_FILES_PER_GROUP = 2500
MAX_FILE_SIZE = 300 * 1024 * 1024

CATEGORIES = (
    ('temp', 'Temporary files', 'Old files in your personal temporary folder. 7+ days old.', 'clean'),
    ('cache', 'Browser cache', 'Old Edge, Chrome and Firefox cached files. Close browsers first.', 'clean'),
    ('reports', 'Crash reports', 'Archived personal Windows Error Reporting files. 30+ days old.', 'clean'),
    ('dumps', 'Crash dumps', 'Old personal application crash dumps. 30+ days old.', 'clean'),
    ('cookies', 'Cookies & site data', 'Review cookies in your browser. Clearing them can sign you out.', 'guided'),
    ('recycle', 'Recycle Bin', 'Review and empty it through Windows when you are ready.', 'guided'),
)


def _under(path, root):
    try:
        resolved, base = Path(path).resolve(strict=False), Path(root).resolve(strict=False)
        return resolved != base and resolved.is_relative_to(base)
    except (ValueError, OSError, RuntimeError):
        return False


def user_startup_folder():
    return Path(os.environ.get('APPDATA', str(Path.home()/'AppData'/'Roaming'))) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'


def _roots():
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData'/'Local')))
    allowed = {}
    temp = Path(tempfile.gettempdir())
    # Never trust an overridden system TEMP to reach arbitrary directories.
    if temp != Path(temp.anchor) and (_under(temp, Path.home()) or _under(temp, local)):
        allowed['temp'] = [(temp, 7, None)]
    cache = []
    for brand, folder in [('Google', 'Chrome'), ('Microsoft', 'Edge')]:
        user_data = local/brand/folder/'User Data'
        if user_data.is_dir():
            for profile in list(user_data.glob('Default')) + list(user_data.glob('Profile *')):
                cache_path = 'Cache/Cache_Data' if (profile/'Cache'/'Cache_Data').is_dir() else 'Cache'
                for rel in (cache_path, 'Code Cache/js', 'Code Cache/wasm'):
                    target = profile/rel
                    if target.is_dir():
                        cache.append((target, 3, None))
    firefox = local/'Mozilla'/'Firefox'/'Profiles'
    if firefox.is_dir():
        for profile in firefox.iterdir():
            target = profile/'cache2'/'entries'
            if target.is_dir():
                cache.append((target, 3, None))
    allowed['cache'] = cache
    allowed['reports'] = [(local/'Microsoft'/'Windows'/'WER'/'ReportArchive', 30, None)]
    allowed['dumps'] = [(local/'CrashDumps', 30, {'.dmp', '.mdmp'})]
    return allowed


def scan_cleanup():
    """Collect file paths + metadata for preview; no deletion or writes."""
    roots = _roots()
    results = {}
    now = time.time()
    for key in ('temp','cache','reports','dumps'):
        matches, total_bytes, skipped, limited = [], 0, 0, False
        for root, min_age, extensions in roots.get(key, []):
            if not root.is_dir() or root.is_symlink():
                continue
            try:
                for cur, dirs, files in os.walk(root, followlinks=False):
                    dirs[:] = [d for d in dirs if not (Path(cur)/d).is_symlink()]
                    for file in files:
                        if len(matches) >= MAX_FILES_PER_GROUP:
                            limited = True
                            break
                        path = Path(cur)/file
                        try:
                            if path.is_symlink() or not _under(path, root):
                                continue
                            if extensions and path.suffix.lower() not in extensions:
                                continue
                            stat = path.stat()
                            if not path.is_file() or stat.st_size > MAX_FILE_SIZE or (now - stat.st_mtime) < min_age*86400:
                                continue
                            entry = {'path':str(path), 'size':stat.st_size, 'mtime_ns':stat.st_mtime_ns,
                                     'root':str(root), 'min_days':min_age}
                            matches.append(entry)
                            total_bytes += stat.st_size
                        except (OSError, PermissionError):
                            skipped += 1
                    if limited:
                        break
            except (OSError, PermissionError):
                skipped += 1
        results[key] = {'files': matches, 'bytes':total_bytes, 'skipped':skipped, 'limited':limited}
    return results


def _running_browsers():
    if os.name != 'nt':
        return []
    try:
        cp = subprocess.run(['tasklist.exe','/FO','CSV','/NH'], capture_output=True,
                           text=True, timeout=12, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if cp.returncode != 0:
            return ['Could not verify browser processes']
        data = cp.stdout.casefold()
        return [x for x in ('chrome.exe','msedge.exe','firefox.exe') if '"'+x+'"' in data]
    except (OSError, subprocess.TimeoutExpired):
        # unknown status: safest not to touch browser cache
        return ['Could not verify browser processes']


def _send_to_recycle_bin(path):
    """Win32 shell recycle; fail closed when undo/recycle is unsupported."""
    if os.name != 'nt':
        raise RuntimeError('Windows is required to use the Recycle Bin.')
    import ctypes.wintypes as wt
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [('hwnd',wt.HWND), ('wFunc',wt.UINT), ('pFrom',wt.LPCWSTR),
                    ('pTo',wt.LPCWSTR), ('fFlags',wt.WORD), ('fAnyOperationsAborted',wt.BOOL),
                    ('hNameMappings',ctypes.c_void_p),('lpszProgressTitle',wt.LPCWSTR)]
    # SHFileOperationW, FO_DELETE with FOF_ALLOWUNDO. Single path; no wildcard.
    src = ctypes.create_unicode_buffer(str(path)+'\0\0')
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = 3
    op.pFrom = ctypes.cast(src, wt.LPCWSTR)
    op.pTo = None
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400
    op.fAnyOperationsAborted = False
    status = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if status != 0 or op.fAnyOperationsAborted:
        raise OSError(f'Windows did not confirm recycling this item (code {status}).')


def clean_selected(preview, chosen):
    """Revalidate age, roots and metadata immediately before any file action."""
    if os.name != 'nt':
        raise RuntimeError('Cleaning is available on Windows only.')
    chosen = set(chosen).intersection({'temp','cache','reports','dumps'})
    if 'cache' in chosen:
        running = _running_browsers()
        if running:
            raise RuntimeError('Close Chrome, Edge and Firefox first. Running: '+', '.join(running))
    fresh_roots = _roots()
    totals = {'recycled':0, 'bytes':0, 'skipped':0, 'categories':sorted(chosen)}
    for key in ('temp','cache','reports','dumps'):
        if key not in chosen:
            continue
        roots = fresh_roots.get(key, [])
        for entry in preview.get(key, {}).get('files', []):
            path = Path(entry['path'])
            try:
                allowed = any(_under(path,r) and not r.is_symlink() for r,_,_ in roots)
                if not allowed or path.is_symlink() or not path.is_file():
                    totals['skipped'] += 1
                    continue
                stat = path.stat()
                if stat.st_size != entry['size'] or stat.st_mtime_ns != entry['mtime_ns']:
                    totals['skipped'] += 1
                    continue
                if (time.time()-stat.st_mtime) < entry['min_days']*86400:
                    totals['skipped'] += 1
                    continue
                _send_to_recycle_bin(path)
                totals['recycled'] += 1
                totals['bytes'] += stat.st_size
            except (OSError, PermissionError, RuntimeError):
                totals['skipped'] += 1
    return totals


def _read_disabled():
    try:
        source = STARTUP_SAVE if STARTUP_SAVE.is_file() else LEGACY_STARTUP_SAVE
        obj = json.loads(source.read_text(encoding='utf-8'))
        return obj if isinstance(obj,dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save_disabled(data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STARTUP_SAVE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data,indent=2),encoding='utf-8')
    os.replace(tmp,STARTUP_SAVE)


def _protected_startup(name, detail):
    line = (name+' '+detail).lower()
    # Prevent tinkering with protection, backup and system tray services from here.
    terms = ('antivirus','antimalware','defender','securityhealth','windows security',
             'firewall','endpoint protection','bitdefender','avast','avg antivirus',
             'norton','kaspersky','malwarebytes','eset','mcafee','sophos',
             'sovela','backups','backup client')
    return any(word in line for word in terms)


def list_startups():
    """Inventory + narrowly reversible actions; machine-wide entries always read-only."""
    if os.name != 'nt':
        raise RuntimeError('Windows only')
    import winreg
    items, notes = [], []
    backups = _read_disabled()
    for hive,label,editable in ((winreg.HKEY_CURRENT_USER,'My account',True),
                                (winreg.HKEY_LOCAL_MACHINE,'All users',False)):
        try:
            with winreg.OpenKey(hive,RUN_KEY,0,winreg.KEY_READ) as key:
                for index in range(min(winreg.QueryInfoKey(key)[1],160)):
                    name,command,kind=winreg.EnumValue(key,index)
                    protected = _protected_startup(str(name),str(command))
                    items.append({'name':str(name),'source':label+' registry','detail':str(command),
                                  'id':'reg:'+str(name) if editable else 'system:'+str(name),
                                  'editable':editable and not protected,'state':'Enabled'})
        except (OSError,PermissionError):
            notes.append('Some registry entries are unavailable.')
    for folder,label,editable in ((user_startup_folder(),'My account',True),
                                   (Path(os.environ.get('ProgramData','C:/ProgramData'))/'Microsoft'/'Windows'/'Start Menu'/'Programs'/'Startup','All users',False)):
        try:
            if folder.is_dir():
                for item in folder.iterdir():
                    if item.is_file() and not item.is_symlink():
                        is_safe=not _protected_startup(item.name,str(item))
                        items.append({'name':item.name,'source':label+' startup folder','detail':str(item),
                                      'id':'file:'+item.name if editable else 'systemfile:'+item.name,
                                      'editable':editable and is_safe,'state':'Enabled'})
        except (OSError,PermissionError):
            notes.append('Some startup folder items are unavailable.')
    for item_id,saved in backups.items():
        if isinstance(saved,dict):
            items.append({'name':saved.get('name',item_id),'source':'My account (saved in Sovela)',
                          'detail':saved.get('description',''),'id':item_id,'editable':True,'state':'Disabled'})
    items.sort(key=lambda x:(x['state']!='Enabled',x['name'].lower()))
    return {'items':items[:140],'total':len(items),'notes':sorted(set(notes))}


def disable_startup(item):
    if os.name != 'nt' or item.get('state')!='Enabled' or not item.get('editable'):
        raise RuntimeError('This startup entry cannot be changed safely in Sovela.')
    import winreg
    item_id = str(item['id'])
    data = _read_disabled()
    if item_id in data:
        raise RuntimeError('A saved change already exists for this entry.')
    if item_id.startswith('reg:'):
        name=item_id[4:]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_READ|winreg.KEY_SET_VALUE) as key:
            current,kind=winreg.QueryValueEx(key,name)
            if str(current)!=item['detail'] or _protected_startup(name,str(current)):
                raise RuntimeError('This entry changed since you reviewed it. Refresh first.')
            data[item_id]={'kind':'registry','name':name,'value':current,'value_type':kind,
                           'description':str(current),'date':datetime.now().isoformat()}
            _save_disabled(data)  # Recovery recorded before changing system state.
            try:
                winreg.DeleteValue(key,name)
            except Exception:
                data.pop(item_id,None)
                _save_disabled(data)
                raise
    elif item_id.startswith('file:'):
        filename=item_id[5:]
        source=user_startup_folder()/filename
        if filename!=source.name or not source.is_file() or source.is_symlink() or not _under(source,user_startup_folder()):
            raise RuntimeError('Selected startup shortcut is unavailable.')
        if _protected_startup(filename,str(source)):
            raise RuntimeError('Security-related startup entries must be changed in their own app.')
        STATE_DIR.mkdir(parents=True,exist_ok=True)
        dest=STATE_DIR/('startup_file_'+str(int(time.time()*1000))+'_'+filename)
        data[item_id]={'kind':'file','name':filename,'saved_path':str(dest),
                       'description':str(source),'date':datetime.now().isoformat()}
        _save_disabled(data)
        try:
            shutil.move(str(source),str(dest))
        except Exception:
            data.pop(item_id,None)
            _save_disabled(data)
            raise
    else:
        raise RuntimeError('All-users startup settings are read-only.')
    return f'Disabled {item["name"]} for your account. It can be restored in Startup.'


def restore_startup(item):
    if os.name!='nt' or item.get('state')!='Disabled':
        raise RuntimeError('Only a saved disabled entry can be restored.')
    item_id=str(item['id']); data=_read_disabled()
    saved=data.get(item_id)
    if not saved:
        raise RuntimeError('No saved startup configuration was found.')
    if saved['kind']=='registry':
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE|winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key,saved['name'])
                raise RuntimeError('Another startup entry now uses this name. Nothing was overwritten.')
            except FileNotFoundError:
                pass
            winreg.SetValueEx(key,saved['name'],0,saved['value_type'],saved['value'])
    elif saved['kind']=='file':
        src=Path(saved['saved_path']); dest=user_startup_folder()/saved['name']
        if not _under(src,STATE_DIR) or not src.is_file() or dest.exists():
            raise RuntimeError('Cannot restore: saved file missing or destination already exists.')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src),str(dest))
    else:
        raise RuntimeError('Unknown saved startup type.')
    data.pop(item_id,None); _save_disabled(data)
    return f'Restored {item["name"]}. It can launch automatically at the next sign-in.'
