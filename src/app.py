#!/usr/bin/env python3
"""iCloud Photos dla Ubuntu - strumieniowo z chmury, bez synchronizacji na dysk."""
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import weakref
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

# Zapytania innych aplikacji (np. linux-skytrack) bez okna i bez GTK - patrz bridge.py
if __name__ == "__main__":
    import bridge as _bridge

    if _bridge.is_bridge_call(sys.argv):
        sys.exit(_bridge.main())

# Wtyczki GStreamera zlinkowane z GTK3 (gtkwaylandsink) lub DirectFB wciągnięte do
# procesu GTK4 potrafią go wywrócić przy odtwarzaniu wideo - wyłączamy je z autowyboru.
os.environ["GST_PLUGIN_FEATURE_RANK"] = ",".join(
    x for x in (os.environ.get("GST_PLUGIN_FEATURE_RANK", ""),
                "gtkwaylandsink:0", "dfbvideosink:0") if x
)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import (Adw, Gdk, GdkPixbuf, Gio, GLib, GObject, Graphene, Gsk, Gtk,  # noqa: E402
                           Pango)

import cast as dlna  # noqa: E402
import airplay  # noqa: E402
import cast_gc  # noqa: E402
import backend  # noqa: E402
import pick  # noqa: E402
from i18n import month_names, plural, tr  # noqa: E402
from version import CREDITS, DATE, VERSION  # noqa: E402
from backend import (CACHE_DIR, CONFIG_DIR, DEBUG_LOG, ICloud, TESTED_PYICLOUD,  # noqa: E402
                     cache_size, clear_cache, pyicloud_version, asset_aspect, is_auth_error, justify_rows, log, parse_date_query,
                     prune_cache)

try:
    import keyring
except ImportError:  # opcjonalne
    keyring = None

PICK = None  # opcje trybu wyboru (--pick, patrz pick.py) albo None w zwykłym trybie
OPEN = None  # prośba innej aplikacji (np. linux-skytrack): {"album": nazwa} albo {"date": "RRRR-MM-DD[..RRRR-MM-DD]"}


def parse_open(argv):
    """Wyjmuje z argv --open-album NAZWA / --open-date DATA. Zwraca (prośba albo None, reszta)."""
    rest, req, i = [], None, 0
    args = list(argv)
    while i < len(args):
        a = args[i]
        if a in ("--open-album", "--open-date"):
            if i + 1 >= len(args):
                raise ValueError(f"missing value for {a}")
            req = {"album" if a == "--open-album" else "date": args[i + 1]}
            i += 2
            continue
        rest.append(a)
        i += 1
    return req, rest
MIN_GTK, MIN_ADW = (4, 10), (1, 2)  # minimalne wersje (z analizy używanych funkcji; testowane na GTK 4.14/Adw 1.5)
KEYRING_SERVICE = "linux-icloud-photos"
OLD_KEYRING_SERVICE = "icloud-photos-linux"  # nazwa sprzed 0.12.2
CONFIG_FILE = CONFIG_DIR / "config.json"
TILE_MIN, TILE_MAX, TILE_DEFAULT = 90, 360, 180
ROW_GAP = 4
POOL = ThreadPoolExecutor(max_workers=6)
COVER_POOL = ThreadPoolExecutor(max_workers=3)
BATCH = 300
SLIDE_SECS = (3, 5, 8, 15)
PRESETS = ((tr('Małe'), 100), (tr('Standardowe'), 180), (tr('Duże'), 260), (tr('Bardzo duże'), 360))

CSS = b"""
.tile { background-color: alpha(currentColor, 0.08); }
.viewer { background-color: black; }
.caption { color: white; background-color: rgba(0,0,0,0.55);
           padding: 4px 12px; border-radius: 8px; margin: 12px; }
.zbar { background-color: rgba(0,0,0,0.6); border-radius: 14px; padding: 4px 10px;
        margin: 16px; }
.zbar button { color: white; }
.albumcover { border-radius: 8px; background-color: alpha(currentColor, 0.1); }
.rubberband { background-color: alpha(@accent_bg_color, 0.25);
             border: 1px solid @accent_bg_color; border-radius: 2px; }
.livebadge { color: white; background-color: rgba(0,0,0,0.55); font-size: 9px;
             font-weight: bold; padding: 1px 6px; border-radius: 6px; margin: 6px; }
"""


def load_cfg():
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_cfg(**kv):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        cfg = load_cfg()
        cfg.update(kv)
        CONFIG_FILE.write_text(json.dumps(cfg))
    except Exception:  # noqa: BLE001
        pass


_AUTH_HOOK = [None]  # ustawiane przez MainWindow: wywoływane, gdy błąd wygląda na wygaśnięcie sesji


def _auth_check(e):
    if _AUTH_HOOK[0] is not None and e is not None and is_auth_error(e):
        GLib.idle_add(lambda: (_AUTH_HOOK[0](), False)[1])


def bg(fn, cb):
    """Uruchom fn w wątku, wynik (result, error) oddaj do cb w głównym wątku."""
    def run():
        try:
            res = (fn(), None)
        except Exception as e:  # noqa: BLE001
            _auth_check(e)
            res = (None, e)

        def deliver():
            cb(*res)
            return False

        GLib.idle_add(deliver)

    threading.Thread(target=run, daemon=True).start()


def _gst_decoders():
    """Diagnostyka: które dekodery wideo widzi GStreamer (do logu przy błędzie odtwarzania)."""
    try:
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        names = ("avdec_h264", "avdec_hevc", "vah264dec", "x264enc", "openh264dec", "qtdemux")
        return {n: Gst.ElementFactory.find(n) is not None for n in names}
    except Exception as e:  # noqa: BLE001
        return f"brak diagnostyki: {e}"


class PhotoObj(GObject.Object):
    def __init__(self, asset, is_video, is_live):
        super().__init__()
        self.asset = asset
        self.is_video = is_video
        self.is_live = is_live
        self.aspect = asset_aspect(asset)  # proporcje do układu rzędów


class RowObj(GObject.Object):
    """Jeden rząd układu „jak w Google Photos”: zdjęcia o równej wysokości."""

    def __init__(self, start, items, height, widths):
        super().__init__()
        self.start, self.items, self.h, self.widths = start, items, height, widths


class RowBox(Gtk.Box):
    def __init__(self):
        super().__init__(spacing=ROW_GAP)
        self.tiles = []
        self.set_halign(Gtk.Align.START)
        self.set_margin_bottom(ROW_GAP)


class TexCache:
    """Mały cache tekstur w RAM (reszta leci z cache na dysku)."""

    def __init__(self, n=600):
        self.d = OrderedDict()
        self.n = n

    def get(self, k):
        t = self.d.get(k)
        if t is not None:
            self.d.move_to_end(k)
        return t

    def put(self, k, t):
        self.d[k] = t
        self.d.move_to_end(k)
        while len(self.d) > self.n:
            self.d.popitem(last=False)


def make_texture(data: bytes) -> Gdk.Texture:
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))


