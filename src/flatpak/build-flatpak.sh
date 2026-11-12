#!/bin/bash
# Builds and installs the Flatpak locally (tested on Ubuntu 26.10 / GNOME 51).
# After it finishes, start the app with:  flatpak run local.linuxicloudphotos.Photos
# Usage: bash flatpak/build-flatpak.sh            (auto-detects the newest GNOME runtime)
#        RUNTIME_VERSION=48 FFMPEG_VERSION=24.08 bash flatpak/build-flatpak.sh   (FFMPEG_VERSION only for GNOME < 49)
set -euo pipefail
cd "$(dirname "$0")"
APPID=local.linuxicloudphotos.Photos

if dpkg-query -W -f="\${Status}" linux-icloud-photos 2>/dev/null | grep -q "^install ok installed"; then
  echo "NOTE: the .deb version of Linux iCloud Photos is installed too."
  echo "Both use the same name and will appear twice in the application menu."
  echo "Keep one of them:  sudo apt remove linux-icloud-photos   or   bash flatpak/remove-flatpak.sh"
fi

sudo apt-get install -y flatpak flatpak-builder python3-pip python3-venv python3-aiohttp python3-yaml curl
flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo

RV="${RUNTIME_VERSION:-$(flatpak remote-ls --user flathub --runtime --columns=application,branch \
      | awk '$1=="org.gnome.Platform" && $2 ~ /^[0-9]+$/ {print $2}' | sort -n | tail -1)}"
[ -n "$RV" ] || { echo "Could not detect the GNOME runtime. Set RUNTIME_VERSION=<number>."; exit 1; }
flatpak install --user -y flathub "org.gnome.Platform//$RV" "org.gnome.Sdk//$RV"

# Video codecs. GNOME 49+ (freedesktop 25.08+): the runtime itself declares the extension
# org.freedesktop.Platform.codecs-extra//<freedesktop version>-extra. Flatpak should pull it in
# automatically, but not always (e.g. after a --user install), so install it explicitly.
# Older GNOME runtimes need the separate ffmpeg-full extension (handled through the manifest).
# The runtime's own metadata names the exact extension branch (GNOME 51 is built on freedesktop 25.08,
# so the branch is 25.08-extra, not 51-extra).
META="$(flatpak info --user --show-metadata "org.gnome.Platform//$RV" 2>/dev/null || true)"
ext_version() {  # $1 = extension id -> its "version=" from the runtime metadata
  printf '%s\n' "$META" | awk -v id="[Extension $1]" '$0==id{f=1;next} /^\[/{f=0} f&&/^version=/{sub(/^version=/,"");print;exit}'
}
if [ "$RV" -ge 49 ] 2>/dev/null; then
  CV="${CODECS_VERSION:-$(ext_version org.freedesktop.Platform.codecs-extra)}"
  if [ -z "$CV" ]; then  # fallback: newest "-extra" branch on Flathub
    CV="$(flatpak remote-ls --user flathub --runtime --columns=application,branch 2>/dev/null \
      | awk '$1=="org.freedesktop.Platform.codecs-extra"{print $2}' | sort -V | tail -1)"
  fi
  echo "GNOME $RV: installing the video codecs (codecs-extra//$CV)..."
  flatpak install --user -y flathub "org.freedesktop.Platform.codecs-extra//$CV" \
    || echo "WARNING: codecs-extra could not be installed - video will not play. Try: CODECS_VERSION=25.08-extra $0"
  FV=""
else
  FV="${FFMPEG_VERSION:-$(ext_version org.freedesktop.Platform.ffmpeg-full)}"
  [ -n "$FV" ] || { echo "Could not detect the ffmpeg-full version. Set FFMPEG_VERSION=<e.g. 24.08>."; exit 1; }
  flatpak install --user -y flathub "org.freedesktop.Platform.ffmpeg-full//$FV" || true
fi

# Python dependencies as offline modules (pyicloud, keyring, pychromecast, pyatv)
# flatpak-pip-generator turns the pinned Python packages into offline Flatpak modules.
# NOTE: the URL must end with .py (the name without .py is only a symlink and downloads as one line of text).
rm -f flatpak-pip-generator   # leftover of an earlier, broken download
if [ ! -s flatpak-pip-generator.py ] || ! head -c2 flatpak-pip-generator.py | grep -q '#!'; then
  curl -fsSL https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator.py \
       -o flatpak-pip-generator.py
