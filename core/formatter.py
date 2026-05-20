"""USB formatlama akışı.

Hedef sürücüde tüm bölüm tablosu ve veri silinir; tek bir bölüm oluşturulup
seçilen dosya sistemiyle (FAT32 / NTFS / exFAT / ext4) biçimlendirilir.

`USBFormatter` `USBWriter`/`USBDumper` ile aynı thread + callback desenini
kullanır: `start()` daemon thread başlatır, ilerleme/durum/bitiş için
callback'ler GLib.idle_add ile UI'a köprülenir.
"""
import os
import subprocess
import threading
import time

from .disk_detector import get_partition_path, unmount_drive
from .i18n import _


FILESYSTEMS = ('FAT32', 'NTFS', 'exFAT', 'ext4')

DEFAULT_LABELS = {
    'FAT32': 'USB',
    'NTFS':  'USB',
    'exFAT': 'USB',
    'ext4':  'usb',
}

# mkfs çağrılarında kullanılacak maksimum etiket uzunlukları
MAX_LABEL_LEN = {
    'FAT32': 11,
    'NTFS':  32,
    'exFAT': 11,
    'ext4':  16,
}


def find_mkfs(fs):
    """Seçilen dosya sistemi için mkfs ikilisinin yolunu döner; yoksa None."""
    candidates = {
        'FAT32': ('mkfs.fat', 'mkfs.vfat'),
        'NTFS':  ('mkfs.ntfs',),
        'exFAT': ('mkfs.exfat', 'mkexfatfs'),
        'ext4':  ('mkfs.ext4',),
    }
    for cmd in candidates.get(fs, ()):
        r = subprocess.run(['which', cmd], capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
    return None


def sanitize_label(fs, label):
    """Dosya sistemine göre etiketi normalize eder ve uzunluk sınırını uygular.

    Kontrol karakterleri (\\x00-\\x1f, \\x7f) ve baştaki kısa çizgiler atılır
    (mkfs argv'sinde flag gibi parse edilmesin diye). FAT32 için uppercase
    yapılır. Sonuçta boş kalırsa filesystem'a özel varsayılan döner.
    """
    raw = label or ''
    cleaned = ''.join(ch for ch in raw if ord(ch) >= 0x20 and ch != '\x7f')
    cleaned = cleaned.strip().lstrip('-').strip()
    if not cleaned:
        cleaned = DEFAULT_LABELS.get(fs, 'USB')
    if fs == 'FAT32':
        cleaned = cleaned.upper()
    return cleaned[:MAX_LABEL_LEN.get(fs, 11)]


class USBFormatter:
    def __init__(self, drive_path, filesystem, label, partition_scheme,
                 on_progress, on_status, on_done):
        self.drive_path       = drive_path
        self.filesystem       = filesystem        # 'FAT32' | 'NTFS' | 'exFAT' | 'ext4'
        self.label            = sanitize_label(filesystem, label)
        self.partition_scheme = partition_scheme  # 'MBR' | 'GPT'
        self.on_progress      = on_progress
        self.on_status        = on_status
        self.on_done          = on_done
        self._cancelled       = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._cancelled = True

    def _check(self):
        if self._cancelled:
            raise InterruptedError(_('res.cancelled'))

    # ------------------------------------------------------------------

    def _run(self):
        try:
            mkfs = find_mkfs(self.filesystem)
            if not mkfs:
                raise Exception(_('err.mkfs_missing', fs=self.filesystem))

            self.on_progress(0.0)
            self.on_status(_('st.unmount'))
            unmount_drive(self.drive_path)
            self._check()
            self.on_progress(0.15)

            self.on_status(_('st.wipe_sigs'))
            subprocess.run(['wipefs', '-a', self.drive_path],
                           capture_output=True)
            self._check()
            self.on_progress(0.30)

            self.on_status(_('st.partition_table'))
            self._create_partition_table()
            self._check()
            self.on_progress(0.50)

            partition = get_partition_path(self.drive_path, 1)
            self._wait_for_partition(partition)
            self._check()
            self.on_progress(0.65)

            self.on_status(_('st.fmt_progress',
                             fs=self.filesystem, label=self.label))
            self._format_partition(mkfs, partition)
            self._check()
            self.on_progress(0.95)

            self.on_status(_('st.sync'))
            subprocess.run(['sync'], check=True)
            self.on_progress(1.0)

            self.on_done(True, _('fmt.done',
                                 fs=self.filesystem,
                                 label=self.label,
                                 scheme=self.partition_scheme))
        except InterruptedError as e:
            self.on_done(False, str(e))
        except Exception as e:
            self.on_done(False, _('err.generic', detail=e))

    # ------------------------------------------------------------------

    def _create_partition_table(self):
        label = 'msdos' if self.partition_scheme == 'MBR' else 'gpt'
        subprocess.run(['parted', '-s', self.drive_path, 'mklabel', label],
                       check=True, capture_output=True)

        # parted için dosya sistemi adı (sadece bölüm tipi tanımlar, asıl format mkfs ile)
        parted_fs = {
            'FAT32': 'fat32',
            'NTFS':  'ntfs',
            'exFAT': 'ntfs',   # exfat parted'te olmayabilir; ntfs tipi en yakını
            'ext4':  'ext4',
        }.get(self.filesystem, 'fat32')

        subprocess.run(
            ['parted', '-s', self.drive_path,
             'mkpart', 'primary', parted_fs, '1MiB', '100%'],
            check=True, capture_output=True,
        )
        if self.partition_scheme == 'MBR':
            subprocess.run(
                ['parted', '-s', self.drive_path, 'set', '1', 'boot', 'on'],
                capture_output=True,
            )
        subprocess.run(['partprobe', self.drive_path], capture_output=True)
        time.sleep(1)

    def _wait_for_partition(self, path, timeout=10):
        for _i in range(timeout * 2):
            if os.path.exists(path):
                return
            time.sleep(0.5)
        raise Exception(_('err.partition_create', path=path))

    def _format_partition(self, mkfs, partition):
        fs = self.filesystem
        if fs == 'FAT32':
            cmd = [mkfs, '-F', '32', '-n', self.label, partition]
        elif fs == 'NTFS':
            cmd = [mkfs, '-f', '-L', self.label, partition]
        elif fs == 'exFAT':
            cmd = [mkfs, '-L', self.label, partition]
        elif fs == 'ext4':
            cmd = [mkfs, '-F', '-L', self.label, partition]
        else:
            raise Exception(_('err.unsupported_fs', fs=fs))

        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise Exception(_('err.mkfs_fail',
                              fs=fs,
                              detail=(r.stderr or r.stdout).strip()))