def make_square_texture(data: bytes, size: int = 96) -> Gdk.Texture:
    """Kwadratowy wycinek ze środka obrazu (okładki albumów) o stałym rozmiarze."""
    try:
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pb = loader.get_pixbuf()
        w, h = pb.get_width(), pb.get_height()
        side = min(w, h)
        pb = pb.new_subpixbuf((w - side) // 2, (h - side) // 2, side, side)
        pb = pb.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
        return Gdk.Texture.new_for_pixbuf(pb)
    except Exception:  # noqa: BLE001
        return make_texture(data)


def blur_texture(tex, size=(24, 16)):
    """Bardzo mała, uśredniona kopia zdjęcia. Rozciągnięta na całe okno (z wygładzaniem) daje miękkie plamy
    kolorów - rozmyte tło bez kosztownego rozmywania podczas rysowania."""
    d = Gdk.TextureDownloader.new(tex)
    d.set_format(Gdk.MemoryFormat.R8G8B8A8)
    data, stride = d.download_bytes()
    pb = GdkPixbuf.Pixbuf.new_from_bytes(data, GdkPixbuf.Colorspace.RGB, True, 8,
                                         tex.get_width(), tex.get_height(), stride)
    return Gdk.Texture.new_for_pixbuf(pb.scale_simple(size[0], size[1], GdkPixbuf.InterpType.BILINEAR))


class Backdrop(Gtk.Widget):
    """Tło okna w trybie przezroczystości: rozmyte kolory bieżącego albumu pod półprzezroczystym interfejsem."""

    def __init__(self):
        super().__init__()
        self.tex = None
        self.strength = 0.0
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_can_target(False)

    def set_texture(self, tex):
        self.tex = tex
        self.queue_draw()

    def set_strength(self, v):
        self.strength = v
        self.queue_draw()

    def do_snapshot(self, snap):
        w, h = self.get_width(), self.get_height()
        if self.tex is None or self.strength <= 0 or w <= 0 or h <= 0:
            return
        snap.push_opacity(self.strength)
        snap.append_scaled_texture(self.tex, Gsk.ScalingFilter.TRILINEAR,
                                   Graphene.Rect().init(0, 0, w, h))
        snap.pop()


class Tile(Gtk.Overlay):
    def __init__(self, size=TILE_DEFAULT):
        super().__init__()
        self.bound = None
        self.future = None
        self.on_context = None
        rc = Gtk.GestureClick()
        rc.set_button(3)
        rc.connect("pressed", lambda g, n, x, y: self.on_context and self.on_context(self, x, y))
        self.add_controller(rc)
        self.on_activate = None  # widok rzędów: kliknięcie otwiera zdjęcie
        ac = Gtk.GestureClick()
        ac.set_button(1)
        ac.connect("released", lambda g, n, x, y: n == 1 and self.on_activate
                   and self.on_activate(self))
        self.add_controller(ac)
        self.on_press = None  # tryb zaznaczania: kliknięcie przełącza zaznaczenie
        pc = Gtk.GestureClick()
        pc.set_button(1)
        pc.connect("pressed", lambda g, n, x, y: self.on_press and self.on_press(self, g))
        self.add_controller(pc)
        self.pic = Gtk.Picture()
        self.pic.set_size_request(size, size)
        self.pic.set_content_fit(Gtk.ContentFit.COVER)
        self.pic.add_css_class("tile")
        self.set_child(self.pic)
        self.vbadge = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.vbadge.add_css_class("osd")
        self.vbadge.set_halign(Gtk.Align.END)
        self.vbadge.set_valign(Gtk.Align.END)
        self.vbadge.set_margin_end(6)
        self.vbadge.set_margin_bottom(6)
        self.add_overlay(self.vbadge)
        self.ph = Gtk.Image()
        self.ph.set_pixel_size(max(24, size // 3))
        self.ph.set_halign(Gtk.Align.CENTER)
        self.ph.set_valign(Gtk.Align.CENTER)
        self.ph.add_css_class("dim-label")
        self.ph.set_visible(False)
        self.ph.set_can_target(False)
        self.add_overlay(self.ph)
        self.lbadge = Gtk.Label(label="LIVE")
        self.lbadge.add_css_class("livebadge")
        self.lbadge.set_halign(Gtk.Align.START)
        self.lbadge.set_valign(Gtk.Align.START)
        self.add_overlay(self.lbadge)
        self.check = Gtk.CheckButton()
        self.check.add_css_class("selection-mode")
        self.check.set_halign(Gtk.Align.END)
        self.check.set_valign(Gtk.Align.START)
        self.check.set_margin_top(6)
        self.check.set_margin_end(6)
        self.check.set_can_target(False)
        self.check.set_visible(False)
        self.add_overlay(self.check)

    def set_fit(self, original):
        """original=True: cała fotografia w oryginalnych proporcjach (bez przycinania)."""
        self.pic.set_content_fit(Gtk.ContentFit.CONTAIN if original else Gtk.ContentFit.COVER)

    def set_dims(self, w, h):
        self.pic.set_size_request(w, h)
        self.ph.set_pixel_size(max(24, min(w, h) // 3))

    def set_size(self, n):
        self.pic.set_size_request(n, n)
        self.ph.set_pixel_size(max(24, n // 3))


class ZoomView(Gtk.ScrolledWindow):
    """Obraz z zoomem: Ctrl+kółko, +/-/0, szczypanie, dwuklik; przeciąganie = pan."""

    MAX_Z = 8.0

    def __init__(self, on_zoom=None):
        super().__init__()
        self.on_zoom = on_zoom
        self.zoom = 1.0
        self.aspect = 0.0
        self._mx = self._my = 0.0
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.pic = Gtk.Picture()
        self.pic.set_can_shrink(True)
        self.pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.set_child(self.pic)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda c, x, y: self._track(x, y))
        self.add_controller(motion)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        scroll.connect("scroll", self._on_scroll)
        self.add_controller(scroll)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_click)
        self.add_controller(click)

        self.on_longpress = None
        self.on_context = None
        lp = Gtk.GestureLongPress()
        lp.connect("pressed", lambda g, x, y: self.zoom <= 1.0 and self.on_longpress
                   and self.on_longpress())
        self.add_controller(lp)
        rc = Gtk.GestureClick()
        rc.set_button(3)
        rc.connect("pressed", lambda g, n, x, y: self.on_context and self.on_context(x, y))
        self.add_controller(rc)

        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        self.add_controller(drag)
        self._drag0 = (0.0, 0.0)

        pinch = Gtk.GestureZoom()
        pinch.connect("begin", lambda g, s: setattr(self, "_pz", self.zoom))
        pinch.connect("scale-changed", lambda g, sc: self.set_zoom(self._pz * sc,
                                                                   self._mx, self._my))
        self.add_controller(pinch)
        self._pz = 1.0

    def _track(self, x, y):
        self._mx, self._my = x, y

    # --- obraz ---
    def set_image(self, tex, keep_zoom=False):
        if tex is None:
            self.pic.set_paintable(None)
            self.aspect = 0.0
            self.set_zoom(1.0)
            return
        self.aspect = tex.get_width() / max(1, tex.get_height())
        self.pic.set_paintable(tex)
        if not keep_zoom:
            self.set_zoom(1.0)

    def _fit_size(self):
        vw, vh = self.get_width(), self.get_height()
        if self.aspect <= 0 or vw <= 0 or vh <= 0:
            return float(max(vw, 1)), float(max(vh, 1))
        if vw / vh > self.aspect:
            return vh * self.aspect, float(vh)
        return float(vw), vw / self.aspect

    # --- zoom ---
    def set_zoom(self, z, px=None, py=None):
        z = max(1.0, min(self.MAX_Z, z))
        h, v = self.get_hadjustment(), self.get_vadjustment()
        vw, vh = self.get_width(), self.get_height()
        if px is None:
            px, py = vw / 2, vh / 2
        cw0, ch0 = max(h.get_upper(), 1.0), max(v.get_upper(), 1.0)
        fx, fy = (h.get_value() + px) / cw0, (v.get_value() + py) / ch0

        self.zoom = z
        if z <= 1.0001:
            self.zoom = 1.0
            self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            self.pic.set_size_request(-1, -1)
            h.set_value(0)
            v.set_value(0)
        else:
            fw, fh = self._fit_size()
            self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            self.pic.set_size_request(int(fw * z), int(fh * z))
            tw, th = max(vw, fw * z), max(vh, fh * z)
            tries = [0]

            def settle(_w, _clock):
                tries[0] += 1
                if h.get_upper() >= tw - 2 and v.get_upper() >= th - 2:
                    h.set_value(fx * h.get_upper() - px)
                    v.set_value(fy * v.get_upper() - py)
                    return GLib.SOURCE_REMOVE
                return GLib.SOURCE_REMOVE if tries[0] > 30 else GLib.SOURCE_CONTINUE

            self.add_tick_callback(settle)
        if self.on_zoom:
            self.on_zoom(self.zoom)

    def zoom_by(self, factor):
        self.set_zoom(self.zoom * factor, self._mx or None, self._my or None)

    # --- sterowanie ---
    def _on_scroll(self, ctrl, _dx, dy):
        state = ctrl.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            self.zoom_by(1 / 1.15 if dy > 0 else 1.15)
            return True
        return self.zoom <= 1.0  # przy 1x połykamy; przy zoomie kółko = przewijanie

    def _on_click(self, _g, n, x, y):
        if n == 2:
            self.set_zoom(1.0 if self.zoom > 1.0 else 2.5, x, y)

    def _drag_begin(self, _g, _x, _y):
        self._drag0 = (self.get_hadjustment().get_value(),
                       self.get_vadjustment().get_value())

    def _drag_update(self, _g, dx, dy):
        if self.zoom > 1.0:
            self.get_hadjustment().set_value(self._drag0[0] - dx)
            self.get_vadjustment().set_value(self._drag0[1] - dy)


class Viewer(Gtk.Window):
    def __init__(self, win, index):
        super().__init__(transient_for=win, title=tr("Podgląd"))
        self.win = win
        win.viewers.add(self)
        self.store = win.store
        self.index = index
        self.token = 0
        self.live_mode = False
        self.orig_done = False
        self._media = None
        self._sigs = []
        self._zguard = False
        self._extra = ""
        self.set_default_size(1200, 800)
        self.add_css_class("viewer")

        self.zv = ZoomView(self._on_zoom)
        self.zv.on_longpress = lambda: self.play_live()  # przytrzymaj = Live Photo
        self.zv.on_context = lambda x, y: self.win.show_context_menu(
            self.zv, x, y, self.store.get_item(self.index))
        self.video = Gtk.Video()
        self.video.set_autoplay(True)
        self.stack = Gtk.Stack()
        self.stack.add_named(self.zv, "img")
        self.stack.add_named(self.video, "vid")

        self.caption = Gtk.Label()
        self.caption.add_css_class("caption")
        self.caption.set_halign(Gtk.Align.START)
        self.caption.set_valign(Gtk.Align.END)
        self.caption.set_can_target(False)
        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.spinner.set_size_request(48, 48)
        self.spinner.set_can_target(False)
        self.live_btn = Gtk.Button(label="◉ LIVE")
        self.live_btn.add_css_class("osd")
        self.live_btn.add_css_class("pill")
        self.live_btn.connect("clicked", lambda *_: self.play_live())

        self.play_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.play_btn.add_css_class("osd")
        self.play_btn.add_css_class("circular")
        self.play_btn.set_size_request(80, 80)
        self.play_btn.set_halign(Gtk.Align.CENTER)
        self.play_btn.set_valign(Gtk.Align.CENTER)
        self.play_btn.set_tooltip_text(tr("Odtwórz (Spacja / Enter)"))
        self.play_btn.set_visible(False)
        self.play_btn.connect("clicked", lambda *_: self._play_video())

        # pasek zoomu: − [suwak] + Dopasuj
        self.zbar = Gtk.Box(spacing=6)
        self.zbar.add_css_class("zbar")
        self.zbar.set_halign(Gtk.Align.CENTER)
        self.zbar.set_valign(Gtk.Align.END)
        b_out = Gtk.Button(icon_name="zoom-out-symbolic")
        b_out.add_css_class("flat")
        b_out.set_tooltip_text(tr("Pomniejsz (Ctrl −)"))
        b_out.connect("clicked", lambda *_: self.zv.zoom_by(1 / 1.25))
        self.zscale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
        self.zscale.set_draw_value(False)
        self.zscale.set_size_request(180, -1)
        self.zscale.connect("value-changed", self._on_zscale)
        b_in = Gtk.Button(icon_name="zoom-in-symbolic")
        b_in.add_css_class("flat")
        b_in.set_tooltip_text(tr("Powiększ (Ctrl +)"))
        b_in.connect("clicked", lambda *_: self.zv.zoom_by(1.25))
        b_fit = Gtk.Button(label=tr("Dopasuj"))
        b_fit.add_css_class("flat")
        b_fit.set_tooltip_text(tr("Dopasuj do okna (Ctrl 0)"))
        b_fit.connect("clicked", lambda *_: self.zv.set_zoom(1.0))
        for w in (b_out, self.zscale, b_in, b_fit):
            self.zbar.append(w)

        self.info_btn = Gtk.Button(icon_name="dialog-information-symbolic")
        self.info_btn.add_css_class("osd")
        self.info_btn.add_css_class("circular")
        self.info_btn.set_tooltip_text(tr("Informacje o zdjęciu (I)"))
        self.info_btn.connect(
            "clicked", lambda *_: self.win.show_info(self.store.get_item(self.index)))

        self.album_btn = Gtk.MenuButton(icon_name="folder-new-symbolic")
        self.album_btn.add_css_class("osd")
        self.album_btn.add_css_class("circular")
        self.album_btn.set_tooltip_text(tr("Dodaj do albumu (A)"))
        self.album_pop = Gtk.Popover()
        self.album_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.album_pop.set_child(self.album_box)
        self.album_pop.connect("show", lambda *_: self._rebuild_album_menu())
        self.album_btn.set_popover(self.album_pop)

        self.trash_btn = Gtk.Button(icon_name="user-trash-symbolic")
        self.trash_btn.add_css_class("osd")
        self.trash_btn.add_css_class("circular")
        self.trash_btn.set_tooltip_text(tr("Usuń zdjęcie (Delete)"))
        self.trash_btn.connect("clicked", lambda *_: self._delete_current())

        topbar = Gtk.Box(spacing=8)
        topbar.set_halign(Gtk.Align.END)
        topbar.set_valign(Gtk.Align.START)
        topbar.set_margin_top(12)
        topbar.set_margin_end(12)
        self.show_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
        self.show_btn.add_css_class("osd")
        self.show_btn.add_css_class("circular")
        self.show_btn.set_tooltip_text(tr("Pokaz slajdów od tego zdjęcia"))
        self.show_btn.connect("clicked", lambda *_: self._start_slideshow_here())
        for w in (self.live_btn, self.show_btn, self.album_btn, self.trash_btn, self.info_btn):
            topbar.append(w)

        ov = Gtk.Overlay()
        ov.set_child(self.stack)
        for w in (self.caption, self.spinner, topbar, self.play_btn, self.zbar):
            ov.add_overlay(w)
        self.set_child(ov)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.connect("close-request", lambda *_: (self._stop_video(), False)[1])

        self.show_index(index)

    # --- klawisze ---
    def toggle_fs(self):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def on_key(self, _c, keyval, _code, _state):
        on_video = self.stack.get_visible_child_name() == "vid"
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.show_index(self.index + 1)
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.show_index(self.index - 1)
        elif keyval == Gdk.KEY_Home:
            self.show_index(0)
        elif keyval == Gdk.KEY_End:
            self.show_index(self.store.get_n_items() - 1)
        elif keyval in (Gdk.KEY_f, Gdk.KEY_F, Gdk.KEY_F11):
            self.toggle_fs()
        elif keyval == Gdk.KEY_Escape:
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.close()
        elif keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add, Gdk.KEY_asterisk):
            self.zv.zoom_by(1.25)
        elif keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract, Gdk.KEY_underscore):
            self.zv.zoom_by(1 / 1.25)
        elif keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.zv.set_zoom(1.0)
        elif keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            cur = self.store.get_item(self.index)
            if on_video and self._media is not None:
                self._media.set_playing(not self._media.get_playing())
            elif cur.is_video:
                self._play_video()
            else:
                self.play_live()
        elif keyval in (Gdk.KEY_l, Gdk.KEY_L):
            self.play_live()
        elif keyval == Gdk.KEY_Delete:
            self._delete_current()
        elif keyval in (Gdk.KEY_a, Gdk.KEY_A):
            self.album_btn.popup()
        elif keyval in (Gdk.KEY_i, Gdk.KEY_I):
            self.win.show_info(self.store.get_item(self.index))
        elif keyval in (Gdk.KEY_m, Gdk.KEY_M):
            obj = self.store.get_item(self.index)
            self.win.play_external(
                obj, self.win.icloud.live_version(obj.asset) if self.live_mode else None)
        else:
            return False
        return True

    # --- wyświetlanie ---
    def _label(self, extra=""):
        n = self.store.get_n_items()
        obj = self.store.get_item(self.index)
        s = f"{obj.asset.filename}   ({self.index + 1}/{n})"
        if self.zv.zoom > 1.0:
            s += f"   {self.zv.zoom:.1f}×"
        return s + (f"   {extra}" if extra else "")

    def _start_slideshow_here(self):
        if self.store.get_n_items() == 0:
            return
        Slideshow(self.win, self.index).present()
        self.close()

    def _delete_current(self):
        if self.store.get_n_items() == 0:
            return
        obj = self.store.get_item(self.index)
        self.win.confirm_delete([obj.asset], parent=self)

    def after_delete(self, ids):
        """Okno główne usunęło zdjęcia: jeśli to bieżące, pokaż następne albo zamknij podgląd."""
        if getattr(self, "_cur_id", None) not in ids:
            return
        n = self.store.get_n_items()
        if n == 0:
            self.close()
        else:
            self.show_index(min(self.index, n - 1))

    def _rebuild_album_menu(self):
        box = self.album_box
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt
        entries = self.win.album_menu_entries(lambda: [self.store.get_item(self.index).asset])
        for label, cb in entries:
            b = Gtk.Button()
            b.add_css_class("flat")
            b.set_child(Gtk.Label(label=label, xalign=0))
            b.connect("clicked", lambda _b, cb=cb: (self.album_pop.popdown(), cb()))
            box.append(b)

    def _on_zscale(self, sc):
        if not self._zguard:
            self.zv.set_zoom(ZoomView.MAX_Z ** sc.get_value())

    def _page(self, name):
        self.stack.set_visible_child_name(name)
        self.zbar.set_visible(name == "img")
        if name == "vid":
            self.play_btn.set_visible(False)

    def _on_zoom(self, z):
        if hasattr(self, "zscale"):
            self._zguard = True
            self.zscale.set_value(math.log(max(z, 1.0)) / math.log(ZoomView.MAX_Z))
            self._zguard = False
        if hasattr(self, "store") and self.store.get_n_items():
            self.caption.set_text(self._label(getattr(self, "_extra", "")))
        if z > 1.5:
            self._upgrade_original()

    def show_index(self, i):
        n = self.store.get_n_items()
        if n == 0:
            return
        self._stop_video()
        self.index = max(0, min(n - 1, i))
        self.token += 1
        token = self.token
        self.orig_done = False
        self.live_mode = False
        self._extra = ""
        obj = self.store.get_item(self.index)
        self._cur_id = obj.asset.id
        self.trash_btn.set_visible(not self.win._in_trash())
        self.win.last_obj = obj
        self.live_btn.set_visible(obj.is_live)
        self.show_btn.set_visible(not obj.is_video)  # pokaz slajdów dotyczy zdjęć, nie wideo

        if obj.is_video and not self.win.external_video_ok():
            self._page("vid")  # tryb wbudowany (bez mpv)
            self.caption.set_text(self._label(tr("(Spacja = pauza, M = mpv)")))
            self._play(obj, self.win.icloud.video_version(obj.asset, True))
            return

        self._page("img")
        self.play_btn.set_visible(obj.is_video)  # film: plakat + przycisk ▶
        if not obj.is_video:
            self.win.cast_asset(obj.asset)
        self.zv.set_image(self.win.tex.get(obj.asset.id))
        hint = (tr("(Spacja/Enter/▶ = odtwórz)") if obj.is_video
                else tr("(L/Spacja = Live)") if obj.is_live else "")
        self.caption.set_text(self._label(hint))
        self.spinner.start()

        def work():
            return make_texture(self.win.icloud.fetch(obj.asset, "medium"))

        def done(tex, err):
            if token != self.token:
                return
            self.spinner.stop()
            if err:
                self.caption.set_text(self._label(tr("[błąd: {0}]").format(err)))
            else:
                self.zv.set_image(tex)

        bg(work, done)
        for j in (self.index + 1, self.index - 1):  # prefetch sąsiadów do cache
            if 0 <= j < n:
                POOL.submit(self._safe_fetch, self.store.get_item(j).asset)

    def _safe_fetch(self, asset):
        try:
            self.win.icloud.fetch(asset, "medium")
        except Exception:  # noqa: BLE001
            pass

    def _upgrade_original(self):
        obj = self.store.get_item(self.index)
        if self.orig_done or obj.is_video:
            return
        self.orig_done = True
        token = self.token

        def work():
            return make_texture(self.win.icloud.fetch_original(obj.asset))

        def done(tex, err):
            if token != self.token:
                return
            if err:
                self._extra = tr("(oryginał niedostępny: brak dekodera HEIC?)")
            else:
                self._extra = tr("(oryginał)")
                self.zv.set_image(tex, keep_zoom=True)
            self.caption.set_text(self._label(self._extra))

        self.spinner.start()
        bg(work, lambda t, e: (self.spinner.stop(), done(t, e)))

    # --- wideo / Live Photos ---
    def _play_video(self):
        obj = self.store.get_item(self.index)
        if not obj.is_video:
            return
        if self.win.cast_target is not None:
            self.win.cast_asset(obj.asset)
            self.caption.set_text(self._label(tr("(wysłano na TV)")))
        elif self.win.external_video_ok():
            self.win.play_external(obj)
        else:
            self._page("vid")
            self._play(obj, self.win.icloud.video_version(obj.asset, True))

    def _play(self, obj, ver):
        if ver is None:
            self.caption.set_text(self._label(tr("[brak wersji wideo]")))
            return
        # GStreamer w sandboxie Flatpak nie ma obsługi http przez GIO, więc odtwarzamy plik lokalny:
        # film (zwykle H.264 'medium') jest najpierw pobierany do cache.
        token = self.token
        self.caption.set_text(self._label(tr("(pobieranie filmu…)")))

        def work():
            try:
                path = self.win.icloud.fetch_video_file(obj.asset, ver)
            except Exception as e:  # noqa: BLE001
                log.error("pobieranie filmu %s: %r", obj.asset.filename, e)
                GLib.idle_add(done, None, str(e))
                return
            GLib.idle_add(done, path, None)

        def done(path, err):
            if token != self.token:
                return False
            if path is None:
                self._fallback(f"[{err}]")
                return False
            self.caption.set_text(self._label(tr("(Spacja = pauza, M = mpv)")))
            self._start_local(path)
            return False

        threading.Thread(target=work, daemon=True).start()

    def _start_local(self, path):
        self.video.set_file(Gio.File.new_for_path(path))
        m = self.video.get_media_stream()
        self._media = m
        if m is not None:
            self._sigs = [m.connect("notify::error", self._on_media_error),
                          m.connect("notify::ended", self._on_ended)]
            token = self.token

            def watchdog():  # wbudowany odtwarzacz nie wystartował -> mpv
                if (token == self.token and self._media is m
                        and not m.is_prepared() and m.get_error() is None):
                    self._fallback(tr("[wbudowany odtwarzacz nie wystartował]"))
                return False

            GLib.timeout_add_seconds(8, watchdog)

    def _fallback(self, why):
        """Zapas: otwórz bieżące wideo w osobnym oknie mpv (raz na pozycję)."""
        obj = self.store.get_item(self.index)
        if getattr(self, "_fb_done", None) == (self.token, self.live_mode):
            return
        self._fb_done = (self.token, self.live_mode)
        ver = self.win.icloud.live_version(obj.asset) if self.live_mode else None
        url = getattr(self, "_cur_path", None) if self.live_mode else None
        ok = self.win.play_external(obj, ver, url=url)
        self.caption.set_text(self._label(why + (" → mpv" if ok else " (zainstaluj mpv)")))

    def _stop_video(self):
        m, self._media = self._media, None
        if m is not None:
            for s in self._sigs:
                m.disconnect(s)
            m.set_playing(False)
        self._sigs = []
        self.video.set_file(None)

    def _on_media_error(self, m, _p):
        if m.get_error() is not None:
            err = m.get_error()
            log.error("błąd odtwarzacza GTK: %s | dekodery: %s | GST_PLUGIN_SYSTEM_PATH=%s",
                      err, _gst_decoders(), os.environ.get("GST_PLUGIN_SYSTEM_PATH"))
            msg = str(getattr(err, "message", err)).strip().replace("\n", " ")[:90]
            self._fallback(tr("[GStreamer nie odtworzył - brak kodeka?]") + f" {{{msg}}}")

    def _on_ended(self, m, _p):
        if self.live_mode and m.get_ended():
            self.live_mode = False
            token = self.token

            def back():  # nie zatrzymujemy strumienia w jego własnym sygnale
                if token == self.token:
                    self._stop_video()
                    self._page("img")
                return False

            GLib.idle_add(back)

    def play_live(self):
        obj = self.store.get_item(self.index)
        if not obj.is_live or self.live_mode:
            return
        ver = self.win.icloud.live_version(obj.asset)
        if ver is None:
            self.caption.set_text(self._label(tr("[brak części wideo tego Live Photo]")))
            return
        self.live_mode = True
        token = self.token
        self.spinner.start()
        self.caption.set_text(self._label(tr("(pobieram Live Photo…)")))

        def work():
            return self.win.icloud.fetch_live(obj.asset, ver)

        def done(path, err):
            self.spinner.stop()
            if token != self.token or not self.live_mode:
                return
            if err:
                self.live_mode = False
                log.error("Live Photo %s: %r", obj.asset.filename, err)
                self.caption.set_text(self._label(f"[Live Photo: {err}]"))
                return
            log.info("Live Photo: %s (%s)", obj.asset.filename, path)
            self._page("vid")
            self._play_path(path)

        bg(work, done)

    def _play_path(self, path):
        """Odtwarza lokalny plik (krótki klip Live Photo); gdy się nie uda - mpv."""
        self._cur_path = path
        self.video.set_file(Gio.File.new_for_path(path))
        m = self.video.get_media_stream()
        self._media = m
        if m is not None:
            self._sigs = [m.connect("notify::error", self._on_media_error),
                          m.connect("notify::ended", self._on_ended)]
            token = self.token

            def watchdog():
                if (token == self.token and self._media is m
                        and not m.is_prepared() and m.get_error() is None):
                    self._fallback(tr("[wbudowany odtwarzacz nie wystartował]"))
                return False

            GLib.timeout_add_seconds(4, watchdog)


class Slideshow(Gtk.Window):
    """Pokaz slajdów bieżącego albumu: PLAY/pauza, ←/→, odstęp, wysyłka na TV."""

    def __init__(self, win, start=0):
        super().__init__(transient_for=win, title=tr("Pokaz slajdów"))
        self.win = win
        self.store = win.store
        self.i = start - 1
        self.playing = True
        self.token = 0
        self.secs = win.slide_secs
        self._timer = 0
        self._hide = 0
        self.front = 0
        self.set_default_size(1200, 800)
        self.add_css_class("viewer")

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(700)
        self.pics = []
        for name in ("0", "1"):
            pic = Gtk.Picture()
            pic.set_can_shrink(True)
            pic.set_content_fit(Gtk.ContentFit.CONTAIN)
            self.stack.add_named(pic, name)
            self.pics.append(pic)

        self.caption = Gtk.Label()
        self.caption.add_css_class("caption")
        self.caption.set_halign(Gtk.Align.START)
        self.caption.set_valign(Gtk.Align.START)
        self.caption.set_can_target(False)

        bar = Gtk.Box(spacing=6)
        bar.add_css_class("zbar")
        prev = Gtk.Button(icon_name="media-skip-backward-symbolic")
        self.pp = Gtk.Button(icon_name="media-playback-pause-symbolic")
        nxt = Gtk.Button(icon_name="media-skip-forward-symbolic")
        for b in (prev, self.pp, nxt):
            b.add_css_class("flat")
        prev.connect("clicked", lambda *_: self.go(-1))
        nxt.connect("clicked", lambda *_: self.go(1))
        self.pp.connect("clicked", lambda *_: self.toggle())
        self.dd = Gtk.DropDown.new_from_strings([f"{n} s" for n in SLIDE_SECS])
        self.dd.set_selected(min(range(len(SLIDE_SECS)),
                                 key=lambda k: abs(SLIDE_SECS[k] - self.secs)))
        self.dd.connect("notify::selected", self._on_secs)
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("flat")
        close.connect("clicked", lambda *_: self.close())
        for w in (prev, self.pp, nxt, self.dd, close):
            bar.append(w)
        self.rev = Gtk.Revealer()
        self.rev.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.rev.set_child(bar)
        self.rev.set_halign(Gtk.Align.CENTER)
        self.rev.set_valign(Gtk.Align.END)
        self.rev.set_reveal_child(True)

        ov = Gtk.Overlay()
        ov.set_child(self.stack)
        ov.add_overlay(self.caption)
        ov.add_overlay(self.rev)
        self.set_child(ov)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *_: self._show_bar())
        self.add_controller(motion)
        self.connect("close-request", self._on_close)
        self.fullscreen()
        self._show_bar()
        self.go(1)

    # --- sterowanie ---
    def _on_key(self, _c, keyval, _code, _state):
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Page_Down):
            self.go(1)
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Page_Up):
            self.go(-1)
        elif keyval == Gdk.KEY_space:
            self.toggle()
        elif keyval == Gdk.KEY_Escape:
            self.close()
        elif keyval in (Gdk.KEY_f, Gdk.KEY_F, Gdk.KEY_F11):
            self.unfullscreen() if self.is_fullscreen() else self.fullscreen()
        else:
            return False
        self._show_bar()
        return True

    def _on_secs(self, dd, _p):
        self.secs = SLIDE_SECS[dd.get_selected()]
        self.win.slide_secs = self.secs
        save_cfg(slide_secs=self.secs)
        if self.playing:
            self._schedule()

    def toggle(self):
        self.playing = not self.playing
        self.pp.set_icon_name("media-playback-pause-symbolic" if self.playing
                              else "media-playback-start-symbolic")
        if self.playing:
            self._schedule()
        else:
            self._cancel()

    def _show_bar(self):
        self.rev.set_reveal_child(True)
        self.set_cursor(None)
        if self._hide:
            GLib.source_remove(self._hide)
        self._hide = GLib.timeout_add_seconds(3, self._hide_bar)

    def _hide_bar(self):
        self._hide = 0
        self.rev.set_reveal_child(False)
        self.set_cursor_from_name("none")
        return False

    def _cancel(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _schedule(self, delay=None):
        self._cancel()
        self._timer = GLib.timeout_add_seconds(delay or self.secs, self._tick)

    def _tick(self):
        self._timer = 0
        if self.playing:
            self.go(1)
        return False

    def _on_close(self, *_):
        self._cancel()
        if self._hide:
            GLib.source_remove(self._hide)
            self._hide = 0
        return False

    # --- przejście do następnego/poprzedniego zdjęcia (pomija filmy) ---
    def go(self, step):
        n = self.store.get_n_items()
        if n == 0:
            return
        if self.i > n - 10 and not self.win.exhausted:
            self.win.load_more()  # doładuj dalszą część albumu
        j = self.i
        for _ in range(n + 1):
            j += step
            if j >= n:
                if not self.win.exhausted:  # jeszcze się ładuje - spróbuj za chwilę
                    self._schedule(1)
                    return
                j = 0  # pętla od początku
            if j < 0:
                j = n - 1
            if not self.store.get_item(j).is_video:
                break
        self.show(j)

    def show(self, j):
        self.token += 1
        token = self.token
        obj = self.store.get_item(j)
        self._cancel()

        def work():
            return make_texture(self.win.icloud.fetch(obj.asset, "medium"))

        def done(tex, err):
            if token != self.token:
                return
            if err:
                log.warning("pokaz: pomijam %s: %r", obj.asset.filename, err)
                self.i = j
                if self.playing:
                    self._schedule(1)
                return
            self.i = j
            nxt = 1 - self.front
            self.pics[nxt].set_paintable(tex)
            self.stack.set_visible_child_name(str(nxt))
            self.front = nxt
            n = self.store.get_n_items()
            more = "+" if not self.win.exhausted else ""
            self.caption.set_text(f"{obj.asset.filename}   ({j + 1}/{n}{more})")
            self.win.cast_asset(obj.asset)
            if self.playing:
                self._schedule()
            for k in (j + 1, j + 2):
                if k < n and not self.store.get_item(k).is_video:
                    POOL.submit(self._safe_fetch, self.store.get_item(k).asset)

        bg(work, done)

    def _safe_fetch(self, asset):
        try:
            self.win.icloud.fetch(asset, "medium")
        except Exception:  # noqa: BLE001
            pass


class UploadDialog(Gtk.Window):
    """Wysyłanie plików z komputera do iCloud z wyborem albumu."""

    def __init__(self, win, paths):
        super().__init__(transient_for=win, modal=True, title=tr("Prześlij do iCloud"))
        self.win = win
        self.paths = paths
        self._cancel = False
        self._running = False
        self.set_default_size(440, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(18)
        names = ", ".join(os.path.basename(p) for p in paths[:3])
        if len(paths) > 3:
            names += f" … (+{len(paths) - 3})"
        title = Gtk.Label(label=tr("Pliki do wysłania: {0}").format(len(paths)), xalign=0)
        title.add_css_class("heading")
        sub = Gtk.Label(label=names, xalign=0, wrap=True)
        sub.add_css_class("dim-label")
        sub.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.append(title)
        box.append(sub)
        box.append(Gtk.Label(label=tr("Dodaj do albumu:"), xalign=0))
        self.names = [tr("Tylko biblioteka (bez albumu)")] + [n for n, _ in win.user_albums]
        self.dd = Gtk.DropDown.new_from_strings(self.names)
        for k, (n, _a) in enumerate(win.user_albums):
            if n == win.cur_title:
                self.dd.set_selected(k + 1)  # domyślnie bieżący album
        box.append(self.dd)
        self.prog = Gtk.ProgressBar()
        self.prog.set_visible(False)
        self.status = Gtk.Label(wrap=True, xalign=0, selectable=True)
        self.status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.append(self.prog)
        box.append(self.status)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.btn_cancel = Gtk.Button(label=tr("Anuluj"))
        self.btn_go = Gtk.Button(label=tr("Prześlij"))
        self.btn_go.add_css_class("suggested-action")
        self.btn_cancel.connect("clicked", self._on_cancel)
        self.btn_go.connect("clicked", self._go)
        row.append(self.btn_cancel)
        row.append(self.btn_go)
        box.append(row)
        self.set_child(box)

    def _on_cancel(self, *_):
        self._cancel = True
        if not self._running:
            self.close()

    def _go(self, *_):
        idx = self.dd.get_selected()
        album = None if idx == 0 else self.win.user_albums[idx - 1][1]
        album_name = None if idx == 0 else self.win.user_albums[idx - 1][0]
        self._running = True
        self.btn_go.set_sensitive(False)
        self.dd.set_sensitive(False)
        self.prog.set_visible(True)
        total = len(self.paths)
        self.status.set_text(tr("Wysyłanie 0/{0}…").format(total))

        def progress(k):
            self.prog.set_fraction(k / total)
            self.status.set_text(tr("Wysyłanie {0}/{1}…").format(k, total))
            return False

        def work():
            ok, errs = 0, []
            for k, path in enumerate(self.paths):
                if self._cancel:
                    break
                try:
                    self.win.icloud.upload(path, album)
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    errs.append(f"{os.path.basename(path)}: {e}")
                    log.error("upload %s: %r", path, e)
                GLib.idle_add(progress, k + 1)
            return ok, errs

        def done(res, err):
            self._running = False
            ok, errs = res if res else (0, [str(err)])
            text = tr("Wysłano {0} z {1}.").format(ok, total)
            if errs:
                text += tr("\nBłędy:\n") + "\n".join(errs[:6])
            self.status.set_text(text)
            self.btn_cancel.set_label(tr("Zamknij"))
            self.btn_cancel.set_sensitive(True)
            if ok:
                self.win.after_upload(album_name)

        bg(work, done)


def _fmt_dt(dt):
    try:
        return dt.astimezone().strftime("%d.%m.%Y  %H:%M")
    except Exception:  # noqa: BLE001
        return "-"


def _fmt_size(n):
    if not n:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class InfoDialog(Gtk.Window):
    """Informacje o zdjęciu: nazwa, daty, rozmiar, lokalizacja, aparat/telefon (EXIF)."""

    def __init__(self, win, obj):
        super().__init__(transient_for=win, title=tr("Informacje o zdjęciu"))
        self.win = win
        self.obj = obj
        self.lat_lon = None
        self.set_default_size(440, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(18)
        self.grid = Gtk.Grid(column_spacing=14, row_spacing=8)
        self.row = 0
        box.append(self.grid)
        self.extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(self.extra)
        self.set_child(box)

        info = win.icloud.asset_info(obj.asset)
        kind = tr("Wideo|typ") if info.get("video") else ("Live Photo" if info.get("live") else tr("Zdjęcie"))
        self._add(tr("Nazwa pliku"), info.get("filename", "-"))
        self._add(tr("Typ"), kind)
        if info.get("asset_date"):
            self._add(tr("Data wykonania"), _fmt_dt(info["asset_date"]))
        if info.get("added_date"):
            self._add(tr("Dodano do iCloud"), _fmt_dt(info["added_date"]))
        w, h = (info.get("dimensions") or (None, None))
        if w and h:
            self._add(tr("Wymiary"), f"{w} × {h}  ({w * h / 1e6:.1f} MP)")
        if info.get("size"):
            self._add(tr("Rozmiar oryginału"), _fmt_size(info["size"]))
        if info.get("gps"):
            self._add_location(*info["gps"])
        if info.get("video"):
            return
        self.cam = Gtk.Label(label=tr("Dane aparatu: wczytuję…"), xalign=0)
        self.cam.add_css_class("dim-label")
        self.extra.append(self.cam)
        bg(lambda: win.icloud.read_exif(obj.asset), lambda r, e: self._exif_done(r, e, False))

    def _add(self, key, value):
        k = Gtk.Label(label=key, xalign=0, yalign=0)
        k.add_css_class("dim-label")
        v = Gtk.Label(label=str(value), xalign=0, selectable=True, wrap=True)
        v.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        v.set_max_width_chars(40)
        self.grid.attach(k, 0, self.row, 1, 1)
        self.grid.attach(v, 1, self.row, 1, 1)
        self.row += 1
        return v

    def _add_location(self, lat, lon):
        if self.lat_lon:
            return
        self.lat_lon = (lat, lon)
        self._add(tr("Lokalizacja"), f"{lat:.5f}, {lon:.5f}")
        link = Gtk.LinkButton.new_with_label(
            f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}",
            tr("Pokaż na mapie (OpenStreetMap)"))
        link.set_halign(Gtk.Align.START)
        name_btn = Gtk.Button(label=tr("Pokaż nazwę miejsca"))
        name_btn.set_halign(Gtk.Align.START)
        name_btn.set_tooltip_text(tr("Wysyła współrzędne do OpenStreetMap (Nominatim)"))

        def go(_b):
            name_btn.set_sensitive(False)
            name_btn.set_label(tr("Szukam…"))
            bg(lambda: self.win.icloud.reverse_geocode(lat, lon), done)

        def done(res, err):
            name_btn.set_visible(False)
            lbl = Gtk.Label(label=res or tr("Nie udało się: {0}").format(err), xalign=0, wrap=True,
                            selectable=True)
            lbl.set_max_width_chars(44)
            self.extra.append(lbl)

        name_btn.connect("clicked", go)
        self.extra.append(link)
        self.extra.append(name_btn)

    def _exif_done(self, res, err, from_original):
        if hasattr(self, "orig_btn"):
            self.orig_btn.set_visible(False)
        if err:
            self.cam.set_text(tr("Nie udało się wczytać danych aparatu: {0}").format(err))
            return
        res = res or {}
        cam = " ".join(x for x in (res.get("Make"), res.get("Model")) if x)
        if res.get("Make") and res.get("Model", "").startswith(res["Make"]):
            cam = res["Model"]
        if not cam and not res:
            self.cam.set_text(tr("Podgląd z iCloud nie zawiera danych aparatu.")
                              if not from_original else tr("Oryginał nie zawiera danych EXIF."))
            if not from_original:
                self.orig_btn = Gtk.Button(label=tr("Wczytaj z oryginału (większy plik)"))
                self.orig_btn.set_halign(Gtk.Align.START)

                def go(_b):
                    self.orig_btn.set_sensitive(False)
                    self.cam.set_text(tr("Pobieram oryginał…"))
                    bg(lambda: self.win.icloud.read_exif(self.obj.asset, original=True),
                       lambda r, e: self._exif_done(r, e, True))

                self.orig_btn.connect("clicked", go)
                self.extra.append(self.orig_btn)
            return
        self.cam.set_visible(False)
        if cam:
            self._add(tr("Telefon / aparat"), cam)
        if res.get("LensModel"):
            self._add(tr("Obiektyw"), res["LensModel"])
        exp = ", ".join(str(res[k]) for k in ("FNumber", "ExposureTime", "FocalLength")
                        if k in res)
        if res.get("ISO"):
            exp += (", " if exp else "") + f"ISO {res['ISO']}"
        if exp:
            self._add(tr("Ekspozycja"), exp)
        if res.get("DateTimeOriginal"):
            self._add(tr("Data (EXIF)"), res["DateTimeOriginal"])
        if res.get("gps"):
            self._add_location(*res["gps"])


SMART_PL = {
    "All Photos": (tr("Wszystkie zdjęcia"), "image-x-generic-symbolic"),
    "Favorites": (tr("Ulubione"), "starred-symbolic"),
    "Videos": (tr("Wideo"), "camera-video-symbolic"),
    "Live": ("Live Photos", "media-playback-start-symbolic"),
    "Screenshots": (tr("Zrzuty ekranu"), "camera-photo-symbolic"),
    "Selfies": (tr("Selfie"), "avatar-default-symbolic"),
    "Portrait": (tr("Portrety"), "avatar-default-symbolic"),
    "Panoramas": (tr("Panoramy"), "image-x-generic-symbolic"),
    "Bursts": (tr("Serie"), "view-grid-symbolic"),
    "Slo-mo": (tr("Slow-motion"), "camera-video-symbolic"),
    "Time-lapse": (tr("Poklatkowe"), "camera-video-symbolic"),
    "Long Exposure": (tr("Długa ekspozycja"), "image-x-generic-symbolic"),
    "Animated": (tr("Animacje"), "image-x-generic-symbolic"),
    "Hidden": (tr("Ukryte"), "view-conceal-symbolic"),
    "Recently Deleted": (tr("Ostatnio usunięte"), "user-trash-symbolic"),
}
PRIMARY = ("All Photos", "Favorites", "Videos", "Live", "Screenshots")
MORE_ORDER = ("Selfies", "Portrait", "Panoramas", "Bursts", "Slo-mo", "Time-lapse",
              "Long Exposure", "Animated", "Hidden", "Recently Deleted")


class SettingsDialog(Gtk.Window):
    """Ustawienia: limit pamięci podręcznej, czyszczenie, odtwarzacz filmów."""

    def __init__(self, win):
        super().__init__(transient_for=win, modal=True, title=tr("Ustawienia"))
        self.win = win
        self.set_default_size(440, -1)
        grid = Gtk.Grid(column_spacing=16, row_spacing=12)
        for m in ("top", "bottom", "start", "end"):
            getattr(grid, f"set_margin_{m}")(18)
        grid.attach(Gtk.Label(label=tr("Limit pamięci podręcznej (GB)"), xalign=0), 0, 0, 1, 1)
        adj = Gtk.Adjustment(value=win.cache_gb, lower=0.25, upper=20, step_increment=0.25,
                             page_increment=1)
        self.spin = Gtk.SpinButton(adjustment=adj, digits=2)
        self.spin.connect("value-changed", self._on_limit)
        grid.attach(self.spin, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=tr("Zajęte teraz"), xalign=0), 0, 1, 1, 1)
        row = Gtk.Box(spacing=8)
        self.size_lbl = Gtk.Label(xalign=0, hexpand=True)
        clear = Gtk.Button(label=tr("Wyczyść pamięć podręczną"))
        clear.connect("clicked", self._on_clear)
        row.append(self.size_lbl)
        row.append(clear)
        grid.attach(row, 1, 1, 1, 1)
        grid.attach(Gtk.Label(label=tr("Odtwarzacz filmów"), xalign=0), 0, 2, 1, 1)
        self.modes = ["auto", "mpv", "embedded"]
        self.dd = Gtk.DropDown.new_from_strings(
            [tr("Automatycznie (mpv, jeśli jest)"), tr("Zawsze mpv"), tr("Wbudowany odtwarzacz")])
        self.dd.set_selected(self.modes.index(win.video_player)
                             if win.video_player in self.modes else 0)
        self.dd.connect("notify::selected", self._on_player)
        grid.attach(self.dd, 1, 2, 1, 1)
        have = tr("znaleziono") if shutil.which("mpv") else tr("NIE znaleziono (sudo apt install mpv)")
        note = Gtk.Label(label=f"mpv: {have}", xalign=0)
        note.add_css_class("dim-label")
        grid.attach(note, 1, 3, 1, 1)
        grid.attach(Gtk.Label(label=tr("Język (wymaga ponownego uruchomienia)"), xalign=0), 0, 4, 1, 1)
        self.langs = ["auto", "pl", "en", "de", "uk"]
        self.lang_dd = Gtk.DropDown.new_from_strings(
            [tr("Automatycznie (język systemu)"), "Polski", "English", "Deutsch", "Українська"])
        cur = load_cfg().get("language", "auto")
        self.lang_dd.set_selected(self.langs.index(cur) if cur in self.langs else 0)
        self.lang_dd.connect("notify::selected", self._on_language)
        grid.attach(self.lang_dd, 1, 4, 1, 1)
        grid.attach(Gtk.Label(label=tr("Przezroczystość okna"), xalign=0), 0, 5, 1, 1)
        self.glass_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.glass_scale.set_hexpand(True)
        self.glass_scale.set_draw_value(True)
        self.glass_scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.glass_scale.set_format_value_func(
            lambda s, v: tr("Wyłączona") if v < 1 else f"{int(v)}%")
        self.glass_scale.set_value(win.glass)
        self.glass_scale.connect("value-changed", self._on_glass)
        grid.attach(self.glass_scale, 1, 5, 1, 1)
        hint = Gtk.Label(label=tr("Rozmyte tło ze zdjęć. Rozmycie pulpitu za oknem robi tylko system "
                                  "(np. rozszerzenie Blur my Shell)."), xalign=0, wrap=True)
        hint.set_max_width_chars(38)
        hint.add_css_class("dim-label")
        grid.attach(hint, 1, 6, 1, 1)
        # motyw wyglądu (wstawiony nad przezroczystością okna)
        grid.insert_row(5)
        grid.attach(Gtk.Label(label=tr("Motyw"), xalign=0), 0, 5, 1, 1)
        self.themes = ["system", "aurora"]
        self.theme_dd = Gtk.DropDown.new_from_strings([tr("Systemowy"), "Aurora"])
        cur_t = load_cfg().get("theme", "system")
        self.theme_dd.set_selected(self.themes.index(cur_t) if cur_t in self.themes else 0)
        self.theme_dd.connect("notify::selected", self._on_theme)
        grid.attach(self.theme_dd, 1, 5, 1, 1)
        pv = Gtk.Label(label=f"pyicloud {pyicloud_version() or '?'}  (tested: {TESTED_PYICLOUD})",
                       xalign=0)
        pv.add_css_class("dim-label")
        grid.attach(pv, 1, 8, 1, 1)
        self.set_child(grid)
        self._refresh_size()

    def _refresh_size(self):
        self.size_lbl.set_text(f"{cache_size() / 1024**2:.0f} MB")

    def _on_limit(self, sp):
        self.win.cache_gb = sp.get_value()
        save_cfg(cache_gb=self.win.cache_gb)
        threading.Thread(target=prune_cache, args=(int(self.win.cache_gb * 1024**3),),
                         daemon=True).start()

    def _on_clear(self, _b):
        def done(freed, err):
            self._refresh_size()
            self.win.toast(tr("Pamięć podręczna wyczyszczona") if not err
                           else tr("Nie udało się wyczyścić: {0}").format(err))
        bg(clear_cache, done)

    def _on_glass(self, scale):
        v = int(scale.get_value())
        self.win.set_glass(v)
        save_cfg(glass=v)

    def _on_theme(self, dd, _p):
        name = self.themes[dd.get_selected()]
        save_cfg(theme=name)
        look = getattr(self.win.get_application(), "look", None)
        if look is not None:
            look.apply(name)

    def _on_language(self, dd, _p):
        save_cfg(language=self.langs[dd.get_selected()])
        self.win.toast(tr("Zmiana języka zadziała po ponownym uruchomieniu aplikacji"))

    def _on_player(self, dd, _p):
        self.win.video_player = self.modes[dd.get_selected()]
        save_cfg(video_player=self.win.video_player)


def format_album_result(name, total, ok, already, errors):
    """Opis wyniku dodawania do albumu: (pełny tekst, krótki tekst do powiadomienia)."""
    if already and not ok and len(already) == total:
        text = (tr("Zdjęcie „{0}” jest już w albumie „{1}”.").format(already[0].filename, name)
                if total == 1 else
                tr("Wszystkie zaznaczone zdjęcia ({0}) są już w albumie „{1}”.").format(total, name))
    else:
        text = tr("Dodano {0} z {1} do albumu „{2}”.").format(ok, total, name)
        if already:
            names = ", ".join(a.filename for a in already[:5])
            more = tr(" i {0} innych").format(len(already) - 5) if len(already) > 5 else ""
            text += tr("\nJuż w albumie „{0}”: {1} ({2}{3}).").format(name, len(already), names, more)
    if errors:
        text += tr("\nBłędy:\n") + "\n".join(errors[:5])
    short = text.split("\n")[0]
    if already and ok:
        short += tr(" ({0} już tam było)").format(len(already))
    return text, short


class AlbumChoiceRow(Gtk.ListBoxRow):
    def __init__(self, name, album, recent):
        super().__init__()
        self.name, self.album, self.recent = name, album, recent
        box = Gtk.Box(spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(6)
        box.append(Gtk.Image.new_from_icon_name("folder-pictures-symbolic"))
        lbl = Gtk.Label(label=name, xalign=0, hexpand=True)
        lbl.set_ellipsize(3)
        box.append(lbl)
        if recent:
            tag = Gtk.Label(label=tr("ostatnio"))
            tag.add_css_class("dim-label")
            box.append(tag)
        self.set_child(box)


class AddToAlbumDialog(Gtk.Window):
    """Dodaje zdjęcia do wybranego albumu: wyszukiwarka + lista (ostatnio używane na górze)."""

    def __init__(self, win, assets):
        super().__init__(transient_for=win, modal=True, title=tr("Dodaj do albumu"))
        self.win, self.assets = win, assets
        self.set_default_size(420, 520)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(18)
        box.append(Gtk.Label(label=tr("Zdjęcia do dodania: {0}").format(len(assets)), xalign=0))
        self.search = Gtk.SearchEntry(placeholder_text=tr("Szukaj albumu…"))
        self.search.connect("search-changed", lambda *_: self.list.invalidate_filter())
        self.search.connect("activate", self._on_enter)
        box.append(self.search)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_min_content_height(240)
        self.list = Gtk.ListBox()
        self.list.add_css_class("boxed-list")
        self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list.set_filter_func(self._filter)
        self.list.connect("row-selected", lambda lb, row: self.go.set_sensitive(row is not None))
        self.list.connect("row-activated", lambda lb, row: self._go())
        names = dict(win.user_albums)
        recents = [n for n in win.recent_albums if n in names]
        rest = sorted((n for n in names if n not in recents), key=str.lower)
        self.rows = [AlbumChoiceRow(n, names[n], n in recents) for n in recents + rest]
        for r in self.rows:
            self.list.append(r)
        sw.set_child(self.list)
        box.append(sw)
        self.status = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.append(self.status)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.cancel = Gtk.Button(label=tr("Anuluj"))
        self.cancel.connect("clicked", lambda *_: self.close())
        self.go = Gtk.Button(label=tr("Dodaj"))
        self.go.add_css_class("suggested-action")
        self.go.set_sensitive(False)
        self.go.connect("clicked", lambda *_: self._go())
        row.append(self.cancel)
        row.append(self.go)
        box.append(row)
        self.set_child(box)
        self.connect("map", lambda *_: self.search.grab_focus())

    def _filter(self, row):
        q = self.search.get_text().strip().lower() if hasattr(self, "search") else ""
        return not q or q in row.name.lower()

    def _on_enter(self, *_):
        """Enter: zaznacz pierwszy pasujący album; drugi Enter dodaje."""
        vis = [r for r in self.rows if self._filter(r)]
        if not vis:
            return
        if self.list.get_selected_row() is vis[0]:
            self._go()
        else:
            self.list.select_row(vis[0])

    def _go(self):
        row = self.list.get_selected_row()
        if row is None or not self.go.get_sensitive():
            return
        self.go.set_sensitive(False)
        self.list.set_sensitive(False)
        self.search.set_sensitive(False)
        self.status.set_text(tr("Sprawdzam, czy zdjęcia już są w albumie…"))

        def progress(k, n):
            GLib.idle_add(lambda: (self.status.set_text(tr("Dodawanie {0}/{1}…").format(k, n)), False)[1])

        def finished(text):
            self.status.set_text(text)
            self.cancel.set_label(tr("Zamknij"))

        self.win.add_to_album_async(self.assets, row.name, row.album, progress, finished)


class PairingDialog(Gtk.Window):
    """Parowanie z odbiornikiem AirPlay (Apple TV): kod PIN pojawia się na ekranie telewizora."""

    def __init__(self, win, target, on_done):
        super().__init__(transient_for=win, modal=True, title=tr("Parowanie: {0}").format(target.name))
        self.win, self.target, self.on_done = win, target, on_done
        self.set_default_size(380, -1)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(18)
        box.append(Gtk.Label(label=tr("Na ekranie telewizora pojawi się kod PIN.\nWpisz go poniżej."),
                             xalign=0, wrap=True))
        self.entry = Gtk.Entry(placeholder_text="PIN", max_length=8)
        self.entry.set_sensitive(False)
        self.entry.connect("activate", self._go)
        self.status = Gtk.Label(label=tr("Łączę z urządzeniem…"), xalign=0, wrap=True,
                                selectable=True)
        self.status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr("Anuluj"))
        cancel.connect("clicked", lambda *_: self.close())
        self.go_btn = Gtk.Button(label=tr("Sparuj"))
        self.go_btn.add_css_class("suggested-action")
        self.go_btn.set_sensitive(False)
        self.go_btn.connect("clicked", self._go)
        row.append(cancel)
        row.append(self.go_btn)
        for w in (self.entry, self.status, row):
            box.append(w)
        self.set_child(box)
        bg(target.pair_begin, self._started)

    def _started(self, shows_pin, err):
        if err:
            log.error("AirPlay pair_begin: %r", err)
            self.status.set_text(tr("Nie udało się rozpocząć parowania: {0}").format(err))
            return
        self.status.set_text(tr("Wpisz PIN z ekranu TV.") if shows_pin
                             else tr("Urządzenie nie pokazuje PIN-u - wpisz kod, którego oczekuje."))
        self.entry.set_sensitive(True)
        self.go_btn.set_sensitive(True)
        self.entry.grab_focus()

    def _go(self, *_):
        pin = self.entry.get_text().strip()
        if not pin:
            return
        self.go_btn.set_sensitive(False)
        self.status.set_text(tr("Parowanie…"))
        bg(lambda: self.target.pair_finish(pin), self._finished)

    def _finished(self, ok, err):
        if err or not ok:
            log.error("AirPlay pair_finish: %r", err)
            self.status.set_text(tr("Zły PIN albo błąd parowania: {0}").format(err or ''))
            self.go_btn.set_sensitive(True)
            return
        self.close()
        self.on_done()


class AlbumRow(Gtk.ListBoxRow):
    def __init__(self, title, icon, album, key=None, cover=False, static=False, bold=False):
        super().__init__()
        self.album = album
        self.title = title
        self.key = key or title
        self.thumb = None
        box = Gtk.Box(spacing=10)
        box.set_margin_top(5 if cover else 6)
        box.set_margin_bottom(5 if cover else 6)
        box.set_margin_start(8)
        box.set_margin_end(8)
        self.icon = Gtk.Image.new_from_icon_name(icon)
        if cover:  # kafelek 40x40: okładka albumu albo (static) duża ikona
            self.thumb = Gtk.Image()
            self.thumb.set_pixel_size(40)
            ov = Gtk.Overlay()
            self.cover_box = ov
            ov.set_child(self.thumb)
            ov.set_size_request(40, 40)
            ov.set_halign(Gtk.Align.START)
            ov.set_valign(Gtk.Align.CENTER)
            ov.set_hexpand(False)
            ov.add_css_class("albumcover")
            ov.set_overflow(Gtk.Overflow.HIDDEN)
            self.icon.set_halign(Gtk.Align.CENTER)
            self.icon.set_valign(Gtk.Align.CENTER)
            if static:
                self.icon.set_pixel_size(26)
                self.thumb = None  # nigdy nie podmieniaj ikony na zdjęcie
            ov.add_overlay(self.icon)
            box.append(ov)
        else:
            box.append(self.icon)
        lbl = Gtk.Label(label=title, xalign=0, hexpand=True)
        lbl.set_ellipsize(3)  # END
        if bold:
            lbl.add_css_class("heading")
        self.lbl = lbl
        box.append(lbl)
        self.set_child(box)

    def set_cover(self, tex):
        if self.thumb is not None:
            self.thumb.set_from_paintable(tex)
            self.icon.set_visible(False)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, icloud=None, autologin=True):
        super().__init__(application=app, title="Linux iCloud Photos")
        self.set_default_size(1200, 780)
        self.icloud = icloud or ICloud()
        # wygasły link do pliku (410) -> odśwież bibliotekę; poza tym zapobiegawczo co 45 minut
        self.icloud.on_links_stale = lambda: GLib.idle_add(self._links_stale)
        GLib.timeout_add_seconds(45 * 60, self._periodic_link_refresh)
        self.tex = TexCache()
        self.store = Gio.ListStore(item_type=PhotoObj)
        self.pending_2fa = False
        self.gen = 0
        self.total = None
        self._pick_busy = False
        self._pick_warn_ts = 0.0
        cfg = load_cfg()
        self.tile_size = max(TILE_MIN, min(TILE_MAX, int(cfg.get("tile", TILE_DEFAULT))))
        self.tiles = weakref.WeakSet()
        self._tguard = False
        self.newest_first = bool(cfg.get("newest_first", True))
        self.flips = {}            # tytuł albumu -> czy odwrócić założony kierunek
        self.cur_album = None
        self.cur_title = ""
        self.it = None
        self.exhausted = True
        self.loading = False
        self._auto_fixed = False
        self.cast_target = None
        self.last_obj = None
        self.fit_original = bool(cfg.get("fit_original", False))
        self.layout_mode = cfg.get("layout", "grid")
        self._rows_dirty = True
        self._rows_src = 0
        self._rows_W = 0
        self._rows_n = 0
        self._rows_watching = False
        self._expired = False
        self._probing = False
        self._jump_q = None
        self.select_mode = False
        self.selected = []
        self._rb = None
        self.cache_gb = float(cfg.get("cache_gb", 1.0))
        self._version_warned = False
        self._refreshing = False
        self._keep_key = None  # album do ponownego zaznaczenia po odświeżeniu listy albumów
        self._pending_open = None  # prośba z innej aplikacji (--open-album / --open-date)
        self._albums_ready = False
        self.recent_albums = list(cfg.get("recent_albums", []))
        self.glass = max(0, min(100, int(cfg.get("glass", 0) or 0)))
        self.viewers = weakref.WeakSet()  # wszystkie otwarte podglądy zdjęć
        self.video_player = cfg.get("video_player", "auto")
        _AUTH_HOOK[0] = self.on_auth_error
        self._rebuild_src = 0
        self._split_src = 0
        self._pguard = False
        self._last_cast_err = ("", 0.0)
        self.user_albums = []
        self.slide_secs = int(cfg.get("slide_secs", 5))
        self._cast_lock = threading.Lock()
        self.embedded_video = (os.environ.get("ICLOUD_PHOTOS_EMBEDDED_VIDEO") == "1"
                               or bool(cfg.get("embedded_video", False)))

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.header = Adw.HeaderBar()
        self.wtitle = Adw.WindowTitle(title="Linux iCloud Photos", subtitle="")
        self.header.set_title_widget(self.wtitle)
        self.sidebar_btn = Gtk.ToggleButton(icon_name="sidebar-show-symbolic")
        self.sidebar_btn.set_visible(False)
        self.header.pack_start(self.sidebar_btn)
        self.count = Gtk.Label()
        self.header.pack_end(self.count)

        # zoom miniatur: − [suwak] +
        self.zoom_box = Gtk.Box(spacing=2)
        b_out = Gtk.Button(icon_name="zoom-out-symbolic")
        b_out.add_css_class("flat")
        b_out.set_tooltip_text(tr("Mniejsze miniatury (Ctrl −)"))
        b_out.connect("clicked", lambda *_: self.set_tile_size(self.tile_size - 20))
        self.tile_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, TILE_MIN, TILE_MAX, 10)
        self.tile_scale.set_draw_value(False)
        self.tile_scale.set_size_request(130, -1)
        self.tile_scale.set_value(self.tile_size)
        self.tile_scale.connect("value-changed", self._on_tile_scale)
        b_in = Gtk.Button(icon_name="zoom-in-symbolic")
        b_in.add_css_class("flat")
        b_in.set_tooltip_text(tr("Większe miniatury (Ctrl +)"))
        b_in.connect("clicked", lambda *_: self.set_tile_size(self.tile_size + 20))
        for w in (b_out, self.tile_scale, b_in):
            self.zoom_box.append(w)
        self.header.pack_end(self.zoom_box)

        # tryby widoku siatki (jak w Google Photos): małe / standardowe / duże / bardzo duże
        self.view_btn = Gtk.MenuButton(icon_name="view-grid-symbolic")
        self.view_btn.set_tooltip_text(tr("Widok siatki"))
        vpop = Gtk.Popover()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for m in ("top", "bottom", "start", "end"):
            getattr(vbox, f"set_margin_{m}")(8)
        self.presets = []
        first = None
        for label, size in PRESETS:
            cb = Gtk.CheckButton(label=f"{label}")
            if first is None:
                first = cb
            else:
                cb.set_group(first)
            cb.connect("toggled", lambda b, size=size: b.get_active()
                       and not self._pguard and self.set_tile_size(size))
            vbox.append(cb)
            self.presets.append((cb, size))
        vbox.append(Gtk.Separator())
        lay_head = Gtk.Label(label=tr("Układ"), xalign=0)
        lay_head.add_css_class("heading")
        vbox.append(lay_head)
        self.layout_grid = Gtk.CheckButton(label=tr("Kafelki (kwadraty)"))
        self.layout_rows = Gtk.CheckButton(label=tr("Rzędy (jak w Google Photos)"))
        self.layout_rows.set_group(self.layout_grid)
        self.layout_rows.set_active(self.layout_mode == "rows")
        self.layout_grid.set_active(self.layout_mode != "rows")
        self.layout_rows.connect("toggled", lambda b: self._on_layout_toggled(b.get_active()))
        vbox.append(self.layout_grid)
        vbox.append(self.layout_rows)
        vbox.append(Gtk.Separator())
        self.fit_check = Gtk.CheckButton(label=tr("Oryginalne proporcje (bez przycinania)"))
        self.fit_check.set_active(self.fit_original)
        self.fit_check.connect("toggled", self._on_fit_toggled)
        vbox.append(self.fit_check)
        vpop.set_child(vbox)
        self.view_btn.set_popover(vpop)
        self.header.pack_end(self.view_btn)
        self._sync_presets()

        # sortowanie, dodawanie plików, PLAY (pokaz slajdów), wysyłka na TV
        self.sort_btn = Gtk.Button()
        self.sort_btn.add_css_class("flat")
        self.sort_btn.connect("clicked", self._toggle_sort)
        self._update_sort_btn()
        self.add_btn = Gtk.Button(icon_name="list-add-symbolic")
        self.add_btn.set_tooltip_text(
            tr("Dodaj zdjęcia do iCloud (możesz też przeciągnąć pliki do okna)"))
        self.add_btn.connect("clicked", self._choose_files)
        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text(tr("Odśwież bibliotekę (F5)"))
        self.refresh_btn.connect("clicked", lambda *_: self.refresh_library())
        self.info_btn = Gtk.Button(icon_name="dialog-information-symbolic")
        self.info_btn.add_css_class("flat")
        self.info_btn.set_tooltip_text(
            tr("Informacje o zdjęciu (ostatnio otwartym lub klikniętym prawym przyciskiem)"))
        self.info_btn.connect("clicked", self._info_clicked)
        self.jump_btn = self._build_jump_button()
        self.select_btn = Gtk.ToggleButton(icon_name="object-select-symbolic")
        self.select_btn.add_css_class("flat")
        self.select_btn.set_tooltip_text(tr("Zaznaczanie wielu zdjęć (Ctrl+klik)"))
        self.select_btn.connect("toggled", lambda b: self.set_select_mode(b.get_active()))
        self.settings_btn = Gtk.Button(icon_name="preferences-system-symbolic")
        self.settings_btn.add_css_class("flat")
        self.settings_btn.set_tooltip_text(tr("Ustawienia"))
        self.settings_btn.connect("clicked", lambda *_: SettingsDialog(self).present())
        for b in (self.refresh_btn, self.sort_btn, self.add_btn, self.info_btn, self.jump_btn,
                  self.select_btn):
            self.header.pack_start(b)
        self.header.pack_end(self.settings_btn)
        self._build_cast()
        self.header.pack_end(self.cast_btn)
        self.logged_widgets = [self.zoom_box, self.view_btn, self.refresh_btn, self.sort_btn, self.add_btn,
                               self.info_btn, self.cast_btn, self.jump_btn,
                               self.select_btn]
        for w in self.logged_widgets:
            w.set_visible(False)
        box.append(self.header)

        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.add_named(self._build_login(), "login")
        self.stack.add_named(self._build_main(), "main")
        self.store.connect("items-changed", self._on_store_changed)
        self._apply_layout(self.layout_mode)
        box.append(self.stack)
        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(box)
        self.backdrop = Backdrop()
        root = Gtk.Overlay()
        root.set_child(self.backdrop)
        root.add_overlay(self.toasts)
        root.set_measure_overlay(self.toasts, True)
        self.set_content(root)
        self._glass_provider = None
        self.set_glass(self.glass)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        dt = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        dt.connect("drop", self._on_drop)
        self.add_controller(dt)

        if autologin:
            self._autologin()

    # --- logowanie ---
    def _build_login(self):
        clamp = Adw.Clamp(maximum_size=380)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        v.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=tr("Zaloguj się do iCloud"))
        title.add_css_class("title-2")
        self.e_id = Gtk.Entry(placeholder_text=tr("Apple ID (e-mail)"))
        self.e_pw = Gtk.PasswordEntry(placeholder_text=tr("Hasło"), show_peek_icon=True)
        self.e_code = Gtk.Entry(placeholder_text=tr("Kod 2FA (6 cyfr)"))
        self.e_code.set_visible(False)
        self.btn = Gtk.Button(label=tr("Zaloguj"))
        self.btn.add_css_class("suggested-action")
        self.status = Gtk.Label(wrap=True, xalign=0, selectable=True)
        self.status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.btn_copy = Gtk.Button(label=tr("Kopiuj błąd"))
        self.btn_copy.set_visible(False)
        self.btn_copy.connect("clicked", self._copy_status)
        for w in (title, self.e_id, self.e_pw, self.e_code, self.btn, self.status,
                  self.btn_copy):
            v.append(w)
        self.btn.connect("clicked", self.on_login)
        self.e_pw.connect("activate", self.on_login)
        self.e_code.connect("activate", self.on_login)
        clamp.set_child(v)
        # version, date and year at the bottom of the login screen
        clamp.set_vexpand(True)
        ver = Gtk.Label(label=f"v{VERSION}  ·  {DATE}\n{CREDITS}", justify=Gtk.Justification.CENTER)
        ver.add_css_class("dim-label")
        ver.add_css_class("caption")
        ver.set_margin_bottom(12)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(clamp)
        outer.append(ver)
        return outer

    def _autologin(self):
        apple_id = None
        try:
            apple_id = json.loads(CONFIG_FILE.read_text()).get("apple_id")
        except Exception:  # noqa: BLE001
            pass
        pw = None
        if apple_id and keyring:
            try:
                pw = keyring.get_password(KEYRING_SERVICE, apple_id)
                if not pw:  # hasło zapisane przed zmianą nazwy aplikacji: użyj go i przepisz pod nową nazwą
                    pw = keyring.get_password(OLD_KEYRING_SERVICE, apple_id)
                    if pw:
                        keyring.set_password(KEYRING_SERVICE, apple_id, pw)
            except Exception:  # noqa: BLE001
                pass
        if apple_id:
            self.e_id.set_text(apple_id)
        self.stack.set_visible_child_name("login")
        if apple_id and pw:
            self.e_pw.set_text(pw)
            self.say(tr("Sesja wygasła - loguję ponownie…") if self._expired
                     else tr("Logowanie z zapisanej sesji…"))
            bg(lambda: self.icloud.login(apple_id, pw), self._after_login)

    def say(self, text, error=False):
        """Komunikat na ekranie logowania; błędy można zaznaczyć i skopiować."""
        self.status.set_text(text)
        self.btn_copy.set_visible(error)

    def _copy_status(self, *_):
        self.get_clipboard().set(self.status.get_text())
        self.btn_copy.set_label(tr("Skopiowano ✓"))
        GLib.timeout_add_seconds(2, lambda: (self.btn_copy.set_label(tr("Kopiuj błąd")), False)[1])

    @staticmethod
    def _describe(err):
        text = f"{type(err).__name__}: {err}"
        if "503" in text:
            text += (tr("\n\nApple chwilowo odrzuca logowanie (503 Service Temporarily "
                     "Unavailable). Odczekaj kilkanaście minut i spróbuj raz - "
                     "wielokrotne próby mogą wydłużyć blokadę."))
        return text

    def on_login(self, *_):
        self.btn.set_sensitive(False)
        if self.pending_2fa:
            code = self.e_code.get_text()
            self.say(tr("Weryfikacja kodu…"))
            bg(lambda: self.icloud.verify_2fa(code), self._after_2fa)
            return
        aid, pw = self.e_id.get_text().strip(), self.e_pw.get_text()
        if not aid or not pw:
            self.say(tr("Podaj Apple ID i hasło."))
            self.btn.set_sensitive(True)
            return
        self.say(tr("Logowanie…"))
        bg(lambda: self.icloud.login(aid, pw), self._after_login)

    def _after_login(self, state, err):
        self.btn.set_sensitive(True)
        if err:
            self.say(tr("Błąd logowania: ") + self._describe(err), True)
        elif state == "2fa":
            self.pending_2fa = True
            self.e_code.set_visible(True)
            self.e_code.grab_focus()
            self.say((tr("Sesja wygasła. ") if self._expired else "")
                     + tr("Wpisz kod z zaufanego urządzenia Apple."))
        else:
            self.logged_in()

    def _after_2fa(self, ok, err):
        self.btn.set_sensitive(True)
        if err or not ok:
            self.say(tr("Błąd: zły kod albo problem z weryfikacją: ") + (self._describe(err) if err else ""), True)
        else:
            self.pending_2fa = False
            self.logged_in()

    def logged_in(self, save=True):
        aid, pw = self.e_id.get_text().strip(), self.e_pw.get_text()
        if save and aid:
            save_cfg(apple_id=aid)
            try:
                if keyring and pw:
                    keyring.set_password(KEYRING_SERVICE, aid, pw)
            except Exception:  # noqa: BLE001
                pass
        self.e_pw.set_text("")
        self._expired = False
        pv = pyicloud_version()
        if pv and pv != TESTED_PYICLOUD and not self._version_warned:
            self._version_warned = True
            self.toast(tr("Zainstalowana wersja pyicloud ({0}) różni się od przetestowanej ({1}). Jeśli coś nie działa, zainstaluj przetestowaną.").format(pv, TESTED_PYICLOUD))
        self._clear_albums()
        for w in self.logged_widgets:
            w.set_visible(True)
        self.stack.set_visible_child_name("main")
        self.sidebar_btn.set_visible(True)
        self.say("")
        if PICK is not None:
            self._enter_pick_mode()
        bg(self.icloud.albums, self._albums_loaded)

    # --- główny widok: menu albumów + siatka ---
    @staticmethod
    def _bold_label(text):
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class("heading")
        return lbl

    def _make_list(self):
        lb = Gtk.ListBox()
        lb.add_css_class("navigation-sidebar")
        lb.set_filter_func(self._row_filter)
        lb.connect("row-selected", self._on_album_selected)
        self.lists.append(lb)
        return lb

    def _build_main(self):
        self.lists = []
        self._busy = False
        # Gtk.Paned: separator, który można przeciągać (szerokość menu jest zapamiętywana)
        self.split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.split.set_wide_handle(True)
        self.split.set_resize_start_child(False)
        self.split.set_shrink_start_child(False)
        self.split.set_resize_end_child(True)
        self.split.set_shrink_end_child(False)
        self.split.set_position(int(load_cfg().get("sidebar_w", 270)))
        self.split.connect("notify::position", self._on_split_pos)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.search = Gtk.SearchEntry(placeholder_text=tr("Szukaj albumu"))
        self.search.set_margin_start(8)
        self.search.set_margin_end(8)
        self.search.set_margin_top(8)
        self.search.connect("search-changed", self._on_search)
        self.search.connect("activate", lambda *_: self._jump_from_query())
        side.append(self.search)

        self.list_jump = self._make_list()
        self.jump_row = AlbumRow(tr("Przejdź do daty"), "x-office-calendar-symbolic", None,
                                 key="__jump__", bold=True)
        self.list_jump.append(self.jump_row)
        self.list_jump.set_visible(False)
        side.append(self.list_jump)
        self.list_primary = self._make_list()
        side.append(self.list_primary)
        self.list_more = self._make_list()
        self.exp_more = Gtk.Expander()
        self.exp_more.set_label_widget(self._bold_label(tr("Typy mediów")))
        self.exp_more.set_child(self.list_more)
        self.exp_more.set_margin_start(8)
        self.exp_more.set_visible(False)
        side.append(self.exp_more)
        self.list_user = self._make_list()
        self.exp_user = Gtk.Expander()
        self.exp_user_lbl = self._bold_label(tr("Moje albumy"))
        self.exp_user.set_label_widget(self.exp_user_lbl)
        self.exp_user.set_child(self.list_user)
        self.exp_user.set_margin_start(8)
        self.exp_user.set_visible(False)
        side.append(self.exp_user)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(side)
        scroller.set_vexpand(True)
        side_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side_col.set_size_request(170, -1)
        side_col.append(scroller)
        ver = Gtk.Label(label=f"v{VERSION}  ·  {DATE}\n{CREDITS}", xalign=0)
        ver.add_css_class("dim-label")
        ver.add_css_class("caption")
        for m in ("start", "end", "top", "bottom"):
            getattr(ver, f"set_margin_{m}")(8)
        side_col.append(ver)
        self.sidebar_scroller = side_col
        side_col.add_css_class("text-panel")  # w trybie przezroczystości: panel z tekstem, mocno kryjący
        self.split.set_start_child(side_col)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        grid_sw = self._build_grid()
        self.rubber = Gtk.Box()
        self.rubber.add_css_class("rubberband")
        self.rubber.set_halign(Gtk.Align.START)
        self.rubber.set_valign(Gtk.Align.START)
        self.rubber.set_can_target(False)
        self.rubber.set_visible(False)
        grid_ov = Gtk.Overlay()
        grid_ov.set_vexpand(True)
        grid_ov.set_child(grid_sw)
        grid_ov.add_overlay(self.rubber)
        self._install_rubberband(grid_sw)
        right.append(grid_ov)
        right.append(self._build_selection_bar())
        self.split.set_end_child(right)
        side_col.bind_property(
            "visible", self.sidebar_btn, "active",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        return self.split

    def _on_split_pos(self, *_):
        if self._split_src:
            GLib.source_remove(self._split_src)

        def save():
            self._split_src = 0
            if self.sidebar_scroller.get_visible():
                save_cfg(sidebar_w=self.split.get_position())
            return False

        self._split_src = GLib.timeout_add(600, save)

    def _row_filter(self, row):
        if row.key == "__jump__":
            return True
        q = self.search.get_text().strip().lower() if hasattr(self, "search") else ""
        return not q or q in row.title.lower()

    def _on_search(self, entry):
        self._jump_q = parse_date_query(entry.get_text())
        self.list_jump.set_visible(self._jump_q is not None)
        if self._jump_q:
            self.jump_row.lbl.set_text(tr("Przejdź do: {0}").format(self._jump_q[2]))
        for lb in self.lists:
            lb.invalidate_filter()
        if entry.get_text().strip():
            self.exp_more.set_expanded(True)
            self.exp_user.set_expanded(True)

    def _albums_loaded(self, albums, err):
        if err:
            self.count.set_text(tr("Błąd albumów: {0}").format(err))
            return
        by_name = dict(albums)
        cover_rows = []
        for key in PRIMARY:
            if key in by_name:
                title, icon = SMART_PL[key]
                static = key in ("Favorites", "Videos")  # gwiazdka / kamera zamiast zdjęcia
                row = AlbumRow(title, icon, by_name[key], key=key, cover=True,
                               static=static, bold=(key == "All Photos"))
                self.list_primary.append(row)
                if not static:
                    cover_rows.append(row)
        more = [k for k in MORE_ORDER if k in by_name]
        for key in more:
            title, icon = SMART_PL[key]
            self.list_more.append(AlbumRow(title, icon, by_name[key], key=key))
        self.exp_more.set_visible(bool(more))
        users = sorted(((n, a) for n, a in albums if n not in SMART_PL),
                       key=lambda t: t[0].lower())
        self.user_albums = users
        for name, album in users:
            row = AlbumRow(name, "folder-pictures-symbolic", album, key=name, cover=True)
            self.list_user.append(row)
            cover_rows.append(row)
        self.exp_user_lbl.set_text(tr("Moje albumy ({0})").format(len(users)))
        self.exp_user.set_visible(bool(users))
        keep, self._keep_key = self._keep_key, None
        target = self._find_row(keep) if keep else None
        first = target or self.list_primary.get_row_at_index(0)
        if first:
            first.get_parent().select_row(first)
        self._albums_ready = True
        if self._pending_open:
            GLib.idle_add(self._apply_open)
        GLib.timeout_add_seconds(2, lambda: (self._load_covers(cover_rows), False)[1])

    # --- prośby innych aplikacji (linux-skytrack: album podróży, zdjęcia z dni podróży) ---
    def open_request(self, req):
        self._pending_open = req
        if self._albums_ready:
            self._apply_open()

    def _apply_open(self):
        req, self._pending_open = self._pending_open, None
        if not req:
            return False
        if "album" in req:
            name = req["album"]
            row = self._find_row(name)
            if row is None:
                # nowy album (np. utworzony przed chwilą przez SkyTrack): odśwież listę i spróbuj raz jeszcze
                if not req.get("retried"):
                    self._pending_open = dict(req, retried=True)
                    self._keep_key = name
                    self._albums_ready = False
                    self._refresh_library_for_open()
                else:
                    self.toast(tr("Nie znaleziono albumu „{0}”").format(name))
                return False
            if row.get_parent() is self.list_user:
                self.exp_user.set_expanded(True)
            row.get_parent().select_row(row)
            return False
        if "date" in req:
            a, _sep, b = req["date"].partition("..")
            first = parse_date_query(a)
            last = parse_date_query(b) if b else first
            if not first or not last:
                self.toast(tr("Nieczytelna data: {0}").format(req["date"]))
                return False
            row = self.list_primary.get_row_at_index(0)  # Wszystkie zdjęcia
            if row is not None:
                row.get_parent().select_row(row)
            label = first[2] if not b else f"{first[2]} – {last[2]}"
            self._do_jump(first[0], last[1], label)
        return False

    def _refresh_library_for_open(self):
        def done(albums, err):
            if err:
                self._albums_ready = True
                self._pending_open = None
                self.toast(tr("Nie udało się odświeżyć: {0}").format(err))
                return
            self._clear_albums()
            self._albums_loaded(albums, None)

        bg(lambda: (self.icloud.refresh_library(), self.icloud.albums())[1], done)

    def _load_covers(self, rows):
        def work(row):
            last = None
            for k in range(3):  # chwilowe błędy / limity Apple - ponów z odstępem
                try:
                    return make_square_texture(self.icloud.album_cover(row.key, row.album))
                except LookupError:
                    raise
                except Exception as e:  # noqa: BLE001
                    last = e
                    time.sleep(2 * (k + 1))
            raise last

        for row in rows:
            fut = COVER_POOL.submit(work, row)

            def done(f, row=row):
                if f.cancelled():
                    return
                if f.exception():
                    log.warning("okładka albumu %r: %r", row.title, f.exception())
                    return
                GLib.idle_add(lambda: (row.set_cover(f.result()), False)[1])

            fut.add_done_callback(done)

    def _on_album_selected(self, lb, row):
        if row is None or self._busy:
            return
        if row.key == "__jump__":
            self._busy = True
            lb.unselect_all()
            self._busy = False
            self._jump_from_query()
            return
        self._busy = True  # tylko jedna zaznaczona pozycja w całym menu
        for other in self.lists:
            if other is not lb:
                other.unselect_all()
        self._busy = False
        self.wtitle.set_title(row.title)
        self.cur_title = row.title
        self.load_album(row.album)
        for ms in (1500, 5000):  # tło przezroczystości: po załadowaniu pierwszych miniatur
            GLib.timeout_add(ms, self._update_backdrop)

    def _build_grid(self):
        self.grid_view = Gtk.GridView(model=Gtk.NoSelection(model=self.store),
                                      factory=self._make_factory())
        self.grid_view.set_single_click_activate(True)
        self.grid_view.set_min_columns(2)
        self.grid_view.set_max_columns(24)
        self.grid_view.connect("activate", self._on_activate)
        self.rows_store = Gio.ListStore(item_type=RowObj)
        self.rows_view = Gtk.ListView(model=Gtk.NoSelection(model=self.rows_store),
                                      factory=self._make_rows_factory())
        self.rows_view.set_show_separators(False)
        self.grid = self.grid_view  # aktualnie pokazywany widok (używa go zaznaczanie ramką)
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self.grid_view)
        sc = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        sc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        sc.connect("scroll", self._on_grid_scroll)
        sw.add_controller(sc)
        self.grid_sw = sw
        adj = sw.get_vadjustment()
        adj.connect("value-changed", lambda *_: self._maybe_more())
        adj.connect("changed", lambda *_: self._maybe_more())
        return sw

    def _make_factory(self):
        f = Gtk.SignalListItemFactory()
        f.connect("setup", lambda _f, li: li.set_child(self._new_tile()))
        f.connect("bind", self._bind)
        f.connect("unbind", self._unbind)
        return f

    def _new_tile(self):
        t = Tile(self.tile_size)
        t.set_fit(self.fit_original)
        t.on_context = self._tile_context
        self.tiles.add(t)
        return t

    def _on_fit_toggled(self, cb):
        self.fit_original = cb.get_active()
        save_cfg(fit_original=self.fit_original)
        if self.layout_mode == "rows":
            return  # w układzie rzędów proporcje i tak są oryginalne
        for t in list(self.tiles):
            t.set_fit(self.fit_original)

    # --- układ rzędów (jak w Google Photos) ---
    def _make_rows_factory(self):
        f = Gtk.SignalListItemFactory()
        f.connect("setup", lambda _f, li: li.set_child(RowBox()))
        f.connect("bind", self._bind_row)
        f.connect("unbind", self._unbind_row)
        return f

    def _bind_row(self, _f, li):
        row, box = li.get_item(), li.get_child()
        n = len(row.items)
        while len(box.tiles) < n:
            t = self._new_tile()
            t.set_fit(False)
            t.on_activate = self._tile_activate
            box.append(t)
            box.tiles.append(t)
        while len(box.tiles) > n:
            t = box.tiles.pop()
            self._unbind_tile(t)
            box.remove(t)
        for t, obj, w in zip(box.tiles, row.items, row.widths):
            t.set_dims(w, row.h)
            self._bind_tile(t, obj)

    def _unbind_row(self, _f, li):
        for t in li.get_child().tiles:
            self._unbind_tile(t)

    def _tile_activate(self, tile):
        if tile.bound is None:
            return
        found, pos = self.store.find(tile.bound)
        if found:
            self._on_activate(None, pos)

    def _on_layout_toggled(self, rows_active):
        mode = "rows" if rows_active else "grid"
        if mode != self.layout_mode:
            save_cfg(layout=mode)
            self._apply_layout(mode)

    def _apply_layout(self, mode):
        self.layout_mode = mode
        if hasattr(self, "fit_check"):
            self.fit_check.set_sensitive(mode != "rows")
        if mode == "rows":
            self.grid = self.rows_view
            self.grid_sw.set_child(self.rows_view)
            self._rows_dirty = True
            self._rows_schedule(30)
            if not self._rows_watching:
                self._rows_watching = True
                GLib.timeout_add(300, self._rows_watch)
        else:
            self.grid = self.grid_view
            self.grid_sw.set_child(self.grid_view)
            for t in list(self.tiles):
                t.set_size(self.tile_size)
                t.set_fit(self.fit_original)

    def _rows_watch(self):
        """Pilnuje szerokości okna: po zmianie przelicza rzędy."""
        if self.layout_mode != "rows":
            self._rows_watching = False
            return False
        w = self.grid_sw.get_width()
        if w > 0 and abs(w - 14 - self._rows_W) > 6:
            self._rows_mark_dirty(150)
        return True

    def _rows_mark_dirty(self, delay=100):
        self._rows_dirty = True
        self._rows_schedule(delay)

    def _rows_schedule(self, delay=80):
        if self.layout_mode == "rows" and not self._rows_src:
            self._rows_src = GLib.timeout_add(delay, self._rows_sync)

    def _on_store_changed(self, store, pos, removed, added):
        if self.layout_mode != "rows":
            return
        if removed:
            self._rows_dirty = True
        self._rows_schedule(60)

    def _rows_sync(self):
        self._rows_src = 0
        if self.layout_mode != "rows":
            return False
        W = max(0, self.grid_sw.get_width() - 14)
        if W <= 0:
            self._rows_schedule(150)
            return False
        n = self.store.get_n_items()
        full = self._rows_dirty or abs(W - self._rows_W) > 6 or n < self._rows_n
        adj = self.grid_sw.get_vadjustment()
        ratio = adj.get_value() / max(1.0, adj.get_upper()) if adj.get_value() > 1 else 0.0
        if full:
            self.rows_store.remove_all()
            start = 0
        else:
            k = self.rows_store.get_n_items()
            start = 0
            if k:  # ostatni rząd mógł być niepełny - policz od niego
                start = self.rows_store.get_item(k - 1).start
                self.rows_store.splice(k - 1, 1, [])
        items = [self.store.get_item(i) for i in range(start, n)]
        rows = justify_rows([o.aspect for o in items], W, self.tile_size, ROW_GAP)
        objs = [RowObj(start + s, items[s:s + c], h, widths) for (s, c, h, widths) in rows]
        self.rows_store.splice(self.rows_store.get_n_items(), 0, objs)
        self._rows_n, self._rows_W, self._rows_dirty = n, W, False
        GLib.timeout_add(250, self._maybe_more)
        if full and ratio > 0:  # wróć mniej więcej w to samo miejsce po zmianie układu
            GLib.timeout_add(150, lambda: (adj.set_value(ratio * adj.get_upper()), False)[1])
        return False

    def _rebuild_grid(self):
        """Wymusza przeliczenie całej siatki (pewniejsze niż same size_request)."""
        self._rebuild_src = 0
        if self.layout_mode == "rows":
            self._rows_mark_dirty(0)
        else:
            self.grid_view.set_factory(self._make_factory())
        return False

    def _sync_presets(self):
        self._pguard = True
        for cb, size in self.presets:
            cb.set_active(size == self.tile_size)
        self._pguard = False

    def set_tile_size(self, n):
        n = int(max(TILE_MIN, min(TILE_MAX, n)))
        if n == self.tile_size:
            return
        self.tile_size = n
        if self.layout_mode != "rows":
            for t in list(self.tiles):
                t.set_size(n)
        self._tguard = True
        self.tile_scale.set_value(n)
        self._tguard = False
        save_cfg(tile=n)
        log.info("rozmiar miniatur: %s", n)
        self._sync_presets()
        if self._rebuild_src:
            GLib.source_remove(self._rebuild_src)
        self._rebuild_src = GLib.timeout_add(250, self._rebuild_grid)

    def _on_tile_scale(self, sc):
        if not self._tguard:
            self.set_tile_size(round(sc.get_value() / 10) * 10)

    def _on_grid_scroll(self, ctrl, _dx, dy):
        if ctrl.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            self.set_tile_size(self.tile_size + (-10 if dy > 0 else 10))
            return True
        return False

    def _bind(self, _f, li):
        self._bind_tile(li.get_child(), li.get_item())

    def _bind_tile(self, tile, obj):
        tile.bound = obj
        tile.check.set_visible(self.select_mode)
        tile.check.set_active(obj in self.selected)
        tile.ph.set_visible(False)
        tile.vbadge.set_visible(obj.is_video)
        tile.lbadge.set_visible(obj.is_live)
        tex = self.tex.get(obj.asset.id)
        if tex is not None:
            tile.pic.set_paintable(tex)
            return
        tile.pic.set_paintable(None)

        def work():
            return make_texture(self.icloud.fetch(obj.asset, "thumb"))

        fut = POOL.submit(work)
        tile.future = fut

        def done(f):
            if f.cancelled():
                return
            if f.exception():
                _auth_check(f.exception())
                GLib.idle_add(self._tile_failed, tile, obj)
                return
            GLib.idle_add(self._apply, tile, obj, f.result())

        fut.add_done_callback(done)

    def _apply(self, tile, obj, tex):
        self.tex.put(obj.asset.id, tex)
        real = tex.get_width() / max(1, tex.get_height())
        # korekta tylko przy zamienionej orientacji (pion/poziom); kwadratowe miniatury
        # nie mogą zepsuć układu, więc samo „inne proporcje” nie wystarcza
        if (self.layout_mode == "rows" and abs(real * obj.aspect - 1) < 0.1
                and abs(real / obj.aspect - 1) > 0.05):
            obj.aspect = real
            self._rows_mark_dirty(600)
        if tile.bound is obj:
            tile.ph.set_visible(False)
            tile.pic.set_paintable(tex)
        return False

    def _tile_failed(self, tile, obj):
        if tile.bound is obj:
            tile.ph.set_from_icon_name(
                "camera-video-symbolic" if obj.is_video else "image-missing-symbolic")
            tile.ph.set_visible(True)
        return False

    def _unbind(self, _f, li):
        self._unbind_tile(li.get_child())

    def _unbind_tile(self, tile):
        tile.bound = None
        if tile.future is not None:
            tile.future.cancel()
            tile.future = None
        tile.pic.set_paintable(None)

    def _on_activate(self, _grid, pos):
        obj = self.store.get_item(pos)
        if obj.is_video and self.cast_target is not None:
            self.cast_asset(obj.asset)
            return
        if obj.is_video and self.external_video_ok():
            self.play_external(obj)
            return
        self._viewer = Viewer(self, pos)
        self._viewer.present()

    # --- ładowanie albumu ---
    def load_album(self, album, _auto=False, jump=None):
        for v in list(self.viewers):  # lista się przeładuje - zamknij otwarte podglądy
            v.close()
        self.gen += 1
        gen = self.gen
        self.cur_album = album
        self.total = None
        self.exhausted = False
        self.loading = False
        self._auto_fixed = _auto or jump is not None
        flip = self.flips.get(self.cur_title, False)
        if jump is not None:
            self.it = self.icloud.iter_jump(album, jump, self.newest_first)
        else:
            self.it = self.icloud.iter_assets(album, self.newest_first, flip)
            self.wtitle.set_subtitle("")
        self.store.remove_all()
        self.selected = []
        self._refresh_selection()
        self.count.set_text(tr("Szukam daty…") if jump is not None else "…")
        bg(lambda: self.icloud.total(album), lambda t, e: self._set_total(gen, t))
        self._load_more(gen)

    def _set_total(self, gen, total):
        if gen == self.gen and total:
            self.total = total
            self._update_count()

    def load_more(self):
        self._load_more()

    def _load_more(self, gen=None):
        """Dociąga kolejną porcję (BATCH) zdjęć. Wołane przy przewijaniu."""
        gen = self.gen if gen is None else gen
        if self.loading or self.exhausted or gen != self.gen or self.it is None:
            return
        self.loading = True
        it = self.it

        def work():
            batch = []
            for asset in it:
                batch.append(PhotoObj(asset, self.icloud.is_video(asset),
                                      self.icloud.is_live(asset)))
                if len(batch) >= BATCH:
                    return batch, False
            return batch, True  # iterator się skończył

        def done(res, err):
            if gen != self.gen:
                return
            self.loading = False
            if err:
                self.exhausted = True
                log.error("lista albumu %r: %r", self.cur_title, err)
                self.count.set_text(tr("Błąd listy: {0}").format(err))
                return
            batch, finished = res
            if batch and self.store.get_n_items() == 0 and self._check_order(batch):
                return  # kolejność była odwrotna - album załadowany ponownie
            if batch:
                self.store.splice(self.store.get_n_items(), 0, batch)
            self.exhausted = finished
            self._update_count()
            GLib.timeout_add(200, self._maybe_more)

        bg(work, done)

    def _check_order(self, batch):
        """Sprawdza po datach pierwszej porcji, czy kolejność zgadza się z żądaniem.
        Jeśli nie - odwraca założenie dla tego albumu i ładuje go ponownie (raz)."""
        d0 = self.icloud.asset_date(batch[0].asset)
        d1 = self.icloud.asset_date(batch[-1].asset)
        log.info("album %r: newest_first=%s flip=%s pierwszy=%s ostatni_w_porcji=%s",
                 self.cur_title, self.newest_first, self.flips.get(self.cur_title, False),
                 d0, d1)
        if self._auto_fixed or len(batch) < 2 or not d0 or not d1 or d0 == d1:
            return False
        if (d0 > d1) != self.newest_first:
            self.flips[self.cur_title] = not self.flips.get(self.cur_title, False)
            log.warning("kolejność albumu %r odwrotna niż żądana - ładuję ponownie",
                        self.cur_title)
            self.load_album(self.cur_album, _auto=True)
            return True
        return False

    def _maybe_more(self, *_):
        if self.loading or self.exhausted or self.cur_album is None:
            return False
        if self.layout_mode == "rows" and (self._rows_dirty or self._rows_src
                                           or self._rows_n != self.store.get_n_items()):
            return False  # rzędy jeszcze się budują - wysokość listy nie jest wiarygodna
        adj = self.grid_sw.get_vadjustment()
        page, upper, val = adj.get_page_size(), adj.get_upper(), adj.get_value()
        if page > 0 and upper - (val + page) < 3 * page:
            self._load_more()
        return False

    def _update_count(self):
        n = self.store.get_n_items()
        if self.total:
            self.count.set_text(f"{n} / {self.total}")
        elif n:
            self.count.set_text(str(n))
        return False

    def _update_sort_btn(self):
        if self.newest_first:
            self.sort_btn.set_icon_name("view-sort-descending-symbolic")
            self.sort_btn.set_tooltip_text(tr("Kolejność: najnowsze najpierw (kliknij, aby odwrócić)"))
        else:
            self.sort_btn.set_icon_name("view-sort-ascending-symbolic")
            self.sort_btn.set_tooltip_text(tr("Kolejność: najstarsze najpierw (kliknij, aby odwrócić)"))

    def _toggle_sort(self, *_):
        self.newest_first = not self.newest_first
        save_cfg(newest_first=self.newest_first)
        self.flips.clear()
        self._update_sort_btn()
        if self.cur_album is not None:
            self.load_album(self.cur_album)

    # --- pokaz slajdów ---
    def _slideshow_from(self, obj):
        """Pokaz slajdów bieżącego albumu od wskazanego zdjęcia (menu prawego przycisku)."""
        found, pos = self.store.find(obj)
        if self.store.get_n_items() == 0:
            return
        Slideshow(self, pos if found else 0).present()

    # --- wysyłanie na TV (DLNA/UPnP) ---
    def _build_cast(self):
        self.cast_btn = Gtk.MenuButton(icon_name="video-display-symbolic")
        self.cast_btn.set_tooltip_text(tr("Wyślij na TV (DLNA/UPnP)"))
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        head = Gtk.Label(label=tr("Wyślij na TV (DLNA/UPnP)"), xalign=0)
        head.add_css_class("heading")
        self.cast_status = Gtk.Label(xalign=0, wrap=True)
        self.cast_status.set_max_width_chars(36)
        self.cast_list = Gtk.ListBox()
        self.cast_list.add_css_class("boxed-list")
        self.cast_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.cast_list.connect("row-activated", self._cast_pick)
        rescan = Gtk.Button(label=tr("Szukaj ponownie"))
        rescan.connect("clicked", lambda *_: self._cast_scan())
        stop = Gtk.Button(label=tr("Zatrzymaj wysyłanie"))
        stop.connect("clicked", self._cast_stop)
        note = Gtk.Label(label=tr("AirPlay: wideo po sparowaniu PIN-em; zdjęcia eksperymentalnie."),
                         xalign=0, wrap=True)
        note.set_max_width_chars(36)
        note.add_css_class("dim-label")
        for w in (head, self.cast_status, self.cast_list, rescan, stop, note):
            box.append(w)
        pop.set_child(box)
        self.cast_pop = pop
        pop.connect("show", lambda *_: self._cast_scan())
        self.cast_btn.set_popover(pop)

    def _cast_scan(self):
        self.cast_status.set_text(tr("Szukam telewizorów w sieci…"))
        child = self.cast_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.cast_list.remove(child)
            child = nxt

        def done(found, err):
            if err or not found:
                self.cast_status.set_text(
                    tr("Nie znaleziono urządzeń DLNA w tej sieci. Upewnij się, że TV jest "
                    "włączony, w tej samej sieci, a DLNA/udostępnianie włączone.")
                    + (f"\n{err}" if err else ""))
                return
            self.cast_status.set_text(tr("Znaleziono: {0}. Wybierz urządzenie:").format(len(found)))
            for r in found:
                row = Gtk.ListBoxRow()
                row.renderer = r
                lbl = Gtk.Label(label=f"{r.name}   ·   {r.kind}", xalign=0)
                lbl.set_margin_top(8)
                lbl.set_margin_bottom(8)
                lbl.set_margin_start(10)
                lbl.set_margin_end(10)
                row.set_child(lbl)
                self.cast_list.append(row)

        bg(self._discover_all, done)

    @staticmethod
    def _discover_all():
        """DLNA/UPnP (LG, Samsung, Sony...) i Chromecast równolegle."""
        from concurrent.futures import ThreadPoolExecutor

        out = []
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(dlna.discover), ex.submit(cast_gc.discover),
                    ex.submit(airplay.discover)]
            for f in futs:
                try:
                    out += f.result()
                except Exception as e:  # noqa: BLE001
                    log.warning("wykrywanie TV: %r", e)
        return out

    def _cast_pick(self, _lb, row):
        r = row.renderer
        self.cast_pop.popdown()
        if getattr(r, "needs_pairing", False):  # AirPlay: najpierw sparuj PIN-em z ekranu TV
            PairingDialog(self, r, lambda: self._set_cast_target(r)).present()
            return
        self._set_cast_target(r)

    def _set_cast_target(self, r):
        self.cast_target = r
        self.cast_btn.add_css_class("suggested-action")
        log.info("cast: wybrano %s (%s)", r.name, r.control_url)
        pending, self._pending_cast = getattr(self, "_pending_cast", None), None
        if pending is not None:  # wybrano TV po „Wyślij na TV” z menu zdjęcia: wyślij od razu
            self.toast(tr("Wysyłanie na: {0}").format(r.name))
            self.cast_asset(pending)
        else:
            self.toast(tr("Wysyłanie na: {0}. Otwórz zdjęcie lub włącz pokaz.").format(r.name))

    def cast_from_menu(self, asset):
        """„Wyślij na TV” z menu prawego przycisku: od razu, albo najpierw wybór telewizora."""
        if self.cast_target is not None:
            self.cast_asset(asset)
            return
        self._pending_cast = asset
        self.cast_btn.popup()

    def _cast_stop(self, *_):
        r, self.cast_target = self.cast_target, None
        self.cast_btn.remove_css_class("suggested-action")
        self.cast_pop.popdown()
        if r is not None:
            bg(r.stop, lambda _res, _e: None)
            self.toast(tr("Zatrzymano wysyłanie na TV"))

    def cast_asset(self, asset):
        """Wysyła bieżące zdjęcie/wideo na wybrany TV (jeśli jakiś jest wybrany)."""
        r = self.cast_target
        if r is None:
            return
        is_vid = self.icloud.is_video(asset)
        if is_vid:
            ver, mime, fname = self.icloud.video_version(asset, True), "video/mp4", "video.mp4"
        else:
            jpg = asset.filename.lower().endswith((".jpg", ".jpeg"))
            ver = "original" if jpg and "original" in asset.versions else "medium"
            mime, fname = "image/jpeg", "photo.jpg"
        if ver is None:
            return

        def work():
            with self._cast_lock:  # jedna wysyłka naraz (telewizory odrzucają nakładające się polecenia)
                ip = self.icloud.lan_ip_for(r.host)
                blob = None
                if not is_vid:
                    try:  # zdjęcie pobieramy z góry: proxy odpowiada wtedy od razu
                        blob = asset.download(ver) or None
                    except Exception as e:  # noqa: BLE001
                        log.warning("cast: pobranie zdjęcia z góry nie powiodło się: %r", e)
                url = self.icloud.stream_url(asset, ver, lan_host=ip, blob=blob) + "/" + fname
                r.play_uri(url, asset.filename, mime, is_vid)

        def done(_res, err):
            if err:
                msg = str(err)
                log.error("cast: %s", msg)
                last, ts = self._last_cast_err
                if msg != last or time.monotonic() - ts > 15:
                    self.toast("TV: " + msg)
                    self._last_cast_err = (msg, time.monotonic())

        bg(work, done)

    # --- wysyłanie plików do iCloud ---
    def _on_drop(self, _target, value, _x, _y):
        if PICK is not None:
            return False  # tryb wyboru jest tylko do odczytu
        if self.stack.get_visible_child_name() != "main":
            return False
        paths = [f.get_path() for f in value.get_files() if f.get_path()]
        self._offer_upload(paths)
        return True

    def _offer_upload(self, paths):
        ok = [p for p in paths if p.lower().endswith(ICloud.UPLOAD_EXT)]
        if not ok:
            self.toast(tr("Brak obsługiwanych plików (JPG, PNG, HEIC, GIF, TIFF, DNG, MOV, MP4)"))
            return
        if len(ok) < len(paths):
            self.toast(tr("Pominięto {0} plik(ów) nieobsługiwanego typu").format(len(paths) - len(ok)))
        UploadDialog(self, ok).present()

    def _choose_files(self, *_):
        dlg = Gtk.FileDialog()
        dlg.set_title(tr("Wybierz zdjęcia i wideo do wysłania"))
        filt = Gtk.FileFilter()
        filt.set_name(tr("Zdjęcia i wideo"))
        for ext in ICloud.UPLOAD_EXT:
            filt.add_suffix(ext[1:])
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filt)
        dlg.set_filters(filters)

        def done(d, res):
            try:
                files = d.open_multiple_finish(res)
            except GLib.Error:
                return  # anulowano
            paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
            self._offer_upload([p for p in paths if p])

        dlg.open_multiple(self, None, done)

    def after_upload(self, album_name):
        self.toast(tr("Zdjęcia wysłane do iCloud"))
        if self.cur_album is not None and (
                self.cur_title == SMART_PL["All Photos"][0] or album_name == self.cur_title):
            # nowe zdjęcia pojawiają się po chwili przetwarzania po stronie Apple
            GLib.timeout_add_seconds(
                4, lambda: (self.load_album(self.cur_album), False)[1])

    # --- mpv jako zapas ---
    # --- informacje i menu prawego przycisku ---
    def show_info(self, obj):
        if obj is None:
            return
        self.last_obj = obj
        InfoDialog(self, obj).present()

    def _info_clicked(self, *_):
        if self.last_obj is None:
            self.toast(tr("Kliknij zdjęcie prawym przyciskiem i wybierz „Informacje”"))
        else:
            self.show_info(self.last_obj)

    def _tile_context(self, tile, x, y):
        if tile.bound is not None:
            self.show_context_menu(tile, x, y, tile.bound)

    def show_context_menu(self, widget, x, y, obj):
        if obj is None:
            return
        self.last_obj = obj
        pop = Gtk.Popover()
        pop.set_parent(widget)
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
        pop.set_pointing_to(rect)
        pop.set_has_arrow(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        def item(label, cb):
            b = Gtk.Button()
            b.add_css_class("flat")
            b.set_child(Gtk.Label(label=label, xalign=0))
            b.connect("clicked", lambda *_: (pop.popdown(), cb()))
            box.append(b)

        item(tr("Informacje"), lambda: self.show_info(obj))
        if isinstance(widget, Tile) and not obj.is_video:  # pokaz slajdów jest dostępny tylko wewnątrz albumu
            item(tr("Pokaz slajdów od tego zdjęcia"), lambda: self._slideshow_from(obj))

        def targets():  # prawy klik na zaznaczonym zdjęciu dotyczy całego zaznaczenia
            if obj in self.selected and len(self.selected) > 1:
                return [o.asset for o in self.selected]
            return [obj.asset]

        box.append(Gtk.Separator())
        for label, cb in self.album_menu_entries(targets):
            item(label, cb)
        box.append(Gtk.Separator())
        if obj.is_video:
            item(tr("Odtwórz w mpv"), lambda: self.play_external(obj))
        item(tr("Wyślij na TV"), lambda: self.cast_from_menu(obj.asset))
        item(tr("Zapisz oryginał jako…"), lambda: self.save_original(obj))
        item(tr("Kopiuj nazwę pliku"), lambda: (
            self.get_clipboard().set(obj.asset.filename), self.toast(tr("Skopiowano nazwę pliku"))))
        if not self._in_trash():
            box.append(Gtk.Separator())
            item(tr("Usuń…"), lambda: self.confirm_delete(targets()))
        pop.set_child(box)
        pop.connect("closed", lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

    def save_original(self, obj):
        dlg = Gtk.FileDialog()
        dlg.set_initial_name(obj.asset.filename)

        def done(d, res):
            try:
                f = d.save_finish(res)
            except GLib.Error:
                return
            path = f.get_path()
            self.toast(tr("Pobieram oryginał…"))
            bg(lambda: self.icloud.save_original(obj.asset, path),
               lambda _r, e: self.toast(tr("Błąd zapisu: {0}").format(e) if e else tr("Zapisano: {0}").format(path)))

        dlg.save(self, None, done)

    # --- wygasła sesja ---
    def on_auth_error(self):
        """Błąd wyglądający na wygaśnięcie sesji: sprawdź lekkim zapytaniem i dopiero wtedy wyloguj."""
        if self._expired or self._probing or self.stack.get_visible_child_name() != "main":
            return

        def done(_r, err):
            self._probing = False
            if err is not None and is_auth_error(err):
                self.session_expired()

        self._probing = True
        bg(self.icloud.probe, done)

    def session_expired(self):
        if self._expired:
            return
        log.warning("sesja iCloud wygasła - wracam do ekranu logowania")
        self._expired = True
        self.gen += 1  # unieważnij trwające ładowanie
        self.set_select_mode(False)
        self.store.remove_all()
        self.cur_album = None
        self._clear_albums()
        for w in self.logged_widgets + [self.sidebar_btn]:
            w.set_visible(False)
        self.pending_2fa = False
        self.e_code.set_text("")
        self.e_code.set_visible(False)
        self.btn.set_sensitive(True)
        self.count.set_text("")
        self.stack.set_visible_child_name("login")
        self.say(tr("Sesja wygasła. Zaloguj się ponownie."))
        self._autologin()  # spróbuj z zapisanym hasłem; wtedy poprosi tylko o kod 2FA

    # --- odświeżanie biblioteki ---
    def _selected_album_key(self):
        for lb in self.lists:
            row = lb.get_selected_row()
            if row is not None:
                return row.key
        return None

    def _find_row(self, key):
        for lb in self.lists:
            row = lb.get_first_child()
            while row is not None:
                if getattr(row, "key", None) == key:
                    return row
                row = row.get_next_sibling()
        return None

    def _links_stale(self):
        """Linki do plików z iCloud wygasły (410): odśwież bibliotekę (najwyżej raz na 2 minuty)."""
        now = time.monotonic()
        if now - getattr(self, "_last_stale_refresh", -1e9) < 120:
            return
        self._last_stale_refresh = now
        log.info("linki do plików wygasły - odświeżam bibliotekę")
        self.refresh_library()

    def _periodic_link_refresh(self):
        """Zapobiegawczo, zanim linki wygasną: co ~45 min odświeżamy listę, gdy nic nie jest otwarte."""
        if not self.viewers and self.stack.get_visible_child_name() == "main":
            self._last_stale_refresh = time.monotonic()
            self.refresh_library()
        return True

    def refresh_library(self):
        """Pobiera od nowa listę albumów i zdjęcia bieżącego albumu (np. po dodaniu zdjęć na telefonie)."""
        if self._refreshing or self._expired or self.stack.get_visible_child_name() != "main":
            return
        self._refreshing = True
        self.refresh_btn.set_sensitive(False)
        self._keep_key = self._selected_album_key()
        self.toast(tr("Odświeżam bibliotekę…"))

        def work():
            self.icloud.refresh_library()
            return self.icloud.albums()

        bg(work, self._refreshed)

    def _refreshed(self, albums, err):
        self._refreshing = False
        self.refresh_btn.set_sensitive(True)
        if err:
            self._keep_key = None
            if is_auth_error(err):
                self.session_expired()
            else:
                self.toast(tr("Nie udało się odświeżyć: {0}").format(err))
            return
        self._clear_albums()
        self._albums_loaded(albums, None)
        self.toast(tr("Biblioteka odświeżona"))

    def _clear_albums(self):
        for lb in (self.list_primary, self.list_more, self.list_user):
            child = lb.get_first_child()
            while child is not None:
                nxt = child.get_next_sibling()
                lb.remove(child)
                child = nxt
        self.user_albums = []

    # --- skok do daty ---
    def _build_jump_button(self):
        btn = Gtk.MenuButton(icon_name="x-office-calendar-symbolic")
        btn.add_css_class("flat")
        btn.set_tooltip_text(tr("Przejdź do daty"))
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        head = Gtk.Label(label=tr("Przejdź do daty"), xalign=0)
        head.add_css_class("heading")
        months = month_names()
        now = time.localtime()
        years = [str(y) for y in range(now.tm_year, 1999, -1)]
        self.cal = Gtk.Calendar()
        row = Gtk.Box(spacing=6)
        self.jump_month = Gtk.DropDown.new_from_strings(months)
        self.jump_year = Gtk.DropDown.new_from_strings(years)
        self.jump_month.set_selected(now.tm_mon - 1)
        self.jump_years = years

        def sync(*_):
            y = int(self.jump_years[self.jump_year.get_selected()])
            self.cal.select_day(GLib.DateTime.new_local(y, self.jump_month.get_selected() + 1,
                                                        1, 0, 0, 0))

        self.jump_month.connect("notify::selected", sync)
        self.jump_year.connect("notify::selected", sync)
        row.append(self.jump_month)
        row.append(self.jump_year)
        go = Gtk.Button(label=tr("Przejdź"))
        go.add_css_class("suggested-action")
        go.connect("clicked", lambda *_: (pop.popdown(), self._jump_from_calendar()))
        hint = Gtk.Label(label=tr("Datę można też wpisać w polu „Szukaj albumu” (np. 08.2024)."),
                         xalign=0, wrap=True)
        hint.add_css_class("dim-label")
        hint.set_max_width_chars(34)
        for w in (head, row, self.cal, go, hint):
            box.append(w)
        pop.set_child(box)
        btn.set_popover(pop)
        return btn

    def _jump_from_calendar(self):
        d = self.cal.get_date()
        y, m, dd = d.get_year(), d.get_month(), d.get_day_of_month()
        from datetime import datetime

        self._do_jump(datetime(y, m, dd), datetime(y, m, dd, 23, 59, 59), f"{dd}.{m:02d}.{y}")

    def _jump_from_query(self):
        if self._jump_q:
            a, b, label = self._jump_q
            self._do_jump(a, b, label)

    def _do_jump(self, start, end, label):
        album = self.cur_album
        if album is None:  # np. po otwarciu wspomnienia/zestawu - skocz w całej bibliotece
            first = self.list_primary.get_row_at_index(0)
            album = first.album if first else None
        if album is None:
            self.toast(tr("Biblioteka jeszcze się ładuje"))
            return
        ts = (end if self.newest_first else start).timestamp()
        self.content_hint = label
        self.load_album(album, jump=ts)
        self.wtitle.set_subtitle(f"od: {label}")
        self.toast(tr("Przechodzę do: {0}…").format(label))

    # --- zaznaczanie wielu zdjęć ---
    def _build_pick_bar(self):
        """Pasek trybu wyboru (--pick): zaznaczanie, „Wybierz” i „Anuluj”. Bez usuwania i zmian w albumach."""
        bar = Gtk.ActionBar()
        self.sel_label = Gtk.Label(label=tr("Zaznacz zdjęcia i filmy, potem kliknij „Wybierz”"))
        bar.pack_start(self.sel_label)
        clear = Gtk.Button(label=tr("Wyczyść"))
        clear.connect("clicked", lambda *_: self._sel_none())
        bar.pack_start(clear)
        self.pick_btn = Gtk.Button(label=tr("Wybierz"))
        self.pick_btn.add_css_class("suggested-action")
        self.pick_btn.set_sensitive(False)
        self.pick_btn.connect("clicked", lambda *_: self._pick_confirm())
        cancel = Gtk.Button(label=tr("Anuluj"))
        cancel.connect("clicked", lambda *_: self.close())
        bar.pack_end(self.pick_btn)
        bar.pack_end(cancel)
        self.sel_revealer = Gtk.Revealer()
        self.sel_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.sel_revealer.set_child(bar)
        return self.sel_revealer

    def _enter_pick_mode(self):
        self.add_btn.set_visible(False)      # bez wysyłania do iCloud
        self.select_btn.set_visible(False)   # zaznaczanie jest w tym trybie zawsze włączone
        self.set_select_mode(True)

    def _pick_confirm(self):
        """Eksportuje zaznaczone pliki do folderu, zapisuje wynik JSON i kończy aplikację."""
        if PICK is None or self._pick_busy or not self.selected:
            return
        assets = [o.asset for o in self.selected]
        self._pick_busy = True
        self.sel_label.set_text(tr("Przygotowuję…"))
        self._refresh_selection()

        def progress(k, n):
            GLib.idle_add(lambda: (self.sel_label.set_text(tr("Przygotowuję {0}/{1}…").format(k, n)), False)[1])

        def work():
            return pick.export_assets(self.icloud, assets, PICK["dir"], progress=progress,
                                      converter=pick.heic_to_jpeg_bytes)

        def done(res, err):
            self._pick_busy = False
            items, errors = res if res else ([], [str(err)])
            if not items:
                self.toast(tr("Nie udało się przygotować plików: {0}").format("; ".join(errors[:2]) or "?"))
                self._refresh_selection()
                return
            try:
                pick.write_result(PICK["out"], items, errors)
            except OSError as e:
                self.toast(tr("Nie udało się przygotować plików: {0}").format(e))
                self._refresh_selection()
                return
            app = self.get_application()
            app.picked = True
            app.quit()

        bg(work, done)

    def _build_selection_bar(self):
        if PICK is not None:
            return self._build_pick_bar()
        bar = Gtk.ActionBar()
        self.sel_label = Gtk.Label(label=tr("Zaznaczono: 0"))
        bar.pack_start(self.sel_label)

        def button(label, cb, icon=None, tip=None):
            b = Gtk.Button(icon_name=icon) if icon else Gtk.Button(label=label)
            if tip:
                b.set_tooltip_text(tip)
            b.connect("clicked", lambda *_: cb())
            return b

        bar.pack_start(button(tr("Zaznacz wszystko"), self._sel_all))
        bar.pack_start(button(tr("Wyczyść"), self._sel_none))
        bar.pack_end(button("", lambda: self.set_select_mode(False), "window-close-symbolic",
                            tr("Zakończ zaznaczanie (Esc)")))
        self.del_btn = button("", self._sel_delete, "user-trash-symbolic",
                              tr("Usuń zaznaczone zdjęcia (Delete)"))
        self.del_btn.add_css_class("destructive-action")
        self.del_btn.set_sensitive(False)
        bar.pack_end(self.del_btn)
        bar.pack_end(button(tr("Zapisz oryginały…"), self._sel_save))
        bar.pack_end(button("", lambda: self._sel_fav(False), "non-starred-symbolic",
                            tr("Usuń z ulubionych")))
        bar.pack_end(button("", lambda: self._sel_fav(True), "starred-symbolic",
                            tr("Dodaj do ulubionych")))
        bar.pack_end(button(tr("Do albumu…"), self._sel_album))
        self.sel_revealer = Gtk.Revealer()
        self.sel_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.sel_revealer.set_child(bar)
        return self.sel_revealer

    def set_select_mode(self, on):
        on = bool(on)
        if PICK is not None and not on:
            self.selected = []  # jak przy wyłączeniu zaznaczania, ale w trybie wyboru zostaje ono włączone
            on = True
        if self.select_btn.get_active() != on:
            self.select_btn.set_active(on)  # wywoła ponownie tę metodę
            return
        self.select_mode = on
        if not on:
            self.selected = []
            self._rb = None
        self.sel_revealer.set_reveal_child(on)
        for t in list(self.tiles):
            t.check.set_visible(on)
        self._refresh_selection()

    def _refresh_selection(self):
        if PICK is not None:
            mx = PICK["max"]
            if len(self.selected) > mx:
                del self.selected[mx:]
                if time.monotonic() - self._pick_warn_ts > 2:
                    self._pick_warn_ts = time.monotonic()
                    self.toast(tr("Można wybrać najwyżej {0} plików naraz").format(mx))
            n = len(self.selected)
            if not self._pick_busy:
                self.sel_label.set_text(tr("Zaznaczono: {0} z {1}").format(n, mx) if n
                                        else tr("Zaznacz zdjęcia i filmy, potem kliknij „Wybierz”"))
            if hasattr(self, "pick_btn"):
                self.pick_btn.set_sensitive(bool(n) and not self._pick_busy)
                self.pick_btn.set_label(tr("Wybierz ({0})").format(n) if n else tr("Wybierz"))
        else:
            self.sel_label.set_text(tr("Zaznaczono: {0}").format(len(self.selected)))
        if hasattr(self, "del_btn"):
            self.del_btn.set_sensitive(bool(self.selected) and not self._in_trash())
        for t in list(self.tiles):
            if t.bound is not None:
                t.check.set_active(t.bound in self.selected)

    def _toggle_tile(self, tile):
        obj = tile.bound
        if obj is None:
            return
        removed = obj in self.selected
        if not removed and PICK is not None and len(self.selected) >= PICK["max"]:
            self.toast(tr("Można wybrać najwyżej {0} plików naraz").format(PICK["max"]))
            return
        if removed:
            self.selected.remove(obj)
        else:
            self.selected.append(obj)
        self._refresh_selection()
        if removed and not self.selected and PICK is None:  # odznaczono ostatnie zdjęcie - koniec zaznaczania
            self.set_select_mode(False)

    def _tile_press(self, tile, gesture):
        """Kliknięcie kafelka (Ctrl+klik lub tryb zaznaczania) przełącza zaznaczenie."""
        ctrl = bool(gesture.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK)
        if tile.bound is None or not (self.select_mode or ctrl):
            return
        if not self.select_mode:
            self.set_select_mode(True)
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)  # nie otwieraj podglądu
        self._toggle_tile(tile)

    # --- zaznaczanie ramką (przeciągnięcie lewym przyciskiem) ---
    def _install_rubberband(self, sw):
        g = Gtk.GestureDrag()
        g.set_button(1)
        g.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        g.connect("drag-begin", self._rb_begin)
        g.connect("drag-update", self._rb_update)
        g.connect("drag-end", self._rb_end)
        sw.add_controller(g)
        self._rb_gesture = g

    def _pt(self, src, dst, x, y):
        p = Graphene.Point()
        p.init(x, y)
        ok, out = src.compute_point(dst, p)
        return (out.x, out.y) if ok else (x, y)

    def _rb_begin(self, g, x, y):
        sw = self.grid_sw
        if x > sw.get_width() - 18:  # pasek przewijania - nie zaczynaj ramki
            self._rb = None
            return
        ctrl = bool(g.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK)
        self._rb = {"start": self._pt(sw, self.grid, x, y), "press": (x, y), "last": (x, y),
                    "moved": False, "claimed": False, "ctrl": ctrl, "decided": {},
                    "base": list(self.selected)}
        if self.select_mode or ctrl:  # kliknięcie ma tylko zaznaczać, nie otwierać podglądu
            g.set_state(Gtk.EventSequenceState.CLAIMED)
            self._rb["claimed"] = True

    def _rb_update(self, g, dx, dy):
        rb = self._rb
        if not rb:
            return
        x0, y0 = rb["press"]
        rb["last"] = (x0 + dx, y0 + dy)
        if not rb["moved"]:
            if math.hypot(dx, dy) < 8:
                return
            rb["moved"] = True
            if not rb["claimed"]:
                g.set_state(Gtk.EventSequenceState.CLAIMED)  # to już przeciąganie, nie kliknięcie
                rb["claimed"] = True
            if not self.select_mode:
                rb["auto"] = True  # to przeciągnięcie samo włączyło tryb zaznaczania
                self.set_select_mode(True)
                self._rb = rb  # set_select_mode(False) zeruje; tu włączamy
            GLib.timeout_add(40, self._rb_tick, rb)
        self._rb_recompute()

    def _rb_tick(self, rb):
        """Przewijanie przy krawędzi okna, gdy ramka jest przeciągana."""
        if self._rb is not rb:
            return False
        sw = self.grid_sw
        adj = sw.get_vadjustment()
        y = rb["last"][1]
        if y < 40:
            adj.set_value(adj.get_value() - 20)
        elif y > sw.get_height() - 40:
            adj.set_value(adj.get_value() + 20)
        else:
            return True
        self._rb_recompute()
        return True

    def _rb_recompute(self):
        rb = self._rb
        if not rb:
            return
        sw, grid = self.grid_sw, self.grid
        sx, sy = rb["start"]
        cx, cy = self._pt(sw, grid, *rb["last"])
        x0, x1, y0, y1 = min(sx, cx), max(sx, cx), min(sy, cy), max(sy, cy)
        for t in list(self.tiles):
            if t.bound is None or not t.get_mapped():
                continue
            ok, r = t.compute_bounds(grid)
            if not ok:
                continue
            hit = (r.origin.x < x1 and r.origin.x + r.size.width > x0
                   and r.origin.y < y1 and r.origin.y + r.size.height > y0)
            rb["decided"][t.bound] = hit  # kafelki spoza widoku zachowują ostatnią decyzję
        base = rb["base"]
        sel = []
        for o in base:
            hit = rb["decided"].get(o, False)
            if not (hit if rb["ctrl"] else False):  # Ctrl odwraca zaznaczenie, bez Ctrl dodaje
                sel.append(o)
        for o, hit in rb["decided"].items():
            if hit and o not in base:
                sel.append(o)
        self.selected = sel
        self._refresh_selection()
        # prostokąt rysowany we współrzędnych okna przewijania
        ax, ay = self._pt(grid, sw, x0, y0)
        bx, by = self._pt(grid, sw, x1, y1)
        ax, ay = max(0, ax), max(0, ay)
        bx, by = min(sw.get_width(), bx), min(sw.get_height(), by)
        self.rubber.set_margin_start(int(ax))
        self.rubber.set_margin_top(int(ay))
        self.rubber.set_size_request(max(1, int(bx - ax)), max(1, int(by - ay)))
        self.rubber.set_visible(True)

    def _rb_end(self, g, dx, dy):
        rb, self._rb = self._rb, None
        self.rubber.set_visible(False)
        if rb and rb["moved"] and not self.selected and (rb["ctrl"] or rb.get("auto")):
            self.set_select_mode(False)  # nic nie zostało zaznaczone - wyłącz tryb
        if rb and not rb["moved"] and rb["claimed"]:  # zwykłe kliknięcie w trybie zaznaczania
            gx, gy = self._pt(self.grid_sw, self.grid, *rb["press"])
            w = self.grid.pick(gx, gy, Gtk.PickFlags.DEFAULT)
            while w is not None and not isinstance(w, Tile):
                w = w.get_parent()
            if w is not None and w.bound is not None:
                if not self.select_mode:
                    self.set_select_mode(True)
                self._toggle_tile(w)

    def _sel_all(self):
        items = [self.store.get_item(i) for i in range(self.store.get_n_items())]
        self.selected = items[:PICK["max"]] if PICK is not None else items
        self._refresh_selection()

    def _sel_none(self):
        self.selected = []
        self._refresh_selection()

    def _sel_assets(self):
        if not self.selected:
            self.toast(tr("Najpierw zaznacz zdjęcia"))
        return [o.asset for o in self.selected]

    def _sel_progress(self, label):
        def progress(k, n):
            GLib.idle_add(lambda: (self.sel_label.set_text(f"{label} {k}/{n}…"), False)[1])
        return progress

    def _sel_album(self):
        assets = self._sel_assets()
        if not assets:
            return
        if not self.user_albums:
            self.toast(tr("Nie masz jeszcze własnych albumów"))
            return
        AddToAlbumDialog(self, assets).present()

    def _sel_fav(self, value):
        assets = self._sel_assets()
        if not assets:
            return

        def done(res, err):
            ok, errors = res if res else (0, [str(err)])
            msg = (tr("Dodano do ulubionych: {0} z {1}") if value
                   else tr("Usunięto z ulubionych: {0} z {1}")).format(ok, len(assets))
            self.toast(msg
                       + (tr(", błędy: {0} (log)").format(len(errors)) if errors else ""))
            self._refresh_selection()
            if not value and self.cur_title == tr("Ulubione") and self.cur_album is not None:
                self.load_album(self.cur_album)

        bg(lambda: self.icloud.set_favorite(assets, value, self._sel_progress(tr("Zmiana"))), done)

    def _sel_save(self):
        assets = self._sel_assets()
        if not assets:
            return
        dlg = Gtk.FileDialog()
        dlg.set_title(tr("Wybierz folder na oryginały"))

        def chosen(d, res):
            try:
                folder = d.select_folder_finish(res).get_path()
            except GLib.Error:
                return

            def done(r, err):
                ok, errors = r if r else (0, [str(err)])
                self.toast(tr("Zapisano oryginały: {0} z {1} w {2}").format(ok, len(assets), folder)
                           + (tr(" (błędy: {0}, log)").format(len(errors)) if errors else ""))
                self._refresh_selection()

            bg(lambda: self.icloud.save_originals(assets, folder,
                                                  self._sel_progress(tr("Zapis"))), done)

        dlg.select_folder(self, None, chosen)

    # --- dodawanie do albumu: ostatnie albumy, menu, wspólna operacja ---
    def remember_album(self, name):
        self.recent_albums = [name] + [n for n in self.recent_albums if n != name]
        self.recent_albums = self.recent_albums[:3]
        save_cfg(recent_albums=self.recent_albums)

    def add_to_album_async(self, assets, name, album, progress=None, on_done=None):
        def done(res, err):
            ok, already, errors = res if res else (0, [], [str(err)])
            text, short = format_album_result(name, len(assets), ok, already, errors)
            self.toast(short)
            if err is None:
                self.remember_album(name)
            if ok and self.cur_title == name and self.cur_album is not None:
                self.load_album(self.cur_album)
            if on_done:
                on_done(text)

        bg(lambda: self.icloud.add_to_album(album, assets, progress), done)

    def album_menu_entries(self, get_assets):
        """Pozycje menu „Dodaj do albumu”: do 3 ostatnich albumów + wybór innego."""
        assets = get_assets()
        n = len(assets)
        word = plural(n, ("zdjęcie", "zdjęcia", "zdjęć"), ("photo", "photos"),
                      de=("Foto", "Fotos"), uk=("фото", "фото", "фото"))
        suffix = f" ({n} {word})" if n > 1 else ""
        by_name = dict(self.user_albums)
        entries = []
        for n in self.recent_albums:
            if n in by_name:
                entries.append((tr("Dodaj do albumu „{0}”{1}").format(n, suffix),
                                lambda n=n: self._add_to(n, get_assets())))
        entries.append((tr("Dodaj do innego albumu…") if entries else tr("Dodaj do albumu…"),
                        lambda: self._open_album_dialog(get_assets())))
        return entries

    def _add_to(self, name, assets):
        album = dict(self.user_albums).get(name)
        if album is None:
            self.toast(tr("Album „{0}” nie jest już dostępny").format(name))
            return
        self.toast(tr("Dodaję do albumu „{0}”…").format(name))
        self.add_to_album_async(assets, name, album)

    def _open_album_dialog(self, assets):
        if not self.user_albums:
            self.toast(tr("Nie masz jeszcze własnych albumów"))
            return
        AddToAlbumDialog(self, assets).present()

    # --- przezroczystość okna (0 = wyłączona) ---
    def set_glass(self, level):
        """Poziom 0-100. 0 = wygląd jak dotąd. Więcej: tło okna i panele stają się półprzezroczyste, a pod
        nimi widać rozmyte kolory zdjęć z bieżącego albumu (czytelność zostaje dzięki mniej przezroczystym
        panelom). Prawdziwe rozmycie pulpitu za oknem jest poza zasięgiem aplikacji GTK4 na GNOME."""
        level = max(0, min(100, int(level)))
        self.glass = level
        if getattr(self, "_glass_provider", None) is None:
            self._glass_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self._glass_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        if level == 0:
            self.remove_css_class("glass")
            self._glass_provider.load_from_data(b"")
            self.backdrop.set_strength(0.0)
            return
        k = level / 100.0
        # Aplikacja nie potrafi rozmyć pulpitu za oknem, więc to, co jest pod spodem, byłoby ostre i nakładałoby się
        # na tekst. Dlatego im bardziej przezroczyste okno, tym mocniej kryje rozmyta warstwa ze zdjęć (Backdrop),
        # a panele z tekstem zawsze mają co najmniej 75% krycia.
        win_a = 1.0 - 0.60 * k            # tło okna (marginesy, szczeliny): do 40% krycia
        panel_a = 1.0 - 0.25 * k          # panele (nagłówek, paski): min. 75% krycia
        # libadwaita >= 1.6: @window_bg_color/@headerbar_bg_color to stałe, NIE śledzą zmiennych CSS, które
        # nadpisuje motyw (Aurora) – stąd var() + color-mix; starsze wersje znają tylko @define-color.
        if (Adw.get_major_version(), Adw.get_minor_version()) >= (1, 6):
            def tint(name, a):
                return f"color-mix(in srgb, var(--{name.replace('_', '-')}-color) {a * 100:.1f}%, transparent)"
        else:
            def tint(name, a):
                return f"alpha(@{name}_color, {a:.3f})"
        css = (
            f"window.glass.background {{ background-color: {tint('window_bg', win_a)}; }}\n"
            f"window.glass headerbar {{ background-color: {tint('headerbar_bg', panel_a)};"
            f" box-shadow: none; }}\n"
            "window.glass .navigation-sidebar, window.glass scrolledwindow, window.glass gridview,"
            " window.glass listview, window.glass paned, window.glass stack, window.glass .view"
            " { background-color: transparent; }\n"
            f"window.glass actionbar > revealer > box, window.glass .text-panel {{ background-color:"
            f" {tint('window_bg', panel_a)}; }}\n"
        )
        self._glass_provider.load_from_data(css.encode())
        self.add_css_class("glass")
        self.backdrop.set_strength(0.25 + 0.40 * k)  # 25-65%: mocne rozmycie maskuje to, co pod oknem
        self._update_backdrop()

    def _update_backdrop(self):
        if not self.glass:
            return False
        for i in range(min(8, self.store.get_n_items())):
            tex = self.tex.get(self.store.get_item(i).asset.id)
            if tex is not None:
                try:
                    self.backdrop.set_texture(blur_texture(tex))
                except Exception as e:  # noqa: BLE001
                    log.warning("tło przezroczystości: %r", e)
                break
        return False

    # --- usuwanie zdjęć (do „Ostatnio usunięte”, z potwierdzeniem u Apple) ---
    def _in_trash(self):
        return self.cur_title == tr("Ostatnio usunięte")

    def _sel_delete(self):
        if PICK is not None:
            return
        assets = self._sel_assets()
        if assets:
            self.confirm_delete(assets)

    def confirm_delete(self, assets, on_done=None, parent=None):
        """Pyta o potwierdzenie (domyślnie „Anuluj”) i dopiero wtedy usuwa."""
        if not assets:
            return
        if self._in_trash():
            self.toast(tr("W albumie „Ostatnio usunięte” nie można usuwać zdjęć tutaj"))
            return
        n = len(assets)
        dlg = Gtk.AlertDialog()
        dlg.set_message(tr("Usunąć to zdjęcie?") if n == 1
                        else tr("Usunąć zaznaczone zdjęcia ({0})?").format(n))
        dlg.set_detail(tr("Zdjęcia zostaną przeniesione do albumu „Ostatnio usunięte” w iCloud "
                          "(Apple zwykle przechowuje je tam 30 dni) i znikną z biblioteki na "
                          "wszystkich Twoich urządzeniach. Ta aplikacja nie ma przycisku "
                          "przywracania - zrobisz to w aplikacji Zdjęcia lub na iCloud.com."))
        dlg.set_buttons([tr("Anuluj"), tr("Usuń")])
        dlg.set_cancel_button(0)
        dlg.set_default_button(0)

        def chosen(d, res):
            try:
                idx = d.choose_finish(res)
            except GLib.Error:
                return  # zamknięto okno bez wyboru
            if idx == 1:
                self._do_delete(assets, on_done)

        dlg.choose(parent or self, None, chosen)

    def _do_delete(self, assets, on_done=None):
        self.toast(tr("Usuwam zdjęcia…"))

        def progress(k, n):
            GLib.idle_add(lambda: (
                self.sel_label.set_text(tr("Usuwanie {0}/{1}…").format(k, n)), False)[1])

        def done(res, err):
            deleted, errors = res if res else ([], [str(err)])
            ids = {a.id for a in deleted}
            if ids:  # usunięcie potwierdzone przez Apple -> znika też z widoku
                for i in range(self.store.get_n_items() - 1, -1, -1):
                    if self.store.get_item(i).asset.id in ids:
                        self.store.remove(i)
                self.selected = [o for o in self.selected if o.asset.id not in ids]
                if self.total:
                    self.total = max(0, self.total - len(ids))
                self._update_count()
                for v in list(self.viewers):
                    if v.get_visible():
                        v.after_delete(ids)
            self._refresh_selection()
            msg = (tr("Przeniesiono do „Ostatnio usunięte”: {0} z {1}").format(
                len(deleted), len(assets)) if deleted else tr("Nie usunięto żadnego zdjęcia"))
            if errors:
                log.error("usuwanie: %s", errors)
                msg += tr(", błąd: {0}").format(str(errors[0])[:110])
            self.toast(msg)
            if on_done:
                on_done(deleted)

        bg(lambda: self.icloud.delete_assets(assets, progress), done)

    def _video_plan_b(self, obj, ver, why):
        """Streaming przez proxy nie zadziałał - pobierz film do cache i odtwórz lokalnie."""
        self.toast(tr("Streaming filmu nie powiódł się, pobieram go do pamięci podręcznej…"))
        log.warning("film %s: plan B po błędzie: %s", obj.asset.filename, why)

        def done(path, err):
            if err:
                log.error("plan B filmu %s: %r", obj.asset.filename, err)
                self.toast(tr("Nie udało się odtworzyć filmu: {0}  [log: {1}]").format(err, DEBUG_LOG))
                return
            self.play_external(obj, url=path, _retry=False)

        bg(lambda: self.icloud.fetch_video_file(obj.asset, ver), done)

    def toast(self, text):
        t = Adw.Toast.new(text[:240])
        t.set_timeout(8)
        self.toasts.add_toast(t)

    def external_video_ok(self):
        if self.embedded_video or self.video_player == "embedded":
            return False
        return shutil.which("mpv") is not None

    def play_external(self, obj, ver=None, url=None, _retry=True):
        """Otwiera wideo (albo część wideo Live Photo) w osobnym oknie mpv."""
        if url is None:
            if ver is None:
                if not obj.is_video:
                    return False
                # lekka wersja H.264 ('medium') zamiast wielkiego oryginału HEVC
                ver = self.icloud.video_version(obj.asset, True)
            if ver is None:
                self.toast(tr("Brak wersji wideo do odtworzenia"))
                return False
        if not shutil.which("mpv"):
            self.toast(tr("Zainstaluj mpv: sudo apt install mpv"))
            return False
        if url is None:
            url = self.icloud.stream_url(obj.asset, ver)
        mpv_log = CACHE_DIR / "mpv.log"
        try:
            fh = open(mpv_log, "wb")
        except OSError:
            fh = subprocess.DEVNULL
        p = subprocess.Popen(
            ["mpv", "--force-window=immediate", "--hwdec=auto-safe", "--network-timeout=20",
             "--cache=yes", "--demuxer-max-bytes=64MiB", f"--title={obj.asset.filename}", url],
            stdout=fh, stderr=subprocess.STDOUT,
        )
        log.info("mpv: %s (%s)", obj.asset.filename, ver)

        def check():
            rc = p.poll()
            if rc not in (None, 0):
                tail = ""
                try:
                    lines = [x for x in mpv_log.read_text(errors="replace").splitlines()
                             if x.strip()]
                    tail = lines[-1] if lines else ""
                except OSError:
                    pass
                log.error("mpv rc=%s: %s", rc, tail)
                if _retry and obj.is_video and str(url).startswith("http"):
                    self._video_plan_b(obj, ver, tr("{0} (kod {1})").format(tail, rc))  # streaming zawiódł
                else:
                    self.toast(tr("mpv zakończył się błędem ({0}): {1}  [log: {2}]").format(rc, tail, DEBUG_LOG))
            return False

        GLib.timeout_add_seconds(4, check)
        return True

    def _on_key(self, _c, keyval, _code, state):
        on_main = self.stack.get_visible_child_name() == "main"
        if on_main and (keyval == Gdk.KEY_F5 or (
                keyval in (Gdk.KEY_r, Gdk.KEY_R) and state & Gdk.ModifierType.CONTROL_MASK)):
            self.refresh_library()
            return True
        if PICK is not None and on_main and keyval == Gdk.KEY_Escape:
            if self.selected:
                self._sel_none()
            else:
                self.close()  # anulowanie wyboru
            return True
        if (PICK is None and on_main and keyval == Gdk.KEY_Delete and self.select_mode and self.selected
                and not isinstance(self.get_focus(), Gtk.Editable)):
            self._sel_delete()
            return True
        if on_main and keyval == Gdk.KEY_Escape and self.select_mode:
            self.set_select_mode(False)
            return True
        if (on_main and keyval in (Gdk.KEY_a, Gdk.KEY_A) and state & Gdk.ModifierType.CONTROL_MASK
                and not isinstance(self.get_focus(), Gtk.Editable)):
            self.set_select_mode(True)
            self._sel_all()
            return True
        if keyval == Gdk.KEY_F11:
            if self.is_fullscreen():
                self.unfullscreen()
            else:
                self.fullscreen()
            return True
        if (state & Gdk.ModifierType.CONTROL_MASK
                and self.stack.get_visible_child_name() == "main"):
            if keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                self.set_tile_size(self.tile_size + 20)
                return True
            if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract, Gdk.KEY_underscore):
                self.set_tile_size(self.tile_size - 20)
                return True
            if keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
                self.set_tile_size(TILE_DEFAULT)
                return True
        return False


