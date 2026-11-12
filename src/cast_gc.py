"""Wysyłanie na Chromecasta (oraz TV z wbudowanym Google Cast) przez bibliotekę pychromecast."""
from __future__ import annotations

from i18n import tr


class ChromecastTarget:
    kind = "Chromecast"

    def __init__(self, cast):
        self._cast = cast
        self.name = cast.name
        try:
            self.host = str(cast.cast_info.host)
        except Exception:  # noqa: BLE001
            self.host = ""
        self.control_url = f"cast://{self.host}"
        self.port = getattr(getattr(cast, "cast_info", None), "port", None) or 8009
        self.uuid = getattr(cast, "uuid", None)
        self.model = getattr(getattr(cast, "cast_info", None), "model_name", None)
        self._conn = None

    def __repr__(self):
        return f"<Chromecast {self.name} @ {self.host}>"

    def _connect(self):
        """Nowe połączenie po samym adresie IP (bez mDNS: wykrywanie jest już zamknięte, a stary
        obiekt po nieudanym połączeniu nie da się uruchomić drugi raz)."""
        import pychromecast
        if self._conn is not None:
            try:
                self._conn.disconnect(timeout=2)
            except Exception:  # noqa: BLE001
                pass
            self._conn = None
        c = pychromecast.get_chromecast_from_host(
            (self.host, self.port, self.uuid, self.model, self.name))
        c.wait(timeout=12)
        self._conn = c
        return c

    def play_uri(self, uri: str, title: str, mime: str, video: bool = False) -> None:
        try:
            c = self._connect()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(tr("{0}: brak połączenia z Chromecastem ({1}:{2}): {3}").format(
                self.name, self.host, self.port, e or type(e).__name__)) from e
        mc = c.media_controller
        mc.play_media(uri, mime, title=title, autoplay=True)
        mc.block_until_active(timeout=10)

    def stop(self) -> None:
        try:
            if self._conn is not None:
                self._conn.media_controller.stop()
        finally:
            try:
                if self._conn is not None:
                    self._conn.disconnect(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            self._conn = None


def discover(timeout: float = 5.0) -> list[ChromecastTarget]:
    try:
        import pychromecast
    except ImportError:
        return []
    casts, browser = pychromecast.get_chromecasts(timeout=timeout)
    try:
        return [ChromecastTarget(c) for c in casts]
    finally:
        browser.stop_discovery()
