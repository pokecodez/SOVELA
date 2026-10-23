"""Sovela Advanced — transparent, rule-based security help; never an antivirus.

All reasoning is local. Only uses evidence passed into it, and never states a
threat is confirmed from metadata, unknown startup names, or resource usage.
"""
import re
from sovela_diagnostics import diagnose, DIAGNOSES


def _mentions(text, *terms):
    return any(t in text for t in terms)


def _bullets(lines):
    return '\n'.join(f'• {line}' for line in lines)


def security_insights(security=None, health=None, file_info=None, startups=None):
    """Evidence-based observations with no invented statuses or verdicts."""
    out=[]
    if security is None:
        out.append('Protection: Not checked. Open Overview → Run a security check first.')
    else:
        av=security.get('antivirus', [])
        if isinstance(av,str): av=[av]
        av=[str(x) for x in av if x]
        if av:
            out.append('Windows lists these antivirus products: '+', '.join(av)+'. This is registration information, not proof that their shields are running.')
        else:
            out.append('Windows returned no registered antivirus product. That can indicate a reporting problem or missing protection; verify in Windows Security.')
        defender=security.get('defender')
        if isinstance(defender,dict):
            active=(str(defender.get('mode','')).lower() == 'normal'
                    and defender.get('antivirus_enabled') is True
                    and defender.get('realtime_enabled') is True)
            if active:
                out.append('Microsoft Defender reported normal mode and real-time antivirus protection enabled at the last check.')
            else:
                out.append('Microsoft Defender active protection was NOT confirmed. If a different antivirus is installed, Defender may be in passive mode. Verify the active antivirus in Windows Security.')
        else:
            out.append('Defender status could not be checked. Sovela cannot determine whether it is active.')
        fw=security.get('firewall', [])
        fw=[fw] if isinstance(fw,dict) else fw
        fw=fw if isinstance(fw,list) else []
        disabled=[str(f.get('Name','Unknown')) for f in fw if isinstance(f,dict) and f.get('Enabled') is False]
        if disabled:
            out.append('Attention: Windows reported firewall profile(s) OFF: '+', '.join(disabled)+'. Check Firewall & network protection; another security product might manage network protection.')
        elif fw and all(isinstance(f,dict) and f.get('Enabled') is True for f in fw):
            out.append('Windows Firewall profiles returned by the last check all reported enabled.')
        else:
            out.append('Firewall data was incomplete, so Sovela cannot confirm firewall coverage.')
    if health:
        total=health.get('disk_total') or 0
        free=health.get('disk_free')
        if total and isinstance(free,(int,float)):
            pct=int(100*free/total)
            out.append(('Storage: only '+str(pct)+'% free; low disk space can affect updates and performance.'
                        if pct<10 else 'Storage: '+str(pct)+'% free (not a malware test).'))
        ram=health.get('ram_total') or 0
        avail=health.get('ram_free')
        if ram and isinstance(avail,(int,float)):
            used=int(100*(ram-avail)/ram)
            if used>90:
                out.append('Memory: '+str(used)+'% used at the last check. High usage can slow apps, but is not evidence of infection.')
    if file_info:
        out.append('Selected file: '+str(file_info.get('name','file'))+'. '+str(file_info.get('note','')).strip()+' Sovela has NOT determined whether it contains malware.')
    if startups:
        out.append('Startup Explorer found '+str(startups.get('total','?'))+' entries in common startup locations. The number alone does not indicate malware.')
    return out


