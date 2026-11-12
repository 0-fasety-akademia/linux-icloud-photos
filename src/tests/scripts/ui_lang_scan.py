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

import re, os
import cast as _dl, cast_gc as _gc, airplay as _ap
class FR:
    def __init__(s,n,k): s.name=n; s.kind=k; s.host="127.0.0.1"; s.control_url=n
class AP:
    kind="AirPlay"; name="Living room Apple TV"; host="127.0.0.1"; control_url="airplay://AA"; needs_pairing=True
    def pair_begin(s): return True
    def pair_finish(s, pin): return pin=="1234"
    def play_uri(s,*a,**k): pass
    def stop(s): pass
_dl.discover=lambda: [FR("[LG] OLED","DLNA")]; _gc.discover=lambda: [FR("Kitchen","Chromecast")]; _ap.discover=lambda: [AP()]
FAKE_DATA={"Podróż 2024","Rodzina","Alpy"}   # nazwy albumów z atrapy (dane użytkownika, nie interfejs)
PL_COMMON = r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]"
PL_WORDS = ["Anuluj", "Zamknij", "Szukaj", "Ustawienia", "Wyczyść", "Dodaj", "Dodano", "Zdjęcia", "Zdjęcie",
            "Odtwórz", "Zapisz", "Zaloguj", "Hasło", "Wyślij", "Przejdź", r"Zaznacz\w*", "Błąd", "Błędy", "Sesja",
            "Parowanie", "Sparuj", "Lokalizacja", "Obiektyw", "Ekspozycja", "Układ", "Kafelki", "Rzędy", "Małe",
            "Duże", "Ostatnio", "ostatnio", "znaleziono", "Ulubione", "Wszystkie", "Moje", "Biblioteka", "Brak",
            "brak", "jest", "się", "już", "Informacje", "Nazwa", "Rozmiar"]
# słowa wspólne z niemieckim/ukraińskim/angielskim (Album, Typ, Kod, Wideo...) pomijamy poza testem angielskim
PL_EN_ONLY = ["Wideo", "Album", "Albumy", "Typ", "Kod"]
def _rx(words): return re.compile(PL_COMMON + r"|\b(" + "|".join(words) + r")\b")
PL = _rx(PL_WORDS + PL_EN_ONLY) if os.environ.get("ICLOUD_PHOTOS_LANG", "en") == "en" else _rx(PL_WORDS)
def kids(w):
    out=[]; c=w.get_first_child()
    while c is not None: out.append(c); c=c.get_next_sibling()
    return out
def texts(widget, acc, where):
    seen=set()
    def walk(w):
        if id(w) in seen: return
        seen.add(id(w))
        def add(t):
            if t and t.strip(): acc.setdefault(t.strip(), where)
        if isinstance(w, Gtk.Label): add(w.get_text())
        if isinstance(w, (Gtk.Button, Gtk.CheckButton)): add(w.get_label() if hasattr(w,"get_label") else None)
        try: add(w.get_tooltip_text())
        except Exception: pass
        if isinstance(w, (Gtk.Entry, Gtk.SearchEntry)):
            try: add(w.get_placeholder_text())
            except Exception: pass
        if isinstance(w, Gtk.DropDown):
            m=w.get_model()
            for i in range(m.get_n_items()):
                try: add(m.get_string(i))
                except Exception: pass
        if isinstance(w, Adw.WindowTitle): add(w.get_title()); add(w.get_subtitle())
        if isinstance(w, Gtk.Window): add(w.get_title())
        if isinstance(w, Gtk.MenuButton) and w.get_popover() is not None: walk(w.get_popover())
        if isinstance(w, Gtk.Popover) and w.get_child() is not None: walk(w.get_child())
        for c in kids(w): walk(c)
    walk(widget)
