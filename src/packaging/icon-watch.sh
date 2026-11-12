#!/bin/sh
# Linux iCloud Photos: small background helper that keeps the app icon (dock, menu) in step with the
# system light/dark theme, also while the app is closed. It does nothing else and does not start the app.
HERE=$(dirname "$(readlink -f "$0")")
DARK=""
for d in "$HERE" /usr/share/linux-icloud-photos; do
    if [ -f "$d/icon-dark.svg" ]; then DARK="$d/icon-dark.svg"; break; fi
done
[ -n "$DARK" ] || exit 0
DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
NAMES="linux-icloud-photos local.linuxicloudphotos.Photos"

is_dark() {
    case "$(gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null)" in *dark*) return 0 ;; esac
    case "$(gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null)" in *-dark*|*-Dark*) return 0 ;; esac
    return 1
}

apply() {
    if is_dark; then
        mkdir -p "$DIR"
        for n in $NAMES; do cmp -s "$DARK" "$DIR/$n.svg" 2>/dev/null || cp "$DARK" "$DIR/$n.svg"; done
    else
        for n in $NAMES; do rm -f "$DIR/$n.svg"; done  # the light icon of the package is used
    fi
    touch "$DIR" "$DIR/.." "$DIR/../.." 2>/dev/null || true  # make the shell re-read the icon theme
}

apply
gsettings monitor org.gnome.desktop.interface 2>/dev/null | while read -r line; do
    case "$line" in *color-scheme*|*gtk-theme*) apply ;; esac
done
