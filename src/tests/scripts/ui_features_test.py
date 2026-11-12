import sys, os, traceback
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); gi.require_version("GdkPixbuf","2.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GdkPixbuf
from datetime import datetime, timedelta, timezone
import app as A

def jpeg(w,h,color):
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h); pb.fill(color)
    ok, data = pb.save_to_bufferv("jpeg", ["quality"], ["80"]); return bytes(data)
BASE = datetime(2020,1,1,tzinfo=timezone.utc)
class FA:
    def __init__(s,i,video=False,live=False):
        s.id=f"id{i}"; s.i=i; s.filename=f"IMG_{i:04d}.{'MOV' if video else 'JPG'}"; s.video=video; s.live=live
        s.asset_date = BASE+timedelta(days=i)
        s.versions = {"original":{}, "medium":{}, "thumb":{}}
class FakeR:
    name="[LG] TV"; host="127.0.0.1"; control_url="http://x/ctl"
    def __init__(s): s.calls=[]; s.stopped=False
    def play_uri(s, uri, title, mime, video=False): s.calls.append((uri,title,mime,video))
    def stop(s): s.stopped=True
class Fake:
    uploads=[]
    def albums(self): return [("All Photos","A"),("Favorites","F"),("Videos","V"),("Live","L"),("Selfies","S"),("Podróż 2024","P"),("Rodzina","R"),("Alpy","Q")]
    def total(self, album): return {"A":750}.get(album, 40)
    def iter_assets(self, album, newest_first=True, flip=False):
        n={"A":750}.get(album,40); desc=(newest_first!=flip)
        if album=="R": desc=not desc          # album o odwrotnej semantyce kierunku
        for i in (range(n-1,-1,-1) if desc else range(n)):
            yield FA(i, video=(i==3), live=(i==5))
    is_video=staticmethod(lambda a:a.video); is_live=staticmethod(lambda a:a.live)
    asset_date=staticmethod(lambda a:a.asset_date)
    live_version=staticmethod(lambda a:"medium_video" if a.live else None)
    video_version=staticmethod(lambda a,c:"medium")
    def fetch(s,a,kind): return jpeg(240 if kind=="thumb" else 1200, 240 if kind=="thumb" else 800, 0x3070b0ff)
    def fetch_original(s,a): return jpeg(2400,1600,0x2288ccff)
    def album_cover(s,key,album): return jpeg(120,120,0xc06030ff)
    def stream_url(s,a,ver,lan_host=None): return f"http://{lan_host or '127.0.0.1'}:9/tok-{ver}"
    def lan_ip_for(s,h): return "192.168.1.50"
    def upload(s,path,album=None): Fake.uploads.append((os.path.basename(path), album)); 
R={}
def step(name, fn):
    try: R[name]=fn()
    except Exception: R[name]="EXC "+traceback.format_exc().splitlines()[-1]
    print(name,"->",R[name],flush=True)
def later(ms, fn): GLib.timeout_add(ms, lambda: (fn(), False)[1])


class Fake2(Fake):
    exif_data = {"Make":"Apple","Model":"iPhone 15 Pro","LensModel":"back triple camera","FNumber":"f/1.8","ExposureTime":"1/120 s","ISO":64,"FocalLength":"6.9 mm","DateTimeOriginal":"2026:08:30 14:05:11"}
    def asset_info(self, a): return {"filename":a.filename,"asset_date":a.asset_date,"added_date":a.asset_date,"size":3_400_000,"dimensions":(4032,3024),"video":a.video,"live":a.live,"gps":(35.34,27.08) if a.i%2==0 else None}
    def read_exif(self, a, original=False): return self.exif_data if (a.i!=7 or original) else {}
    def fetch_live(self, a, ver): return os.path.join(os.environ["TEST_TMP"], "test.ogv")
    def reverse_geocode(self, lat, lon): return "Kos, Grecja"
import cast as _dl, cast_gc as _gc
class FR:
    def __init__(s,n,k): s.name=n; s.kind=k; s.host="127.0.0.1"; s.control_url=n
_dl.discover=lambda: [FR("[LG] OLED","DLNA")]; _gc.discover=lambda: [FR("Salon","Chromecast")]