TOPICS={
 'avast':('Avast adverts and interruptions',[
    'Open Avast and look for Settings → Notifications, Silent Mode or Do Not Disturb (wording differs by version).',
    'Disable promotional notices if your version allows it. Keep important security alerts enabled.',
    'If the problem persists, tell me the exact wording of the popup, without account details.']),
 'suspicious_file':('Suspicious download',[
    'Do not open or run the file while uncertain.',
    'Use Sovela → Downloads to inspect its extension and fingerprint. These checks cannot prove it is safe.',
    'Use your currently active antivirus to scan it and inspect its official detection results.',
    'For an unexpected attachment, verify the sender through another trusted channel.']),
 'account':('Account security',[
    'From a trusted device, change the password for the affected account using its official website.',
    'Sign out of other sessions and turn on multifactor authentication where available.',
    'Check recovery email, forwarding rules and recent account activity for unexpected changes.',
    'If money or identity information is involved, contact the provider directly.']),
 'phishing':('Suspicious message or website',[
    'Do not click the link or download attachments.',
    'Go to the service using its official app or a bookmarked address instead.',
    'Treat urgent payment demands, unexpected sign-in links and requests for codes as warning signs.',
    'If you already entered a password, tell me so I can help you prioritise next steps.']),
 'ransomware':('Possible ransomware',[
    'If files are actively being encrypted or renamed unexpectedly, disconnect the computer from networks to reduce further spread.',
    'Do not delete evidence, pay a ransom, or download random decryptors.',
    'Use a trusted security professional or incident-response service, especially for business machines.',
    'Preserve backup copies and avoid plugging backup drives into a potentially infected device.']),
 'popups':('Browser popups and redirects',[
    'Close the suspicious page; avoid clicking its warning buttons.',
    'Check the browser’s notification permissions and remove unfamiliar sites.',
    'Review recently added browser extensions, then scan with your active antivirus.',
    'If popups appear even with the browser closed, tell me — the next checks are different.']),
 'performance':('Slow computer',[
    'Open Sovela → PC Health to inspect free storage and memory use.',
    'Open Startup to review programs that launch automatically; an unfamiliar name is not proof of malware.',
    'Install Windows updates, restart, and identify which activity is slow (boot, browsing, gaming, or all apps).',
    'Do not install “one-click speed boosters” or registry cleaners.']),
 'updates':('Windows updates',[
    'Open Sovela → Tools → Windows Update.',
    'Install security updates from Windows itself, then restart when required.',
    'If updates fail, record the exact error code and ask me about that code.']),
 'firewall':('Firewall and network security',[
    'Review Sovela → Protection to see what Windows reported at the last check.',
    'Open Windows Security → Firewall & network protection to confirm the live state.',
    'Don’t disable firewall profiles simply to get an application working; use official troubleshooting first.']),
 'defender':('Antivirus and Microsoft Defender',[
    'Open Sovela → Overview → Run a security check.',
    'Verify which antivirus product is actually active in Windows Security.',
    'When a third-party antivirus is active, Microsoft Defender can be passive. This is not by itself an infection.',
    'Never disable your active antivirus without verified replacement protection.']),
 'startup':('Startup applications',[
    'Open Sovela → Startup → Inspect startup programs.',
    'Search unfamiliar entries by their full publisher and path; avoid judging safety from a name alone.',
    'Use Windows Settings → Apps → Startup for changes after confirming the app is unnecessary.']),
 'privacy':('Privacy in Sovela',[
    'Built-in chat and Windows checks are processed locally on your computer.',
    'When hosted AI is connected, Sovela sends your typed question and recent conversation to its online provider.',
    'Do not paste passwords, API keys, security codes or private documents into chat.',
    'Sovela does not upload selected files during local file inspection.']),
 'backup':('Backups and recovery',[
    'Keep backups of important files on a trusted drive or reputable service.',
    'Maintain a backup that is disconnected or otherwise protected from malware.',
    'Periodically confirm you can restore a sample file.']),
 'password':('Password safety',[
    'Use a unique, long password for each important account.',
    'Use a trustworthy password manager and enable multifactor authentication.',
    'Never share one-time login codes with anyone who contacts you unexpectedly.']),
 'scam':('Potential tech support scam',[
    'Real security tools should not demand that you call a random number on a web page.',
    'Do not grant remote access to an unexpected caller or website.',
    'If you already installed remote-control software or paid someone, tell me what happened without sending private details.']),
}

PATTERNS=[
 ('ransomware', ('ransomware','encrypted my files','files encrypted','ransom note')),
 ('account', ('hacked account','account hacked','someone logged in','compromised account','stolen account')),
 ('scam', ('tech support scam','call this number','remote access scam','scammer','fake antivirus warning')),
 ('phishing', ('phishing','suspicious email','dodgy email','strange email','fake login','suspicious link')),
 ('popups', ('browser popup','popups in chrome','browser redirect','redirects','chrome notification','pop ups in edge')),
 ('avast', ('avast','avast popup','avast advert')),
 ('suspicious_file', ('suspicious download','downloaded a file','suspicious file','is this file safe','exe file','attachment','unknown download','scan a file')),
 ('password', ('password','2fa','two factor','multifactor','authentication code')),
 ('backup', ('backup','restore files','recovery drive')),
 ('firewall', ('firewall','wifi','wi-fi','network protection')),
 ('defender', ('defender','antivirus','virus protection','realtime protection','real-time protection','real time protection')),
 ('startup', ('startup','start-up','boot programs','launch on startup')),
 ('performance', ('slow','lag','storage','disk space','ram','performance','free space','computer freezing')),
 ('updates', ('update','windows patch','patches','update error')),
 ('privacy', ('privacy','tracking','send data','data upload','who can see my','your data')),
]