fi
head -c2 flatpak-pip-generator.py | grep -q '#!' || { echo "Downloading flatpak-pip-generator.py failed."; rm -f flatpak-pip-generator.py; exit 1; }
# its own small virtual environment, so it does not depend on distribution package names
[ -x .genvenv/bin/python ] || python3 -m venv .genvenv
.genvenv/bin/pip install -q 'requirements-parser<1.0.0,>=0.11.0' 'packaging>=23.0'
# the same pinned versions the .deb uses (requirements*.txt in the project root)
PKGS="$(grep -hv '^#' ../requirements.txt ../requirements-optional.txt | grep -v '^$' | tr '\n' ' ')"
# Packages with compiled code must come as ready-made wheels: building cryptography or pydantic-core from
# source needs Rust, which the GNOME SDK does not have ("Cannot import 'maturin'"). If the generator reports more
# packages that only exist as platform wheels, the loop below adds them and tries again.
# Only the architecture of this machine is needed (by default the generator also demands aarch64 wheels, and
# some packages, e.g. miniaudio, have none: "No compatible platform wheel found for arch 'aarch64'").
ARCH="$(uname -m)"
PREFER="cryptography,cffi,pydantic-core,aiohttp,multidict,yarl,frozenlist,propcache,miniaudio,zeroconf,charset-normalizer,protobuf"
rm -f python3-deps.json
for attempt in 1 2 3 4; do
  if .genvenv/bin/python flatpak-pip-generator.py --runtime "org.gnome.Sdk//$RV" --prefer-wheels "$PREFER" \
        --wheel-arches "$ARCH" --output python3-deps $PKGS 2>&1 | tee gen.log; then
    [ -s python3-deps.json ] && break
  fi
  EXTRA="$(sed -n "s/.*Only platform wheels are available for: \(.*\)\. Use '--runtime.*/\1/p" gen.log | head -1)"
  [ -n "$EXTRA" ] || { echo "flatpak-pip-generator failed (see the messages above)."; exit 1; }
  PREFER="$PREFER,$EXTRA"
  echo "Retrying with more wheel-only packages: $EXTRA"
done
[ -s python3-deps.json ] || { echo "flatpak-pip-generator did not produce python3-deps.json."; exit 1; }

if [ -n "$FV" ]; then
  sed -e "s/@RUNTIME_VERSION@/$RV/" -e "s/@FFMPEG_VERSION@/$FV/" \
      local.linuxicloudphotos.Photos.yml > "$APPID.build.yml"
else  # drop the ffmpeg-full block (not used with GNOME 49+)
  sed -e '/# BEGIN-FFMPEG/,/# END-FFMPEG/d' -e "s/@RUNTIME_VERSION@/$RV/" \
      local.linuxicloudphotos.Photos.yml > "$APPID.build.yml"
fi

flatpak-builder --user --install --force-clean --install-deps-from=flathub \
                build-dir "$APPID.build.yml"
flatpak build-bundle ~/.local/share/flatpak/repo "../$APPID.flatpak" "$APPID"
# Small background helper: keeps the app icon in step with the light/dark system theme, also while the
# app is closed (it only swaps the icon file; it does not start the app). Runs on the host, from autostart.
H="$HOME/.local/share/linux-icloud-photos"
install -Dm755 ../packaging/icon-watch.sh "$H/icon-watch.sh"
install -Dm644 ../packaging/icon-dark.svg "$H/icon-dark.svg"
mkdir -p "$HOME/.config/autostart"
sed "s#^Exec=.*#Exec=$H/icon-watch.sh#" ../packaging/linux-icloud-photos-icon.desktop \
  > "$HOME/.config/autostart/linux-icloud-photos-icon.desktop"
pkill -f "$H/icon-watch.sh" 2>/dev/null || true
nohup setsid "$H/icon-watch.sh" >/dev/null 2>&1 &
echo "Installed. Run:  flatpak run $APPID"
echo "To remove it again:  bash $(cd "$(dirname "$0")" && pwd)/remove-flatpak.sh"
echo "Bundle for sharing: $(realpath ../$APPID.flatpak)"
