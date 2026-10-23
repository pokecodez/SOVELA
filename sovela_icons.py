"""Extract Windows executable and shortcut icons without launching any programs."""
import os,re,json,subprocess
from pathlib import Path

ICON_PS = r'''
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Drawing
$paths = ConvertFrom-Json $env:SOVELA_ICON_PATHS
$output=@{}
foreach($p in $paths) {
  try {
    if (!(Test-Path -LiteralPath $p -PathType Leaf)) {continue}
    $icon=[System.Drawing.Icon]::ExtractAssociatedIcon([string]$p)
    if($null -eq $icon) {continue}
    $bitmap=$icon.ToBitmap()
    $ms=New-Object System.IO.MemoryStream
    $bitmap.Save($ms,[System.Drawing.Imaging.ImageFormat]::Png)
    $output[[string]$p]=[Convert]::ToBase64String($ms.ToArray())
    $ms.Dispose();$bitmap.Dispose();$icon.Dispose()
  } catch { continue }
}
ConvertTo-Json -InputObject $output -Compress -Depth 3
'''

def extract_path(command):
    if not command:return None
    command=os.path.expandvars(str(command).strip())
    m=re.match(r'^\s*"([^"]+\.(?:exe|lnk|ico))"',command,re.I)
    if not m:m=re.match(r'^\s*([^\r\n]+?\.(?:exe|lnk|ico))(?=\s|$)',command,re.I)
    candidate=m.group(1) if m else (command if command.lower().endswith(('.lnk','.exe','.ico')) else '')
    if candidate.startswith(('\\\\','//')) or candidate.lower().startswith(('http:','https:')):return None
    if candidate and os.path.isfile(candidate):return str(Path(candidate).resolve())
    return None

def extract_icons(items, max_items=50):
    if os.name!='nt':return {}
    paths=list(dict.fromkeys(p for item in items[:max_items] if (p:=extract_path(item.get('detail','')))))
    if not paths:return {}
    env=os.environ.copy();env['SOVELA_ICON_PATHS']=json.dumps(paths)
    try:
        res=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',ICON_PS],
            capture_output=True,text=True,timeout=40,encoding='utf-8',errors='replace',
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=env)
        if res.returncode!=0:return {}
        obj=json.loads(res.stdout.strip().lstrip('\ufeff'))
        return {k:v for k,v in obj.items() if isinstance(v,str) and len(v)<200000} if isinstance(obj,dict) else {}
    except Exception:return {}
