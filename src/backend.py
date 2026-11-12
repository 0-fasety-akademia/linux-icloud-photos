"""Backend iCloud Photos: logowanie, leniwa lista zdjęć, cache miniatur i proxy wideo.

Nic nie jest synchronizowane. Na dysku ląduje wyłącznie ograniczony cache
(miniatury + podglądy "medium"), przycinany do MAX_CACHE_BYTES (LRU).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import socket
import time
import secrets
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from i18n import month_abbr, tr

# Tryb wyboru (--pick): biblioteka jest tylko do odczytu, żeby w oknie wyboru nie dało się przypadkiem
# niczego usunąć, dodać do albumu, oznaczyć ani wysłać do iCloud.
READ_ONLY = False


def _guard_write() -> None:
    if READ_ONLY:
        raise PermissionError(tr("Tryb wyboru: biblioteka jest tylko do odczytu"))

_XDG_CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
_XDG_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

APP_NAME = "linux-icloud-photos"
OLD_APP_NAME = "icloud-photos-linux"  # nazwa sprzed 0.12.2
CACHE_DIR = _XDG_CACHE / APP_NAME
CONFIG_DIR = _XDG_CONFIG / APP_NAME


def migrate_old_data() -> list:
    """Po zmianie nazwy aplikacji przenosi ustawienia, sesję i pamięć podręczną ze starych katalogów
    (tylko gdy nowy katalog jeszcze nie istnieje, więc nigdy niczego nie nadpisuje)."""
    moved = []
    for base, new in ((_XDG_CONFIG, CONFIG_DIR), (_XDG_CACHE, CACHE_DIR)):
        old = base / OLD_APP_NAME
        try:
            if old.is_dir() and not new.exists():
                shutil.move(str(old), str(new))
                moved.append(str(new))
        except OSError:
            pass
    return moved


migrate_old_data()
THUMB_DIR = CACHE_DIR / "thumbs"
MEDIUM_DIR = CACHE_DIR / "medium"
LIVE_DIR = CACHE_DIR / "live"
VIDEO_DIR = CACHE_DIR / "videos"
# opis DLNA (contentFeatures) dla obrazów i wideo wysyłanych na telewizor
DLNA_FEATURES_IMAGE = "DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00f00000000000000000000000000000"
DLNA_FEATURES_VIDEO = "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
MAX_CACHE_BYTES = 1 * 1024**3  # 1 GB
TESTED_PYICLOUD = "2026.10.1"  # wersja pyicloud, z którą aplikacja była testowana


def pyicloud_version():
    """Zainstalowana wersja pyicloud (albo None)."""
    try:
        from importlib.metadata import version

        return version("pyicloud")
    except Exception:  # noqa: BLE001
        return None

VIDEO_EXT = (".mov", ".mp4", ".m4v", ".avi", ".mkv")

DEBUG_LOG = CACHE_DIR / "debug.log"
COVERS_FILE = CACHE_DIR / "covers.json"
log = logging.getLogger("icloud-photos")
log.setLevel(logging.INFO)
try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler

    _h = RotatingFileHandler(DEBUG_LOG, maxBytes=512 * 1024, backupCount=1, encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(_h)
except OSError:
    pass


AUTH_CLASS_HINTS = ("failedlogin", "authentication", "autherror", "notloggedin", "2fa",
                    "twofactor", "nostoredpassword", "unauthorized", "reauth")
AUTH_TEXT_HINTS = ("unauthorized", "invalid global session", "http 401", "http 403", "(401)",
                   "(421)", "(450)", "session expired", "not authenticated",
                   "authentication required", "needs 2fa", "requires 2fa")


def is_auth_error(e: BaseException) -> bool:
    """Czy wyjątek wygląda na wygaśnięcie sesji/uwierzytelnienia Apple?"""
    for cls in type(e).__mro__:
        name = cls.__name__.lower()
        if any(h in name for h in AUTH_CLASS_HINTS):
            return True
    text = str(e).lower()
    return any(h in text for h in AUTH_TEXT_HINTS)


_PREFIX = {"sty": 1, "jan": 1, "lut": 2, "feb": 2, "mar": 3, "kwi": 4, "apr": 4, "maj": 5,
           "may": 5, "cze": 6, "jun": 6, "lip": 7, "jul": 7, "sie": 8, "aug": 8, "wrz": 9,
           "sep": 9, "paź": 10, "paz": 10, "oct": 10, "lis": 11, "nov": 11, "gru": 12,
           "dec": 12,
           # niemiecki
           "mär": 3, "mai": 5, "okt": 10, "dez": 12,
           # ukraiński
           "січ": 1, "лют": 2, "бер": 3, "кві": 4, "тра": 5, "чер": 6, "лип": 7, "сер": 8,
           "вер": 9, "жов": 10, "лис": 11, "гру": 12}
_MON_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]


def parse_date_query(text: str):
    """Rozpoznaje daty wpisane w wyszukiwarce: 2024, 08.2024, 2024-08, 15.08.2024, 2024-08-15,
    „sierpień 2024”, „15 sie 2024”. Zwraca (początek, koniec, etykieta) lub None."""
    import calendar
    import re
    from datetime import datetime

    t = text.strip().lower()
    if not t:
        return None

    def span(y, m=None, d=None):
        try:
            if m is None:
                a, b, lab = datetime(y, 1, 1), datetime(y, 12, 31, 23, 59, 59), str(y)
            elif d is None:
                last = calendar.monthrange(y, m)[1]
                a, b = datetime(y, m, 1), datetime(y, m, last, 23, 59, 59)
                lab = f"{month_abbr()[m - 1]} {y}"
            else:
                a, b = datetime(y, m, d), datetime(y, m, d, 23, 59, 59)
                lab = f"{d} {month_abbr()[m - 1]} {y}"
        except ValueError:
            return None
        return (a, b, lab) if 1990 <= y <= 2100 else None

    if re.fullmatch(r"\d{4}", t):
        return span(int(t))
    m = re.fullmatch(r"(\d{4})[./-](\d{1,2})", t)
    if m:
        return span(int(m[1]), int(m[2]))
    m = re.fullmatch(r"(\d{1,2})[./-](\d{4})", t)
    if m:
        return span(int(m[2]), int(m[1]))
    m = re.fullmatch(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", t)
    if m:
        return span(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", t)
    if m:
        return span(int(m[3]), int(m[2]), int(m[1]))
    m = re.fullmatch(r"(?:(\d{1,2})\s+)?([^\W\d_]{3,})\.?\s+(\d{4})", t)
    if m and m[2][:3] in _PREFIX:
        return span(int(m[3]), _PREFIX[m[2][:3]], int(m[1]) if m[1] else None)
    return None


def justify_rows(aspects, width, target_h, gap=4, max_stretch=1.6):
    """Układ w stylu Google Photos: zdjęcia w rzędach o równej wysokości, rząd wypełnia całą
    szerokość. Zwraca listę (start, ile, wysokość, [szerokości]). Ostatni rząd bywa krótszy."""
    rows, i, n = [], 0, len(aspects)
    width = max(120, int(width))
    while i < n:
        j, total = i, 0.0
        while j < n:
            total += aspects[j] * target_h
            j += 1
            if total + gap * (j - i - 1) >= width:
                break
        cnt = j - i
        avail = width - gap * (cnt - 1)
        full = total + gap * (cnt - 1) >= width
        sum_asp = sum(aspects[i:j])
        h = avail / sum_asp if full else float(target_h)
        h = min(h, target_h * max_stretch)
        widths = [max(1, int(round(a * h))) for a in aspects[i:j]]
        if full and h < target_h * max_stretch:
            widths[-1] += avail - sum(widths)  # dopasuj ostatni do pełnej szerokości
            widths[-1] = max(1, widths[-1])
        rows.append((i, cnt, max(1, int(round(h))), widths))
        i = j
    return rows


def asset_aspect(asset) -> float:
    """Proporcje (szerokość/wysokość) zdjęcia z uwzględnieniem orientacji; 4:3, gdy brak danych."""
    try:
        w, h = asset.dimensions
        if not w or not h:
            return 4 / 3
        try:
            from pyicloud.services.photos_cloudkit.mappers import record_field_value

            rec = asset._asset_record
            o = record_field_value(rec, "orientation") or record_field_value(
                rec, "originalOrientation") or 1
            if int(o) in (5, 6, 7, 8):  # zdjęcie obrócone o 90° - zamień wymiary
                w, h = h, w
        except Exception:  # noqa: BLE001
            pass
        return max(0.4, min(3.0, w / h))
    except Exception:  # noqa: BLE001
        return 4 / 3


def cache_size() -> int:
    total = 0
    for d in (THUMB_DIR, MEDIUM_DIR, LIVE_DIR, VIDEO_DIR):
        if d.exists():
            for p in d.iterdir():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return total


def clear_cache() -> int:
    """Usuwa całą pamięć podręczną (miniatury, podglądy, klipy, filmy). Zwraca zwolnione bajty."""
    freed = cache_size()
    for d in (THUMB_DIR, MEDIUM_DIR, LIVE_DIR, VIDEO_DIR):
        if d.exists():
            for p in d.iterdir():
                try:
                    p.unlink()
                except OSError:
                    pass
    try:
        COVERS_FILE.unlink()
    except OSError:
        pass
    return freed


def prune_cache(limit: int = MAX_CACHE_BYTES) -> None:
    """Usuwa najstarsze pliki cache, aż całość zmieści się w limicie."""
    files = []
    total = 0
    for d in (THUMB_DIR, MEDIUM_DIR, LIVE_DIR, VIDEO_DIR):
        if not d.exists():
            continue
        for p in d.iterdir():
            try:
                st = p.stat()
            except OSError:
                continue
            files.append((st.st_mtime, st.st_size, p))
            total += st.st_size
    if total <= limit:
        return
    files.sort()  # najstarsze pierwsze
    for _, size, p in files:
        try:
            p.unlink()
            total -= size
        except OSError:
            pass
        if total <= limit * 0.9:
            break


class ICloud:
    def __init__(self) -> None:
        self.api = None
        self._streams: dict[str, tuple[object, str]] = {}
        self._blobs: dict[str, bytes] = {}  # zdjęcia dla TV trzymane w pamięci (szybka odpowiedź)
        self._servers: dict[bool, ThreadingHTTPServer] = {}
        self._proxy_lock = threading.Lock()
        self._cover_lock = threading.Lock()
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        MEDIUM_DIR.mkdir(parents=True, exist_ok=True)
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        (CONFIG_DIR / "session").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _fix_download_urls(session) -> None:
        """Adresy pobierania z CloudKit mogą zawierać szablon "${f}" (miejsce na nazwę pliku).
        pyicloud go nie podstawia, a Apple odpowiada wtedy 410 ("endpoint withdrawn") - tak padały
        np. dane aparatu niektórych zdjęć. Podstawiamy nazwę w jednym miejscu: w każdym żądaniu sesji."""
        orig = session.request

        def request(method, url, *a, **kw):
            if isinstance(url, str) and "${f}" in url:
                url = url.replace("${f}", "file")
            return orig(method, url, *a, **kw)

        session.request = request

    # ---------- logowanie ----------
    def login(self, apple_id: str, password: str) -> str:
        """Zwraca "ok" albo "2fa". Błędy logowania lecą jako wyjątki."""
        from pyicloud import PyiCloudService

        v = pyicloud_version()
        if v and v != TESTED_PYICLOUD:
            log.warning("pyicloud %s różni się od przetestowanej %s", v, TESTED_PYICLOUD)

        self.api = PyiCloudService(
            apple_id,
            password,
            cookie_directory=str(CONFIG_DIR / "session"),
        )
        self._fix_download_urls(self.api.session)
        if getattr(self.api, "requires_2fa", False):
            return "2fa"
        if getattr(self.api, "requires_2sa", False):
            raise RuntimeError(
                tr("Konto wymaga starszej weryfikacji 2SA (zaufane urządzenie) - "
                "ta wersja aplikacji obsługuje tylko 2FA z kodem.")
            )
        return "ok"

    def verify_2fa(self, code: str) -> bool:
        ok = bool(self.api.validate_2fa_code(code.strip()))
        if ok and not self.api.is_trusted_session:
            self.api.trust_session()
        return ok

    # ---------- albumy i lista ----------
    def albums(self) -> list[tuple[str, object]]:
        """[(nazwa, album)]: 'All Photos' pierwszy, potem reszta (bez folderów)."""
        library = self.api.photos
        out = [("All Photos", library.all)]
        seen = {"All Photos"}
        for a in library.albums:
            name = getattr(a, "name", "") or ""
            if not name or name in seen:
                continue
            if type(a).__name__ == "PhotoAlbumFolder":
                continue  # foldery nie zawierają zdjęć bezpośrednio
            seen.add(name)
            out.append((name, a))
        return out

    def refresh_library(self):
        """Wymusza ponowne pobranie listy albumów (pyicloud trzyma ją w pamięci) i zapomina zapisane
        okładki, żeby pobrały się od nowa. Same zdjęcia w albumie zawsze są pobierane na bieżąco."""
        photos = self.api.photos
        fn = getattr(photos, "refresh_albums", None)
        if fn is None:
            fn = getattr(getattr(photos, "_root_library", None), "refresh_albums", None)
        if fn is not None:
            fn()
        with self._cover_lock:
            try:
                COVERS_FILE.unlink()
            except FileNotFoundError:
                pass
        log.info("odświeżono bibliotekę")

    @staticmethod
    def total(album) -> int:
        return len(album)

    @staticmethod
    def iter_assets(album, newest_first: bool = True, flip: bool = False):
        """Leniwie. newest_first=True -> od najnowszych.

        Różne albumy Apple mają różny domyślny kierunek, więc ustawiamy go jawnie;
        flip odwraca założenie, gdy aplikacja wykryje, że kolejność wyszła odwrotna."""
        try:
            from pyicloud.services.photos import DirectionEnum

            want_desc = newest_first != flip
            album._direction = DirectionEnum.DESCENDING if want_desc else DirectionEnum.ASCENDING
        except Exception:  # noqa: BLE001
            log.warning("nie udało się ustawić kierunku albumu:\n%s", traceback.format_exc())
        yield from album

    @staticmethod
    def asset_date(asset):
        try:
            return asset.asset_date
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def is_video(asset) -> bool:
        try:
            if asset.item_type == "movie":
                return True
        except Exception:
            pass
        return asset.filename.lower().endswith(VIDEO_EXT)

    @staticmethod
    def is_live(asset) -> bool:
        try:
            return bool(asset.is_live_photo)
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def live_version(asset) -> str | None:
        v = asset.versions
        return next((k for k in ("medium_video", "original_video") if k in v), None)

    @staticmethod
    def video_version(asset, compat: bool) -> str | None:
        """compat=True: 'medium' (H.264, szybki start) dla odtwarzacza w aplikacji;
        compat=False: 'original' dla mpv."""
        v = asset.versions
        order = ("medium", "original") if compat else ("original", "medium")
        return next((k for k in order if k in v), None)

    # ---------- obrazy (z cache) ----------
    @staticmethod
    def _pick(asset, order):
        versions = asset.versions
        return next((v for v in order if v in versions), None)

    def _cache_path(self, asset, kind: str):
        if self.is_video(asset):
            # Dla filmów klucze "thumb"/"medium" to PLIKI WIDEO - obrazki są pod *_image.
            order = (("thumb_image", "medium_image") if kind == "thumb"
                     else ("medium_image", "thumb_image"))
        else:
            order = ("thumb", "medium") if kind == "thumb" else ("medium", "original")
        ver = self._pick(asset, order)
        if ver is None:
            log.warning("brak wersji %s dla %s (są: %s)", kind, asset.filename,
                        list(asset.versions))
            raise LookupError(tr("brak wersji do pobrania"))
        d = THUMB_DIR if kind == "thumb" else MEDIUM_DIR
        key = hashlib.sha1(f"{asset.id}:{ver}".encode()).hexdigest()
        return d / f"{key}.img", ver

    def fetch(self, asset, kind: str) -> bytes:
        """kind: 'thumb' albo 'medium'. Zwraca bajty (JPEG/HEIC), z cache lub z sieci."""
        path, ver = self._cache_path(asset, kind)
        if path.exists():
            try:
                os.utime(path)  # odśwież "LRU"
                return path.read_bytes()
            except OSError:
                pass
        last: Exception | None = None
        for _ in range(2):
            try:
                data = asset.download(ver)
                if not data:
                    raise IOError(tr("pusta odpowiedź"))
                tmp = path.with_suffix(".tmp" + secrets.token_hex(3))
                tmp.write_bytes(data)
                tmp.replace(path)
                return data
            except Exception as e:  # noqa: BLE001
                last = e
        log.warning("pobieranie %s/%s nieudane: %r", asset.filename, ver, last)
        self._notify_gone(last)
        raise last  # type: ignore[misc]

    def _notify_gone(self, err: Exception | None) -> None:
        """Apple odpowiada 410 na adres, którego ważność minęła (linki do plików żyją około godziny).
        Aplikacja ustawia on_links_stale i wtedy sama pobiera od nowa listę z aktualnymi adresami."""
        if err is not None and "EndpointGone" in type(err).__name__:
            cb = getattr(self, "on_links_stale", None)
            if cb:
                try:
                    cb()
                except Exception:  # noqa: BLE001
                    pass

    # ---------- okładki albumów ----------
    def album_cover(self, key: str, album) -> bytes:
        """Miniatura reprezentująca album (najnowsze zdjęcie). Zapamiętana na dysku."""
        with self._cover_lock:
            try:
                covers = json.loads(COVERS_FILE.read_text())
            except Exception:  # noqa: BLE001
                covers = {}
        name = covers.get(key)
        if name and (THUMB_DIR / name).exists():
            return (THUMB_DIR / name).read_bytes()
        asset = next(iter(self.iter_assets(album, True)), None)
        if asset is None:
            raise LookupError(tr("pusty album"))
        data = self.fetch(asset, "thumb")
        path, _ = self._cache_path(asset, "thumb")
        with self._cover_lock:
            try:
                covers = json.loads(COVERS_FILE.read_text())
            except Exception:  # noqa: BLE001
                covers = {}
            covers[key] = path.name
            COVERS_FILE.write_text(json.dumps(covers))
        return data

    # ---------- wysyłanie do iCloud ----------
    UPLOAD_EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tif", ".tiff",
                  ".dng", ".mov", ".mp4", ".m4v")

    def upload(self, path: str, album=None):
        """Wysyła plik do biblioteki; gdy podano album użytkownika - dodaje go też tam."""
        _guard_write()
        if not path.lower().endswith(self.UPLOAD_EXT):
            raise ValueError(tr("nieobsługiwany typ pliku: ") + os.path.basename(path))
        target = album if album is not None else self.api.photos.all
        asset = target.upload(path)
        if asset is None:
            raise RuntimeError(tr("iCloud nie przyjął pliku (ten album nie przyjmuje zdjęć?)"))
        log.info("wysłano %s -> %s", os.path.basename(path),
                 getattr(album, "name", "biblioteka"))
        return asset

    # ---------- skok do daty ----------
    def probe(self) -> int:
        """Lekki test, czy sesja nadal działa (rzuca wyjątek, gdy wygasła)."""
        return len(self.api.photos.all)

    def find_start(self, album, target_ts: float, newest_first: bool):
        """Wyszukiwanie binarne pozycji zdjęcia najbliższego dacie. Zwraca (pozycja, malejąco)
        - od której pozycji i w którą stronę czytać, żeby lista zaczynała się od tej daty."""
        from pyicloud.services.photos import DirectionEnum

        n = len(album)
        if n == 0:
            return 0, True

        def date_at(i):
            return next(album._get_photos_at(i, DirectionEnum.ASCENDING, 1)).asset_date.timestamp()

        asc = date_at(0) <= date_at(n - 1)  # czy daty rosną wraz z pozycją
        lo, hi = 0, n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            d = date_at(mid)
            before = d < target_ts if asc else d > target_ts
            if before:
                lo = mid + 1
            else:
                hi = mid
        rank = lo
        if newest_first:
            # chcemy zdjęcia nie nowsze niż data -> jedno „przed” pierwszym nowszym
            if (asc and date_at(rank) > target_ts) or (not asc and date_at(rank) < target_ts):
                rank = rank - 1 if asc else rank
            rank = max(0, min(n - 1, rank))
            return rank, asc          # malejąco po dacie = malejąco po pozycji, gdy daty rosną
        return max(0, min(n - 1, rank)), not asc

    def iter_jump(self, album, target_ts: float, newest_first: bool = True):
        """Leniwie czyta album od zdjęcia najbliższego podanej dacie (w wątku roboczym)."""
        import copy

        from pyicloud.services.photos import DirectionEnum

        a = copy.copy(album)
        rank, desc = self.find_start(a, target_ts, newest_first)
        log.info("skok do daty: pozycja %d (malejąco=%s)", rank, desc)
        direction = DirectionEnum.DESCENDING if desc else DirectionEnum.ASCENDING
        size, offset, seen = a.page_size, rank, set()
        while offset >= 0:
            n = 0
            for photo in a._get_photos_at(offset, direction, size):
                n += 1
                if photo.id in seen:
                    continue
                seen.add(photo.id)
                yield photo
            if n < size // 2:
                break
            offset = offset - n if desc else offset + n

    # ---------- operacje grupowe ----------
    def album_member_ids(self, album, limit: int = 50000) -> set:
        """ID wszystkich zdjęć, które już są w albumie (czyta album, nie zmienia go)."""
        import copy

        ids = set()
        for a in self.iter_assets(copy.copy(album), True):
            ids.add(a.id)
            if len(ids) >= limit:
                break
        return ids

    def add_to_album(self, album, assets, progress=None):
        """Dodaje zdjęcia do albumu, pomijając te, które już w nim są.
        Zwraca (dodane, już_w_albumie, błędy); „już_w_albumie” to lista zdjęć."""
        _guard_write()
        ok, already, errors, todo = 0, [], [], list(assets)
        try:
            members = self.album_member_ids(album)
            already = [a for a in assets if a.id in members]
            todo = [a for a in assets if a.id not in members]
        except Exception as e:  # noqa: BLE001
            log.warning("nie udało się sprawdzić zawartości albumu: %r", e)
            errors.append(tr("Nie udało się sprawdzić, czy zdjęcia już są w albumie "
                          "- dodano bez sprawdzania."))
        for k, a in enumerate(todo):
            try:
                if album.add_photo(a):
                    ok += 1
                else:
                    errors.append(tr("{0}: album nie przyjęło zdjęcia").format(a.filename))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{a.filename}: {e}")
                log.error("add_to_album %s: %r", a.filename, e)
            if progress:
                progress(k + 1, len(todo))
        return ok, already, errors

    def set_favorite(self, assets, value: bool, progress=None):
        _guard_write()
        ok, errors = 0, []
        for k, a in enumerate(assets):
            try:
                if (a.favorite() if value else a.unfavorite()):
                    ok += 1
                else:
                    errors.append(tr("{0}: nie zmieniono").format(a.filename))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{a.filename}: {e}")
                log.error("favorite %s: %r", a.filename, e)
            if progress:
                progress(k + 1, len(assets))
        return ok, errors

    def _confirm_deleted(self, assets) -> set:
        """Id-ki zdjęć, które Apple potwierdziło jako usunięte (pole isDeleted=1).

        Jedno zapytanie o rekordy na paczkę (do 100). NIE używaj do tego album.get(): dla zdjęcia, którego
        już nie ma, pyicloud przegląda CAŁĄ bibliotekę (setki zapytań) - wersja 0.11.0 przez to „wisiała”."""
        from pyicloud.common.cloudkit import CKZoneIDReq
        from pyicloud.services.photos_cloudkit.constants import PRIMARY_ZONE
        from pyicloud.services.photos_cloudkit.mappers import (record_field_value, record_name,
                                                               record_zone)

        client = getattr(self.api.photos, "private_client", None)
        if client is None:
            raise RuntimeError("brak klienta CloudKit do sprawdzenia")
        groups = {}
        for a in assets:
            zone = record_zone(a._asset_record) or PRIMARY_ZONE
            groups.setdefault(json.dumps(zone, sort_keys=True, default=str), (zone, []))[1].append(a)
        confirmed = set()
        for zone, items in groups.values():
            zid = CKZoneIDReq(zoneName=zone["zoneName"], ownerRecordName=zone.get("ownerRecordName"),
                              zoneType=zone.get("zoneType"))
            for i in range(0, len(items), 100):
                chunk = {record_name(a._asset_record): a for a in items[i:i + 100]}
                resp = client.lookup(list(chunk), zone_id=zid, desired_keys=["isDeleted"])
                for rec in resp.records:
                    try:
                        name = record_name(rec)
                    except Exception:  # noqa: BLE001  (rekord błędu / usunięty na stałe)
                        continue
                    if name in chunk and bool(record_field_value(rec, "isDeleted")):
                        confirmed.add(chunk[name].id)
        return confirmed

    def delete_assets(self, assets, progress=None):
        """Przenosi zdjęcia do „Ostatnio usunięte” (jak aplikacja Zdjęcia) i POTWIERDZA to u Apple jednym
        zapytaniem o rekordy (isDeleted=1). Zwraca (lista_usuniętych_zdjęć, błędy)."""
        _guard_write()
        sent, errors = [], []
        for k, a in enumerate(assets):
            try:
                a.delete()
                sent.append(a)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{a.filename}: {e}")
                log.error("delete %s: %r", a.filename, e)
            if progress:
                progress(k + 1, len(assets))
        deleted = list(sent)
        if sent:
            try:
                ok = self._confirm_deleted(sent)
            except Exception as e:  # noqa: BLE001
                # nie udało się sprawdzić (sieć, zmiana API): polecenie usunięcia przyjęło się bez błędu
                log.warning("nie udało się potwierdzić usunięcia (%d zdjęć): %r", len(sent), e)
            else:
                deleted = [a for a in sent if a.id in ok]
                for a in sent:
                    if a.id not in ok:
                        errors.append(tr("{0}: Apple nie potwierdziło usunięcia").format(a.filename))
                        log.error("Apple nie potwierdziło usunięcia %s", a.filename)
        log.info("usunięto %d z %d zdjęć", len(deleted), len(assets))
        return deleted, errors

    def save_originals(self, assets, folder: str, progress=None):
        ok, errors = 0, []
        for k, a in enumerate(assets):
            name = os.path.basename(a.filename) or f"{a.id}.bin"
            base, ext = os.path.splitext(name)
            path, i = os.path.join(folder, name), 1
            while os.path.exists(path):
                path, i = os.path.join(folder, f"{base} ({i}){ext}"), i + 1
            try:
                self.save_original(a, path)
                ok += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"{a.filename}: {e}")
                log.error("save_original %s: %r", a.filename, e)
            if progress:
                progress(k + 1, len(assets))
        return ok, errors

    def fetch_video_file(self, asset, ver: str, max_bytes: int = 700 * 1024**2) -> str:
        """Plan B dla filmów: pobiera film (zwykle H.264 'medium') do cache oficjalną ścieżką
        pyicloud (jak miniatury) i zwraca ścieżkę pliku do odtworzenia lokalnie."""
        key = hashlib.sha1(f"{asset.id}:{ver}".encode()).hexdigest()
        path = VIDEO_DIR / f"{key}.mp4"
        if path.exists():
            os.utime(path)
            return str(path)
        size = (asset.versions.get(ver) or {}).get("size")
        if isinstance(size, (int, float)) and size > max_bytes:
            raise IOError(tr("film jest za duży do pobrania do cache ({0} MB); użyj „Zapisz oryginał jako…”"
                             ).format(f"{size / 1024**2:.0f}"))
        data = asset.download(ver)
        if not data:
            raise IOError(tr("pusta odpowiedź przy pobieraniu filmu"))
        tmp = path.with_suffix(".tmp" + secrets.token_hex(3))
        tmp.write_bytes(data)
        tmp.replace(path)
        log.info("film zapisany w cache: %s (%d MB)", asset.filename, len(data) // 1024**2)
        return str(path)

    def fetch_live(self, asset, ver: str) -> str:
        """Pobiera krótką część wideo Live Photo do cache i zwraca ścieżkę pliku."""
        key = hashlib.sha1(f"{asset.id}:{ver}".encode()).hexdigest()
        path = LIVE_DIR / f"{key}.mov"
        if path.exists():
            os.utime(path)
            return str(path)
        data = asset.download(ver)
        if not data:
            raise IOError(tr("pusta odpowiedź przy pobieraniu Live Photo"))
        tmp = path.with_suffix(".tmp" + secrets.token_hex(3))
        tmp.write_bytes(data)
        tmp.replace(path)
        return str(path)

    def asset_info(self, asset) -> dict:
        """Dane ze rekordu iCloud: nazwa, daty, rozmiar, wymiary, lokalizacja."""
        info: dict = {"filename": asset.filename}
        for key, attr in (("asset_date", "asset_date"), ("added_date", "added_date"),
                          ("size", "size"), ("dimensions", "dimensions")):
            try:
                info[key] = getattr(asset, attr)
            except Exception:  # noqa: BLE001
                pass
        info["video"] = self.is_video(asset)
        info["live"] = self.is_live(asset)
        try:
            from pyicloud.services.photos_cloudkit.mappers import record_field_value

            lat = record_field_value(asset._asset_record, "locationLatitude")
            lon = record_field_value(asset._asset_record, "locationLongitude")
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) \
                    and not (lat == 0 and lon == 0):
                info["gps"] = (float(lat), float(lon))
        except Exception:  # noqa: BLE001
            log.info("brak pól lokalizacji: %r", traceback.format_exc().splitlines()[-1])
        return info

    def read_exif(self, asset, original: bool = False) -> dict:
        """Dane aparatu z EXIF. Domyślnie z podglądu 'medium'; original=True z oryginału."""
        import exif

        data = self.fetch_original(asset) if original else self.fetch(asset, "medium")
        return exif.parse_exif(data)

    def save_original(self, asset, path: str) -> None:
        """Zapisuje oryginał na dysk strumieniowo (bez ładowania całości do pamięci)."""
        self.save_version(asset, "original", path)

    def save_version(self, asset, ver: str, path: str) -> None:
        """Zapisuje wskazaną wersję pliku ('original', 'medium'...) na dysk strumieniowo."""
        url = asset.download_url(ver)
        if not url:
            raise IOError(tr("brak oryginału") if ver == "original" else tr("brak wersji do pobrania"))
        with self.api.session.get(url, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)

    @staticmethod
    def reverse_geocode(lat: float, lon: float) -> str:
        """Nazwa miejsca z OpenStreetMap Nominatim (tylko na żądanie użytkownika)."""
        import urllib.request

        url = (f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=16"
               f"&accept-language=pl&lat={lat}&lon={lon}")
        req = urllib.request.Request(url, headers={"User-Agent": "linux-icloud-photos/0.4"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode("utf-8")).get("display_name", tr("(brak nazwy)"))

    def fetch_original(self, asset) -> bytes:
        """Oryginał - bez cache, tylko na żądanie."""
        try:
            data = asset.download("original")
        except Exception as e:  # noqa: BLE001
            self._notify_gone(e)
            raise
        if not data:
            raise IOError(tr("brak oryginału"))
        return data

    # ---------- wideo/zdjęcia przez lokalny proxy z Range ----------
    @staticmethod
    def lan_ip_for(target_host: str) -> str:
        """Adres IP tego komputera widoczny dla urządzenia w sieci lokalnej."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
                sk.connect((target_host, 9))
                return sk.getsockname()[0]
        except OSError:
            return "127.0.0.1"

    def stream_url(self, asset, ver: str, lan_host: str | None = None, blob: bytes | None = None) -> str:
        """URL strumienia (przez proxy z Range). lan_host: adres tego komputera dla TV."""
        server = self._ensure_server(lan=bool(lan_host))
        while len(self._streams) > 300:  # nie rośnij bez końca (długie pokazy slajdów)
            self._streams.pop(next(iter(self._streams)))
        token = secrets.token_urlsafe(16)
        self._streams[token] = (asset, ver)
        if blob is not None:
            while len(self._blobs) > 12:
                self._blobs.pop(next(iter(self._blobs)))
            self._blobs[token] = blob
        return f"http://{lan_host or '127.0.0.1'}:{server.server_address[1]}/{token}"

    def _ensure_server(self, lan: bool) -> ThreadingHTTPServer:
        with self._proxy_lock:
            if lan in self._servers:
                return self._servers[lan]
            outer = self

            class Handler(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def log_message(self, *a):  # cisza
                    pass

                def _serve(self, head_only: bool) -> None:
                    entry = outer._streams.get(self.path.split("?")[0].strip("/").split("/")[0])
                    if not entry:
                        self.send_error(404)
                        return
                    asset, ver = entry
                    blob = outer._blobs.get(self.path.split("?")[0].strip("/").split("/")[0])
                    if blob is not None:  # zdjęcie z pamięci: natychmiastowa odpowiedź (TV ma krótkie limity)
                        try:
                            self.send_response(200)
                            self.send_header("Content-Type", "image/jpeg")
                            self.send_header("Content-Length", str(len(blob)))
                            self.send_header("Accept-Ranges", "none")
                            self.send_header("transferMode.dlna.org", "Interactive")
                            self.send_header("contentFeatures.dlna.org", DLNA_FEATURES_IMAGE)
                            self.send_header("Access-Control-Allow-Origin", "*")
                            self.end_headers()
                            if not head_only:
                                self.wfile.write(blob)
                            log.info("proxy %s %s z pamięci len=%d", self.command, asset.filename, len(blob))
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                        return
                    rng = self.headers.get("Range")
                    resp = None
                    try:
                        url = asset.download_url(ver)
                        if not url:
                            log.warning("proxy: brak URL dla %s/%s", asset.filename, ver)
                            self.send_error(404)
                            return
                        headers = {"Range": rng} if rng else {}
                        resp = outer.api.session.get(url, headers=headers, stream=True)
                        log.info("proxy %s %s range=%s -> %s len=%s", self.command,
                                 asset.filename, rng, resp.status_code,
                                 resp.headers.get("Content-Length"))
                        if resp.status_code >= 400:
                            self.send_error(resp.status_code)
                            return
                        self.send_response(resp.status_code)
                        # Typ z końcówki adresu (/photo.jpg, /video.mp4): CDN Apple bywa
                        # niejednoznaczny (octet-stream), a telewizory DLNA odrzucają taki obraz.
                        path_only = self.path.split("?")[0].lower()
                        forced = ("image/jpeg" if path_only.endswith((".jpg", ".jpeg"))
                                  else "video/mp4" if path_only.endswith(".mp4") else None)
                        for h in ("Content-Type", "Content-Length", "Content-Range"):
                            if h == "Content-Type" and forced:
                                self.send_header(h, forced)
                            elif h in resp.headers:
                                self.send_header(h, resp.headers[h])
                        if forced:  # nagłówki DLNA wymagane przez wiele telewizorów
                            self.send_header("transferMode.dlna.org",
                                             "Interactive" if forced.startswith("image") else "Streaming")
                            self.send_header("contentFeatures.dlna.org",
                                             DLNA_FEATURES_IMAGE if forced.startswith("image")
                                             else DLNA_FEATURES_VIDEO)
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        if head_only:
                            return
                        for chunk in resp.iter_content(256 * 1024):
                            self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        pass  # odtwarzacz przeskoczył / zamknął połączenie
                    except Exception:  # noqa: BLE001
                        log.error("proxy błąd dla %s:\n%s", asset.filename,
                                  traceback.format_exc())
                        try:
                            self.send_error(502)
                        except Exception:  # noqa: BLE001
                            pass
                    finally:
                        if resp is not None:
                            resp.close()

                def do_GET(self):
                    self._serve(False)

                def do_HEAD(self):
                    self._serve(True)

            server = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", 0), Handler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self._servers[lan] = server
            return server
