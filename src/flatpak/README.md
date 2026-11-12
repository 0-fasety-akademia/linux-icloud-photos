# Flatpak package

The Flatpak bundles GTK 4, libadwaita and GStreamer from the GNOME runtime, so it behaves the same
on any distribution and does not depend on Ubuntu package names.

**Status:** tested on Ubuntu 26.10 (GNOME 51): build, installation, sign-in, browsing and video playback work. Other distributions have not been tried yet; please report any error message.

## Build and install

    bash flatpak/build-flatpak.sh
    flatpak run local.linuxicloudphotos.Photos

Packages with compiled code (cryptography, pydantic-core, aiohttp and others) are taken as ready-made wheels (`--prefer-wheels`), because building them from source needs Rust, which the GNOME SDK does not have; if the generator reports more wheel-only packages, the script adds them and retries.

The build downloads `flatpak-pip-generator.py` (the address must end in `.py`: the name without it is only a symlink) and runs it in its own small environment `.genvenv`; both are removed by `remove-flatpak.sh`.

`flatpak-launcher.sh` in this folder is the start-up script used **inside** the sandbox (it becomes
`/app/bin/linux-icloud-photos`). Do not run it by hand: it only works after the build installs the app.
## Remove it (and avoid duplicates with the .deb)

The Flatpak and the `.deb` use the same name and the same desktop id, so with both installed the app
appears twice in the menu. They do not share settings: the Flatpak keeps its data in
`~/.var/app/local.linuxicloudphotos.Photos/`, the `.deb` in `~/.config/linux-icloud-photos` and
`~/.cache/linux-icloud-photos`, so you would have to sign in twice.

Remove only the Flatpak (keeps the .deb):

    bash flatpak/remove-flatpak.sh

or by hand:

    flatpak uninstall --delete-data local.linuxicloudphotos.Photos
    flatpak uninstall --unused
    rm -rf flatpak/build-dir flatpak/.flatpak-builder local.linuxicloudphotos.Photos.flatpak

Check what is installed:

    flatpak list --app | grep -i icloud     # Flatpak
    dpkg -l | grep icloud-photos            # .deb

Remove only the .deb (keeps the Flatpak): `sudo apt remove linux-icloud-photos`
(use `purge` to also delete `/opt/linux-icloud-photos`).

## Notes

- `mpv` is not available inside the sandbox, so videos play in the built-in GTK player (GStreamer + the
  `ffmpeg-full` codec extension). HEIC originals may not decode (no HEIF loader in the runtime); the
  JPEG preview is used instead.
- Permissions: network (iCloud, TV discovery), Wayland/X11, GPU, audio, and the secret service (keyring).
- To publish on Flathub the app id must be changed to a domain you own (for example
  `io.github.<user>.ICloudPhotos`), screenshots must be added to the metainfo file, and Flathub requires
  all Python dependencies to be listed with checksums (generated into `python3-deps.json`).
