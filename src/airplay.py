"""AirPlay (Apple TV i inne odbiorniki AirPlay) przez bibliotekę pyatv.

- wideo: pyatv `stream.play_url` (wymaga parowania PIN-em, dane zapisywane w keyring/pliku 0600)
- zdjęcia: pyatv ich nie obsługuje, więc wysyłamy je samodzielnie protokołem AirPlay 1
  (`PUT /photo`, port 7000). To rozwiązanie eksperymentalne - nowsze Apple TV mogą je odrzucić.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.request
import uuid
from pathlib import Path

from i18n import tr

KEYRING_SERVICE = "linux-icloud-photos-airplay"
OLD_KEYRING_SERVICE = "icloud-photos-linux-airplay"  # nazwa sprzed 0.12.2
_CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "linux-icloud-photos"
CREDS_FILE = _CONFIG / "airplay.json"

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


class AirPlayError(Exception):
    pass


def _pyatv():
    import pyatv  # import leniwy: bez pyatv AirPlay po prostu nie pojawia się na liście
    from pyatv.const import Protocol

    return pyatv, Protocol


def _get_loop() -> asyncio.AbstractEventLoop:
    """Jedna pętla asyncio w wątku w tle (GTK ma własną pętlę zdarzeń)."""
    global _loop
    with _lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True, name="airplay-loop").start()
        return _loop


def _run(coro, timeout: float = 20.0):
    return asyncio.run_coroutine_threadsafe(coro, _get_loop()).result(timeout)


# ---------- przechowywanie danych parowania ----------
def load_creds(identifier: str) -> str | None:
    try:
        import keyring

        v = keyring.get_password(KEYRING_SERVICE, identifier)
        if v:
            return v
        v = keyring.get_password(OLD_KEYRING_SERVICE, identifier)
        if v:
            keyring.set_password(KEYRING_SERVICE, identifier, v)
            return v
    except Exception:  # noqa: BLE001
        pass
    try:
        return json.loads(CREDS_FILE.read_text()).get(identifier)
    except Exception:  # noqa: BLE001
        return None


def save_creds(identifier: str, creds: str) -> None:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, identifier, creds)
        return
    except Exception:  # noqa: BLE001
        pass
    _CONFIG.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(CREDS_FILE.read_text())
    except Exception:  # noqa: BLE001
        data = {}
    data[identifier] = creds
    CREDS_FILE.write_text(json.dumps(data))
    os.chmod(CREDS_FILE, 0o600)


class AirPlayTarget:
    kind = "AirPlay"

    def __init__(self, conf):
        self.conf = conf
        self.name = conf.name
        self.host = str(conf.address)
        self.identifier = str(conf.identifier)
        self.control_url = f"airplay://{self.identifier}"
        self._pairing = None
        self._atv = None
        self._fut = None
        creds = load_creds(self.identifier)
        if creds:
            self._apply_creds(creds)

    def __repr__(self):
        return f"<AirPlay {self.name} @ {self.host}>"

    def _apply_creds(self, creds):
        _, Protocol = _pyatv()
        self.conf.set_credentials(Protocol.AirPlay, creds)

    @property
    def needs_pairing(self) -> bool:
        return load_creds(self.identifier) is None

    # ---------- parowanie PIN-em ----------
    def pair_begin(self) -> bool:
        """Zaczyna parowanie (na TV pojawi się PIN). Zwraca True, jeśli PIN wyświetla urządzenie."""
        pyatv, Protocol = _pyatv()

        async def go():
            self._pairing = await pyatv.pair(self.conf, Protocol.AirPlay, _get_loop())
            await self._pairing.begin()
            return bool(self._pairing.device_provides_pin)

        return _run(go())

    def pair_finish(self, pin: str) -> bool:
        async def go():
            p = self._pairing
            p.pin(pin)
            await p.finish()
            ok = bool(p.has_paired)
            creds = p.service.credentials if ok else None
            await p.close()
            return ok, creds

        ok, creds = _run(go())
        if ok and creds:
            save_creds(self.identifier, creds)
            self._apply_creds(creds)
        return ok

    # ---------- odtwarzanie ----------
    def play_uri(self, uri: str, title: str, mime: str, video: bool = False) -> None:
        if self.needs_pairing:
            raise AirPlayError(tr("{0}: urządzenie nie jest sparowane").format(self.name))
        if video:
            self._play_video(uri)
        else:
            self._put_photo(uri)

    def _play_video(self, url: str) -> None:
        pyatv, _ = _pyatv()
        self._drop_connection()

        async def go():
            self._atv = await pyatv.connect(self.conf, _get_loop())
            await self._atv.stream.play_url(url)  # blokuje do końca odtwarzania

        self._fut = asyncio.run_coroutine_threadsafe(go(), _get_loop())

        def report(f):
            if not f.cancelled() and f.exception():
                from backend import log

                log.error("AirPlay %s: %r", self.name, f.exception())

        self._fut.add_done_callback(report)

    def _put_photo(self, url: str) -> None:
        """Eksperymentalne: AirPlay 1 PUT /photo (zdjęcie pobieramy z naszego proxy)."""
        _, Protocol = _pyatv()
        try:
            port = self.conf.get_service(Protocol.AirPlay).port or 7000
        except Exception:  # noqa: BLE001
            port = 7000
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                data = r.read()
        except Exception as e:  # noqa: BLE001
            raise AirPlayError(tr("{0}: nie udało się przygotować zdjęcia: {1}").format(self.name, e)) from e
        req = urllib.request.Request(
            f"http://{self.host}:{port}/photo", data=data, method="PUT",
            headers={"User-Agent": "MediaControl/1.0", "X-Apple-AssetKey": str(uuid.uuid4()),
                     "X-Apple-Transition": "Dissolve", "Content-Type": "image/jpeg"})
        try:
            with urllib.request.urlopen(req, timeout=20):
                pass
        except Exception as e:  # noqa: BLE001
            raise AirPlayError(
                tr("{0}: to urządzenie nie przyjmuje zdjęć przez AirPlay ({1}). Wideo i pokaz slajdów jako wideo działają tylko po sparowaniu.").format(self.name, e)) from e

    def _drop_connection(self):
        atv, self._atv = self._atv, None
        if self._fut is not None:
            self._fut.cancel()
            self._fut = None
        if atv is not None:
            try:
                atv.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        self._drop_connection()


def discover(timeout: int = 5) -> list[AirPlayTarget]:
    try:
        pyatv, Protocol = _pyatv()
    except ImportError:
        return []

    async def scan():
        return await pyatv.scan(_get_loop(), timeout=timeout, protocol={Protocol.AirPlay})

    out = []
    for conf in _run(scan(), timeout + 10):
        try:
            model = str(conf.device_info.model)
        except Exception:  # noqa: BLE001
            model = ""
        if "HomePod" in model:  # głośniki nie odtwarzają obrazu
            continue
        out.append(AirPlayTarget(conf))
    return out
