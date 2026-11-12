#!/bin/bash
# Removes the Flatpak version of Linux iCloud Photos, including its data, so that it does not
# duplicate the .deb version. The .deb version and its settings (~/.config/linux-icloud-photos)
# are not touched.
set -u
APPID=local.linuxicloudphotos.Photos
cd "$(dirname "$0")"

flatpak uninstall --user --delete-data -y "$APPID" 2>/dev/null \
  || sudo flatpak uninstall --system --delete-data -y "$APPID" 2>/dev/null \
  || echo "The Flatpak is not installed."
flatpak uninstall --unused -y 2>/dev/null || true
# the icon helper and the icon files it wrote
H="$HOME/.local/share/linux-icloud-photos"
pkill -f "$H/icon-watch.sh" 2>/dev/null || true
rm -rf "$H" "$HOME/.config/autostart/linux-icloud-photos-icon.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/linux-icloud-photos.svg" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/local.linuxicloudphotos.Photos.svg"
rm -rf build-dir .flatpak-builder .genvenv "../$APPID.flatpak" "$APPID.build.yml" python3-deps.json flatpak-pip-generator flatpak-pip-generator.py
echo "Done. Check with:  flatpak list --app | grep -i icloud   (should print nothing)"
