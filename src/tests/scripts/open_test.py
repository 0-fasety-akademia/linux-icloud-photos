import sys, os, traceback
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); gi.require_version("GdkPixbuf","2.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GdkPixbuf
from datetime import datetime, timedelta, timezone
import app as A

# Prośby innych aplikacji (0.15.0, linux-skytrack): --open-album / --open-date otwierają album albo
# skaczą do dni podróży; nieznany album -> odświeżenie listy i komunikat.

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
class Fake15(Fake12):
    refreshed = 0
    extra = []
    def albums(self): return Fake12.albums(self) + self.extra
    def refresh_library(self): Fake15.refreshed += 1
class T(Adw.Application):
    def do_activate(self):
        prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.fk=Fake15(); self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,700); w.present()
        self.toasts=[]; w.toast=lambda t:self.toasts.append(t)
        w.open_request({"album": "Rodzina"})          # zanim albumy się wczytają
        step("pending_before_login", lambda: (w._pending_open, w._albums_ready))
        w.logged_in(save=False); later(3000, self.a)
    def a(self):
        w=self.win
        step("album_opened", lambda: (w.cur_title, w.exp_user.get_expanded(), w._pending_open))
        w.open_request({"date": "2020-03-01..2020-03-05"}); later(2500, self.b)
    def b(self):
        w=self.win
        step("date_jump", lambda: (w.wtitle.get_subtitle(), w.cur_title, self.toasts[-1]))
        step("first_after_jump", lambda: str(w.store.get_item(0).asset.asset_date.date()))
        Fake15.extra = [("✈ Dubaj 2025", "D")]
        w.open_request({"album": "✈ Dubaj 2025"}); later(3000, self.c)
    def c(self):
        w=self.win
        step("new_album_after_refresh", lambda: (Fake15.refreshed, w.cur_title))
        w.open_request({"album": "Nie ma"}); later(3000, self.d)
    def d(self):
        w=self.win
        step("missing_album_toast", lambda: (Fake15.refreshed, self.toasts[-1]))
        w.open_request({"date": "jutro"}); later(300, self.e)
    def e(self):
        step("bad_date_toast", lambda: self.toasts[-1])
        self.quit()
T(application_id="test.open15", flags=Gio.ApplicationFlags.NON_UNIQUE).run([])
