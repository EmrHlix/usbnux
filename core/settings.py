"""Kullanıcı ayarlarını ~/.config/usbnux/settings.json içinde saklar.

Uygulama pkexec ile root çalıştığı için HOME, pkexec wrapper'ı
tarafından çağıran kullanıcının home'una yönlendirilir. Yazılan dosya
root sahipli olur — dosyayı çağıran kullanıcıya chown ederiz ki
kullanıcı manuel olarak da düzenleyebilsin.
"""
import json
import os
import pwd


CONFIG_SUBDIR = 'usbnux'
CONFIG_FILE   = 'settings.json'

DEFAULTS = {
    'language':     'tr',          # 'tr' | 'en'
    'color_scheme': 'auto',        # 'auto' | 'light' | 'dark'
}


def _config_dir():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(
        os.path.expanduser('~'), '.config')
    return os.path.join(base, CONFIG_SUBDIR)


def _config_path():
    return os.path.join(_config_dir(), CONFIG_FILE)


def load():
    path = _config_path()
    data = dict(DEFAULTS)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            user = json.load(f)
        if isinstance(user, dict):
            data.update({k: v for k, v in user.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return data


def save(settings):
    path = _config_path()
    try:
        os.makedirs(_config_dir(), exist_ok=True)
        clean = {k: settings[k] for k in DEFAULTS if k in settings}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(clean, f, indent=2, ensure_ascii=False)
        _chown_to_invoker(path)
        _chown_to_invoker(_config_dir())
    except OSError:
        pass


def _chown_to_invoker(path):
    """Root yazdığı dosyayı çağıran kullanıcıya devret."""
    for env in ('PKEXEC_UID', 'SUDO_UID'):
        uid = os.environ.get(env)
        if uid and uid.isdigit():
            try:
                pw = pwd.getpwuid(int(uid))
                os.chown(path, pw.pw_uid, pw.pw_gid)
                return
            except (KeyError, OSError):
                continue