class T(Adw.Application):
    def do_activate(self):
        prov=Gtk.CssProvider(); prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.fk=Fake12(); self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,700); w.present()
        self.acc={}; self.toasts=[]; w.toast=lambda t:self.toasts.append(t)
        texts(w, self.acc, "okno główne – ekran logowania")
        w.on_login(); texts(w, self.acc, "logowanie – puste pola"); w.btn.set_sensitive(True)
        w.logged_in(save=False); later(3500,self.a)
    def snap(self, where):
        for t in Gtk.Window.list_toplevels():
            texts(t, self.acc, where)
    def a(self):
        w=self.win; self.snap("okno główne (po zalogowaniu)")
        w.cast_btn.popup() if False else None
        w._cast_scan(); later(1200,self.b)
    def b(self):
        w=self.win; self.snap("popover TV po skanowaniu")
        T_=[t for t in w.tiles if t.bound is not None and t.get_mapped()][:3]
        w.show_context_menu(T_[0],20,20,T_[0].bound); self.snap("menu prawego przycisku")
        w.recent_albums=["Rodzina","Alpy"]; w.show_context_menu(T_[1],20,20,T_[1].bound); self.snap("menu prawego przycisku z ostatnimi albumami")
        w.set_select_mode(True); w.selected=[T_[0].bound,T_[1].bound]; w._refresh_selection(); w.show_context_menu(T_[0],20,20,T_[0].bound); self.snap("zaznaczanie + menu")
        w._sel_none(); w._sel_fav(True); w._sel_album(); self.snap("pasek zaznaczania / brak zaznaczenia")
        w.set_select_mode(False)
        for cls_args in ((A.SettingsDialog,(w,)), (A.UploadDialog,(w,["/tmp/a.jpg","/tmp/b.mov"])), (A.AddToAlbumDialog,(w,[w.store.get_item(0).asset])), (A.PairingDialog,(w,AP(),lambda:None)), (A.InfoDialog,(w,w.store.get_item(10)))):
            d=cls_args[0](*cls_args[1]); d.present(); self.snap(cls_args[0].__name__)
        w.play_external(w.store.get_item(0))   # brak mpv -> komunikat
        w._on_fit_toggled(w.fit_check)
        self.snap("po akcjach"); later(1200,self.c)
    def c(self):
        w=self.win; self.snap("dialogi po chwili (Info/EXIF)")
        for t in [t for t in Gtk.Window.list_toplevels() if not isinstance(t, A.MainWindow)]: t.close()
        # podgląd: zdjęcie, wideo, Live
        idx={}
        for k in range(w.store.get_n_items()):
            o=w.store.get_item(k)
            if o.is_video and "v" not in idx: idx["v"]=k
            if o.is_live and "l" not in idx: idx["l"]=k
        self.views=[A.Viewer(w, 2)]
        for key in ("v","l"):
            if key in idx: self.views.append(A.Viewer(w, idx[key]))
        for v in self.views: v.present()
        later(1500,self.d)
    def d(self):
        w=self.win
        for v in self.views:
            v._rebuild_album_menu(); v.zv.set_zoom(2.0); self.snap("podgląd (zdjęcie/wideo/Live)")
            v.on_key(None, Gdk.KEY_l, 0, 0)
        later(1200, self.e)
    def e(self):
        w=self.win; self.snap("podgląd po L (Live)")
        for v in self.views: v.close()
        sl=A.Slideshow(w,0); sl.present(); later(1500, lambda: self.f(sl))
    def f(self, sl):
        w=self.win; self.snap("pokaz slajdów"); sl.close()
        w.sidebar_btn.set_active(True); w.search.set_text("08.2021")
        later(500, self.g)
    def g(self):
        w=self.win; self.snap("wyszukiwanie daty")
        w.set_tile_size(260); w.layout_rows.set_active(True)
        w.session_expired(); self.snap("sesja wygasła (login)")
        w.say(A.tr("Wpisz kod z zaufanego urządzenia Apple."))
        self.report()
    def report(self):
        flagged={t:wh for t,wh in self.acc.items() if PL.search(t) and t not in FAKE_DATA}
        lang=os.environ.get("ICLOUD_PHOTOS_LANG","?")
        pol=[t for t in self.acc if re.search(r"[ąćęłńóśźż]", t) and t not in FAKE_DATA]

        allt=list(self.toasts)
        pol_toasts=[t for t in allt if PL.search(t) and not any(f in t for f in FAKE_DATA)]
        if lang in ("en","de","uk"):
            print(f"polish_texts_in_{lang}_ui ->", len(flagged)+len(pol_toasts))
            title={"en":"All Photos","de":"Alle Fotos","uk":"Усі фото"}[lang]
            print("sidebar_title_translated ->", title in self.acc)
            print("settings_texts_translated ->", {"en":"Settings","de":"Einstellungen","uk":"Налаштування"}[lang] in self.acc)
            for t,wh in sorted(flagged.items()): print("  *", repr(t)[:90], "<-", wh)
            for t in pol_toasts: print("  * toast:", repr(t)[:90])
        else:
            pass

        self.quit()
T(application_id="t.lang").run([])
