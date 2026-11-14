# Linux iCloud Photos

**Current version: 0.17.3 (2026-11-14)**

Created by: JGu  
Supported by Claude

An unofficial, free iCloud Photos client for Ubuntu (GTK4 + libadwaita).
Photos stay in the cloud: the app streams thumbnails, previews and videos on demand
and keeps only a small, size-limited cache on disk.

Free of charge to use and to share **unmodified**. Modification is **not permitted** (see `LICENSE`). This is not an open-source license. Versions before 0.12.2 were published under the MIT License, and copies obtained under it stay under it.
Created with the help of Claude (Anthropic).
Not affiliated with, endorsed by or sponsored by Apple Inc. "iCloud" is a trademark of Apple Inc.
It relies on the unofficial `pyicloud` library, so Apple may break it at any time. Use at your own risk.

## Features

- Streams photos and videos from iCloud; no library sync to disk
- Thumbnail/preview cache limited to 1 GB (least recently used files are removed)
- Interface in English and Polish, chosen by the system language (Polish if the system is set to Polish, English otherwise)
- German and Ukrainian are available as optional languages: choose them in Settings (applies after a restart) or force a language with `ICLOUD_PHOTOS_LANG=pl`, `en`, `de` or `uk`. The system language only selects Polish or English automatically. The German and Ukrainian texts were written without review by native speakers
- Month names, plural forms and the names of Apple's built-in albums are translated as well
- Sign in with Apple ID and two-factor code; session and password (system keyring) are remembered
- Login errors are selectable and copyable, with a "Copy error" button
- When the Apple session expires, the app returns to the login screen with a "Session expired" message
- It signs in again automatically with the saved password, so usually only the 2FA code is needed
- Jump to a date: type a date in "Search album" (2024, 08.2024, 15.08.2024, "August 2024") and pick "Go to"
- Jump to a date with the calendar button in the header (calendar with month and year pickers)
- Date jump uses a binary search (about 17 requests for 12,000 photos) and then continues from that place
- Multi-select mode: select button, Ctrl+click, check marks on tiles, Ctrl+A, Esc to leave
- Rubber-band selection: press the left mouse button on the grid and drag to select a block of photos
- Dragging switches on selection mode by itself; Ctrl+drag toggles photos; the grid scrolls at the window edge
- Selection mode switches off automatically when the last selected photo is deselected
- Actions on the selection: add to an album, add to or remove from favourites, save originals to a folder
- Adding to an album first checks which photos are already in it, skips them and tells you the album name
- Only the photos that are not in the album yet are added, with a summary of how many were skipped
- Settings window: cache size limit (GB), "Clear cache" button, video player (automatic / mpv / built-in)
- Left menu: collapsible "Media types" and "My albums (N)" sections with an album search box
- Album cover thumbnails (same size for all, cached on disk); star icon for Favorites, camera icon for Videos
- Section titles and "All Photos" are bold; app version and date are shown at the bottom of the menu
- Resizable divider between the menu and the photo grid (the width is remembered), menu can be hidden
- Newest photos first, including the "All Photos" library of 12,000+ items
- Photos load in batches of 300 while you scroll
- Sort toggle (newest/oldest first) that remembers your choice
- Automatic correction of albums that Apple returns in the opposite order
- Grid zoom slider (− / +), Ctrl +, Ctrl −, Ctrl 0 and Ctrl + mouse wheel
- Grid view presets: small, standard, large, extra large
- Grid option "Original proportions" shows whole photos without cropping
- Layout option "Rows (like Google Photos)": photos keep their proportions in rows of equal height that fill the width
- The row height follows the zoom slider, Ctrl +/-, and the view presets; rows re-flow when the window or menu width changes
- New photos are appended to the rows while scrolling without resetting the view; portrait/landscape orientation is respected
- Photo viewer with fullscreen, arrow-key navigation and prefetching of neighbouring photos
- Photo zoom bar (− / slider / + / Fit), pinch gesture, double-click zoom and drag to pan
- Original-quality image is fetched automatically when you zoom in
- Video thumbnails (poster frame) in the grid and a play button in the viewer
- Videos open in a separate mpv window and use the light H.264 version instead of the huge original
- If streaming a video fails, the app automatically downloads it to the cache and plays the local file
- If mpv still fails, a message shows the reason (details in `mpv.log` and `debug.log`)
- Optional built-in video player (set `ICLOUD_PHOTOS_EMBEDDED_VIDEO=1`)
- Live Photos: LIVE badge, play with the LIVE button, `L`, Space or by pressing and holding the photo
- Photo information: file name, capture date, added date, dimensions, size, location and device (EXIF)
- Place name lookup via OpenStreetMap only on request; "Show on map" link
- Right-click menu: Information, Add to album, Play in mpv, Send to TV, Save original as…, Copy file name
- "Add to album" in the right-click menu lists the 3 most recently used albums plus "Add to another album…"
- Right-clicking a photo that is part of the selection adds the whole selection
- The photo viewer has an "Add to album" button (and the `A` key) with the same recent-albums list
- The album picker has a search box (Enter selects the first match, a second Enter adds) and lists recent albums first
- Slideshow of the current album with crossfade, 3/5/8/15 s per photo, pause and skip. It starts only from inside an album: with the play button in the viewer (next to the information and add-to-album buttons) or from the right-click menu ("Slideshow from this photo"); there is no play button in the header bar
- Send photos, videos and slideshows to a TV over DLNA/UPnP (LG, Samsung, Sony and others)
- Send to Chromecast and Google Cast TVs
- Send to Apple TV and other AirPlay receivers: videos after one-time PIN pairing (the pairing is remembered in the system keyring)
- Photos to AirPlay receivers are experimental (AirPlay 1 photo protocol) and newer devices may reject them
- Upload photos and videos by drag and drop or with the "+" button
- Choose the destination album for uploads, with progress and error reporting
- Window transparency (Settings, slider; 0 = off, the default): the window and its panels become translucent and a strongly blurred background made from the colours of your photos shows through. The more transparent the window, the stronger that blurred layer, and panels with text always keep at least 75% opacity, so text stays readable. The app cannot blur the desktop behind the window (GTK4 on GNOME does not allow it); for a real blur of what is behind the window use an extension such as Blur my Shell, which can blur any translucent window
- Refresh button in the header bar (also `F5` or `Ctrl+R`): fetches the album list and the photos of the current album again (for example after adding photos on your phone), keeps the album you were in and forgets the cached album covers so they are downloaded again
- Delete photos (selection bar, right-click menu, viewer button or the `Delete` key): they go to "Recently Deleted" in iCloud (like the Photos app), after a confirmation, and disappear from your other devices. The app asks Apple to confirm each deletion before it removes the photo from the view.
- The pinned library versions (pyicloud, keyring, PyChromecast, pyatv) are the ones the app was tested with; the app warns if the installed pyicloud differs
- Picker mode for other apps (`--pick`): `linux-icloud-photos --pick --pick-out result.json --pick-dir DIR [--pick-max 30]` opens the app with a read-only library (no delete, favourite, album or upload actions). You select photos and videos and click "Choose"; they are exported to DIR (JPEG/PNG/GIF unchanged, HEIC converted to JPEG, videos as H.264, Live Photos as a still photo) and listed in the JSON file. Exit code 0 = files chosen, 1 = cancelled. linux-whazzapp uses it for "Photos & videos" in the WhatsApp attach menu
- Links from other apps: `linux-icloud-photos --open-album "NAME"` opens an album, `--open-date 2025-02-14..2025-02-28` jumps to those days in All Photos. If the app is already open, the request goes to the open window. linux-skytrack uses it for "Open album" and "Photos from the trip days"
- Bridge for other apps, without a window (`bridge.py`, uses the saved session, never asks for a password or 2FA code): `--albums-json`, `--album-thumbs NAME`, `--range-thumbs --from ISO --to ISO`, `--create-album NAME --from ISO --to ISO` (creates the album or reuses an existing one with that name and adds the photos taken in that time, skipping duplicates), `--create-album NAME --allow-empty` (an empty album, e.g. for a planned trip; with a date range it also creates the album when there are no photos yet). `--drive-upload FILE --drive-folder NAME [--prefix P --keep N]` (0.16.0) uploads a file to a folder in the iCloud Drive root, replacing a file with the same name and keeping only the newest N files that start with the prefix (linux-skytrack backups); error `drive_unavailable` when iCloud Drive is off or has no web access. Results are written as JSON to `--json OUT`; error `login_required` means the app needs to be opened once to sign in
- Diagnostic log in `~/.cache/linux-icloud-photos/debug.log`
- Installs as a `.deb` package with a desktop launcher and icon
- Flatpak: builds, installs and runs (tested on Ubuntu 26.10 / GNOME 51), including video playback

