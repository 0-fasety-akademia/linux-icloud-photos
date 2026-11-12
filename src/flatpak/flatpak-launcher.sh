#!/bin/sh
# Starts Linux iCloud Photos INSIDE the Flatpak sandbox. Do not run this file by hand.
if [ ! -d /app/lib/linux-icloud-photos ]; then
    echo "This is the start-up script used inside the Flatpak sandbox; it is not meant to be run directly." >&2
    echo "Build and install the Flatpak with:  bash flatpak/build-flatpak.sh" >&2
    echo "Then start the app with:             flatpak run local.linuxicloudphotos.Photos" >&2
    exit 1
fi
for d in /app/lib/python3*/site-packages; do
    [ -d "$d" ] && export PYTHONPATH="$d${PYTHONPATH:+:$PYTHONPATH}"
done
export PYTHONDONTWRITEBYTECODE=1
cd /app/lib/linux-icloud-photos || exit 1
exec python3 app.py "$@"
