#!/usr/bin/env bash
# USBnux - .deb paketi olusturma scripti.
# Kullanim: ./build-deb.sh
# Cikti: dist/usbnux_<surum>_all.deb
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="$ROOT_DIR/packaging/debian"
BUILD_DIR="$ROOT_DIR/build/deb"
DIST_DIR="$ROOT_DIR/dist"

VERSION="$(awk -F': *' '/^Version:/ {print $2; exit}' "$TEMPLATE_DIR/DEBIAN/control")"
ARCH="$(awk -F': *' '/^Architecture:/ {print $2; exit}' "$TEMPLATE_DIR/DEBIAN/control")"
PKG_NAME="$(awk -F': *' '/^Package:/ {print $2; exit}' "$TEMPLATE_DIR/DEBIAN/control")"
OUTPUT="$DIST_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo "==> Temizlik: $BUILD_DIR"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "==> Sablon dosyalari kopyalaniyor..."
cp -a "$TEMPLATE_DIR/." "$BUILD_DIR/"

echo "==> Python kaynak dosyalari /usr/lib/usbnux altina kopyalaniyor..."
INSTALL_LIB="$BUILD_DIR/usr/lib/usbnux"
install -m 0644 "$ROOT_DIR/main.py" "$INSTALL_LIB/main.py"
cp -a "$ROOT_DIR/core" "$INSTALL_LIB/core"
cp -a "$ROOT_DIR/ui"   "$INSTALL_LIB/ui"

echo "==> __pycache__ temizleniyor..."
find "$INSTALL_LIB" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_LIB" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

echo "==> Dosya izinleri ayarlaniyor..."
# Calistirilabilirler
chmod 0755 "$BUILD_DIR/usr/bin/usbnux"
chmod 0755 "$BUILD_DIR/usr/lib/usbnux/usbnux-pkexec"
chmod 0755 "$BUILD_DIR/DEBIAN/postinst"
chmod 0755 "$BUILD_DIR/DEBIAN/postrm"

# Veri dosyalari
find "$BUILD_DIR/usr/share" -type f -exec chmod 0644 {} +
find "$BUILD_DIR/usr/lib/usbnux" -type f ! -name 'usbnux-pkexec' -exec chmod 0644 {} +
find "$BUILD_DIR/usr" -type d -exec chmod 0755 {} +

# DEBIAN/control ve script izinleri
chmod 0644 "$BUILD_DIR/DEBIAN/control"

# Dpkg, dunya yazilabilir dizinleri reddedebilir
find "$BUILD_DIR" -type d -exec chmod g-w,o-w {} +

echo "==> dpkg-deb cagriliyor..."
dpkg-deb --root-owner-group --build "$BUILD_DIR" "$OUTPUT"

echo ""
echo "OK: $OUTPUT"
echo ""
echo "Kurmak icin:"
echo "  sudo apt install $OUTPUT"
echo "Veya:"
echo "  sudo dpkg -i $OUTPUT && sudo apt -f install"
