"""Extensible, explainable troubleshooting catalogue. Not machine diagnosis or LLM."""
import re

# Each item = topic, matching phrases, conservative first steps, follow-up question.
# A phrase match identifies a possible topic; it does not prove a cause.
DIAGNOSES = [
 ('PC will not start', 'pc wont boot|computer wont start|windows wont load|no boot device|black screen on boot', 'Disconnect newly attached peripherals; check whether the machine powers on; use Windows Recovery options if available.', 'Do you see the manufacturer logo or any error message?'),
 ('Blue screen errors', 'blue screen|bsod|stop code|kernel security check failure|irql not less or equal', 'Record the exact stop code; note recent driver/hardware changes; check Windows Update and official device drivers.', 'What stop code is shown?'),
 ('Unexpected restarts', 'keeps restarting|random restart|reboot loop|restarting by itself', 'Check overheating and power connections; review Windows Reliability Monitor for crashes and updates.', 'Does it restart while idle, gaming, or starting Windows?'),
 ('Device running hot', 'overheating|very hot|hot laptop|cpu temperature|thermal throttling', 'Check vents and fans for dust; avoid soft surfaces blocking airflow; inspect temperatures using trusted device tools.', 'Does the device feel hot during a specific activity?'),
 ('Fan noise', 'loud fan|fan constantly running|fans spinning|fan noise', 'Look for unusually busy apps in Task Manager; check ventilation; avoid downloading unknown fan-control utilities.', 'Is the fan loud immediately after startup or only during games?'),
 ('Slow startup', 'slow boot|takes ages to start|slow startup|slow sign in', 'Use Sovela → Startup to review optional sign-in apps; leave security and backup services alone; restart after Windows updates.', 'How many minutes does startup take?'),
 ('Slow browser', 'browser slow|chrome slow|edge slow|firefox slow|slow web pages', 'Test another website and browser; disable only unfamiliar extensions; check Task Manager and browser updates.', 'Is just one website slow or every site?'),
 ('High RAM usage', 'ram usage|memory usage|out of memory|low memory|memory pressure', 'Use PC Health and Task Manager to identify the app using memory; restart a stuck app; keep tabs under control.', 'Which process is using the most memory?'),
 ('High CPU usage', '100% cpu|cpu at 100|high cpu|processor maxed', 'Open Task Manager, sort by CPU and check which app is responsible; update that app and avoid ending unknown system processes.', 'What process is listed at the top?'),
 ('High disk activity', 'disk 100|100% disk|disk usage high|hard disk busy', 'Check Task Manager disk activity, storage free space and Windows updates; back up important files if you hear drive errors.', 'Is your main drive an SSD or hard disk?'),
 ('Low storage', 'disk full|low storage|not enough disk space|drive almost full|c drive full', 'Use Sovela → Cleaner to preview old personal temporary files, then Windows Storage settings to review large files.', 'How much free space does Windows show?'),
 ('Slow file transfers', 'copying slow|file transfer slow|slow usb|slow transfer', 'Try a different trusted USB port or cable and check available drive space; do not unplug a drive while writing.', 'Is the transfer between two drives or over the network?'),
 ('Wi-Fi disconnects', 'wifi disconnect|wi-fi disconnect|keeps losing wifi|wireless drops', 'Restart the router and device; check whether other devices disconnect; update your adapter from its manufacturer.', 'Does it happen to every device or just this PC?'),
 ('No internet connection', 'no internet|internet not working|offline on pc|cannot connect to internet', 'Check another device, airplane mode, network cable and router status; use Windows Network Troubleshooter.', 'Are other devices connected to the internet?'),
 ('Slow connection', 'slow internet|internet lag|slow wifi|slow wi-fi', 'Compare wired and wireless connections and try different websites; check for large downloads or VPN connections.', 'Is it slow on only this PC?'),
 ('DNS problems', 'dns error|dns probe|dns server not responding|name resolution', 'Restart router and browser; check DNS settings before changing them; avoid random DNS-fixer tools.', 'What exact error appears in the browser?'),
 ('VPN problems', 'vpn not connecting|vpn disconnect|vpn slow|vpn blocked', 'Confirm VPN credentials and subscription status, then update the VPN app using its official installer.', 'Does normal browsing work without the VPN?'),
 ('Firewall questions', 'firewall blocked|firewall off|blocked by firewall|windows firewall', 'Review Sovela → Protection and the live Windows Security firewall page; do not disable the firewall to fix one app.', 'Which app or network connection is affected?'),
 ('Update stuck', 'windows update stuck|update stuck|update error|windows update failed|0x800f', 'Restart normally, check free storage and use official Windows Update troubleshooting; note the update error code.', 'What is the exact error code?'),
 ('Driver trouble', 'driver error|driver issue|device driver|driver not working|code 43', 'Use Device Manager to identify the affected hardware, then install drivers only from Windows Update or the manufacturer.', 'Which device has the warning symbol?'),
 ('Bluetooth trouble', 'bluetooth not working|bluetooth disconnect|bluetooth missing|pairing failed', 'Toggle Bluetooth off/on, check the device battery and re-pair it through Windows Settings.', 'Is the Bluetooth button missing or does pairing fail?'),
 ('USB device unrecognised', 'usb not recognized|usb not recognised|usb device unknown|usb not detected', 'Try another port and cable, then inspect Device Manager; do not format a drive that contains important data.', 'Is the device a drive, phone or accessory?'),
 ('Audio problems', 'no sound|audio not working|speakers silent|headphones no sound', 'Check output selection, volume mixer and mute keys; verify the audio device in Windows Settings.', 'Are you using speakers, wired headphones or Bluetooth?'),
 ('Microphone not working', 'mic not working|microphone not working|cant talk in discord|voice input not working', 'Review microphone permissions and input device selection in Windows Settings; test using Voice Recorder.', 'Does the microphone work in any other app?'),
 ('Webcam problems', 'camera not working|webcam not working|camera blocked', 'Check camera privacy permissions and any physical shutter switch; close apps that might be using the camera.', 'Is there an error code or black preview?'),
 ('Display problems', 'screen flicker|flickering monitor|display problem|screen tearing', 'Check cable connection, refresh rate and official GPU drivers; note if it happens outside games.', 'Does it also flicker on the Windows desktop?'),
 ('Low game FPS', 'fps drop|low fps|game stutter|gaming lag|frame drops', 'Check GPU/CPU usage and temperatures; install official GPU drivers; reduce demanding graphics settings before tweaking Windows.', 'Which game and when does it stutter?'),
 ('App crashing', 'app crashing|program keeps closing|application crash|crashes to desktop', 'Update the app and Windows, check Reliability Monitor, and note any exact error; avoid deleting system files.', 'Which app crashes and what error is displayed?'),
 ('App not installing', 'installation failed|installer error|cannot install|app wont install|setup failed', 'Confirm sufficient free space and use the software publisher’s official installer; review the exact error message.', 'Which installer and error code?'),
 ('Unknown startup program', 'unknown startup|suspicious startup|strange startup|disable startup', 'Open Startup, inspect publisher and file location; only disable optional user-level entries you recognise.', 'What is the startup entry name?'),
 ('Browser notifications', 'website notifications|browser notification spam|fake virus popup|browser popups', 'Review browser site-notification permissions and remove unknown sites; ignore frightening popups asking you to pay or call.', 'Do the alerts appear only when your browser is open?'),
 ('Browser redirects', 'browser redirect|search hijack|homepage changed|unknown search engine', 'Review extensions, default search provider and site permissions; scan with your active antivirus.', 'Which browser is affected?'),
 ('Unwanted extensions', 'bad extension|malicious extension|browser extension|unwanted addon', 'Remove extensions you do not recognise using the browser’s extension manager; restart browser and scan if symptoms persist.', 'Do you know when the extension appeared?'),
 ('Cookies and site data', 'delete cookies|clear cookies|cookie problem|site data|logged out websites', 'Use Sovela → Cleaner → Cookies & site data to open your browser’s own controls. This can sign you out of websites.', 'Which browser do you use?'),
 ('Suspicious download', 'suspicious download|untrusted file|is this exe safe|unknown file|malware download', 'Do not execute the file; inspect it in Sovela → Downloads and scan it with your active antivirus. Metadata alone cannot prove safety.', 'Where did you get the file?'),
 ('Windows Defender', 'microsoft defender|defender passive|defender off|windows security protection', 'Open Windows Security and confirm which antivirus is active. Avoid running multiple real-time engines in conflict.', 'What does Windows Security currently report?'),
 ('Avast problems', 'avast|avast adverts|avast popups', 'Review Avast’s notification and silent-mode preferences. Keep genuine protection alerts enabled; avoid disabling shields to suppress marketing.', 'Are you seeing adverts, performance slowdowns or actual detections?'),
 ('Norton problems', 'norton antivirus|norton popup|norton ads|norton warning', 'Check the product’s notification and subscription settings. Verify alerts in the installed app, not through a web popup.', 'What is the exact alert text?'),
 ('McAfee problems', 'mcafee|mcafee notification|mcafee popup', 'Open the official installed app to check alerts and notification options; ignore unexpected support phone numbers on websites.', 'Is this a program notification or browser notification?'),
 ('Bitdefender problems', 'bitdefender', 'Check the official app’s protection status and notification options; leave malware protections enabled.', 'Is the issue an alert, performance or detection?'),
 ('Malwarebytes questions', 'malwarebytes', 'Use the official app to view detection details and scan history; do not assume a detection from an unfamiliar filename alone.', 'What exact item was flagged?'),
 ('Trojan alert', 'trojan|virus detected|malware detected|threat found', 'Do not run a flagged file; inspect the alert in the active antivirus history and follow trusted cleanup recommendations.', 'What is the detection name and which product reported it?'),
 ('Ransomware warning', 'ransomware|encrypted files|ransom note|files encrypted', 'If encryption is actively progressing, disconnect the PC from networks; avoid connecting backup drives and obtain trusted incident-response help.', 'Are files already inaccessible or is this just an alert?'),
 ('Phishing', 'phishing|fake email|suspicious email|fake login|dodgy link', 'Do not click links; visit the service through its official website. If you entered credentials, change them from a trusted device.', 'Did you click anything or enter a password?'),
 ('Password stolen', 'password leaked|account hacked|stolen password|entered my password|password breach', 'Change the affected password on the official website, sign out other sessions and enable MFA; change reused passwords elsewhere.', 'Is this an email, gaming or banking account?'),
 ('Account takeover', 'account compromised|someone logged into|unknown login|hacked account', 'Use the official recovery channel, secure your recovery email and review devices/sessions before trusting messages from the account.', 'Can you still sign in yourself?'),
 ('Remote access scam', 'remote access scam|teamviewer scam|anydesk scam|someone controlling my pc', 'Disconnect from the internet if an unknown person has live access; do not share more codes; seek trusted support and secure accounts.', 'Is another person currently connected to your PC?'),
 ('Pop-up scam', 'call microsoft number|security support number|fake microsoft alert|support scam', 'Close the browser tab without interacting with its buttons; no legitimate web page can scan your PC by itself.', 'Did you install anything or call a number?'),
 ('Suspicious QR code', 'qr code scam|unknown qr|scan qr phishing', 'Treat unfamiliar QR links like any untrusted link; inspect the target domain before signing in or paying.', 'Did the code open a website or request a payment?'),
 ('Two-factor authentication', '2fa|mfa|authenticator|two factor|verification code', 'Use a trusted authenticator or security key and keep recovery codes safe. Never share one-time codes with unexpected callers.', 'Are you setting up MFA or troubleshooting a code?'),
 ('Lost files', 'deleted my files|missing files|lost documents|where are my files', 'Check Recycle Bin and cloud trash first; avoid installing untrusted recovery tools onto the affected drive.', 'Were the files deleted, moved or encrypted?'),
 ('Backups', 'backup|restore point|file history|recovery drive', 'Maintain backups of important files and test restoring a sample; keep a copy separate from the PC.', 'Do you want to back up documents or the whole PC?'),
 ('Encryption', 'bitlocker|encrypted drive|recovery key', 'Find your BitLocker recovery key through your legitimate Microsoft or organisation account; never share it publicly.', 'Is Windows requesting a recovery key right now?'),
 ('Windows permissions', 'access denied|permission denied|administrator rights|need admin access', 'Check whether the app/file is from a trusted source; do not disable UAC or change system-folder ownership blindly.', 'What action triggered the access error?'),
 ('Windows notification noise', 'too many notifications|notification spam|turn off notifications', 'Use Windows Settings → System → Notifications to control non-security interruptions; keep critical security alerts on.', 'Which app is sending the notifications?'),
 ('Clean temporary files', 'clean my pc|pc cleaner|clear temp|temporary files|clean junk', 'Open Sovela → Cleaner; preview categories and select only the ones you want. Files are sent to Recycle Bin, not silently removed.', 'Are you trying to recover space or troubleshoot a particular issue?'),
 ('Recycle Bin', 'empty recycle bin|recycle bin full|clear recycle bin', 'Open the Recycle Bin, inspect important items, then empty it only if you no longer need to restore them.', 'Do you need to recover anything before emptying it?'),
 ('Cache cleanup', 'clear cache|browser cache|cached files', 'Sovela can preview old browser cache when browsers are closed. Clearing cache can cause sites to load slower temporarily.', 'Which browser should be cleaned?'),
 ('Privacy settings', 'tracking|privacy|telemetry|who sees my data', 'Review Windows privacy permissions and browser settings. Sovela’s local checks do not automatically upload files.', 'Are you concerned about an app permission or online tracking?'),
 ('Suspicious process', 'unknown process|suspicious process|strange background task|task manager process', 'Record the name, publisher and executable location; do not end unfamiliar Windows processes without identification.', 'What is the full process name?'),
 ('Task Scheduler', 'scheduled task|task scheduler|unknown scheduled job', 'Review tasks in Windows Task Scheduler; Sovela does not disable scheduled services or security maintenance tasks.', 'Which task name concerns you?'),
 ('Email spam', 'spam email|junk mail|unwanted email', 'Use your email provider’s spam controls. Do not click unsubscribe links in clearly malicious messages.', 'Is the message an advert or a suspicious sign-in request?'),
 ('Windows activation', 'activation error|windows not activated|product key', 'Use Windows Settings → System → Activation and Microsoft’s activation troubleshooter; avoid unofficial activators.', 'What activation error is shown?'),
 ('Battery drain', 'battery drains|poor battery life|laptop battery dies', 'Check Windows battery usage by app, display brightness and power mode; update firmware from the manufacturer.', 'Is the battery draining while asleep or while in use?'),
 ('Sleep and wake', 'computer wont sleep|wakes by itself|sleep mode issue', 'Review Windows power settings and wake-capable devices; disconnect recently added peripherals as a test.', 'Does it fail to sleep or wake unexpectedly?'),
 ('Printer trouble', 'printer offline|printer not working|print queue stuck', 'Check power/network connection, clear the stuck print job through Windows Settings and update from the printer manufacturer.', 'Does Windows detect the printer?'),
 ('Cloud sync trouble', 'onedrive not syncing|sync error|dropbox not syncing', 'Check sync-app status and account connection; do not delete local synced folders in an attempt to repair syncing.', 'Which sync service shows an error?'),
 ('Unknown executable', 'unknown exe|exe suspicious|strange executable|unknown installer', 'Do not run an unexpected executable. Inspect its publisher and use your trusted antivirus to scan it.', 'Where did you find the executable?'),
 ('Browser sign-in loop', 'keeps logging out|sign in loop|browser login issue|login loop', 'Cookies or browser settings may be blocked; inspect third-party cookie rules and extensions before clearing data.', 'Is it one website or every site?'),
 ('Slow shutdown', 'slow shutdown|takes long to shut down|shutting down forever', 'Close apps normally, check pending updates and avoid forcibly ending system processes unless necessary.', 'Does Windows display an app waiting to close?'),
 ('Windows search broken', 'search not working|start menu search broken|windows search issue', 'Restart normally and use Windows Search troubleshooting options before changing indexing settings.', 'Does Start open but search find nothing?'),
 ('Clipboard trouble', 'clipboard not working|copy paste broken|cant paste', 'Test another app and restart the affected program; check clipboard-history settings.', 'Does copying work in Notepad?'),
 ('Time incorrect', 'wrong clock|time incorrect|date wrong|time sync', 'Check timezone and automatic time sync in Windows Settings. Incorrect time can cause website certificate errors.', 'Is the timezone or actual clock time wrong?'),
 ('Certificate warnings', 'certificate error|not secure connection|ssl error|privacy error browser', 'Check date and time; verify the website address and avoid bypassing certificate warnings on login/payment pages.', 'Is it happening on one site or many?'),
 ('System file corruption', 'sfc error|dism error|corrupt system files|windows corruption', 'Use official Windows recovery documentation and back up important files before repair operations.', 'What exact SFC or DISM message appears?'),
 ('Device storage errors', 'drive error|bad sectors|smart warning|disk failing', 'Back up important data immediately; avoid intensive cleanup/benchmarks until the drive has been assessed.', 'Are you seeing an actual SMART warning or missing files?'),
]

def diagnose(question):
    """Return evidence-bounded topic help for clear phrases, otherwise None."""
    text = re.sub(r'\s+', ' ', (question or '').casefold()).strip()
    if not text:
        return None
    hits=[]
    for title,phrases,steps,follow in DIAGNOSES:
        match=[p for p in phrases.split('|') if p in text]
        if match:
            # Prefer longer distinguishing phrases; prevents broad keyword overmatching.
            hits.append((max(map(len,match)),title,steps,follow))
    if not hits:
        return None
    hits.sort(reverse=True)
    _,title,steps,follow=hits[0]
    return (f'POSSIBLE TOPIC: {title.upper()}\n\n'
            'This is a suggested troubleshooting route, not a confirmed diagnosis.\n\n'
            f'FIRST STEPS\n• {steps}\n\nTO NARROW IT DOWN\n{follow}')
