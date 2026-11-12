"""Tryb wyboru (--pick): inna aplikacja (np. linux-whazzapp) prosi o wskazanie zdjęć i filmów.

Aplikacja otwiera się w normalnym oknie, ale biblioteka jest tylko do odczytu, a zaznaczone pliki
po kliknięciu „Wybierz” trafiają do folderu i zostają opisane w pliku JSON. Ten moduł nie importuje GTK
(poza dekodowaniem HEIC, ładowanym leniwie), więc da się go testować bez okna.

Wywołanie:
    linux-icloud-photos --pick --pick-out wynik.json --pick-dir folder [--pick-max 30]

Kod wyjścia: 0 = wybrano pliki (lista w JSON), 1 = anulowano lub błąd.

Format wyniku:
    {"version": 1, "cancelled": false, "errors": ["..."],
     "files": [{"path": "/…/IMG_1.jpg", "name": "IMG_1.jpg", "kind": "photo"|"video",
                "mime": "image/jpeg", "live": false, "source": "original"|"converted"|"medium"|...}]}

Zasady eksportu (pod WhatsApp Web):
  - zdjęcie JPG/PNG/GIF: oryginał bez zmian;
  - zdjęcie HEIC i inne formaty: oryginał zamieniony na JPEG (gdy system ma dekoder), a jeśli się nie da,
    podgląd „medium” z iCloud (to też JPEG);
  - Live Photo: tylko zdjęcie (bez krótkiego filmu);
  - film: wersja H.264 („medium”), którą WhatsApp odtwarza; oryginał tylko gdy nie ma innej.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import tempfile
from pathlib import Path

from i18n import tr

log = logging.getLogger("icloud-photos")

DEFAULT_MAX = 30  # tyle plików naraz pozwala wysłać WhatsApp Web
PASSTHROUGH = (".jpg", ".jpeg", ".png", ".gif")
_OPTS = ("out", "dir", "max")


def parse_cli(argv):
    """Wyjmuje z argv opcje trybu wyboru. Zwraca (opcje albo None, pozostałe argumenty)."""
    args, rest, opts, i = list(argv), [], None, 0
    while i < len(args):
        a = args[i]
        if a == "--pick":
            opts = opts or {}
        elif a.startswith("--pick-"):
            name, eq, val = a[len("--pick-"):].partition("=")
            if name not in _OPTS:
                raise ValueError(f"unknown option: {a}")
            if not eq:
                i += 1
                if i >= len(args):
                    raise ValueError(f"missing value for {a}")
                val = args[i]
            opts = opts or {}
            opts[name] = val
        else:
            rest.append(a)
        i += 1
    if opts is None:
        return None, rest
    try:
        maximum = int(opts.get("max", DEFAULT_MAX))
    except ValueError:
        raise ValueError("--pick-max must be a number") from None
    folder = opts.get("dir") or tempfile.mkdtemp(prefix="icloud-pick-")
    os.makedirs(folder, exist_ok=True)
    return {"out": opts.get("out"), "dir": folder, "max": max(1, min(maximum, 100))}, rest


def _unique_path(folder: str, name: str) -> str:
    base, ext = os.path.splitext(name)
    path, i = os.path.join(folder, name), 1
    while os.path.exists(path):
        path, i = os.path.join(folder, f"{base} ({i}){ext}"), i + 1
    return path


def _item(path: str, kind: str, live: bool, source: str) -> dict:
    return {"path": path, "name": os.path.basename(path), "kind": kind,
            "mime": mimetypes.guess_type(path)[0] or "application/octet-stream",
            "live": live, "source": source}


def heic_to_jpeg_bytes(data: bytes, quality: int = 92) -> bytes:
    """HEIC (i inne formaty znane GdkPixbuf) -> JPEG z uwzględnieniem obrotu. Rzuca wyjątek, gdy się nie da."""
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    loader = GdkPixbuf.PixbufLoader()
    loader.write(data)
    loader.close()
    pixbuf = loader.get_pixbuf()
    if pixbuf is None:
        raise IOError("could not decode the image")
    pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
    ok, buf = pixbuf.save_to_bufferv("jpeg", ["quality"], [str(quality)])
    if not ok:
        raise IOError("could not encode JPEG")
    return bytes(buf)


def _remove(*paths: str) -> None:
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass


def export_asset(icloud, asset, folder: str, converter=None) -> dict:
    """Zapisuje jedno zdjęcie/film w folderze w formacie dobrym dla WhatsApp. Zwraca opis pliku."""
    name = os.path.basename(asset.filename) or f"{asset.id}.bin"
    base, ext = os.path.splitext(name)
    versions = asset.versions

    if icloud.is_video(asset):
        ver = icloud.video_version(asset, True)  # 'medium' = H.264
        if ver is None:
            raise IOError(tr("brak wersji do pobrania"))
        path = _unique_path(folder, base + (ext if ver == "original" else ".mp4"))
        icloud.save_version(asset, ver, path)
        return _item(path, "video", False, ver)

    live = bool(icloud.is_live(asset))  # Live Photo: bierzemy tylko zdjęcie
    if ext.lower() in PASSTHROUGH and "original" in versions:
        path = _unique_path(folder, name)
        icloud.save_version(asset, "original", path)
        return _item(path, "photo", live, "original")

    path = _unique_path(folder, base + ".jpg")
    if converter is not None and "original" in versions:
        part = path + ".part"
        try:
            icloud.save_version(asset, "original", part)
            Path(path).write_bytes(converter(Path(part).read_bytes()))
            _remove(part)
            return _item(path, "photo", live, "converted")
        except Exception as e:  # noqa: BLE001
            log.warning("pick: konwersja %s nie powiodła się (%r), biorę podgląd medium", asset.filename, e)
            _remove(part, path)
    if "medium" not in versions:
        raise IOError(tr("brak wersji do pobrania"))
    icloud.save_version(asset, "medium", path)
    return _item(path, "photo", live, "medium")


def export_assets(icloud, assets, folder: str, progress=None, cancel=None, converter=None):
    """Eksportuje listę zdjęć. Zwraca (lista_opisów, lista_błędów); błąd jednego pliku nie zatrzymuje reszty."""
    items, errors = [], []
    for k, asset in enumerate(assets):
        if cancel is not None and cancel():
            break
        try:
            items.append(export_asset(icloud, asset, folder, converter))
        except Exception as e:  # noqa: BLE001
            errors.append(f"{asset.filename}: {e}")
            log.error("pick: %s: %r", asset.filename, e)
        if progress:
            progress(k + 1, len(assets))
    return items, errors


def write_result(out: str | None, items, errors, cancelled: bool = False) -> None:
    """Zapisuje wynik jako JSON do pliku `out` (atomowo) albo na stdout, gdy `out` nie podano."""
    data = {"version": 1, "cancelled": bool(cancelled), "errors": list(errors), "files": list(items)}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if not out:
        print(text, flush=True)
        return
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, out)
