#!/bin/bash
# Buduje paczkę .deb: ./build-deb.sh [wersja] [katalog_wyjściowy]
set -euo pipefail
cd "$(dirname "$0")"
VERSION="${1:-$(python3 -c 'import version; print(version.VERSION)')}"
OUT="${2:-.}"
mkdir -p "$OUT"
PKG=linux-icloud-photos
ROOT="$(mktemp -d)/${PKG}_${VERSION}_all"

install -d "$ROOT/DEBIAN" "$ROOT/usr/bin" "$ROOT/usr/lib/$PKG" \
  "$ROOT/usr/share/applications" "$ROOT/usr/share/doc/$PKG" \
  "$ROOT/usr/share/icons/hicolor/scalable/apps" "$ROOT/usr/share/icons/hicolor/256x256/apps" \
  "$ROOT/usr/share/linux-icloud-photos"

install -m 0644 app.py aurora.py backend.py bridge.py cast.py cast_gc.py airplay.py exif.py pick.py i18n.py i18n_de.py i18n_uk.py version.py "$ROOT/usr/lib/$PKG/"
install -m 0755 packaging/launcher "$ROOT/usr/bin/$PKG"
install -m 0755 packaging/icon-watch.sh "$ROOT/usr/lib/$PKG/icon-watch.sh"
install -d "$ROOT/etc/xdg/autostart"
install -m 0644 packaging/linux-icloud-photos-icon.desktop "$ROOT/etc/xdg/autostart/"
install -m 0644 packaging/local.linuxicloudphotos.Photos.desktop "$ROOT/usr/share/applications/"
install -m 0644 packaging/linux-icloud-photos.svg "$ROOT/usr/share/icons/hicolor/scalable/apps/"
install -m 0644 packaging/linux-icloud-photos.svg "$ROOT/usr/share/linux-icloud-photos/icon-light.svg"
install -m 0644 packaging/icon-dark.svg "$ROOT/usr/share/linux-icloud-photos/icon-dark.svg"
install -m 0644 README.md LICENSE "$ROOT/usr/share/doc/$PKG/"
install -m 0644 packaging/copyright "$ROOT/usr/share/doc/$PKG/copyright"
sed "s/@VERSION@/$VERSION/" packaging/control > "$ROOT/DEBIAN/control"
chmod 0644 "$ROOT/DEBIAN/control"
install -m 0755 packaging/postinst packaging/postrm "$ROOT/DEBIAN/"
install -m 0644 packaging/triggers "$ROOT/DEBIAN/triggers"
install -m 0644 requirements.txt requirements-optional.txt constraints.txt "$ROOT/usr/share/linux-icloud-photos/"

# PNG 256 dla środowisk bez obsługi SVG (wymaga python3-gi + loadera SVG)
python3 - "$ROOT/usr/share/icons/hicolor/256x256/apps/$PKG.png" <<'PY' || echo "(pominięto PNG)"
import sys, gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
GdkPixbuf.Pixbuf.new_from_file_at_size("packaging/linux-icloud-photos.svg", 256, 256).savev(sys.argv[1], "png", [], [])
PY

dpkg-deb --build --root-owner-group "$ROOT" "$OUT/${PKG}_${VERSION}_all.deb"
echo "Gotowe: $OUT/${PKG}_${VERSION}_all.deb"
