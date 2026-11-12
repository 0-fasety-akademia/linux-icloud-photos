"""Minimalny parser EXIF (JPEG i HEIC) - bez zależności. Zwraca słownik z danymi aparatu."""
from __future__ import annotations

import struct

IFD0 = {0x010F: "Make", 0x0110: "Model", 0x0131: "Software", 0x0132: "DateTime"}
EXIF = {0x829A: "ExposureTime", 0x829D: "FNumber", 0x8827: "ISO", 0x9003: "DateTimeOriginal",
        0x920A: "FocalLength", 0xA434: "LensModel", 0xA433: "LensMake"}
SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _find_tiff(data: bytes) -> int | None:
    if data[:2] == b"\xff\xd8":  # JPEG: segment APP1 "Exif\0\0"
        i = 2
        while i + 4 <= len(data) and data[i] == 0xFF:
            marker = data[i + 1]
            if marker in (0xD9, 0xDA):
                break
            seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
                return i + 10
            i += 2 + seglen
    j = data.find(b"Exif\x00\x00", 0, 4_000_000)  # HEIC i inne kontenery
    if j >= 0 and data[j + 6:j + 8] in (b"II", b"MM"):
        return j + 6
    for sig in (b"MM\x00\x2a", b"II\x2a\x00"):
        j = data.find(sig, 0, 4_000_000)
        if j >= 0:
            return j
    return None


def parse_exif(data: bytes) -> dict:
    t = _find_tiff(data)
    if t is None or data[t:t + 2] not in (b"II", b"MM"):
        return {}
    e = "<" if data[t:t + 2] == b"II" else ">"
    u16 = lambda o: struct.unpack(e + "H", data[o:o + 2])[0]  # noqa: E731
    u32 = lambda o: struct.unpack(e + "I", data[o:o + 4])[0]  # noqa: E731

    def read_ifd(off):
        out = {}
        try:
            n = u16(t + off)
            for k in range(n):
                p = t + off + 2 + k * 12
                tag, typ, cnt = u16(p), u16(p + 2), u32(p + 4)
                size = SIZES.get(typ, 1) * cnt
                vo = p + 8 if size <= 4 else t + u32(p + 8)
                out[tag] = (typ, cnt, vo)
        except (struct.error, IndexError):
            pass
        return out

    def val(typ, cnt, vo):
        try:
            if typ == 2:
                return data[vo:vo + cnt].split(b"\x00")[0].decode("utf-8", "replace").strip()
            if typ == 3:
                return [u16(vo + 2 * i) for i in range(cnt)] if cnt > 1 else u16(vo)
            if typ == 4:
                return [u32(vo + 4 * i) for i in range(cnt)] if cnt > 1 else u32(vo)
            if typ in (5, 10):
                fmt = e + ("II" if typ == 5 else "ii")
                r = [struct.unpack(fmt, data[vo + 8 * i:vo + 8 * i + 8]) for i in range(cnt)]
                r = [a / b if b else 0.0 for a, b in r]
                return r if cnt > 1 else r[0]
        except (struct.error, IndexError):
            pass
        return None

    res: dict = {}
    ifd0 = read_ifd(u32(t + 4))
    for tag, name in IFD0.items():
        if tag in ifd0:
            res[name] = val(*ifd0[tag])
    if 0x8769 in ifd0:
        ex = read_ifd(val(*ifd0[0x8769]))
        for tag, name in EXIF.items():
            if tag in ex:
                res[name] = val(*ex[tag])
    if 0x8825 in ifd0:
        g = read_ifd(val(*ifd0[0x8825]))
        try:
            def dms(tag, ref):
                d, m, s = val(*g[tag])
                v = d + m / 60 + s / 3600
                return -v if val(*g[ref]) in ("S", "W") else v
            res["gps"] = (dms(2, 1), dms(4, 3))
        except (KeyError, TypeError, ValueError):
            pass
    # czytelne formaty
    if isinstance(res.get("ExposureTime"), float) and res["ExposureTime"] > 0:
        et = res["ExposureTime"]
        res["ExposureTime"] = f"1/{round(1 / et)} s" if et < 1 else f"{et:g} s"
    if isinstance(res.get("FNumber"), float):
        res["FNumber"] = f"f/{res['FNumber']:.1f}"
    if isinstance(res.get("FocalLength"), float):
        res["FocalLength"] = f"{res['FocalLength']:.1f} mm"
    return {k: v for k, v in res.items() if v not in (None, "")}
