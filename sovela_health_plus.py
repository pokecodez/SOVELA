"""Read-only evidence-based PC health suggestions. No game-use tracking."""
from pathlib import Path
import time

INSTALL_EXTS={'.exe','.msi','.iso','.zip','.7z','.rar'}

def suggest(health, startups=None):
    if not health:return []
    rec=[]
    total=max(1,int(health.get('disk_total',0)))
    free=int(health.get('disk_free',0))/total
    if free<.10:
        rec.append(('Storage nearly full','Less than 10% of your system drive is free. Check large downloads and Windows Storage settings. Never delete files you do not recognise.','high'))
    elif free<.20:
        rec.append(('Storage could use attention','Less than 20% disk space remains. Consider reviewing old installers and temporary files.','normal'))
    else:
        rec.append(('Storage looks comfortable','Your system drive has at least 20% free space. Aggressive cleaning is not needed.','good'))
    mem_total=max(1,int(health.get('ram_total',0)))
    used=1-(int(health.get('ram_free',0))/mem_total)
    if used>.90:
        rec.append(('Memory is very busy','Over 90% of RAM is currently in use. Check Task Manager and close programs you are not using.','high'))
    elif used>.80:
        rec.append(('Memory is fairly busy','Over 80% of RAM is in use. If your PC is slow, review currently open applications.','normal'))
    else:
        rec.append(('No obvious memory pressure','RAM usage is below 80% right now; memory may not be the cause of any slowdown.','good'))
    n=int(health.get('startup_count',0))
    if n>=15:
        rec.append(('Review optional startup programs',f'{n} common startup entries detected. Consider disabling apps you recognise that are not needed at sign-in.','normal'))
    else:
        rec.append(('Startup review is optional',f'{n} common startup entries detected. Their count alone does not prove your computer is slow.','good'))
    rec.append(('Keep Windows updated','Open Windows Update to review outstanding updates. Sovela has not independently checked application update dates.','normal'))
    return rec

def older_large_downloads(limit=5, now=None, base=None):
    """List large old installers/archives in top-level Downloads; never delete them."""
    now=time.time() if now is None else now
    folder=Path(base) if base else Path.home()/'Downloads'
    if not folder.is_dir():return []
    out=[]
    try:
        for p in folder.iterdir():
            try:
                if p.is_symlink() or not p.is_file() or p.suffix.lower() not in INSTALL_EXTS:continue
                st=p.stat()
                if st.st_size<200*1024*1024 or now-st.st_mtime<90*86400:continue
                out.append({'name':p.name,'bytes':st.st_size,'age_days':int((now-st.st_mtime)/86400)})
            except OSError:continue
    except OSError:return []
    return sorted(out,key=lambda x:-x['bytes'])[:limit]
