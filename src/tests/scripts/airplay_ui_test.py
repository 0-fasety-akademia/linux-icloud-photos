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
    def stream_url(s,a,ver,lan_host=None,blob=None): return f"http://{lan_host or '127.0.0.1'}:9/tok-{ver}"
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

import cast as _d, cast_gc as _g, airplay as _a
class AP:
    kind="AirPlay"; name="Salon Apple TV"; host="127.0.0.1"; control_url="airplay://AA"; needs_pairing=True
    def __init__(s): s.calls=[]; s.pin=None
    def pair_begin(s): return True
    def pair_finish(s, pin): s.pin=pin; ok = pin=="1234"; s.needs_pairing = not ok; return ok
    def play_uri(s, uri, title, mime, video=False): s.calls.append((uri.split("/")[-1], mime, video))
    def stop(s): s.stopped=True
ap=AP()
_d.discover=lambda: [FR("[LG] OLED","DLNA")]; _g.discover=lambda: [FR("Kuchnia","Chromecast")]; _a.discover=lambda: [ap]
def tl(cls): return [t for t in Gtk.Window.list_toplevels() if isinstance(t, cls)]
class T(Adw.Application):
    def do_activate(self):
        self.win=w=A.MainWindow(self, icloud=Fake2(), autologin=False); w.set_default_size(1200,700); w.present(); w.logged_in(save=False)
        self.toasts=[]; w.toast=lambda t:self.toasts.append(t); later(2500,self.a)
    def a(self):
        w=self.win; w._cast_scan(); later(900,self.b)
    def b(self):
        w=self.win
        step("rows", lambda: [r.get_child().get_text() for r in [w.cast_list.get_row_at_index(i) for i in range(4)] if r])
        step("airplay_in_list", lambda: any("AirPlay" in r.get_child().get_text() for r in [w.cast_list.get_row_at_index(i) for i in range(4)] if r))
        row=[r for r in [w.cast_list.get_row_at_index(i) for i in range(4)] if r and "AirPlay" in r.get_child().get_text()][0]
        step("pick_airplay_opens_pairing", lambda: (w._cast_pick(None,row), None)[1]); later(500,self.c)
    def c(self):
        w=self.win; d=tl(A.PairingDialog)
        step("pairing_dialog_open", lambda: len(d))
        step("pin_entry_enabled", lambda: (d[0].entry.get_sensitive(), d[0].status.get_text()))
        step("target_not_set_before_pairing", lambda: w.cast_target is None)
        d[0].entry.set_text("0000"); d[0]._go(); later(500,self.d)
    def d(self):
        w=self.win; d=tl(A.PairingDialog)
        step("wrong_pin_message", lambda: (d[0].status.get_text()[:30], d[0].go_btn.get_sensitive(), w.cast_target is None))
        d[0].entry.set_text("1234"); d[0]._go(); later(600,self.e)
    def e(self):
        w=self.win
        step("pin_saved_to_target", lambda: ap.pin)
        step("dialog_closed_target_set", lambda: (len(tl(A.PairingDialog)), w.cast_target is ap, w.cast_btn.has_css_class("suggested-action")))
        byi=lambda n: [w.store.get_item(k) for k in range(w.store.get_n_items()) if w.store.get_item(k).asset.i==n]
        step("cast_photo_to_airplay", lambda: (w.cast_asset(w.store.get_item(10).asset), None)[1])
        later(800,self.f)
    def f(self):
        w=self.win
        step("airplay_calls_photo", lambda: ap.calls)
        step("no_second_pairing_after_paired", lambda: (w._cast_pick(None, [r for r in [w.cast_list.get_row_at_index(i) for i in range(4)] if r and "AirPlay" in r.get_child().get_text()][0]), len(tl(A.PairingDialog)))[1])
        step("stop", lambda: (w._cast_stop(), getattr(ap,"stopped",False), w.cast_target)[1:])
        self.quit()
T(application_id="t.ap").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