## Installation

### Debian/Ubuntu package (recommended)

1. Download the newest `linux-icloud-photos_<version>_all.deb` from the [Releases page](https://github.com/jgu-linux-apps/linux-icloud-photos/releases/latest).
2. Run `sudo apt install ./linux-icloud-photos_<version>_all.deb` (requires internet: `pyicloud` and the optional Chromecast/AirPlay libraries are installed into `/opt/linux-icloud-photos/venv`).
3. Start **Linux iCloud Photos** from the application menu and sign in.

Upgrade: run the same command with the newer file. Remove: `sudo apt remove linux-icloud-photos`.
If a library failed to install: `sudo /opt/linux-icloud-photos/venv/bin/pip install pyicloud keyring pychromecast pyatv`.

### Flatpak

The `src/` folder of the repository (or the source archive from the Releases page) contains a `flatpak/` folder. From that folder's parent, build and install with `bash flatpak/build-flatpak.sh`, then run
`flatpak run local.linuxicloudphotos.Photos`. The script installs the GNOME runtime and the video codec extension
(`codecs-extra` on GNOME 49 and newer, `ffmpeg-full` on older runtimes) by itself. The build also produces a single
file `local.linuxicloudphotos.Photos.flatpak` that can be installed elsewhere with
`flatpak install --user local.linuxicloudphotos.Photos.flatpak`. Tested on Ubuntu 26.10 (GNOME 51), including sign-in,
browsing and video playback; other distributions are expected to work but have not been tried. In the Flatpak the
videos play in the built-in player (the film is downloaded to the cache first); mpv is not used there.
`flatpak/flatpak-launcher.sh` is the start-up script used inside the sandbox and is not meant to be run by hand; see `flatpak/README.md`.

**Do not keep both versions.** The Flatpak and the `.deb` share the same name, so both would appear in the
menu, and they keep separate settings and sign-ins. To remove the Flatpak (and its data) and keep the `.deb`:
`bash flatpak/remove-flatpak.sh` or `flatpak uninstall --delete-data local.linuxicloudphotos.Photos`.
To remove the `.deb` and keep the Flatpak: `sudo apt remove linux-icloud-photos`.
Check what is installed: `flatpak list --app | grep -i icloud` and `dpkg -l | grep icloud-photos`.
Inside the Flatpak, mpv is not available, so videos play in the built-in player.

### Upgrading from the old name (before 0.12.2)

The app was renamed from `icloud-photos-linux` to **Linux iCloud Photos** (package and command: `linux-icloud-photos`). Installing the new `.deb` replaces the old package automatically. Your settings, session and cache are moved to the new folders (`~/.config/linux-icloud-photos`, `~/.cache/linux-icloud-photos`) the first time the app starts, and the saved Apple ID password and AirPlay pairing are copied to the new keyring entries. Nothing is overwritten if the new folders already exist. The Flatpak id changed too (`local.linuxicloudphotos.Photos`); if you built the old Flatpak, remove it with `flatpak uninstall --delete-data local.icloudphotos.linux`.

### Upgrading the system

The package keeps its own Python environment in `/opt/linux-icloud-photos/venv`. When the system Python changes (for example after an Ubuntu upgrade), the package rebuilds that environment by itself during the upgrade (it needs an internet connection). If the app says its Python environment is broken, repair it with:

```
sudo dpkg-reconfigure linux-icloud-photos
```

### Troubleshooting

- Videos do not play: look at `~/.cache/linux-icloud-photos/mpv.log` and `~/.cache/linux-icloud-photos/debug.log`, and make sure `mpv` is installed (`sudo apt install mpv`).
- "Session expired": sign in again; the app keeps your Apple ID and password in the system keyring.
- Anything else: `~/.cache/linux-icloud-photos/debug.log` records errors with timestamps.

## Keyboard shortcuts

- Grid: `Ctrl +`, `Ctrl −`, `Ctrl 0` (thumbnail size), `F11` (fullscreen), `F5` or `Ctrl+R` (refresh the library)
- Grid: drag with the left mouse button (rubber-band selection), `Ctrl`+drag (toggle), `Ctrl`+click (start selecting), `Ctrl A` (select all loaded photos), `Esc` (leave selection mode)
- Viewer: `←` `→` `Home` `End` (navigate), `Ctrl +/−/0` (zoom), `F` (fullscreen), `I` (information)
- Viewer: `L` or Space (Live Photo / play video), `M` (open video in mpv), `A` (add to album), `Esc` (close)
- Slideshow: Space (pause), `←` `→` (previous/next), `Esc` (exit)

## Requirements and limitations

- Ubuntu 24.04 or newer (GTK 4.10+, libadwaita 1.2+, Python 3.10+). The minimum versions come from the API the app uses; it was tested on GTK 4.14 and libadwaita 1.5. On older systems the app exits with a clear message instead of failing in unclear ways
- Other distributions: use the Flatpak
- Advanced Data Protection must be turned off in your Apple account (otherwise the web API is unavailable)
- The two-factor session expires every few weeks; the unofficial API may change without notice
- Accounts that use legacy two-step verification (trusted devices) are not supported
- Album covers are cached and are refreshed only when you press the refresh button
- A firewall must allow incoming connections from the TV for casting to work
- AirPlay needs the `pyatv` library; the TV must allow access (Settings > AirPlay and HomeKit) and show a PIN when pairing

## Development

The repository keeps the source code in `src/`; built packages are not stored in git but attached to [GitHub Releases](https://github.com/jgu-linux-apps/linux-icloud-photos/releases).

```
linux-icloud-photos/
├── .github/workflows/   # ci.yml (tests + .deb build), release.yml (publishes a release for a tag)
├── src/                 # application source: app.py, backend.py, packaging/, flatpak/, tests/, tools/
├── .gitignore
├── LICENSE
└── README.md
```

All commands below are run inside `src/`.

- Build the `.deb`: `bash build-deb.sh` (the version comes from `version.py`; `bash build-deb.sh "" dist` writes it to `dist/`)
- Release: set `VERSION` and `DATE` in `version.py`, add a line to the version history below, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z`. GitHub Actions checks that the tag matches `version.py`, builds and installs the `.deb`, and publishes it with a source archive as a release
- Tests: `python3 tests/run_tests.py` (needs `xvfb`; compares results with the golden files in `tests/golden`, which keep only values that do not depend on the theme or fonts). Refresh the golden files after intended changes with `python3 tests/run_tests.py --update`
- Translations: `python3 tools/check_i18n.py`
- GitHub Actions (`.github/workflows/ci.yml`) runs the tests on Ubuntu 24.04, the newest LTS and the newest regular release, and builds and installs the `.deb`

## Version history

- 0.17.3: The release package again includes the 256 px PNG icon (the 0.17.2 build server lacked the image library and skipped it). No app changes.
- 0.17.2: The Aurora theme now also colours the top bar when window transparency (glass) is on. Before, the glass setting kept the stock Adwaita header colour.
- 0.17.1: German and Ukrainian translations for the new Theme setting (the 0.17.0 test suite flagged them as missing). No other changes.
- 0.17.0: new **Aurora** theme (Settings → Theme): pastel glass in light mode, an aurora glow on deep navy in dark mode, following the system light/dark setting; violet → cyan gradient on selection and main buttons, rounded thumbnails with a glowing frame on hover. *System* keeps the standard look; works together with window transparency. Homepage in the package points to GitHub.
- 0.16.3: the license (`LICENSE`, `packaging/copyright`) names its author, JGu; the terms are unchanged. No other changes in the app.
- 0.16.2: no changes in the app. The repository now holds the source code in `src/` instead of a source archive, and the `.deb` is published on the GitHub Releases page (built by GitHub Actions for every version tag). README brought up to date (installation steps, removed the finished roadmap).
- 0.16.1: the date shown next to the version (sign-in screen, sidebar) is the release date again (0.16.0 still showed 2026-11-08).
- 0.16.0: `--drive-upload FILE --drive-folder NAME [--prefix P --keep N]` in the window-less bridge: uploads a file to a folder in the iCloud Drive root (replacing a file with the same name, keeping only the newest N files with the prefix). Used by linux-skytrack 1.2.0 to keep its backups in iCloud Drive. Needs iCloud Drive with web access (not available with Advanced Data Protection unless “Access iCloud Data on the Web” is on).
- 0.15.1: `--allow-empty` for `--create-album`: creates an empty album (linux-skytrack 0.8.0 creates a trip album when you plan a trip).
- 0.15.0: links and a window-less bridge for other apps (`--open-album`, `--open-date`, `--albums-json`, `--album-thumbs`, `--range-thumbs`, `--create-album`), used by linux-skytrack 0.3.0 to attach an iCloud album to a flight, show its photos on the boarding pass and create a trip album from the trip days.
- 0.14.0: picker mode (`--pick`) for other apps, used by linux-whazzapp 1.3.0 to attach iCloud photos and videos to a WhatsApp chat. Read-only library in this mode, selection limit, export to a folder, JSON result.
- 0.13.9: expired iCloud file links (Apple answers 410 "endpoint withdrawn" about an hour after the list was loaded): the app now reloads the library by itself when it gets such an answer (at most every 2 minutes) and also every 45 minutes when nothing is open.
- 0.13.8: "Created by: JGu / Supported by Claude" shown under the version on the sign-in screen and in the sidebar.
- 0.13.7: a small background helper (autostart, no window, does not start the app) keeps the app icon in step with the light/dark system theme also while the app is closed. The .deb installs it system-wide (/etc/xdg/autostart); the Flatpak build script installs it for your user (~/.local/share/linux-icloud-photos) and `remove-flatpak.sh` removes it. It takes effect after the next sign-in (the Flatpak build also starts it right away).
- 0.13.6: download links from iCloud that contain the placeholder "${f}" (Apple answered 410 "endpoint withdrawn", e.g. for the camera data of some photos) now get the placeholder replaced before the request.
- 0.13.5: the app icon follows the system light/dark theme (light tile in the light theme, dark tile in the dark theme). The app switches it at start and whenever the theme changes while it runs; the Flatpak gets permission to write only ~/.local/share/icons for this.
- 0.13.4: new dark app icon (dark tile with the colourful flower), matching the dark icons of the other apps in the series.
- 0.13.3: "Send to TV" is always in the right-click menu of a photo or video in an album; if no TV is selected yet, the device list opens and the photo is sent right after you pick one.
- 0.13.2: casting to LG webOS and Chromecast: before every send the TV gets Stop, Play is retried (the TV needs a moment to load), photos are downloaded first and served from memory instantly (the TV was waiting 2-4 s for the proxy), only one send runs at a time, and UPnP error codes are written to the log. Chromecast: a fresh connection by IP address for each send (fixes "threads can only be started once" and the 10 s timeout).
- 0.13.1: DLNA photos on TV: the stream now has a fixed Content-Type (image/jpeg or video/mp4) and the DLNA headers/protocolInfo (contentFeatures, transferMode) that many TVs require; before, some TVs showed crossed-out image icons and no picture.
- 0.13.0: the Flatpak is no longer experimental: build, installation, sign-in and video playback were tested on Ubuntu 26.10 (GNOME 51). No other changes.
- 0.12.8: video in the Flatpak: the built-in player now plays a local file (the film is downloaded to the cache first), because GStreamer inside the sandbox cannot open http:// addresses (log: "No input stream provided by subclass"). Codecs were never the problem.
- 0.12.7: the slideshow button is hidden for videos (also in the right-click menu); when the built-in player fails, the real GStreamer error and the list of available decoders go to the caption and debug.log; the Flatpak build only warns about the .deb when it is really installed.
- 0.12.6: version, date and year shown at the bottom of the login screen; the Flatpak build prints the full path of the remove script.
- 0.12.5: Flatpak video: the build script installs the codec extension `org.freedesktop.Platform.codecs-extra` (GNOME 49+) explicitly; the branch (e.g. `25.08-extra`) is read from the runtime metadata, because without the extension GStreamer cannot decode H.264/HEVC.
- 0.12.4: Flatpak build fixed: the desktop entry is written straight into the app folder (the builder gives every command its own /tmp, so the temporary file was lost). The Python libraries already build correctly
- 0.12.3: Flatpak build asks the pip generator for wheels only for the architecture of the build machine (miniaudio has no aarch64 wheel and stopped the build)
- 0.12.2: renamed to Linux iCloud Photos (package and command `linux-icloud-photos`) with automatic migration of settings, cache and saved passwords; new license (free of charge, modification not permitted); Flatpak build uses ready-made wheels for packages with compiled code (cryptography needed Rust and failed to build)
- 0.12.1: refresh button (F5), the slideshow button now exists only inside albums (viewer and right-click menu, not in the header bar), transparency keeps text readable with a stronger blurred layer, Flatpak build fixed again (the pip generator was downloaded from a wrong address)
- 0.12.0: fixed deletion that took very long (the confirmation scanned the whole library; it now uses one record lookup), optional German and Ukrainian interface, window transparency slider with a blurred photo background, slideshow button shown after clicking an album and in the viewer, Flatpak build fixed for GNOME 49+
- 0.11.0: delete photos (to "Recently Deleted", confirmed by Apple), pinned library versions, minimum GTK/libadwaita versions, self-repairing Python environment, automated tests and CI
- 0.10.0: English and Polish interface (follows the system language), language setting
- 0.9.1: "Add to album" in the right-click menu and the viewer with the 3 most recent albums, searchable album picker
- 0.9.0: "Rows (like Google Photos)" layout, selection mode switches off after the last photo is deselected, instructions to remove the Flatpak
- 0.8.2: adding to an album skips photos that are already in it and says so
- 0.8.1: rubber-band (drag) selection of photos with auto-scroll
- 0.8.0: session-expiry handling, jump to a date (search box and calendar), multi-select with actions, settings window
- 0.7.1: fixes video playback (H.264 version by default, automatic fallback to a local file), adds the "Original proportions" grid option, tidier download package
- 0.7.0: AirPlay (Apple TV) casting with PIN pairing, Flatpak packaging files, Memories removed, documentation update
- 0.6.0: (Memories, removed in 0.7.0) named after albums, 2:30 limit, progressive start and optional local music; bold sidebar titles; star and camera icons; version label; English package description and README; fixes for album covers and heavy background scans
- 0.4.0: photo information, right-click menu, resizable divider, grid presets, Live Photo and Chromecast support
- 0.3.0: infinite scroll, sort toggle, album covers, slideshow, DLNA casting, upload with album choice
- 0.2.x: sidebar menu, zoom, Live Photos, videos, `.deb` package and desktop launcher
- 0.1.0: first working GTK4 client streaming from iCloud

## Third-party software

`pyicloud` (MIT), `pychromecast` (MIT), `pyatv` (MIT), `keyring` (MIT), GTK 4 and libadwaita (LGPL-2.1+), mpv (GPL-2.0+/LGPL-2.1+),
OpenStreetMap Nominatim (optional, only on request; see its usage policy).
