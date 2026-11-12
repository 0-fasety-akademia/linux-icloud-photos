"""Most dla innych aplikacji (np. linux-skytrack): zapytania do biblioteki bez okna.

Używa tej samej zapisanej sesji co aplikacja (ciasteczka w ~/.config/linux-icloud-photos/session,
hasło z keyringu). Nigdy nie pyta o hasło ani kod 2FA - gdy sesja wymaga logowania, zwraca błąd
"login_required" i trzeba raz otworzyć Linux iCloud Photos. Nie importuje GTK.

Wywołania (wynik zawsze w pliku JSON z --json, kod wyjścia 0 = ok, 1 = błąd, 2 = złe opcje):

    linux-icloud-photos --albums-json --json OUT
        {"ok": true, "albums": [{"name": "Dubaj 2025", "smart": false}, ...]}

    linux-icloud-photos --album-thumbs NAME --out-dir DIR [--max 8] --json OUT
        miniatury pierwszych zdjęć albumu (najnowsze najpierw)
        {"ok": true, "album": NAME, "count": 123, "files": ["/…/0.jpg", ...]}

    linux-icloud-photos --range-thumbs --from ISO --to ISO --out-dir DIR [--max 8] --json OUT
        miniatury zdjęć zrobionych w podanym czasie (np. dni podróży); "count" = ile zdjęć w zakresie
        (najwyżej --limit, domyślnie 3000)

    linux-icloud-photos --create-album NAME --from ISO --to ISO [--allow-empty] --json OUT
    linux-icloud-photos --create-album NAME --allow-empty --json OUT     (pusty album, np. na planowaną podróż)
        tworzy album (albo używa istniejącego o tej nazwie) i dodaje zdjęcia z zakresu dat, pomijając
        te, które już w nim są; postęp na stdout: "progress <zrobione> <wszystkie>"
        {"ok": true, "album": NAME, "created": true, "found": 87, "added": 87, "already": 0, "errors": []}
        Bez --allow-empty album nie powstaje, gdy w zakresie nie ma zdjęć ("created": false, "found": 0).

    linux-icloud-photos --drive-upload PLIK [--drive-folder NAZWA] [--prefix P --keep N] --json OUT
        (0.16.0) wysyła plik do folderu NAZWA w katalogu głównym iCloud Drive (domyślnie "Kopie
        zapasowe"; folder powstaje, gdy go nie ma). Plik o tej samej nazwie jest zastępowany. Z
        --prefix i --keep zostawia w folderze tylko N najnowszych plików zaczynających się od P
        (starsze trafiają do „Ostatnio usuniętych” w iCloud Drive).
        {"ok": true, "folder": "SkyTrack", "name": "skytrack-kopia-2026-11-09.skytrack",
         "size": 12345, "replaced": false, "removed": ["skytrack-kopia-2026-10-01.skytrack"]}
        Błąd "drive_unavailable": iCloud Drive wyłączony albo niedostępny w przeglądarce (np. przy
        Zaawansowanej ochronie danych bez dostępu do danych przez www).

ISO = data/czas z ISO 8601, np. 2025-02-14T00:00:00+01:00 (bez strefy = czas lokalny tego komputera).
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime

OPTIONS = {"--albums-json": 0, "--album-thumbs": 1, "--range-thumbs": 0, "--create-album": 1,
           "--from": 1, "--to": 1, "--out-dir": 1, "--max": 1, "--limit": 1, "--json": 1,
           "--allow-empty": 0, "--drive-upload": 1, "--drive-folder": 1, "--prefix": 1, "--keep": 1}
COMMANDS = ("--albums-json", "--album-thumbs", "--range-thumbs", "--create-album", "--drive-upload")
API_VERSION = 1


class BridgeError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code


def is_bridge_call(argv) -> bool:
    return any(a in COMMANDS for a in argv[1:])


def parse(argv):
    opts, i, args = {}, 0, list(argv[1:])
    while i < len(args):
        a = args[i]
        if a not in OPTIONS:
            raise BridgeError("bad_option", f"unknown option: {a}")
        if OPTIONS[a]:
            if i + 1 >= len(args):
                raise BridgeError("bad_option", f"missing value for {a}")
            opts[a] = args[i + 1]
            i += 2
        else:
            opts[a] = True
            i += 1
    cmds = [c for c in COMMANDS if c in opts]
    if len(cmds) != 1:
        raise BridgeError("bad_option", "exactly one command expected")
    if "--json" not in opts:
        raise BridgeError("bad_option", "--json OUT is required")
    return cmds[0], opts


def parse_time(text: str) -> float:
    try:
        dt = datetime.fromisoformat(text.strip())
    except ValueError as e:
        raise BridgeError("bad_option", f"bad date: {text}") from e
    if dt.tzinfo is None:
        dt = dt.astimezone()          # czas lokalny tego komputera
    return dt.timestamp()


def connect():
    """Logowanie zapisaną sesją. Zwraca backend.ICloud albo rzuca BridgeError('login_required')."""
    import backend

    cfg_file = backend.CONFIG_DIR / "config.json"
    try:
        apple_id = json.loads(cfg_file.read_text()).get("apple_id")
    except Exception:  # noqa: BLE001
        apple_id = None
    if not apple_id:
        raise BridgeError("login_required", "no saved Apple ID")
    pw = None
    try:
        import keyring

        pw = keyring.get_password("linux-icloud-photos", apple_id) or \
            keyring.get_password("icloud-photos-linux", apple_id)
    except Exception:  # noqa: BLE001
        pw = None
    if not pw:
        raise BridgeError("login_required", "no saved password")
    ic = backend.ICloud()
    try:
        state = ic.login(apple_id, pw)
    except Exception as e:  # noqa: BLE001
        if backend.is_auth_error(e):
            raise BridgeError("login_required", str(e)) from e
        raise
    if state != "ok":
        raise BridgeError("login_required", "two-factor code needed")
    return ic


def find_album(ic, name):
    for n, album in ic.albums():
        if n == name:
            return album
    raise BridgeError("album_not_found", name)


def write_thumbs(ic, assets, out_dir, maxn):
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for asset in assets:
        if len(files) >= maxn:
            break
        try:
            data = ic.fetch(asset, "thumb")
        except Exception:  # noqa: BLE001
            continue
        path = os.path.join(out_dir, f"{len(files)}.jpg")
        with open(path, "wb") as f:
            f.write(data)
        files.append(path)
    return files


def assets_in_range(ic, t_from, t_to, limit):
    """Zdjęcia z biblioteki (Wszystkie zdjęcia) zrobione między t_from a t_to (timestampy)."""
    library = ic.api.photos.all
    out = []
    for asset in ic.iter_jump(library, t_from, newest_first=False):
        d = ic.asset_date(asset)
        if d is None:
            continue
        ts = d.timestamp()
        if ts < t_from:
            continue
        if ts > t_to:
            break
        out.append(asset)
        if len(out) >= limit:
            break
    return out


def _drive_root(ic):
    try:
        drive = ic.api.drive
        drive.refresh_root()
        root = drive.root
        root.get_children(force=True)
        return drive, root
    except Exception as e:  # noqa: BLE001
        raise BridgeError("drive_unavailable", f"{type(e).__name__}: {e}") from e


def drive_upload(ic, path, folder, prefix="", keep=0):
    import io as _io

    if not os.path.isfile(path):
        raise BridgeError("bad_option", f"no such file: {path}")
    folder = (folder or "Kopie zapasowe").strip().strip("/")
    if not folder or "/" in folder:
        raise BridgeError("bad_option", "--drive-folder: one folder name in the iCloud Drive root")
    drive, root = _drive_root(ic)
    node = next((c for c in root.get_children() if c.name == folder and c.type == "folder"), None)
    if node is None:
        root.mkdir(folder)
        drive.refresh_root()
        node = next((c for c in drive.root.get_children(force=True)
                     if c.name == folder and c.type == "folder"), None)
        if node is None:
            raise BridgeError("drive_unavailable", f"could not create folder {folder}")
    name = os.path.basename(path)
    replaced = False
    for c in list(node.get_children(force=True)):
        if c.type == "file" and c.name == name:
            c.delete()
            replaced = True
    with open(path, "rb") as f:
        data = f.read()
    buf = _io.BytesIO(data)
    buf.name = name                      # pyicloud sends file_object.name as the file name
    node.upload(buf)
    removed = []
    if prefix and keep > 0:
        files = [c for c in node.get_children(force=True)
                 if c.type == "file" and c.name.startswith(prefix) and c.name != name]
        def when(c):
            d = c.date_modified or c.date_changed
            return d.timestamp() if d else 0
        files.sort(key=lambda c: (when(c), c.name), reverse=True)
        for c in files[max(0, keep - 1):]:
            try:
                c.delete()
                removed.append(c.name)
            except Exception:  # noqa: BLE001
                pass
    return {"folder": folder, "name": name, "size": len(data), "replaced": replaced, "removed": removed}


def run(cmd, o):
    maxn = max(1, min(48, int(o.get("--max", 8))))
    limit = max(1, int(o.get("--limit", 3000)))
    if cmd == "--albums-json":
        ic = connect()
        smart = {"All Photos", "Library", "Favorites", "Videos", "Live", "Panoramas", "Time-lapse",
                 "Slo-mo", "Bursts", "Screenshots", "Selfies", "Portrait", "Long Exposure",
                 "Animated", "Hidden", "Recently Deleted", "Recently Added", "Screen Recordings",
                 "RAW"}
        return {"albums": [{"name": n, "smart": n in smart} for n, _a in ic.albums()]}
    if cmd == "--album-thumbs":
        if "--out-dir" not in o:
            raise BridgeError("bad_option", "--out-dir is required")
        ic = connect()
        album = find_album(ic, o["--album-thumbs"])
        try:
            count = len(album)
        except Exception:  # noqa: BLE001
            count = None
        files = write_thumbs(ic, ic.iter_assets(album, True), o["--out-dir"], maxn)
        return {"album": o["--album-thumbs"], "count": count, "files": files}
    if cmd == "--range-thumbs":
        if "--out-dir" not in o or "--from" not in o or "--to" not in o:
            raise BridgeError("bad_option", "--from, --to and --out-dir are required")
        t_from, t_to = parse_time(o["--from"]), parse_time(o["--to"])
        ic = connect()
        assets = assets_in_range(ic, t_from, t_to, limit)
        files = write_thumbs(ic, assets, o["--out-dir"], maxn)
        return {"count": len(assets), "files": files,
                "first": assets[0].asset_date.isoformat() if assets else None,
                "last": assets[-1].asset_date.isoformat() if assets else None}
    if cmd == "--create-album":
        allow_empty = "--allow-empty" in o
        has_range = "--from" in o and "--to" in o
        if not has_range and not allow_empty:
            raise BridgeError("bad_option", "--from and --to are required (or --allow-empty)")
        name = o["--create-album"].strip()
        if not name:
            raise BridgeError("bad_option", "empty album name")
        ic = connect()
        assets = []
        if has_range:
            t_from, t_to = parse_time(o["--from"]), parse_time(o["--to"])
            assets = assets_in_range(ic, t_from, t_to, limit)
        if not assets and not allow_empty:
            return {"album": name, "created": False, "found": 0, "added": 0, "already": 0,
                    "errors": []}
        created = False
        try:
            album = find_album(ic, name)
        except BridgeError:
            album = ic.api.photos.create_album(name)
            if album is None:
                raise BridgeError("create_failed", name)
            created = True

        def progress(done, total):
            print(f"progress {done} {total}", flush=True)

        added, already, errors = (ic.add_to_album(album, assets, progress=progress) if assets
                                  else (0, [], []))
        try:
            ic.refresh_library()        # nowy album widoczny także w otwartej aplikacji po odświeżeniu
        except Exception:  # noqa: BLE001
            pass
        return {"album": name, "created": created, "found": len(assets), "added": added,
                "already": len(already), "errors": errors[:20]}
    if cmd == "--drive-upload":
        try:
            keep = max(0, int(o.get("--keep", 0)))
        except ValueError as e:
            raise BridgeError("bad_option", "--keep must be a number") from e
        path = o["--drive-upload"]
        if not os.path.isfile(path):
            raise BridgeError("bad_option", f"no such file: {path}")
        ic = connect()
        return drive_upload(ic, path, o.get("--drive-folder", ""), o.get("--prefix", ""), keep)
    raise BridgeError("bad_option", cmd)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv
    out = None
    try:
        cmd, o = parse(argv)
        out = o["--json"]
        result = {"version": API_VERSION, "ok": True, "error": None}
        result.update(run(cmd, o))
        rc = 0
    except BridgeError as e:
        result = {"version": API_VERSION, "ok": False, "error": e.code, "message": str(e)}
        rc = 2 if e.code == "bad_option" else 1
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        result = {"version": API_VERSION, "ok": False, "error": "failed",
                  "message": f"{type(e).__name__}: {e}"}
        rc = 1
    if out:
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        os.replace(tmp, out)
    else:
        print(json.dumps(result, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