def apply_theme_icon(dark: bool) -> None:
    """Ikona aplikacji w menu/docku ma jasny albo ciemny wariant zależnie od motywu systemu.
    Dock czyta ikonę z motywu, więc wariant ciemny zapisujemy w ~/.local/share/icons (ma pierwszeństwo
    przed systemową), a dla jasnego usuwamy ten plik (zostaje systemowa, jasna)."""
    try:
        target_dirs = [Path.home() / ".local/share/icons/hicolor/scalable/apps"]
        cands = (Path("/usr/share/linux-icloud-photos/icon-dark.svg"),
                 Path("/app/share/linux-icloud-photos/icon-dark.svg"))
        src = next((p for p in cands if p.exists()), None)
        changed = False
        for d in target_dirs:
            for name in ("linux-icloud-photos.svg", "local.linuxicloudphotos.Photos.svg"):
                f = d / name
                if dark and src is not None:
                    data = src.read_bytes()
                    if not f.exists() or f.read_bytes() != data:
                        d.mkdir(parents=True, exist_ok=True)
                        f.write_bytes(data)
                        changed = True
                elif not dark and f.exists():
                    f.unlink()
                    changed = True
            if changed:
                os.utime(d.parent.parent, None)  # motyw ikon odświeży się przy zmianie katalogu
                os.utime(d, None)
    except Exception as e:  # noqa: BLE001
        log.warning("ikona motywu: %r", e)


