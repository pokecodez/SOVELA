"""Non-sensitive Sovela UI preferences saved for this Windows user."""
import json
import os
from pathlib import Path

DEFAULTS = {
    'smooth_motion': True,
    'safe_window_frame': False,
    'motion_style': 'Variety',
    'motion_speed': 'Balanced',
    'scan_notifications': True,
    'scan_error_notifications': True,
    'notification_seconds': 10,
    'show_scan_timer': True,
    'always_on_top': False,
    'hover_hints': True,
    'start_page': 'Overview',
    'scan_opens_page': True,
    'check_at_launch': True,
}
VALID_PAGES = ('Overview', 'Malware Scan', 'PC Health', 'Cleaner')
MOTION_STYLES = ('Variety', 'Tiles', 'Ink', 'Liquid Streaks', 'Glitch Reveal', 'Pixelate')
MOTION_SPEEDS = ('Snappy', 'Balanced', 'Relaxed')


def preferences_file():
    base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.config')
    return base / 'Sovela' / 'preferences.json'


def validated(source):
    result = DEFAULTS.copy()
    if not isinstance(source, dict):
        return result
    for key in ('safe_window_frame','smooth_motion','scan_notifications','scan_error_notifications','show_scan_timer',
                'always_on_top','hover_hints','scan_opens_page','check_at_launch'):
        if type(source.get(key)) is bool:
            result[key] = source[key]
    if source.get('motion_style') in MOTION_STYLES:
        result['motion_style'] = source['motion_style']
    if source.get('motion_speed') in MOTION_SPEEDS:
        result['motion_speed'] = source['motion_speed']
    if source.get('notification_seconds') in (6, 10, 15):
        result['notification_seconds'] = source['notification_seconds']
    if source.get('start_page') in VALID_PAGES:
        result['start_page'] = source['start_page']
    return result


def load(path=None):
    if path is None:
        new_path = preferences_file()
        legacy = new_path.parent.parent / 'GuardianAI' / 'preferences.json'
        path = new_path if new_path.exists() else legacy if legacy.is_file() else new_path
    path = Path(path)
    try:
        if path.stat().st_size > 8192:
            return DEFAULTS.copy()
        return validated(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, UnicodeError):
        return DEFAULTS.copy()


def save(prefs, path=None):
    path = Path(path) if path else preferences_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement so closing the app mid-save cannot corrupt settings.
    scratch = path.with_suffix('.tmp')
    try:
        scratch.write_text(json.dumps(validated(prefs), indent=2), encoding='utf-8')
        scratch.replace(path)
    finally:
        try:
            if scratch.exists(): scratch.unlink()
        except OSError:
            pass
