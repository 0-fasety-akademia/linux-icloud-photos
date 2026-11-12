"""Wysyłanie zdjęć i wideo na telewizory/odtwarzacze DLNA/UPnP (LG, Samsung, Sony...).

Wykrywanie przez SSDP, sterowanie przez UPnP AVTransport (SOAP). Bez zależności.
Nie obejmuje AirPlay ani Chromecasta - to osobne protokoły.
"""
from __future__ import annotations

import socket
import re
import time
import urllib.request
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from i18n import tr

SSDP_ADDR = ("239.255.255.250", 1900)
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
DIDL_NS = ('xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/" '
           'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"')


class CastError(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class Renderer:
    kind = "DLNA"

    def __init__(self, name: str, location: str, control_url: str):
        self.name = name
        self.location = location
        self.control_url = control_url
        self.host = urlparse(location).hostname or ""

    def __repr__(self):
        return f"<Renderer {self.name} @ {self.host}>"

    def _soap(self, action: str, body: str, timeout: float = 6.0) -> str:
        env = ('<?xml version="1.0" encoding="utf-8"?>'
               '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
               f'<u:{action} xmlns:u="{AVT}">{body}</u:{action}></s:Body></s:Envelope>')
        req = urllib.request.Request(
            self.control_url, data=env.encode("utf-8"), method="POST",
            headers={"Content-Type": 'text/xml; charset="utf-8"',
                     "SOAPACTION": f'"{AVT}#{action}"'},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            detail = ""
            if hasattr(e, "read"):
                try:
                    body = e.read().decode("utf-8", "replace")
                    m = re.search(r"<errorCode>\s*(\d+)\s*</errorCode>", body)
                    d = re.search(r"<errorDescription>(.*?)</errorDescription>", body, re.S)
                    detail = (f"UPnP {m.group(1)} {d.group(1).strip() if d else ''}".strip()
                              if m else re.sub(r"\s+", " ", body)[:300])
                except Exception:  # noqa: BLE001
                    pass
            raise CastError(tr("{0}: {1} nie powiodło się: {2} {3}").format(self.name, action, e, detail)) from e

    @staticmethod
    def didl(uri: str, title: str, mime: str, video: bool) -> str:
        klass = "object.item.videoItem" if video else "object.item.imageItem.photo"
        feat = ("DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000" if video
                else "DLNA.ORG_OP=00;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=00f00000000000000000000000000000")
        return (f'<DIDL-Lite {DIDL_NS}><item id="0" parentID="-1" restricted="1">'
                f"<dc:title>{escape(title)}</dc:title><upnp:class>{klass}</upnp:class>"
                f'<res protocolInfo="http-get:*:{mime}:{feat}">{escape(uri)}</res>'
                "</item></DIDL-Lite>")

    def play_uri(self, uri: str, title: str, mime: str, video: bool = False) -> None:
        meta = self.didl(uri, title, mime, video)
        try:  # poprzedni obraz/film musi być zatrzymany, inaczej LG/Samsung zwracają błąd 500/701
            self._soap("Stop", "<InstanceID>0</InstanceID>", timeout=3.0)
            time.sleep(0.4)
        except CastError:
            pass
        self._soap("SetAVTransportURI",
                   "<InstanceID>0</InstanceID>"
                   f"<CurrentURI>{escape(uri)}</CurrentURI>"
                   f"<CurrentURIMetaData>{escape(meta)}</CurrentURIMetaData>")
        last = None
        for _ in range(4):  # telewizor potrzebuje chwili na wczytanie, zanim przyjmie Play
            time.sleep(0.8)
            try:
                self._soap("Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")
                return
            except CastError as e:
                last = e
        if video:
            raise last
        # zdjęcie: wiele telewizorów pokazuje je już po SetAVTransportURI, a Play zwraca błąd

    def stop(self) -> None:
        self._soap("Stop", "<InstanceID>0</InstanceID>")


def from_location(location: str, timeout: float = 3.0) -> Renderer | None:
    """Pobiera opis urządzenia i zwraca Renderer, jeśli ma usługę AVTransport."""
    try:
        with urllib.request.urlopen(location, timeout=timeout) as r:
            root = ET.fromstring(r.read())
    except Exception:  # noqa: BLE001
        return None
    base = location
    for el in root.iter():
        if _local(el.tag) == "URLBase" and (el.text or "").strip():
            base = el.text.strip()
    name, control = None, None
    for dev in root.iter():
        if _local(dev.tag) != "device":
            continue
        fn = next((c.text for c in dev if _local(c.tag) == "friendlyName"), None)
        for svc in dev.iter():
            if _local(svc.tag) != "service":
                continue
            st = next((c.text for c in svc if _local(c.tag) == "serviceType"), "") or ""
            cu = next((c.text for c in svc if _local(c.tag) == "controlURL"), None)
            if "AVTransport" in st and cu:
                control, name = urljoin(base, cu.strip()), fn or name
                break
        if control:
            break
    if not control:
        return None
    return Renderer(name or urlparse(location).hostname or "TV", location, control)


def parse_ssdp_location(data: bytes) -> str | None:
    for line in data.decode("utf-8", "replace").splitlines():
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip()
    return None


SEARCH_TARGETS = (AVT, "urn:schemas-upnp-org:device:MediaRenderer:1",
                  "upnp:rootdevice", "ssdp:all")


def discover(timeout: float = 4.0) -> list[Renderer]:
    """Szuka w sieci lokalnej urządzeń z AVTransport (DLNA MediaRenderer).

    Telewizory odpowiadają różnie (jedne na AVTransport, inne tylko na MediaRenderer albo
    rootdevice), więc wysyłamy kilka zapytań i filtrujemy po opisie urządzenia."""
    from concurrent.futures import ThreadPoolExecutor

    locations: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        sock.settimeout(0.4)
        for _ in range(2):
            for st in SEARCH_TARGETS:
                msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
                       'MAN: "ssdp:discover"\r\nMX: 2\r\n'
                       f"ST: {st}\r\n\r\n").encode()
                try:
                    sock.sendto(msg, SSDP_ADDR)
                except OSError:
                    pass
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, _addr = sock.recvfrom(65507)
            except socket.timeout:
                continue
            except OSError:
                break
            loc = parse_ssdp_location(data)
            if loc and loc not in locations:
                locations.append(loc)
    finally:
        sock.close()
    found, seen = [], set()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for r in pool.map(from_location, locations):
            if r and r.control_url not in seen:
                seen.add(r.control_url)
                found.append(r)
    return found
