"""Sovela v2.1: meaningful startup preflight, measured cleanup previews,
accurate firewall presentation, quiet assistant and compact utility dashboards.

The backend's safety boundaries are unchanged: no automatic cleanup, no startup
changes at launch, and no malware verdicts inferred from cleanup or firewall.
"""
from __future__ import annotations

import os
import time
import tkinter as tk
from collections import Counter
from datetime import datetime

from sovela_ai import SovelaApp, open_windows_security
from sovela_care import CATEGORIES, list_startups, scan_cleanup
from sovela_ui_v19 import SovelaBounceApp
from sovela_ui_v15 import (SLATE_BG, SLATE_MUTED, SLATE_GREEN,
    SLATE_GREEN_SOFT, SLATE_LINE, SLATE_FONT, SLATE_INK_SOFT,
    SLATE_TEXT, SLATE_CARD, WHITE, ACTIVE)

WELCOME = ("Hello! I'm Sovela, your PC security and care assistant. "
           "Tell me what's happening—for example, a slow PC, a Windows error, "
           "a suspicious download, or an antivirus warning—and I'll help you "
           "work through safe next steps. I can also explain Sovela's real "
           "security checks.\n\n"
           "Guided answers work offline. Full AI conversations require the "
           "developer's online service to be connected; I won't pretend otherwise.")

AUTOMATIC = ('temp', 'cache', 'reports', 'dumps')


def firewall_enabled(raw):
    """Interpret both PowerShell's typed JSON bool and string/enum representations.

    Return None, never a guessed status, for absent or unsupported values.
    """
    if raw is True:
        return True
    if raw is False:
        return False
    if isinstance(raw, str):
        normalized = raw.strip().casefold()
        if normalized in ('true', 'on', 'enabled', '1'):
            return True
        if normalized in ('false', 'off', 'disabled', '0'):
            return False
    if isinstance(raw, int) and not isinstance(raw, bool):
        if raw == 1:
            return True
        if raw == 0:
            return False
    return None


def firewall_report(data):
    if not isinstance(data, dict) or data.get('firewall_error'):
        return 'Status unavailable — check Windows Security'
    profiles = data.get('firewall')
    if isinstance(profiles, dict):
        profiles = [profiles]
    if not isinstance(profiles, list) or not profiles:
        return 'Status unavailable — check Windows Security'
    values = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get('Name', profile.get('name', ''))).strip().casefold()
        if name not in ('domain', 'private', 'public'):
            continue
        value = firewall_enabled(profile.get('Enabled', profile.get('enabled')))
        values[name] = 'On' if value is True else 'Off' if value is False else 'Unavailable'
    if not values:
        return 'Status unavailable — check Windows Security'
    return '  ·  '.join(f'{name.title()}: {values.get(name, "Unavailable")}'
                       for name in ('domain', 'private', 'public'))


def estimate_bytes(preview, category):
    """Potential old eligible bytes, not guaranteed recovered disk space."""
    if not isinstance(preview, dict):
        return None
    record = preview.get(category, {})
    if not isinstance(record, dict):
        return None
    try:
        return max(0, int(record.get('bytes', 0)))
    except (ValueError, TypeError):
        return None


def pretty_estimate(num):
    if num is None:
        return 'Not checked'
    if num >= 1024**3:
        return f'{num / 1024**3:.1f} GB'
    if num >= 1024**2:
        return f'{num / 1024**2:.0f} MB' if num >= 10*1024**2 else f'{num / 1024**2:.1f} MB'
    if num > 0:
        return f'{max(0.01, num / 1024**2):.2f} MB'
    return '0 MB'


