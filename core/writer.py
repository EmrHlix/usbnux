import hashlib
import mmap
import os
import shutil
import subprocess
import tempfile
import threading
import time

from .disk_detector import unmount_drive, get_partition_path
from .i18n import _

BLOCK_SIZE          = 4 * 1024 * 1024          # 4 MB — Windows ağaç kopyalama
LINUX_BLOCK_SIZE    = 16 * 1024 * 1024         # 16 MB — Linux dd-tarzı yazma
DIRECT_ALIGN        = 4096                     # O_DIRECT için tail padding hizası
SYNC_INTERVAL_BYTES = 256 * 1024 * 1024        # 256 MB'de bir fdatasync
FAT32_LIMIT         = 4 * 1024 * 1024 * 1024   # 4 GB


def _find_wimlib():
    """wimlib-imagex komutunun yolunu döner, bulunamazsa None."""
    for cmd in ('wimlib-imagex', 'wim'):
        result = subprocess.run(['which', cmd], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    return None


def _ensure_wimlib():
    """wimlib-imagex yoksa açıklayıcı hata fırlatır.

    Eskiden burada sessizce `apt-get install -y wimtools` çağrılırdı.
    Bu davranış kaldırıldı: root yetkili bir GUI'nin çalışma zamanında
    sürpriz şekilde apt çağırması güven sorunu yaratır. `.deb` paketi ve
    `install.sh` zaten wimtools'u Depends'e koyar; bu hata sadece source
    ağacından elle çalıştıran + install.sh'yi atlayan kullanıcıya çıkar.
    """
    if _find_wimlib():
        return
    raise Exception(_('err.wimtools_missing'))


WIN11_BYPASS_AUTOUNATTEND = """<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
    <settings pass="windowsPE">
        <component name="Microsoft-Windows-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
            <RunSynchronous>
                <RunSynchronousCommand wcm:action="add">
                    <Order>1</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassTPMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>2</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassSecureBootCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>3</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassRAMCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>4</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassStorageCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>5</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\LabConfig /v BypassCPUCheck /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
                <RunSynchronousCommand wcm:action="add">
                    <Order>6</Order>
                    <Path>reg add HKLM\\SYSTEM\\Setup\\MoSetup /v AllowUpgradesWithUnsupportedTPMOrCPU /t REG_DWORD /d 1 /f</Path>
                </RunSynchronousCommand>
            </RunSynchronous>
        </component>
    </settings>
</unattend>
"""


class USBWriter:
    def __init__(self, iso_path, drive_path, iso_type, partition_scheme,
                 on_progress, on_status, on_done,
                 on_file_status=None,
                 bypass_win11_checks=False, verify_after_write=False):
        self.iso_path             = iso_path
        self.drive_path           = drive_path
        self.iso_type             = iso_type
        self.partition_scheme     = partition_scheme
        self.on_progress          = on_progress
        self.on_status            = on_status
        self.on_file_status       = on_file_status or on_status
        self.on_done              = on_done
        self.bypass_win11_checks  = bypass_win11_checks
        self.verify_after_write   = verify_after_write
        self._cancelled           = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._cancelled = True

    # ------------------------------------------------------------------

    def _run(self):
        try:
            if self.iso_type == 'windows':
                self._write_windows()
            else:
                self._write_linux()
        except InterruptedError as e:
            self.on_done(False, str(e))
        except Exception as e:
            self.on_done(False, _('err.generic', detail=e))

    def _check(self):
        if self._cancelled:
            raise InterruptedError(_('res.cancelled'))

    # ------------------------------------------------------------------
    # Linux ISO – doğrudan blok kopyalama

    def _write_linux(self):
        self.on_status(_('st.unmount'))
        unmount_drive(self.drive_path)

        iso_size = os.path.getsize(self.iso_path)
        self.on_status(_('st.iso_write'))

        # O_DIRECT: page cache'i bypass et — ilerleme çubuğu gerçek USB
        # yazım hızını gösterir, sondaki uzun "sync" beklemesi olmaz.
        # Bazı egzotik aygıtlarda O_DIRECT reddedilirse buffered'a düş.
        flags = os.O_WRONLY | os.O_CLOEXEC
        try:
            fd_dst = os.open(self.drive_path, flags | os.O_DIRECT)
            use_direct = True
        except OSError:
            fd_dst = os.open(self.drive_path, flags)
            use_direct = False

        # mmap anonim sayfası page-aligned — O_DIRECT için aligned tampon.
        buf = mmap.mmap(-1, LINUX_BLOCK_SIZE)
        try:
            with open(self.iso_path, 'rb') as src:
                written = 0
                since_sync = 0
                mv = memoryview(buf)
                while True:
                    self._check()
                    n = src.readinto(mv)
                    if not n:
                        break

                    if use_direct:
                        # O_DIRECT yazım boyu blok hizasına yuvarlanmalı;
                        # tail'i sıfırla. En fazla 4095 byte zero padding.
                        pad = (-n) % DIRECT_ALIGN
                        if pad:
                            buf[n:n + pad] = b'\x00' * pad
                        write_size = n + pad
                    else:
                        write_size = n

                    view = mv[:write_size]
                    while view:
                        w = os.write(fd_dst, view)
                        view = view[w:]

                    written += n
                    since_sync += n
                    self.on_progress(min(written, iso_size) / iso_size)
                    self.on_file_status(_(
                        'st.writing_progress',
                        done=written / (1024**2),
                        total=iso_size / (1024**2),
                    ))

                    if since_sync >= SYNC_INTERVAL_BYTES:
                        os.fdatasync(fd_dst)
                        since_sync = 0

            os.fdatasync(fd_dst)
        finally:
            buf.close()
            os.close(fd_dst)

        self.on_status(_('st.sync'))
        subprocess.run(['sync'], check=True)
        self.on_progress(1.0)

        msg = _('res.linux_done')
        if self.verify_after_write:
            self._verify_linux(iso_size)
            msg += _('res.linux_verified')
        self.on_done(True, msg)

    # ------------------------------------------------------------------
    # Windows ISO – bölümleme + FAT32 + dosya kopyalama + WIM bölme

    def _write_windows(self):
        iso_mount = None
        usb_mount = None
        try:
            self.on_status(_('st.unmount'))
            unmount_drive(self.drive_path)

            self.on_status(_('st.partition_table'))
            self._create_partition_table()

            partition = get_partition_path(self.drive_path, 1)
            self._wait_for_partition(partition)

            self.on_status(_('st.fat32_format'))
            result = subprocess.run(
                ['mkfs.fat', '-F', '32', '-n', 'WINDOWS', partition],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise Exception(_('err.mkfs_fat', detail=result.stderr.strip()))

            self.on_status(_('st.mount_iso'))
            iso_mount = tempfile.mkdtemp(prefix='usbnux_iso_')
            subprocess.run(
                ['mount', '-o', 'loop,ro', self.iso_path, iso_mount],
                check=True, capture_output=True,
            )

            self.on_status(_('st.mount_usb'))
            usb_mount = tempfile.mkdtemp(prefix='usbnux_usb_')
            subprocess.run(
                ['mount', partition, usb_mount],
                check=True, capture_output=True,
            )

            wim_src   = os.path.join(iso_mount, 'sources', 'install.wim')
            wim_size  = os.path.getsize(wim_src) if os.path.exists(wim_src) else 0
            needs_split = wim_size >= FAT32_LIMIT

            if needs_split:
                _ensure_wimlib()

            self.on_status(_('st.copying'))
            exclude = {wim_src} if needs_split else set()
            p_end   = 0.75 if needs_split else 1.0
            self._copy_tree(iso_mount, usb_mount, exclude=exclude,
                            p_start=0.0, p_end=p_end)

            if needs_split:
                self._check()
                self.on_status(_('st.wim_split', size=wim_size / (1024**3)))
                dest_sources = os.path.join(usb_mount, 'sources')
                os.makedirs(dest_sources, exist_ok=True)
                result = subprocess.run(
                    [_find_wimlib(), 'split', wim_src,
                     os.path.join(dest_sources, 'install.swm'), '3800'],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    raise Exception(_('err.wim_split_fail',
                                      detail=result.stderr.strip()))
                self.on_progress(1.0)

            if self.bypass_win11_checks:
                self.on_status(_('st.bypass_inject'))
                autounattend_path = os.path.join(usb_mount, 'autounattend.xml')
                with open(autounattend_path, 'w', encoding='utf-8') as f:
                    f.write(WIN11_BYPASS_AUTOUNATTEND)

            self.on_status(_('st.sync'))
            subprocess.run(['sync'], check=True)

        finally:
            for mnt in (usb_mount, iso_mount):
                if mnt:
                    subprocess.run(['umount', mnt], capture_output=True)
                    shutil.rmtree(mnt, ignore_errors=True)

        msg = _('res.win_done')
        if self.bypass_win11_checks:
            msg += _('res.win_bypass_note')
        if self.verify_after_write:
            self._verify_windows()
            msg += _('res.win_verified')
        self.on_done(True, msg)

    # ------------------------------------------------------------------

    def _create_partition_table(self):
        label = 'msdos' if self.partition_scheme == 'MBR' else 'gpt'
        subprocess.run(['parted', '-s', self.drive_path, 'mklabel', label],
                       check=True, capture_output=True)

        if self.partition_scheme == 'MBR':
            subprocess.run(
                ['parted', '-s', self.drive_path,
                 'mkpart', 'primary', 'fat32', '1MiB', '100%'],
                check=True, capture_output=True,
            )
            subprocess.run(
                ['parted', '-s', self.drive_path, 'set', '1', 'boot', 'on'],
                capture_output=True,
            )
        else:
            subprocess.run(
                ['parted', '-s', self.drive_path,
                 'mkpart', 'EFI', 'fat32', '1MiB', '100%'],
                check=True, capture_output=True,
            )
            subprocess.run(
                ['parted', '-s', self.drive_path, 'set', '1', 'esp', 'on'],
                check=True, capture_output=True,
            )

        subprocess.run(['partprobe', self.drive_path], capture_output=True)
        time.sleep(1)

    def _wait_for_partition(self, path, timeout=10):
        for _i in range(timeout * 2):
            if os.path.exists(path):
                return
            time.sleep(0.5)
        raise Exception(_('err.partition_create', path=path))

    # ------------------------------------------------------------------
    # Yazma sonrası doğrulama

    def _hash_n_bytes(self, path, n_bytes, status_key, p_start, p_end):
        """path'ten n_bytes kadar okuyup SHA256 hesaplar (file veya block device)."""
        h = hashlib.sha256()
        done = 0
        with open(path, 'rb') as f:
            while done < n_bytes:
                self._check()
                to_read = min(BLOCK_SIZE, n_bytes - done)
                chunk = f.read(to_read)
                if not chunk:
                    break
                h.update(chunk)
                done += len(chunk)
                frac = p_start + (done / n_bytes) * (p_end - p_start)
                self.on_progress(frac)
                self.on_status(_(
                    status_key,
                    done=done / (1024**2),
                    total=n_bytes / (1024**2),
                ))
        return h.hexdigest()

    def _verify_linux(self, iso_size):
        self.on_progress(0.0)
        iso_hash = self._hash_n_bytes(
            self.iso_path, iso_size, 'st.hashing_iso', 0.0, 0.5)
        usb_hash = self._hash_n_bytes(
            self.drive_path, iso_size, 'st.hashing_usb', 0.5, 1.0)
        if iso_hash != usb_hash:
            raise Exception(_('err.verify_linux',
                              iso_h=iso_hash, usb_h=usb_hash))

    def _verify_windows(self):
        """USB'yi yeniden bağlayıp dosya yapısını ISO ile karşılaştırır.

        Bit-bit karşılaştırma yapılmaz (FAT32 dosya yapısı raw ISO'dan farklı).
        Her dosyanın varlığını ve boyutunu kontrol eder; install.wim
        bölünmüşse onu install.swm* dosyalarıyla denkleştirir.
        """
        self.on_progress(0.0)
        self.on_status(_('st.verify_setup'))

        iso_mount = tempfile.mkdtemp(prefix='usbnux_vfy_iso_')
        usb_mount = tempfile.mkdtemp(prefix='usbnux_vfy_usb_')
        try:
            subprocess.run(
                ['mount', '-o', 'loop,ro', self.iso_path, iso_mount],
                check=True, capture_output=True,
            )
            partition = get_partition_path(self.drive_path, 1)
            subprocess.run(
                ['mount', '-o', 'ro', partition, usb_mount],
                check=True, capture_output=True,
            )

            wim_src = os.path.join(iso_mount, 'sources', 'install.wim')
            wim_split = (os.path.exists(wim_src)
                         and os.path.getsize(wim_src) >= FAT32_LIMIT)

            iso_files = []
            total_size = 0
            for root, dirs, fnames in os.walk(iso_mount, followlinks=False):
                # Symlink dizinlere inme (RockRidge'li düşman ISO host fs'ine kaçabilir)
                dirs[:] = [d for d in dirs
                           if not os.path.islink(os.path.join(root, d))]
                for fname in fnames:
                    fpath = os.path.join(root, fname)
                    if os.path.islink(fpath):
                        continue
                    if wim_split and fpath == wim_src:
                        continue
                    rel = os.path.relpath(fpath, iso_mount)
                    sz  = os.path.getsize(fpath)
                    iso_files.append((rel, sz))
                    total_size += sz

            mismatches = []
            processed = 0
            for rel, expected_size in iso_files:
                self._check()
                dst = os.path.join(usb_mount, rel)
                if not os.path.exists(dst):
                    mismatches.append(_('err.verify_missing', file=rel))
                else:
                    actual = os.path.getsize(dst)
                    if actual != expected_size:
                        mismatches.append(_('err.verify_size',
                                            file=rel, actual=actual,
                                            expected=expected_size))
                processed += expected_size
                if total_size:
                    self.on_progress(processed / total_size)
                self.on_file_status(_('st.verify_file', file=rel))

            if wim_split:
                self._check()
                self.on_status(_('st.verify_swm'))
                swm = os.path.join(usb_mount, 'sources', 'install.swm')
                if not os.path.exists(swm):
                    mismatches.append(
                        _('err.verify_missing', file='sources/install.swm'))

            if mismatches:
                preview = '\n'.join(mismatches[:5])
                more = (_('err.verify_win_more', n=len(mismatches) - 5)
                        if len(mismatches) > 5 else '')
                raise Exception(_('err.verify_win',
                                  count=len(mismatches),
                                  preview=preview, more=more))

            self.on_progress(1.0)
        finally:
            for mnt in (usb_mount, iso_mount):
                subprocess.run(['umount', mnt], capture_output=True)
                shutil.rmtree(mnt, ignore_errors=True)

    # ------------------------------------------------------------------

    def _copy_tree(self, src_dir, dst_dir, exclude, p_start, p_end):
        """Ağaç kopyalama; progress callback'i p_start–p_end aralığında günceller.

        Symlink'ler (hem dosya hem dizin) atlanır: RockRidge extension'lı
        düşman bir ISO host filesystem'ine (örn. /etc/shadow) işaret eden
        symlink koyup root-kontekstinde dosya sızdırabilir.
        """
        files = []
        total = 0
        for root, dirs, fnames in os.walk(src_dir, followlinks=False):
            dirs[:] = [d for d in dirs
                       if not os.path.islink(os.path.join(root, d))]
            for fname in fnames:
                fpath = os.path.join(root, fname)
                if os.path.islink(fpath):
                    continue
                if fpath in exclude:
                    continue
                size = os.path.getsize(fpath)
                rel  = os.path.relpath(fpath, src_dir)
                files.append((fpath, rel, size))
                total += size

        copied = 0
        for src_path, rel, size in files:
            self._check()
            self.on_file_status(_('st.copying_file', file=rel))
            dst_path = os.path.join(dst_dir, rel)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)

            with open(src_path, 'rb') as src, open(dst_path, 'wb') as dst:
                while True:
                    self._check()
                    block = src.read(BLOCK_SIZE)
                    if not block:
                        break
                    dst.write(block)
                    copied += len(block)
                    if total:
                        frac = p_start + (copied / total) * (p_end - p_start)
                        self.on_progress(frac)
