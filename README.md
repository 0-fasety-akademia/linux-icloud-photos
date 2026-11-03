# iCloud Photos (Linux)

**Current version: 0.9.1 (2026-11-03)**

An unofficial, free iCloud Photos client for Ubuntu (GTK4 + libadwaita).
Photos stay in the cloud: the app streams thumbnails, previews and videos on demand
and keeps only a small, size-limited cache on disk.

Free to use, modify and share under the MIT License (see `LICENSE`).
Created with the help of Claude (Anthropic).
Not affiliated with, endorsed by or sponsored by Apple Inc. "iCloud" is a trademark of Apple Inc.
It relies on the unofficial `pyicloud` library, so Apple may break it at any time. Use at your own risk.

## Features

- Streams photos and videos from iCloud; no library sync to disk
- Thumbnail/preview cache limited to 1 GB (least recently used files are removed)
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
- Slideshow of the current album with a PLAY button, crossfade, 3/5/8/15 s per photo, pause and skip
- Send photos, videos and slideshows to a TV over DLNA/UPnP (LG, Samsung, Sony and others)
- Send to Chromecast and Google Cast TVs
- Send to Apple TV and other AirPlay receivers: videos after one-time PIN pairing (the pairing is remembered in the system keyring)
- Photos to AirPlay receivers are experimental (AirPlay 1 photo protocol) and newer devices may reject them
- Upload photos and videos by drag and drop or with the "+" button
- Choose the destination album for uploads, with progress and error reporting
- Diagnostic log in `~/.cache/icloud-photos-linux/debug.log`
- Installs as a `.deb` package with a desktop launcher and icon
- Flatpak packaging files included (experimental, not yet built or tested)

## Installation

### Debian/Ubuntu package (recommended)

1. Download `icloud-photos-linux_0.9.1_all.deb`.
2. Run `sudo apt install ./icloud-photos-linux_0.9.1_all.deb` (requires internet: `pyicloud` and the optional Chromecast/AirPlay libraries are installed into `/opt/icloud-photos-linux/venv`).
3. Start **iCloud Photos (Linux)** from the application menu and sign in.

Upgrade: run the same command with the newer file. Remove: `sudo apt remove icloud-photos-linux`.
If a library failed to install: `sudo /opt/icloud-photos-linux/venv/bin/pip install pyicloud keyring pychromecast pyatv`.

### Flatpak (experimental)

The source archive contains a `flatpak/` folder. Build and install with `bash flatpak/build-flatpak.sh`, then run
`flatpak run local.icloudphotos.linux`. It has **not been built or tested yet**; see `flatpak/README.md`.

**Do not keep both versions.** The Flatpak and the `.deb` share the same name, so both would appear in the
menu, and they keep separate settings and sign-ins. To remove the Flatpak (and its data) and keep the `.deb`:
`bash flatpak/remove-flatpak.sh` or `flatpak uninstall --delete-data local.icloudphotos.linux`.
To remove the `.deb` and keep the Flatpak: `sudo apt remove icloud-photos-linux`.
Check what is installed: `flatpak list --app | grep -i icloud` and `dpkg -l | grep icloud-photos`.
Inside the Flatpak, mpv is not available, so videos play in the built-in player.

### Troubleshooting

- Videos do not play: look at `~/.cache/icloud-photos-linux/mpv.log` and `~/.cache/icloud-photos-linux/debug.log`, and make sure `mpv` is installed (`sudo apt install mpv`).
- "Session expired": sign in again; the app keeps your Apple ID and password in the system keyring.
- Anything else: `~/.cache/icloud-photos-linux/debug.log` records errors with timestamps.

## Keyboard shortcuts

- Grid: `Ctrl +`, `Ctrl −`, `Ctrl 0` (thumbnail size), `F11` (fullscreen)
- Grid: drag with the left mouse button (rubber-band selection), `Ctrl`+drag (toggle), `Ctrl`+click (start selecting), `Ctrl A` (select all loaded photos), `Esc` (leave selection mode)
- Viewer: `←` `→` `Home` `End` (navigate), `Ctrl +/−/0` (zoom), `F` (fullscreen), `I` (information)
- Viewer: `L` or Space (Live Photo / play video), `M` (open video in mpv), `A` (add to album), `Esc` (close)
- Slideshow: Space (pause), `←` `→` (previous/next), `Esc` (exit)

## Requirements and limitations

- Advanced Data Protection must be turned off in your Apple account (otherwise the web API is unavailable)
- The two-factor session expires every few weeks; the unofficial API may change without notice
- Accounts that use legacy two-step verification (trusted devices) are not supported
- Album covers are cached and are not refreshed automatically
- A firewall must allow incoming connections from the TV for casting to work
- AirPlay needs the `pyatv` library; the TV must allow access (Settings > AirPlay and HomeKit) and show a PIN when pairing

## Roadmap (not implemented yet)

- Verify and finish the Flatpak package (and decide how to handle mpv inside the sandbox)
- More reliable photo casting to AirPlay receivers

## Version history

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