class SovelaCarePlusApp(SovelaBounceApp):
    BOOT_WAIT_SECONDS = 6.0

    def __init__(self, root):
        self._preflight_started = False
        self._preflight_deadline = 0.0
        self._estimate_labels = {}
        self._activity_opened_at = datetime.now().strftime('%H:%M')
        super().__init__(root)
        root.title('Sovela | Slate v2.1')
        self.messages = [('sovela', WELCOME)]
        self._replace_footer_version(self.frame)

    def _replace_footer_version(self, widget):
        super()._replace_footer_version(widget)
        def relabel(w):
            try:
                if isinstance(w, tk.Label):
                    value = str(w.cget('text'))
                    if 'v1.9' in value:
                        w.configure(text=value.replace('v1.9', 'v2.1'))
                for child in w.winfo_children():
                    relabel(child)
            except tk.TclError:
                pass
        relabel(widget)

    def _startup_overlay(self):
        super()._startup_overlay()
        # Read-only background enumeration. No launch-time deletion, disable or
        # virus scan. Both tasks run asynchronously with bounded UI waiting.
        if not self._preflight_started and os.name == 'nt':
            self._preflight_started = True
            self._preflight_deadline = time.monotonic() + self.BOOT_WAIT_SECONDS
            self.working_startups = True
            self.care_busy = True
            self._boot_stage.set('Inspecting startup apps and cleanable files…')
            self.run_job('startups', list_startups)
            self.run_job('care_preview', scan_cleanup)

    def _warm_next_page(self):
        total = len(self._WARM_PAGES)
        if (self._boot_step >= total and self._booting and self._preflight_started and
            time.monotonic() < self._preflight_deadline and
            (self.working_startups or self.care_busy)):
            self._set_boot_percent(93)
            self._boot_stage.set('Checking startup entries and cleanup estimates…')
            self.root.after(110, self._warm_next_page)
            return
        super()._warm_next_page()

    def receive_security(self, data):
        super().receive_security(data)
        self.security_details['firewall'] = firewall_report(data)
        # Security checks should update Protection and Activity, not interrupt a
        # conversation with an unsolicited second Sovela greeting.
        self.messages = [(role, text) for role, text in self.messages
                         if not (role == 'sovela' and
                                 text.startswith('I’ve received your latest Windows security check.'))]
        if not self.messages:
            self.messages = [('sovela', WELCOME)]

    def cleaner_page(self):
        self._estimate_labels = {}
        super().cleaner_page()
        for key, (_edge, inside, _heading, marker, _detail) in self._quick_clean_widgets.items():
            parent = marker.master
            label = tk.Label(parent, text='', bg=ACTIVE if self.clean_choices[key].get() else WHITE,
                             fg=SLATE_INK_SOFT, font=(SLATE_FONT, 8, 'bold'),
                             anchor='e')
            label.pack(side='right', padx=(0, 6))
            self._estimate_labels[key] = label
            self.tip(label, 'Estimated eligible files',
                     'Measured bytes in old files from allowed folders. Moving files to Recycle Bin does not free disk space until you empty it. Estimates can change.')
            # Preserve the whole-card click target.
            label.configure(cursor='hand2')
            label.bind('<Button-1>', lambda _e, k=key: self._toggle_tile(k))
        self._update_estimates()
        footer = self._label(self.view,
            'Figures are potential bytes found, not guaranteed free space. Files go to Recycle Bin after your confirmation.',
            8, color=SLATE_MUTED, wraplength=690)
        footer.pack(anchor='w', pady=(4, 0))

    def _update_estimates(self):
        for key, label in self._estimate_labels.items():
            try:
                if not label.winfo_exists():
                    continue
                amount = estimate_bytes(self.clean_preview, key)
                label.configure(text='Checking…' if amount is None and self.care_busy
                                else pretty_estimate(amount))
            except tk.TclError:
                pass

    def _selection_changed(self):
        super()._selection_changed()
        self._update_estimates()

    def activity_page(self):
        self._page_header('Activity', 'Your recent actions and the latest information Sovela actually collected.')
        summary = tk.Frame(self.view, bg=SLATE_BG)
        summary.pack(fill='x', pady=(0, 12))
        detected = len(self.startups.get('items', [])) if isinstance(self.startups, dict) else None
        total = sum(estimate_bytes(self.clean_preview, k) or 0 for k in AUTOMATIC) if self.clean_preview else None
        cards = (
            ('ACTIONS THIS SESSION', str(len(self.activity)), 'Stored only until you close Sovela'),
            ('STARTUP ENTRIES', str(detected) if detected is not None else 'Not checked', 'Read-only inspection unless you choose a change'),
            ('CLEANUP CANDIDATES', pretty_estimate(total), 'Potential bytes, not yet freed'),
        )
        for i, (heading, metric, explanation) in enumerate(cards):
            edge, inside = self._surface(summary, padding=12)
            edge.grid(row=0, column=i, sticky='nsew', padx=(0, 8 if i < 2 else 0))
            summary.grid_columnconfigure(i, weight=1, uniform='activity')
            self._label(inside, heading, 8, True, color=SLATE_MUTED).pack(anchor='w')
            self._label(inside, metric, 15, True).pack(anchor='w', pady=(7, 4))
            self._label(inside, explanation, 8, color=SLATE_MUTED, wraplength=175).pack(anchor='w')
        status = tk.Frame(self.view, bg=SLATE_BG)
        status.pack(fill='x', pady=(1, 9))
        self._label(status, 'LATEST INFORMATION', 9, True, color=SLATE_MUTED).pack(anchor='w', pady=(0, 7))
        detail = ('Windows protection checked' if self.last_data else 'No Windows protection result yet')
        self._label(status, '●  '+detail, 10, color=SLATE_GREEN if self.last_data else SLATE_MUTED).pack(anchor='w')
        self._label(status, '●  '+str(getattr(self, 'device_scan_message', 'No malware scan requested.'))[:95],
                    9, color=SLATE_INK_SOFT, wraplength=650).pack(anchor='w', pady=(3, 0))
        line = tk.Frame(self.view, bg=SLATE_BG)
        line.pack(fill='x', pady=(6, 8))
        self._label(line, 'RECENT EVENTS', 9, True, color=SLATE_MUTED).pack(side='left')
        self._button(line, 'Clear log', self.clear_activity, False, True).pack(side='right')
        edge, inner = self._surface(self.view, padding=10)
        edge.pack(fill='both', expand=True)
        rows = list(reversed(self.activity[-7:]))
        if not rows:
            self._label(inner, 'No actions recorded yet. Use a tool to see its results here.',
                        10, color=SLATE_MUTED).pack(anchor='w', pady=9)
        for index, line_text in enumerate(rows):
            self._label(inner, ('✓  ' if ' · done' in line_text else '•  ') + line_text[:100],
                        9, color=SLATE_TEXT, wraplength=650).pack(anchor='w', pady=4)
            if index != len(rows) - 1:
                tk.Frame(inner, bg=SLATE_LINE, height=1).pack(fill='x', pady=(3, 1))
        buttons = tk.Frame(self.view, bg=SLATE_BG)
        buttons.pack(fill='x', pady=(9, 0))
        self._button(buttons, 'Protection', lambda: self.show_tab('Protection'), False, True).pack(side='left')
        self._button(buttons, 'Cleaner', lambda: self.show_tab('Cleaner'), False, True).pack(side='left', padx=(8, 0))
        self._button(buttons, 'Startup', lambda: self.show_tab('Startup'), False, True).pack(side='left', padx=(8, 0))

    def tools_page(self):
        self._page_header('Tools', 'Useful Windows utilities, one click away.')
        shortcuts = [
            ('◇', 'Windows Security', 'Antivirus & firewall', open_windows_security),
            ('↻', 'Windows Update', 'Install system patches', lambda: self.open_settings('ms-settings:windowsupdate', 'Windows Update')),
            ('≡', 'Startup apps', 'Control launch programs', lambda: self.open_settings('ms-settings:startupapps', 'Startup Apps')),
            ('✧', 'Storage', 'Manage disk usage', lambda: self.open_settings('ms-settings:storagesense', 'Storage settings')),
            ('▣', 'Task Manager', 'Processes & performance', self.open_task_manager),
            ('▤', 'Installed apps', 'Review or uninstall apps', lambda: self.open_settings('ms-settings:appsfeatures', 'Installed apps')),
            ('◎', 'Network', 'Connection troubleshooting', lambda: self.open_settings('ms-settings:network-status', 'Network settings')),
            ('⟲', 'Recovery', 'Windows recovery options', lambda: self.open_settings('ms-settings:recovery', 'Recovery settings')),
            ('☼', 'Security history', 'View threat detections', lambda: self.open_settings('windowsdefender://threat', 'Protection history')),
        ]
        grid = tk.Frame(self.view, bg=SLATE_BG)
        grid.pack(fill='both', expand=True)
        for i, (icon, title, description, command) in enumerate(shortcuts):
            edge, inner = self._surface(grid, padding=11)
            edge.grid(row=i//3, column=i%3, sticky='nsew',
                      padx=(0, 8 if i%3<2 else 0), pady=(0, 8))
            grid.grid_columnconfigure(i%3, weight=1, uniform='utilities')
            row = tk.Frame(inner, bg=WHITE)
            row.pack(fill='x')
            self._label(row, icon, 18, color=SLATE_GREEN).pack(side='left')
            self._label(row, title, 10, True).pack(side='left', padx=(7, 0))
            self._label(inner, description, 8, color=SLATE_MUTED).pack(anchor='w', pady=(5, 7))
            self._button(inner, 'Open ↗', command, False, True).pack(anchor='w')
        self._label(self.view,
                    'These open Microsoft Windows utilities. Sovela does not change their settings automatically.',
                    8, color=SLATE_MUTED).pack(anchor='w', pady=(8, 0))
