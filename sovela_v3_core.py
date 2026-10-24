"""Sovela v3 release helpers: local user settings and opt-in Gemini.

Nothing in this module gives admin rights, modifies subscriptions, or makes
unattended file deletions. AI only receives messages the user submits.
"""
from __future__ import annotations
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

from sovela_auth import AccountError, local_data, dpapi_encrypt, dpapi_decrypt, valid_repo

SUPPORT_EMAIL = 'finleyhope80@gmail.com'
GEMINI_MODEL = 'gemini-2.5-flash'


def local_settings_path():
    return local_data() / 'v3-settings.json'


def load_local_settings(path=None):
    defaults = {'updates_repo':'','weekly_reminders':True,
                'premium_weekly_defender':False,'premium_clean_preview':False,
                'last_weekly_reminder':'','last_maintenance':'',
                'premium_weekly_clean_enabled':False, 'premium_clean_categories':[],
                'last_weekly_cleanup':'','last_scan_prompt':''}
    path=Path(path or local_settings_path())
    try:
        if path.stat().st_size > 10000:return defaults.copy()
        obj=json.loads(path.read_text('utf-8'))
        if isinstance(obj,dict):
            defaults['updates_repo']=valid_repo(obj.get('updates_repo',''))
            for key in ('weekly_reminders','premium_weekly_defender','premium_clean_preview',
                        'premium_weekly_clean_enabled'):
                if type(obj.get(key)) is bool:defaults[key]=obj[key]
            for key in ('last_weekly_reminder','last_maintenance','last_weekly_cleanup','last_scan_prompt'):
                if isinstance(obj.get(key),str) and len(obj[key])<50:
                    defaults[key]=obj[key]
            groups=obj.get('premium_clean_categories')
            if isinstance(groups,list):
                defaults['premium_clean_categories']=[k for k in ('temp','cache','reports','dumps') if k in groups]
            # Old preview-only settings can never opt a user into scheduled deletion.
            if not defaults['premium_clean_categories']:
                defaults['premium_weekly_clean_enabled']=False
    except (OSError,ValueError,UnicodeError):pass
    return defaults


def save_local_settings(obj,path=None):
    path=Path(path or local_settings_path())
    path.parent.mkdir(parents=True,exist_ok=True)
    allowed=load_local_settings(path)
    allowed.update({k:v for k,v in obj.items() if k in allowed})
    allowed['updates_repo']=valid_repo(allowed['updates_repo'])
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(allowed,indent=2),encoding='utf-8')
    tmp.replace(path)


def reminder_due(last,now=None,days=7):
    now=now or datetime.now(timezone.utc)
    try:
        then=datetime.fromisoformat(last)
        if then.tzinfo is None:return True
        return (now-then).total_seconds()>=days*86400
    except (ValueError,TypeError):return True


def premium_allowed(entitlement):
    return isinstance(entitlement,dict) and entitlement.get('tier') in ('trial','premium')


class PrivateGeminiKey:
    """DPAPI-encrypted per-Windows-user key, never stored in project files."""
    def __init__(self,path=None):
        self.path=Path(path or local_data()/'gemini-key.dpapi')

    def save(self,key):
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_\-]{20,200}',key):
            raise ValueError('That does not look like a Gemini API key.')
        blob=dpapi_encrypt(key.encode('utf-8'))
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_bytes(blob)
        tmp.replace(self.path)

    def get(self):
        try:return dpapi_decrypt(self.path.read_bytes()).decode('utf-8')
        except (OSError,ValueError,UnicodeError,AccountError):return None

    def remove(self):
        self.path.unlink(missing_ok=True)


def ask_gemini(key,history,opener=None):
    """Send ONLY user-authorised chat history, never telemetry, files or scan logs."""
    if not key:raise ValueError('Add a Gemini key in Account first.')
    contents=[]
    for role,text in history[-12:]:
        if role not in ('you','sovela') or not str(text).strip():continue
        contents.append({'role':'user' if role=='you' else 'model',
                         'parts':[{'text':str(text)[:3500]}]})
    # Always end with the new user message.
    if not contents or contents[-1]['role']!='user':
        raise ValueError('No user question provided.')
    payload={'systemInstruction':{'parts':[{'text':
        'You are Sovela, a friendly PC-care assistant. Be accurate and concise. '
        'Never claim to have scanned the computer. Do not recommend disabling antivirus. '
        'Ask the user before any destructive action. Explain uncertainty clearly. '
        'For Gemini API key help, point to https://aistudio.google.com/apikey.'}]},
        'contents':contents,'generationConfig':{'maxOutputTokens':750,'temperature':0.35}}
    url='https://generativelanguage.googleapis.com/v1beta/models/'+GEMINI_MODEL+':generateContent'
    req=urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type':'application/json','x-goog-api-key':key,'User-Agent':'SovelaPC/3.0'}, method='POST')
    opener=opener or urllib.request.urlopen
    try:
        with opener(req,timeout=25) as response:
            raw=response.read(180_001)
        if len(raw)>180_000:raise ValueError('AI reply was too large.')
        obj=json.loads(raw)
        candidates=obj.get('candidates',[])
        content=candidates[0].get('content',{}) if candidates else {}
        answer='\n'.join(x.get('text','') for x in content.get('parts',[]) if isinstance(x,dict)).strip()
        if not answer:raise ValueError('AI did not return a readable answer.')
        return answer[:8000]
    except urllib.error.HTTPError as exc:
        if exc.code==429:raise ValueError('Gemini free usage limit reached. Try again later.') from None
        if exc.code in (401,403):raise ValueError('Gemini rejected this API key or permissions.') from None
        raise ValueError('Gemini is unavailable (HTTP '+str(exc.code)+').') from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise ValueError('Could not reach Gemini. Check your connection.') from None
