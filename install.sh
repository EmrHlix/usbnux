#!/usr/bin/env bash
# USBnux – bağımlılık yükleyici (Debian/Ubuntu/Mint)
set -e

echo "==> Paket listesi güncelleniyor…"
apt-get update -q

echo "==> Bağımlılıklar yükleniyor…"
apt-get install -y \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    parted \
    dosfstools \
    ntfs-3g \
    exfatprogs \
    e2fsprogs \
    wimtools \
    genisoimage \
    p7zip-full \
    util-linux

echo ""
echo "✓ Kurulum tamamlandı!"
echo ""
echo "Uygulamayı çalıştırmak için:"
echo "  cd $(dirname "$0")"
echo "  sudo python3 main.py"