import tempfile
class PyiCloudFailedLoginException(Exception): pass
class Fake8(Fake2):
    expired=False; logins=0
    def probe(s):
        if s.expired: raise PyiCloudFailedLoginException("Invalid global session")
        return 750
    def login(s, aid, pw): s.logins+=1; return "2fa"
    def verify_2fa(s, code): return code=="123456"
    def iter_jump(s, album, ts, newest_first=True):
        n={"A":750}.get(album,40); last=min(n-1, int((ts-BASE.timestamp())//86400))
        idx = range(last,-1,-1) if newest_first else range(max(0,int((ts-BASE.timestamp())//86400)), n)
        for i in idx: yield FA(i)
    def add_to_album(s, album, assets, progress=None): s.added=(album,[a.id for a in assets]); return len(assets), [], []
    def set_favorite(s, assets, value, progress=None): s.fav=(value,[a.id for a in assets]); return len(assets), []
    def save_originals(s, assets, folder, progress=None): s.saved=(folder, len(assets)); return len(assets), []
class KR:
    @staticmethod
    def get_password(svc, aid): return "pw"
    @staticmethod
    def set_password(*a): pass
class G:
    def __init__(s, state=0): s.state=state; s.claimed=None
    def get_current_event_state(s): return s.state
    def set_state(s, st): s.claimed=st
CTRL=Gdk.ModifierType.CONTROL_MASK
def tl(cls): return [t for t in Gtk.Window.list_toplevels() if isinstance(t, cls)]

prov = Gtk.CssProvider()
class Fake12(Fake8):
    def __init__(s): s.add_calls=[]
    def add_to_album(s, album, assets, progress=None):
        s.add_calls.append((album,[a.id for a in assets])); return len(assets), [], []
def kids(w):
    out=[]; c=w.get_first_child()
    while c is not None: out.append(c); c=c.get_next_sibling()
    return out
def labels(box):
    out=[]
    for c in kids(box):
        if isinstance(c, Gtk.Separator): out.append("---")
        elif isinstance(c, Gtk.Button):
            ch=c.get_child(); out.append(ch.get_text() if isinstance(ch, Gtk.Label) else (c.get_label() or "?"))
    return out
def popover_of(widget):
    pops=[c for c in kids(widget) if isinstance(c, Gtk.Popover)]
    return pops[-1] if pops else None

def alphas(widget, points):
    """Przezroczystość (kanał alfa 0-255) wyrenderowanego okna w podanych punktach."""
    p = Gtk.WidgetPaintable.new(widget); w, h = widget.get_width(), widget.get_height()
    snap = Gtk.Snapshot(); p.snapshot(snap, w, h)
    tex = widget.get_native().get_renderer().render_texture(snap.to_node(), None)
    d = Gdk.TextureDownloader.new(tex); d.set_format(Gdk.MemoryFormat.R8G8B8A8)
    data, stride = d.download_bytes(); b = data.get_data()
    return [b[y * stride + x * 4 + 3] for x, y in points]
class FakeR(Fake12):
    refreshes = 0
    refresh_fail = False
    def refresh_library(self):
        if self.refresh_fail: raise RuntimeError("sieć niedostępna")
        self.refreshes += 1
    def albums(self):
        base = super().albums()
        return base + [("Nowy album", "N")] if self.refreshes else base
class T(Adw.Application):
    def do_activate(self):
        prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.fk=FakeR(); self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,700); w.present(); w.logged_in(save=False)
        self.toasts=[]; w.toast=lambda t:self.toasts.append(t); later(3500,self.a)
    # ---- przycisk pokazu slajdów: nie ma go na belce, jest wewnątrz albumu ----
    def a(self):
        w=self.win
        step("no_slideshow_button_in_header", lambda: hasattr(w, "slide_btn"))
        step("refresh_button_in_header", lambda: (w.refresh_btn.get_visible(), w.refresh_btn.get_tooltip_text(), w.refresh_btn.get_sensitive()))
        step("other_header_buttons_visible", lambda: (w.info_btn.get_visible(), w.sort_btn.get_visible(), w.select_btn.get_visible()))
        T_=[t for t in w.tiles if t.bound is not None and t.get_mapped()]
        self.obj=T_[2].bound; self.pos=w.store.find(self.obj)[1]
        w.show_context_menu(T_[2], 20, 20, self.obj); pop=popover_of(T_[2])
        step("context_menu_has_slideshow", lambda: [l for l in labels(pop.get_child()) if "slajdów" in l])
        w._slideshow_from(self.obj); later(900, self.a2)
    def a2(self):
        s=tl(A.Slideshow)
        step("slideshow_from_context_menu_starts_at_photo", lambda: (len(s), s[0].i == self.pos if s else None))
        for x in s: x.close()
        later(300, self.b)
    def b(self):
        w=self.win; v=A.Viewer(w, 3); v.present(); self.v=v; later(800, self.c)
    def c(self):
        w=self.win; v=self.v
        step("viewer_has_slideshow_button", lambda: (v.show_btn.get_visible(), v.show_btn.get_tooltip_text(), v.album_btn.get_visible(), v.info_btn.get_visible()))
        step("viewer_button_order", lambda: [type(c).__name__ for c in kids(v.show_btn.get_parent())])
        v._start_slideshow_here(); later(900, self.d)
    def d(self):
        w=self.win
        s=tl(A.Slideshow)
        step("slideshow_opened_from_viewer", lambda: (len(s), s[0].i == 3 if s else None, self.v.get_visible()))
        for x in s: x.close()
        later(300, self.e)
    # ---- przezroczystość ----
    def e(self):
        w=self.win; self.pts=[(130, 450), (700, 8)]
        step("glass_off_by_default", lambda: (w.glass, w.has_css_class("glass"), w.backdrop.strength))
        step("glass_off_window_opaque", lambda: [a == 255 for a in alphas(w, self.pts)])
        w.set_glass(80); later(900, self.f)
    def f(self):
        w=self.win
        step("glass_on_class_and_backdrop", lambda: (w.glass, w.has_css_class("glass"), w.backdrop.strength > 0, w.backdrop.tex is not None))
        step("glass_on_window_translucent", lambda: [a < 255 for a in alphas(w, self.pts)])
        step("glass_on_not_fully_transparent", lambda: [a > 60 for a in alphas(w, self.pts)])
        w.set_glass(20); later(700, self.f2)
    def f2(self):
        w=self.win; self.a20=alphas(w, self.pts)[0]; w.set_glass(100); later(700, self.f3)
    def f3(self):
        w=self.win; a100=alphas(w, self.pts)[0]
        step("glass_100_more_transparent_than_20_but_still_readable", lambda: (self.a20 > a100, a100 >= 190))
        step("glass_100_header_and_sidebar_readable", lambda: [a >= 190 for a in alphas(w, self.pts)])
        d=A.SettingsDialog(w); d.present(); self.d=d
        step("settings_has_glass_scale", lambda: (d.glass_scale.get_value(), d.glass_scale.get_adjustment().get_upper()))
        d.glass_scale.set_value(40)
        step("slider_applies_and_saves", lambda: (w.glass, A.load_cfg().get("glass"), w.has_css_class("glass")))
        d.glass_scale.set_value(0); later(500, self.g)
    def g(self):
        w=self.win; d=self.d
        step("slider_zero_turns_it_off", lambda: (w.glass, w.has_css_class("glass"), A.load_cfg().get("glass"), w.backdrop.strength))
        step("off_again_opaque", lambda: [a == 255 for a in alphas(w, self.pts)])
        step("language_dropdown_options", lambda: [d.lang_dd.get_model().get_string(i) for i in range(d.lang_dd.get_model().get_n_items())])
        for idx in (3, 4, 2, 1, 0):
            d.lang_dd.set_selected(idx)
            step(f"language_choice_{idx}_saved", lambda: A.load_cfg().get("language"))
        step("language_toast", lambda: self.toasts[-1])
        d.close()
        row=w._find_row("Rodzina"); row.get_parent().select_row(row); later(1500, self.h)
    # ---- odświeżanie biblioteki ----
    def h(self):
        w=self.win; fk=self.fk
        step("album_selected_before_refresh", lambda: (w.cur_title, w._selected_album_key()))
        step("new_album_absent_before", lambda: w._find_row("Nowy album") is None)
        w.refresh_library(); w.refresh_library()   # drugie wywołanie w trakcie ma być zignorowane
        step("button_disabled_while_refreshing", lambda: w.refresh_btn.get_sensitive())
        later(1800, self.i)
    def i(self):
        w=self.win; fk=self.fk
        step("backend_refreshed_once", lambda: fk.refreshes)
        step("new_album_appears", lambda: w._find_row("Nowy album") is not None)
        step("selected_album_kept", lambda: (w.cur_title, w._selected_album_key()))
        step("album_reloaded_has_items", lambda: w.store.get_n_items() > 0)
        step("button_enabled_again", lambda: w.refresh_btn.get_sensitive())
        step("toast_refreshed", lambda: self.toasts[-1])
        step("f5_handled", lambda: w._on_key(None, Gdk.KEY_F5, 0, 0)); later(1800, self.j)
    def j(self):
        w=self.win; fk=self.fk
        step("f5_refreshed_again", lambda: fk.refreshes)
        step("ctrl_r_handled", lambda: w._on_key(None, Gdk.KEY_r, 0, Gdk.ModifierType.CONTROL_MASK)); later(1800, self.k)
    def k(self):
        w=self.win; fk=self.fk
        step("ctrl_r_refreshed_again", lambda: fk.refreshes)
        fk.refresh_fail=True; w.refresh_library(); later(1500, self.l)
    def l(self):
        w=self.win; fk=self.fk
        step("error_toast", lambda: self.toasts[-1])
        step("error_keeps_albums_and_selection", lambda: (w._find_row("Nowy album") is not None, w._selected_album_key(), w.refresh_btn.get_sensitive()))
        w.session_expired()
        step("refresh_hidden_after_session_expired", lambda: w.refresh_btn.get_visible())
        step("refresh_ignored_when_logged_out", lambda: (w.refresh_library(), fk.refreshes)[1])
        self.quit()
T(application_id="t.feat").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
