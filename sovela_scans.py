"""Request Defender scans, then verify recorded completion before reporting success.

Never reports 'clean' or 'no malware' from the command exit code. Some Windows
installations can't expose a matching completion stamp: those get UNVERIFIED.
"""
import json
import os
import subprocess
import time
from datetime import datetime

SCAN_PS = r'''
$ErrorActionPreference = 'Stop'
try {
  $mode = $env:SOVELA_SCAN_MODE
  if ($mode -notin @('quick','full')) { throw 'Invalid scan type' }
  $before = Get-MpComputerStatus -ErrorAction Stop
  if ([string]$before.AMRunningMode -ne 'Normal' -or !$before.AntivirusEnabled -or !$before.RealTimeProtectionEnabled) {
    @{ outcome='inactive'; detail='Microsoft Defender is not active.' } | ConvertTo-Json -Compress
    exit 3
  }
  $at = Get-Date
  if ($mode -eq 'quick') {
    $previous = $before.QuickScanEndTime
    Start-MpScan -ScanType QuickScan -ErrorAction Stop
  } else {
    $previous = $before.FullScanEndTime
    Start-MpScan -ScanType FullScan -ErrorAction Stop
  }
  # Start-MpScan can return before Defender has recorded the end time.
  # Wait for authoritative evidence. Do not invent a percent-complete figure.
  $deadline = (Get-Date).AddHours(3)
  $complete = $false
  $end = $null
  while ((Get-Date) -lt $deadline) {
    $current = Get-MpComputerStatus -ErrorAction Stop
    if ($mode -eq 'quick') { $end = $current.QuickScanEndTime }
    else { $end = $current.FullScanEndTime }
    if ($end -is [datetime] -and $end -gt $previous -and $end -ge $at.AddSeconds(-5)) {
      $complete = $true; break
    }
    Start-Sleep -Seconds 4
  }
  if ($complete) {
    @{outcome='complete'; completed_at=([datetime]$end).ToString('o'); detail='Windows recorded the scan completion.'} | ConvertTo-Json -Compress
  } else {
    @{outcome='unverified'; detail='Defender did not expose a new scan completion timestamp within the monitoring window.'} | ConvertTo-Json -Compress
  }
} catch {
  # Deliberately never output the exception: it may contain local sensitive paths.
  @{outcome='failed'; detail='Windows did not complete or confirm the scan request.'} | ConvertTo-Json -Compress
  exit 5
}
'''


def _parse_result(output):
    # Invoke PowerShell with a strict final JSON contract.
    for line in reversed(output.splitlines()):
        line = line.lstrip('\ufeff').strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and obj.get('outcome') in ('inactive','complete','unverified','failed'):
                    return obj
            except ValueError:
                pass
    raise RuntimeError('Defender did not return a readable scan result. Check Windows Security.')


def run_defender_scan(mode):
    if mode not in ('quick','full'):
        raise ValueError('Unsupported scan type.')
    if os.name != 'nt':
        raise RuntimeError('This scanner requires Windows and an active Microsoft Defender installation.')
    environ = os.environ.copy()
    environ['SOVELA_SCAN_MODE'] = mode
    started = time.monotonic()
    try:
        cp = subprocess.run(
            ['powershell.exe','-NoProfile','-NonInteractive','-Command',SCAN_PS],
            capture_output=True,text=True,timeout=3*3600+180,encoding='utf-8',errors='replace',
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=environ)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Sovela reached its scan monitoring limit. Check Windows Security for the scan state.') from exc
    except OSError as exc:
        raise RuntimeError('Could not start Microsoft Defender. Use Windows Security instead.') from exc
    data = _parse_result(cp.stdout)
    if data['outcome']=='inactive':
        raise RuntimeError('Defender is not your active antivirus. Open Windows Security and scan with your active provider.')
    if data['outcome']=='failed' or cp.returncode != 0:
        raise RuntimeError('Defender did not confirm that the scan succeeded. Review Windows Security.')
    outcome = data['outcome']
    elapsed = max(0,round(time.monotonic()-started))
    if outcome=='complete' and cp.returncode==0:
        message = ('Microsoft Defender recorded that the scan finished. Review Windows Security → '
                   'Protection history for detected threats and any actions. A finished scan is not a guarantee the PC is malware-free.')
    else:
        outcome='unverified'
        message = ('The scan was requested, but its completion could not be verified. '
                   'Open Windows Security to see whether it is still running and review results.')
    return {'mode':mode,'outcome':outcome,'duration_seconds':elapsed,
            'finished_at':datetime.now().strftime('%H:%M'),
            'completed_at':data.get('completed_at') if outcome=='complete' else None,
            'message':message}