def advanced_offline_reply(question, security=None, health=None, file_info=None, startups=None, history=None):
    """Rule-based, context-aware support. Does NOT generate arbitrary AI text."""
    raw=' '.join((question or '').strip().split())
    q=raw.casefold()
    if not q:
        return 'Ask a Windows security question, or try “Review my protection”, “What about the file I checked?” or “My antivirus keeps showing adverts”.'
    history=history or []
    if re.search(r'\b(hello|hi|hey|good morning|good evening)\b',q) and len(q)<35:
        return 'Hi! I can explain Windows protection, downloads, scams, popups and your last Sovela checks. What would you like help with?'
    if re.search(r'\b(thanks|thank you|cheers)\b',q) and len(q)<45:
        return 'Glad to help. Ask me about another issue whenever you need.'
    if _mentions(q,'entered my password','typed my password','gave my password','shared my password',
                 'sent my code','shared my code','entered my code'):
        return ('IF YOU SHARED A PASSWORD OR LOGIN CODE\n\n'+_bullets([
            'Use the official website or app on a trusted device; change the affected password immediately.',
            'If you reused that password elsewhere, change those accounts too.',
            'Enable multifactor authentication and sign out other sessions.',
            'Check account recovery options and activity. If payment details were involved, contact your bank/provider promptly.',
        ])+'\n\nIf you tell me which kind of account was involved (without credentials), I can suggest more specific next steps.')
    if _mentions(q,'clicked the link','clicked a link','opened suspicious link','clicked suspicious link'):
        return ('IF YOU CLICKED A SUSPICIOUS LINK\n\n'+_bullets([
            'Close the page. Do not enter passwords or download anything.',
            'If you entered login details, change them using the official site from a trusted device.',
            'If a download started, do not open it; have your active antivirus scan it.',
            'If you installed or ran something, disconnect from networks if active compromise is suspected and seek trusted help.',
        ])+'\n\nDid you only view the page, enter information, or download/run a file?')
    report_terms=('review my protection','security report','am i protected','am i safe','check my pc','my protection','my security','how secure','summarise my checks','summarize my checks','overall health','what needs attention','anything wrong','review my pc','status report','scan results')
    file_terms=('the file i checked','last file','selected file','what about that file','that file i inspected')
    if _mentions(q,*report_terms):
        facts=security_insights(security,health,file_info,startups)
        return ('SOVELA CHECK REVIEW\n\n'+_bullets(facts)+'\n\nNEXT STEP\n'
                'Review any uncertain or disabled protection in Windows Security. These checks cannot guarantee your PC is malware-free.')
    if _mentions(q,*file_terms):
        if file_info:
            return ('ABOUT YOUR LAST FILE\n\n'+_bullets(security_insights(None,None,file_info,None)[-1:])
                    +'\n\nNEXT STEP\nUse your active antivirus to scan it before opening if it came from an unfamiliar source. A hash or extension cannot prove safety.')
        return 'No file inspection is available yet. Open Downloads → Choose a file, then come back and ask again.'
    if 'what can you do' in q or 'help me'==q or 'features'==q:
        return ('I’m Sovela Advanced, a built-in *rules-based* security guide, not a full AI model. '
                'I can explain your real protection checks, last inspected file, PC health and startup entries. '
                'I also have guided help for phishing, ransomware, accounts, antivirus popups, updates, backups and privacy. '
                'For real AI chat, connect your own Gemini key in Account → Personal AI; guided help still works offline.')
    suggestion=diagnose(q)
    if suggestion:
        return suggestion
    for topic,words in PATTERNS:
        if _mentions(q,*words):
            title,steps=TOPICS[topic]
            extra=''
            if topic=='performance' and health:
                h=security_insights(None,health,None,None)
                extra='\n\nFROM YOUR LAST PC HEALTH CHECK\n'+_bullets(h[1:]) if len(h)>1 else ''
            if topic in ('defender','firewall') and security:
                extra='\n\nFROM YOUR LAST WINDOWS CHECK\n'+_bullets(security_insights(security)[:4])
            if topic=='suspicious_file' and file_info:
                extra='\n\nLAST INSPECTED FILE\n'+_bullets(security_insights(None,None,file_info)[-1:])
            return title.upper()+'\n\n'+_bullets(steps)+extra
    # Tiny conversational memory for follow-up questions: use previous topic only
    # when the current utterance is a brief follow-up; never silently infer context.
    if len(q)<65 and _mentions(q,'what next','then what','how do i do that','where is that','can you explain','tell me more','what if'):
        for role,msg in reversed(history[-8:]):
            if role!='you' or msg==question:
                continue
            previous=' '.join(msg.casefold().split())
            for topic,words in PATTERNS:
                if _mentions(previous,*words):
                    title,steps=TOPICS[topic]
                    return ('Following up on '+title.lower()+':\n\n'+_bullets(steps)+
                            '\n\nIf you tell me which step is confusing, I can explain that part.')
    return ('I don’t want to guess about that. I’m an advanced *guided* security helper, not a full generative AI. '
            'Can you tell me whether this is about a download, a suspicious message, your antivirus, '
            'a slow PC or an account problem? You can also ask “Review my protection” after running a Sovela check.')
