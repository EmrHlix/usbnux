import re
import subprocess
import json


def get_usb_drives():
    """Bağlı USB/çıkarılabilir sürücüleri listeler."""
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-b', '-o', 'NAME,SIZE,MODEL,TRAN,TYPE,RM'],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        drives = []
        for dev in data.get('blockdevices', []):
            tran = dev.get('tran') or ''
            typ  = dev.get('type') or ''
            rm   = dev.get('rm') or False
            if typ != 'disk':
                continue
            if tran != 'usb' and not rm:
                continue
            size  = int(dev.get('size') or 0)
            model = (dev.get('model') or '').strip() or 'USB Sürücü'
            name  = dev['name']
            drives.append({
                'name':    name,
                'path':    f'/dev/{name}',
                'size':    size,
                'model':   model,
                'display': f'{model} ({format_size(size)})  [{name}]',
            })
        return drives
    except Exception:
        return []


def format_size(size_bytes):
    if not size_bytes:
        return '?'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f'{size_bytes:.1f} {unit}'
        size_bytes /= 1024.0
    return f'{size_bytes:.1f} PB'


def get_partition_path(drive_path, num=1):
    """Sürücü yolundan bölüm yolunu türetir (/dev/sdb -> /dev/sdb1)."""
    if drive_path[-1].isdigit():
        return f'{drive_path}p{num}'
    return f'{drive_path}{num}'


def unmount_drive(drive_path):
    """Sürücünün tüm bölümlerini unmount eder."""
    drive_name = drive_path.split('/')[-1]
    try:
        result = subprocess.run(
            ['lsblk', '-no', 'NAME', drive_path],
            capture_output=True, text=True,
        )
        for line in result.stdout.strip().split('\n'):
            name = re.sub(r'[^a-z0-9]', '', line.lower())
            if name and name != drive_name:
                subprocess.run(['umount', f'/dev/{name}'], capture_output=True)
        subprocess.run(['umount', drive_path], capture_output=True)
    except Exception:
        pass
