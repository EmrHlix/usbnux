"""ISO butunluk dogrulamasi: sidecar tespiti ve hash hesaplama."""
import hashlib
import os


HASH_LEN = {'md5': 32, 'sha1': 40, 'sha256': 64, 'sha512': 128}
ALGOS = ('sha256', 'sha512', 'sha1', 'md5')
BLOCK_SIZE = 4 * 1024 * 1024

SUMS_FILES = {
    'sha256': ('SHA256SUMS', 'SHA256SUMS.txt', 'sha256sums.txt', 'sha256sum.txt'),
    'sha512': ('SHA512SUMS', 'SHA512SUMS.txt', 'sha512sums.txt'),
    'sha1':   ('SHA1SUMS',   'SHA1SUMS.txt',   'sha1sums.txt'),
    'md5':    ('MD5SUMS',    'MD5SUMS.txt',    'md5sums.txt'),
}


def _is_hex(s):
    return bool(s) and all(c in '0123456789abcdefABCDEF' for c in s)


def detect_algo(hash_str):
    """Uzunluga gore hash algoritmasini cikarir; gecersizse None."""
    h = (hash_str or '').strip().lower()
    if not _is_hex(h):
        return None
    for algo, n in HASH_LEN.items():
        if len(h) == n:
            return algo
    return None


def _read_single(path, iso_name, expected_len):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(None, 1)
                token = parts[0].lower()
                if not (_is_hex(token) and len(token) == expected_len):
                    continue
                if len(parts) == 1:
                    return token
                name = parts[1].lstrip('*').strip()
                if not name or name == iso_name or name.endswith('/' + iso_name):
                    return token
    except OSError:
        return None
    return None


def _read_sums(path, iso_name, expected_len):
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                token = parts[0].lower()
                name  = parts[1].lstrip('*').strip()
                if (_is_hex(token) and len(token) == expected_len
                        and (name == iso_name or name.endswith('/' + iso_name))):
                    return token
    except OSError:
        return None
    return None


def find_sidecar_hash(iso_path):
    """ISO yaninda checksum dosyalari ara.

    Sirasi:
      1) <iso>.sha256 / .sha512 / .sha1 / .md5  (tek-hash sidecar)
      2) SHA256SUMS, SHA512SUMS, ... (sha256sum -b ciktisi)

    Donus: {'sha256': '...', 'sha512': '...'} -- bulunanlar. Ayrica
    'source' anahtariyla algoritma -> kaynak dosya adi sozluk verir:
    {'sha256': 'abc...', 'source': {'sha256': 'SHA256SUMS'}}
    """
    folder = os.path.dirname(iso_path) or '.'
    iso_name = os.path.basename(iso_path)
    found = {}
    source = {}

    for algo in ALGOS:
        cand = os.path.join(folder, iso_name + '.' + algo)
        if os.path.isfile(cand):
            h = _read_single(cand, iso_name, HASH_LEN[algo])
            if h:
                found[algo] = h
                source[algo] = os.path.basename(cand)

    for algo, names in SUMS_FILES.items():
        if algo in found:
            continue
        for n in names:
            cand = os.path.join(folder, n)
            if os.path.isfile(cand):
                h = _read_sums(cand, iso_name, HASH_LEN[algo])
                if h:
                    found[algo] = h
                    source[algo] = n
                    break

    if source:
        found['source'] = source
    return found


def compute_hash(path, algo='sha256', progress_cb=None, cancelled_cb=None):
    """Dosyanin hash'ini hesaplar.

    progress_cb(done_bytes, total_bytes) ilerleme icin cagrilir.
    cancelled_cb() True donerse InterruptedError firlatir.
    """
    if algo not in HASH_LEN:
        raise ValueError(f'desteklenmeyen algoritma: {algo}')
    h = hashlib.new(algo)
    total = os.path.getsize(path)
    done = 0
    with open(path, 'rb') as f:
        while True:
            if cancelled_cb and cancelled_cb():
                raise InterruptedError('hash iptal edildi')
            chunk = f.read(BLOCK_SIZE)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)
    return h.hexdigest()