class App(Adw.Application):
    def __init__(self):
        # tryb wyboru działa jako osobny proces, nawet gdy zwykła aplikacja jest już otwarta
        flags = Gio.ApplicationFlags.NON_UNIQUE if PICK is not None else Gio.ApplicationFlags.FLAGS_NONE
        super().__init__(application_id="local.linuxicloudphotos.Photos", flags=flags)
        self.picked = False
        self.pending_open = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        for name, key in (("open-album", "album"), ("open-date", "date")):
            act = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            act.connect("activate", lambda _a, v, k=key: self._open_from_action({k: v.get_string()}))
            self.add_action(act)

    def _open_from_action(self, req):
        win = self.props.active_window
        if win is None:
            self.pending_open = req
            self.activate()
            return
        win.present()
        win.open_request(req)

    def do_activate(self):
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        Gtk.Window.set_default_icon_name("linux-icloud-photos")
        sm = Adw.StyleManager.get_default()
        apply_theme_icon(sm.get_dark())
        sm.connect("notify::dark", lambda m, _p: apply_theme_icon(m.get_dark()))
        # motyw wyglądu: Systemowy (Adwaita) albo Aurora – miniatury z poświatą po najechaniu
        from aurora import AuroraTheme
        if getattr(self, "look", None) is None:
            glow = {False: "gridview > child:hover { box-shadow: 0 0 0 2px #ffffff, 0 0 0 4px alpha(#7c5cff, 0.7),"
                           " 0 12px 30px alpha(#7c5cff, 0.45); }",
                    True: "gridview > child:hover { box-shadow: 0 0 0 2px alpha(#22d3ee, 0.85),"
                          " 0 0 28px alpha(#22d3ee, 0.5); }"}
            common = "gridview > child { border-radius: 12px; transition: box-shadow 150ms; }\n"
            self.look = AuroraTheme(extra={k: common + v for k, v in glow.items()})
            self.look.apply(load_cfg().get("theme", "system"))
        for old in ("index.json", "albums_index.json", "places.json"):  # po usuniętych Wspomnieniach
            try:
                (CACHE_DIR / old).unlink()
            except OSError:
                pass
        threading.Thread(target=prune_cache,
                         args=(int(float(load_cfg().get("cache_gb", 1.0)) * 1024**3),),
                         daemon=True).start()
        win = self.props.active_window or MainWindow(self)
        win.present()
        if self.pending_open and hasattr(win, "open_request"):
            req, self.pending_open = self.pending_open, None
            win.open_request(req)


