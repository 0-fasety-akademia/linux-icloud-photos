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
class T(Adw.Application):
    def do_activate(self):
        prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.fk=Fake12(); self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,700); w.present(); w.logged_in(save=False)
        w.recent_albums=[]; self.toasts=[]; w.toast=lambda t:self.toasts.append(t); later(3500,self.a)
    # ---- okno wyboru albumu z wyszukiwarką ----
    def a(self):
        w=self.win; assets=[w.store.get_item(i).asset for i in range(2)]
        d=A.AddToAlbumDialog(w, assets); d.present(); self.d=d
        step("dialog_rows_alphabetical_no_recents", lambda: [r.name for r in d.rows])
        step("add_disabled_until_selected", lambda: d.go.get_sensitive())
        d.search.set_text("pod"); later(500,self.b)
    def b(self):
        d=self.d
        step("search_filters", lambda: [r.name for r in d.rows if d._filter(r)])
        step("enter_selects_first_match", lambda: (d._on_enter(), d.list.get_selected_row().name, d.go.get_sensitive())[1:])
        step("second_enter_adds", lambda: (d._on_enter(), None)[1]); later(900,self.c)
    def c(self):
        w=self.win; d=self.d; fk=self.fk
        step("added_to_searched_album", lambda: (fk.add_calls[-1][0], len(fk.add_calls[-1][1])))
        step("dialog_status_and_close_label", lambda: (d.status.get_text(), d.cancel.get_label()))
        step("recent_remembered_and_saved", lambda: (w.recent_albums, A.load_cfg().get("recent_albums")))
        d.close()
        # limit 3 i kolejność
        w.recent_albums=[]; [w.remember_album(n) for n in ("X1","X2","X3","X4","X2")]
        step("recent_cap3_order", lambda: w.recent_albums)
        w.recent_albums=["Rodzina","Alpy"]
        d2=A.AddToAlbumDialog(w, [w.store.get_item(0).asset]); d2.present(); self.d2=d2
        step("dialog_recents_first", lambda: ([r.name for r in d2.rows], [r.recent for r in d2.rows]))
        d2.close()
        # ---- wpisy menu ----
        one=lambda: [w.store.get_item(0).asset]
        w.recent_albums=[]
        step("menu_no_recents", lambda: [l for l,_ in w.album_menu_entries(one)])
        w.recent_albums=["Rodzina","Nieistniejący","Alpy"]
        step("menu_with_recents_skips_missing", lambda: [l for l,_ in w.album_menu_entries(one)])
        three=lambda: [w.store.get_item(i).asset for i in range(3)]
        step("menu_multi_suffix", lambda: [l for l,_ in w.album_menu_entries(three)])
        ents=w.album_menu_entries(one)
        step("menu_first_entry_adds_directly", lambda: (ents[0][1](), None)[1]); later(900,self.e)
    def e(self):
        w=self.win; fk=self.fk
        step("direct_add_called", lambda: (fk.add_calls[-1][0], fk.add_calls[-1][1]))
        step("direct_add_remembered_first", lambda: w.recent_albums[0])
        step("direct_add_toast", lambda: self.toasts[-1])
        ents=w.album_menu_entries(lambda: [w.store.get_item(0).asset])
        step("menu_other_opens_dialog", lambda: (ents[-1][1](), len([t for t in Gtk.Window.list_toplevels() if isinstance(t, A.AddToAlbumDialog)]))[1])
        for t in [t for t in Gtk.Window.list_toplevels() if isinstance(t, A.AddToAlbumDialog)]: t.close()
        # ---- prawdziwe menu prawego przycisku ----
        T_=[t for t in w.tiles if t.bound is not None and t.get_mapped()][:4]; self.T_=T_
        w.show_context_menu(T_[0], 20, 20, T_[0].bound); pop=popover_of(T_[0]); self.pop=pop
        step("context_menu_items", lambda: labels(pop.get_child()))
        step("context_info_first_album_before_save", lambda: (lambda L:(L[0], L.index("Zapisz oryginał jako…")>max(i for i,l in enumerate(L) if "albumu" in l)))(labels(pop.get_child())))
        pop.popdown()
        # zaznaczenie obejmujące klikniętą fotografię
        w.set_select_mode(True); w.selected=[T_[0].bound,T_[1].bound,T_[2].bound]; w._refresh_selection()
        w.show_context_menu(T_[0], 20, 20, T_[0].bound); pop2=popover_of(T_[0])
        step("context_menu_selection_suffix", lambda: [l for l in labels(pop2.get_child()) if "albumu" in l])
        btn=[c for c in kids(pop2.get_child()) if isinstance(c, Gtk.Button) and "Rodzina" in (c.get_child().get_text() if isinstance(c.get_child(), Gtk.Label) else "")][0]
        step("context_click_adds_all_selected", lambda: (btn.emit("clicked"), None)[1]); later(900,self.f)
    def f(self):
        w=self.win; fk=self.fk; w.set_select_mode(False)
        step("selection_added", lambda: (fk.add_calls[-1][0], len(fk.add_calls[-1][1])))
        # ---- podgląd ----
        v=A.Viewer(w, 5); v.present(); self.v=v; later(900,self.g)
    def g(self):
        w=self.win; v=self.v; fk=self.fk
        step("viewer_topbar_buttons_together", lambda: (v.album_btn.get_parent() is v.info_btn.get_parent(), v.live_btn.get_parent() is v.info_btn.get_parent()))
        step("viewer_album_menu_entries", lambda: (v._rebuild_album_menu(), labels(v.album_box))[1])
        b=[c for c in kids(v.album_box) if isinstance(c, Gtk.Button)][0]
        step("viewer_click_adds_current", lambda: (b.emit("clicked"), None)[1]); later(800,self.h)
    def h(self):
        w=self.win; v=self.v; fk=self.fk
        step("viewer_added_current_photo", lambda: (fk.add_calls[-1][0], fk.add_calls[-1][1]==[v.store.get_item(v.index).asset.id]))
        step("viewer_key_a_opens_menu", lambda: (v.on_key(None, Gdk.KEY_a, 0, 0), v.album_pop.get_visible())[1])
        v.album_pop.popdown()
        step("viewer_right_click_menu_has_album", lambda: (v.zv.on_context(30,30), [l for l in labels(popover_of(v.zv).get_child()) if "albumu" in l])[1])
        self.quit()
T(application_id="t.am").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
