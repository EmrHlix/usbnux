import struct
import subprocess


def analyze_iso(iso_path):
    """ISO'nun Windows mu Linux mu olduğunu tespit eder."""
    # Yöntem 1: ISO 9660 kök dizinini doğrudan oku (dış araç gerektirmez)
    if _check_by_iso_directory(iso_path):
        return 'windows'
    # Yöntem 2: Volume Label kontrolü (dış araç gerektirmez)
    if _check_volume_label(iso_path):
        return 'windows'
    # Yöntem 3: 7z ile içerik listesi
    if _check_with_7z(iso_path):
        return 'windows'
    # Yöntem 4: isoinfo ile içerik listesi
    if _check_with_isoinfo(iso_path):
        return 'windows'
    return 'linux'


def get_wim_size_in_iso(iso_path):
    """ISO içindeki install.wim boyutunu döner (bayt), yoksa 0."""
    try:
        result = subprocess.run(
            ['7z', 'l', '-slt', iso_path, 'sources/install.wim'],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stdout.split('\n'):
            if line.lower().startswith('size = '):
                return int(line.split('=')[1].strip())
    except Exception:
        pass
    return 0


# ── Yöntem 1: ISO 9660 dosya sistemi okuma ──────────────────────────────────

def _check_by_iso_directory(iso_path):
    """
    ISO 9660 PVD'den kök dizin dosya listesini okur.
    Windows ISO'larında kök dizinde her zaman BOOTMGR ve SETUP.EXE bulunur.
    """
    try:
        files = _read_iso_root_filenames(iso_path)
        return 'BOOTMGR' in files and 'SETUP.EXE' in files
    except Exception:
        return False


def _read_iso_root_filenames(iso_path):
    """ISO 9660 kök dizinindeki dosya adlarını döner (büyük harf).

    PVD'den okunan root_size kullanıcı (ISO yazarı) kontrolündedir; 32-bit
    unsigned olduğu için 4 GiB'e kadar gidebilir. Düşman ISO bunu maksimuma
    çekerse read() RAM'i şişirir. Aşağıda 16 MiB tavanı uygulanır
    (gerçek root dizinler birkaç KiB'dir, 16 MiB fazlasıyla yeterli).
    """
    SECTOR = 2048
    MAX_ROOT_SIZE = 16 * 1024 * 1024   # DoS koruması

    with open(iso_path, 'rb') as f:
        # Primary Volume Descriptor sektör 16'dadır
        f.seek(16 * SECTOR)
        pvd = f.read(SECTOR)

    if len(pvd) < 190 or pvd[0] != 0x01:
        return set()

    # Kök dizin kaydı PVD içinde 156. bayttadır
    root_dr   = pvd[156:190]
    root_lba  = struct.unpack_from('<I', root_dr, 2)[0]   # little-endian LBA
    root_size = struct.unpack_from('<I', root_dr, 10)[0]  # bayt cinsinden boyut

    if root_size <= 0 or root_size > MAX_ROOT_SIZE:
        return set()

    with open(iso_path, 'rb') as f:
        f.seek(root_lba * SECTOR)
        dir_data = f.read(root_size)

    names   = set()
    offset  = 0
    while offset < len(dir_data):
        dr_len = dir_data[offset]
        if dr_len == 0:
            # Sonraki sektör sınırına atla
            offset = ((offset // SECTOR) + 1) * SECTOR
            continue
        # name_len attacker-controlled — dr_len ile sınırla
        if offset + 33 > len(dir_data):
            break
        name_len = dir_data[offset + 32]
        name_end = min(offset + 33 + name_len, offset + dr_len, len(dir_data))
        raw_name = dir_data[offset + 33:name_end]
        # ISO 9660: dosya adı "AD;1" formatında, sürüm sonekini kaldır
        name = raw_name.decode('ascii', errors='ignore').split(';')[0].strip()
        if name:
            names.add(name.upper())
        offset += dr_len

    return names


# ── Yöntem 2: Volume Label ──────────────────────────────────────────────────

def _check_volume_label(iso_path):
    """
    PVD'den Volume Identifier okur.
    Windows 11/10 ISO etiketleri: CCCOMA_X64FRE_..., CCSA_..., CPBA_...
    """
    try:
        with open(iso_path, 'rb') as f:
            f.seek(16 * 2048 + 40)   # PVD + Volume Identifier alanı
            label = f.read(32).decode('ascii', errors='ignore').strip().upper()
        keywords = ['WIN', 'CCSA', 'CCCOMA', 'CPBA', 'CFRE', 'ULFR', 'ULRM']
        return any(kw in label for kw in keywords)
    except Exception:
        return False


# ── Yöntem 3: 7z ────────────────────────────────────────────────────────────

def _check_with_7z(iso_path):
    try:
        result = subprocess.run(
            ['7z', 'l', iso_path],
            capture_output=True, text=True, timeout=60,
        )
        lower = result.stdout.lower()
        markers = [
            'sources\\install.wim', 'sources/install.wim',
            'sources\\install.esd', 'sources/install.esd',
            'setup.exe', 'bootmgr',
        ]
        return sum(1 for m in markers if m in lower) >= 2
    except Exception:
        return False


# ── Yöntem 4: isoinfo ───────────────────────────────────────────────────────

def _check_with_isoinfo(iso_path):
    try:
        result = subprocess.run(
            ['isoinfo', '-l', '-i', iso_path],
            capture_output=True, text=True, timeout=60,
        )
        out = result.stdout
        return ('BOOTMGR' in out or 'SETUP.EXE' in out) and 'SOURCES' in out
    except Exception:
        return False
