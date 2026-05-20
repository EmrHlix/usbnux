"""USB → ISO disk imaj cikarma.

ISO9660 PVD okunarak gercek volume boyutu tespit edilir; yoksa tum aygit
boyutuna duser. Aygittan ISO9660 boyutu kadar (veya tam aygit) byte
4 MB bloklarla dosyaya kopyalanir.
"""
import os
import pwd
import subprocess
import threading

from .disk_detector import unmount_drive
from .i18n import _


BLOCK_SIZE = 4 * 1024 * 1024


def detect_iso_size(device_path):
    """ISO9660 Primary Volume Descriptor'dan volume boyutunu cikarir.

    Donus: (size_bytes, kind) - kind 'iso9660' veya 'raw'.
    PVD bulunamazsa (None, 'raw').
    """
    try:
        with open(device_path, 'rb') as f:
            f.seek(16 * 2048)              # PVD sector 16
            pvd = f.read(2048)
            if len(pvd) < 2048:
                return (None, 'raw')
            if pvd[0] != 0x01 or pvd[1:6] != b'CD001':
                return (None, 'raw')
            # Volume Space Size (8 byte LBA-LSB + LBA-MSB); LSB = little-endian
            blocks = int.from_bytes(pvd[80:84], 'little')
            if blocks <= 0:
                return (None, 'raw')
            return (blocks * 2048, 'iso9660')
    except (OSError, PermissionError):
        return (None, 'raw')


def get_device_size(device_path):
    """Blok aygitinin toplam boyutu (byte). lsblk -bno SIZE."""
    r = subprocess.run(
        ['lsblk', '-bdno', 'SIZE', device_path],
        capture_output=True, text=True,
    )
    line = r.stdout.strip().splitlines()[:1]
    if line:
        try:
            return int(line[0].strip())
        except ValueError:
            pass
    return 0


class USBDumper:
    def __init__(self, drive_path, output_path, size_bytes,
                 on_progress, on_status, on_done, on_file_status=None):
        self.drive_path     = drive_path
        self.output_path    = output_path
        self.size_bytes     = size_bytes
        self.on_progress    = on_progress
        self.on_status      = on_status
        self.on_file_status = on_file_status or on_status
        self.on_done        = on_done
        self._cancelled     = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self):
        self._cancelled = True

    def _check(self):
        if self._cancelled:
            raise InterruptedError(_('res.cancelled'))

    def _run(self):
        try:
            self.on_status(_('st.unmount'))
            unmount_drive(self.drive_path)

            self.on_status(_('st.reading'))
            total = self.size_bytes
            done = 0
            with open(self.drive_path, 'rb') as src, \
                 open(self.output_path, 'wb') as dst:
                while done < total:
                    self._check()
                    to_read = min(BLOCK_SIZE, total - done)
                    block = src.read(to_read)
                    if not block:
                        break
                    dst.write(block)
                    done += len(block)
                    self.on_progress(done / total)
                    self.on_file_status(_(
                        'st.reading_progress',
                        done=done / (1024**2),
                        total=total / (1024**2),
                    ))

            self.on_status(_('st.sync'))
            subprocess.run(['sync'], check=True)
            self._chown_to_invoker(self.output_path)
            self.on_progress(1.0)
            self.on_done(True, _('dump.done', path=self.output_path))
        except InterruptedError as e:
            try:
                if os.path.exists(self.output_path):
                    os.unlink(self.output_path)
            except OSError:
                pass
            self.on_done(False, str(e))
        except Exception as e:
            self.on_done(False, _('err.generic', detail=e))

    def _chown_to_invoker(self, path):
        """Cikti dosyasini pkexec/sudo cagrisini yapan kullaniciya devret."""
        for env in ('PKEXEC_UID', 'SUDO_UID'):
            uid = os.environ.get(env)
            if uid and uid.isdigit():
                try:
                    pw = pwd.getpwuid(int(uid))
                    os.chown(path, pw.pw_uid, pw.pw_gid)
                    return
                except (KeyError, OSError):
                    continue
