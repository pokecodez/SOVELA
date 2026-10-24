"""Sovela accounts: optional owner-configured Supabase email/password authentication.

No developer service-role key or user password is stored in the app.  Windows
DPAPI protects a rotating refresh token belonging to the signed-in OS user.
All paid entitlements must ALSO be enforced by a backend; client UI is not an
access-control boundary.
"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
import re
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit

VERSION = '3.1.1'
MAX_RESPONSE_BYTES = 1_000_000


class AccountError(Exception):
    pass


def local_data():
    return Path(os.environ.get('LOCALAPPDATA') or (Path.home() / '.config')) / 'Sovela'


def bundle_directory():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def read_cloud_config(path=None):
    if path is None:
        # A packaged client reads the public configuration beside Sovela.exe.
        # Source-code runs read the same file beside main.py.
        app_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        path = app_dir / 'sovela_cloud.json'
        if not path.is_file():
            path = bundle_directory() / 'sovela_cloud.json'
    path = Path(path)
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(obj, dict):
            return {}
        url = str(obj.get('supabase_url', '')).strip().rstrip('/')
        key = str(obj.get('supabase_publishable_key', '')).strip()
        parts = urlsplit(url)
        if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 443) or parts.path or parts.query or parts.fragment
            or not key or 'YOUR_' in key.upper()):
            return {'updates_repo': valid_repo(obj.get('updates_repo', ''))}
        return {'supabase_url': url, 'supabase_publishable_key': key,
                'updates_repo': valid_repo(obj.get('updates_repo', ''))}
    except (OSError, ValueError, TypeError):
        return {}


def valid_repo(repo):
    repo = str(repo or '').strip()
    return repo if re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) else ''


class _Blob(ctypes.Structure):
    _fields_ = [('cbData', ctypes.wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data):
    array = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    return _Blob(len(data), ctypes.cast(array, ctypes.POINTER(ctypes.c_ubyte))), array


def dpapi_encrypt(data: bytes):
    if os.name != 'nt':
        raise AccountError('Remember me requires Windows.')
    original, backing = _blob(data)
    output = _Blob()
    crypt = ctypes.windll.crypt32.CryptProtectData
    crypt.argtypes = [ctypes.POINTER(_Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                      ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.DWORD,
                      ctypes.POINTER(_Blob)]
    crypt.restype = ctypes.wintypes.BOOL
    if not crypt(ctypes.byref(original), 'Sovela session', None, None, None, 0,
                 ctypes.byref(output)):
        raise AccountError('Windows could not securely remember this session.')
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def dpapi_decrypt(data: bytes):
    if os.name != 'nt':
        raise AccountError('Saved sessions can only be restored on Windows.')
    original, backing = _blob(data)
    output = _Blob()
    decrypt = ctypes.windll.crypt32.CryptUnprotectData
    decrypt.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.DWORD,
                       ctypes.POINTER(_Blob)]
    decrypt.restype = ctypes.wintypes.BOOL
    if not decrypt(ctypes.byref(original), None, None, None, None, 0,
                   ctypes.byref(output)):
        raise AccountError('This saved login is no longer valid on this Windows account.')
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


class TokenStore:
    def __init__(self, path=None):
        self.path = Path(path or (local_data() / 'session.dpapi'))

    def save(self, refresh_token):
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise AccountError('The service did not return a usable session.')
        ciphertext = dpapi_encrypt(refresh_token.encode('utf-8'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        scratch = self.path.with_suffix('.tmp')
        try:
            with scratch.open('wb') as f:
                f.write(ciphertext)
            scratch.replace(self.path)
        finally:
            scratch.unlink(missing_ok=True)

    def load(self):
        try:
            if self.path.stat().st_size > 16_384:
                return None
            return dpapi_decrypt(self.path.read_bytes()).decode('utf-8')
        except (OSError, UnicodeError, AccountError, ValueError):
            return None

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


@dataclass
class Session:
    access_token: str
    refresh_token: str
    email: str
    user_id: str
    entitlement: dict | None = None


def _sanitize_error(status, text):
    try:
        body = json.loads(text)
        message = str(body.get('msg') or body.get('message') or body.get('error_description') or '')
    except (ValueError, TypeError):
        message = ''
    if status == 429:
        return 'Too many attempts. Please try again later.'
    if status in (401, 403):
        return 'Unable to sign in. Check your email, password, and email verification.'
    if status in (400, 403, 422) and any(word in message.lower() for word in ('invalid otp', 'otp expired', 'token expired', 'token has expired', 'expired or invalid', 'invalid token')):
        return 'That confirmation code is invalid or has expired. Request another code.'
    if status == 422:
        return (message[:150] if message and 'token' not in message.lower()
                else 'Check your email and password and try again.')
    if status >= 500:
        return 'The account service is temporarily unavailable. Please retry.'
    if status == 400 and ('already registered' in message.lower()):
        return 'An account may already exist. Try signing in or resetting your password.'
    return 'The account service could not complete that request. Please try again.'


class SupabaseAccounts:
    def __init__(self, config, store=None, opener=None):
        self.url = config.get('supabase_url', '').rstrip('/')
        self.key = config.get('supabase_publishable_key', '')
        self.store = store or TokenStore()
        self.opener = opener or urllib.request.urlopen
        if not self.url or not self.key:
            raise AccountError('The creator has not connected an account service yet.')

    def request(self, method, path, payload=None, token=None):
        if not path.startswith(('/auth/v1/', '/rest/v1/')):
            raise AccountError('Unsupported account request.')
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        headers = {'apikey': self.key, 'Accept': 'application/json',
                   'Content-Type': 'application/json', 'User-Agent': 'Sovela/2.3'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(self.url + path, data=body, headers=headers, method=method)
        try:
            with self.opener(req, timeout=15) as res:
                raw = res.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise AccountError('The account service returned an unexpectedly large response.')
                return json.loads(raw.decode('utf-8')) if raw else {}
        except urllib.error.HTTPError as e:
            raise AccountError(_sanitize_error(e.code, e.read(4096).decode('utf-8','replace'))) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AccountError('Cannot reach Sovela accounts. Check your internet and try again.') from None
        except (ValueError, UnicodeError):
            raise AccountError('The account service returned an invalid response.') from None

    def signup(self, email, password):
        self._validate(email, password)
        return self._consume_response(
            self.request('POST', '/auth/v1/signup', {'email': email.strip().lower(), 'password': password}),
            allow_pending=True)

    def verify_email_code(self, email, code):
        """Verify Supabase's signup OTP inside Sovela; no localhost callback.

        Requires an administrator to put {{ .Token }} in the project's
        Authentication > Email Templates > Confirm sign up template.
        """
        email = str(email or '').strip().lower()
        code = str(code or '').strip().replace(' ', '')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise AccountError('Enter the email address you signed up with.')
        if not re.fullmatch(r'\d{6,8}', code):
            raise AccountError('Enter the 6–8 digit confirmation code from your email.')
        answer = self.request('POST', '/auth/v1/verify',
                              {'email': email, 'token': code, 'type': 'email'})
        return self._consume_response(answer)

    def resend_confirmation(self, email):
        email = str(email or '').strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise AccountError('Enter the email address you signed up with.')
        self.request('POST', '/auth/v1/resend', {'type': 'signup', 'email': email})

    def signin(self, email, password):
        self._validate(email, password)
        response = self.request('POST', '/auth/v1/token?grant_type=password',
                                {'email': email.strip().lower(), 'password': password})
        return self._consume_response(response)

    @staticmethod
    def _validate(email, password):
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()):
            raise AccountError('Enter a valid email address.')
        if not isinstance(password, str) or len(password) < 8:
            raise AccountError('Use a password with at least 8 characters.')
        if len(password) > 1024:
            raise AccountError('That password is too long.')

    def _consume_response(self, response, allow_pending=False):
        if not isinstance(response, dict):
            raise AccountError('The account service returned an invalid response.')
        if allow_pending and not response.get('access_token'):
            return None  # Email confirmation is required; no authenticated session yet.
        access = response.get('access_token')
        refresh = response.get('refresh_token')
        user = response.get('user') or {}
        if not isinstance(user, dict) or not access or not refresh or not user.get('id'):
            raise AccountError('The account service did not return a valid login.')
        sess = Session(access, refresh, user.get('email') or '', str(user['id']))
        # Only save the rotating refresh token, encrypted for the Windows user.
        self.store.save(refresh)
        sess.entitlement = self.entitlement(sess)
        return sess

    def entitlement(self, session):
        payload = self.request('POST', '/rest/v1/rpc/my_entitlement', {}, session.access_token)
        if not isinstance(payload, dict) or 'tier' not in payload:
            raise AccountError('The subscription database is not configured. Ask the creator to install the SQL setup.')
        return payload

    def resume(self):
        token = self.store.load()
        if not token:
            return None
        response = self.request('POST', '/auth/v1/token?grant_type=refresh_token',
                                {'refresh_token': token})
        return self._consume_response(response)

    def password_reset(self, email):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()):
            raise AccountError('Enter your account email first.')
        self.request('POST', '/auth/v1/recover', {'email': email.strip().lower()})

    def admin_status(self,session):
        value=self.request('POST','/rest/v1/rpc/sovela_is_admin',{},session.access_token)
        return value is True

    def admin_accounts(self,session):
        value=self.request('POST','/rest/v1/rpc/sovela_admin_accounts',{},session.access_token)
        if not isinstance(value,list):
            raise AccountError('Admin account list unavailable.')
        return value[:100]

    def admin_grant(self,session,user_id,days):
        import uuid
        try: uuid.UUID(str(user_id))
        except ValueError:raise AccountError('Invalid account identifier.') from None
        if type(days)!=int or not (1<=days<=365):
            raise AccountError('Grant duration must be between 1 and 365 days.')
        return self.request('POST','/rest/v1/rpc/sovela_admin_grant',
                            {'target_user':str(user_id),'grant_days':days},session.access_token)

    def start_checkout(self,session):
        # Supabase Edge Function only; session user is verified on the SERVER.
        endpoint=self.url+'/functions/v1/create-checkout'
        req=urllib.request.Request(endpoint,data=b'{}',method='POST',headers={
            'apikey':self.key,'Authorization':'Bearer '+session.access_token,
            'Content-Type':'application/json','User-Agent':'Sovela/3.1.1'})
        try:
            with self.opener(req,timeout=20) as response:
                value=json.loads(response.read(20000))
        except (OSError,urllib.error.URLError,ValueError,TypeError):
            raise AccountError('Premium checkout is not available yet.') from None
        url=str(value.get('url','')) if isinstance(value,dict) else ''
        if not url.startswith('https://checkout.stripe.com/'):
            raise AccountError('Checkout did not return a verified Stripe address.')
        return url

    def public_config(self):
        # Public RPC returns only safe text and feature policies.
        return self.request('POST','/rest/v1/rpc/sovela_public_config',{})

    def admin_config(self,session):
        return self.request('POST','/rest/v1/rpc/sovela_admin_config',{},session.access_token)

    def admin_set_config(self,session,setting,value):
        allowed={'trial_days','headline','subline','announcement','min_supported_version','checkout_url'}
        if setting not in allowed:raise AccountError('This setting cannot be edited.')
        return self.request('POST','/rest/v1/rpc/sovela_admin_set_config',
            {'setting_name':setting,'setting_value':str(value)},session.access_token)

    def admin_find(self,session,email):
        text=str(email or '').strip().lower()
        if len(text)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',text):
            raise AccountError('Enter an exact customer email address.')
        return self.request('POST','/rest/v1/rpc/sovela_admin_find_account',
            {'account_email':text},session.access_token)

    def admin_revoke(self,session,user_id):
        import uuid
        try:uuid.UUID(str(user_id))
        except (ValueError,TypeError):raise AccountError('Invalid account ID.') from None
        return self.request('POST','/rest/v1/rpc/sovela_admin_revoke',
            {'target_user':str(user_id)},session.access_token)

    def admin_end_trial(self,session,user_id):
        import uuid
        try:uuid.UUID(str(user_id))
        except (ValueError,TypeError):raise AccountError('Invalid account ID.') from None
        return self.request('POST','/rest/v1/rpc/sovela_admin_end_trial',
            {'target_user':str(user_id)},session.access_token)

    def verify_recovery_code(self,email,code):
        email=str(email or '').strip().lower()
        code=str(code or '').strip().replace(' ','')
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            raise AccountError('Enter the email address you registered with.')
        if not re.fullmatch(r'\d{6,8}',code):
            raise AccountError('Enter the emailed 6–8 digit reset code.')
        response=self.request('POST','/auth/v1/verify',
                {'email':email,'token':code,'type':'recovery'})
        return self._consume_response(response)

    def change_password(self,session,new_password):
        if not isinstance(new_password,str) or len(new_password)<8 or len(new_password)>1024:
            raise AccountError('Use a new password between 8 and 1024 characters.')
        return self.request('PUT','/auth/v1/user',{'password':new_password},session.access_token)

    def signout(self, session):
        self.store.clear()  # immediate local sign-out even if service is offline
        try:
            self.request('POST', '/auth/v1/logout', {}, session.access_token)
        except AccountError:
            pass


def update_info(repo, opener=None):
    repo = valid_repo(repo)
    if not repo:
        return None
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request('https://api.github.com/repos/' + repo + '/releases/latest',
                                     headers={'Accept': 'application/vnd.github+json',
                                              'User-Agent': 'SovelaUpdateChecker/2.3'})
    try:
        with opener(request, timeout=8) as res:
            raw = res.read(100_001)
        if len(raw) > 100_000:
            return None
        result = json.loads(raw)
        tag = str(result.get('tag_name', ''))
        page = str(result.get('html_url', ''))
        if not page.startswith('https://github.com/' + repo + '/releases/tag/'):
            return None
        def ver(s):
            hit = re.search(r'(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)', s)
            return tuple(map(int, hit.groups())) if hit else None
        return {'available': bool(ver(tag) and ver(tag) > ver(VERSION)),
                'tag': tag, 'url': page}
    except (OSError, urllib.error.URLError, ValueError, TypeError):
        return None