def check_versions():
    """Zamiast niejasnej awarii na zbyt starym systemie - czytelny komunikat."""
    gtk = (Gtk.get_major_version(), Gtk.get_minor_version())
    adw = (Adw.get_major_version(), Adw.get_minor_version())
    if gtk >= MIN_GTK and adw >= MIN_ADW:
        return
    msg = tr("Ta aplikacja wymaga GTK {0}.{1} i libadwaita {2}.{3} lub nowszych "
             "(masz GTK {4}.{5} i libadwaita {6}.{7}). Zaktualizuj system."
             ).format(*MIN_GTK, *MIN_ADW, *gtk, *adw)
    print(msg, file=sys.stderr)
    try:
        subprocess.run(["notify-send", "Linux iCloud Photos", msg], check=False)
    except OSError:
        pass
    sys.exit(1)


if __name__ == "__main__":
    try:
        PICK, _argv = pick.parse_cli(sys.argv)
        OPEN, _argv = parse_open(_argv)
    except ValueError as e:
        print(f"linux-icloud-photos: {e}", file=sys.stderr)
        sys.exit(2)
    if PICK is not None:
        backend.READ_ONLY = True
        OPEN = None
    check_versions()
    _app = App()
    if OPEN is not None:
        # aplikacja już działa: przekaż prośbę otwartemu oknu i zakończ ten proces
        _app.register(None)
        if _app.get_is_remote():
            key = "album" if "album" in OPEN else "date"
            _app.activate_action(f"open-{key}", GLib.Variant.new_string(OPEN[key]))
            _app.activate()
            sys.exit(0)
        _app.pending_open = OPEN
    rc = _app.run(_argv)
    if PICK is not None and not _app.picked:  # okno zamknięte bez wyboru
        try:
            pick.write_result(PICK["out"], [], [], cancelled=True)
        except OSError:
            pass
        rc = 1
    sys.exit(rc)
