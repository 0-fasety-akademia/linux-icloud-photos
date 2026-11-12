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

class Fake13(Fake12):
    fail_ids=set()
    def __init__(s): super().__init__(); s.delete_calls=[]
    def delete_assets(s, assets, progress=None):
        s.delete_calls.append([a.id for a in assets]); ok=[a for a in assets if a.id not in s.fail_ids]; bad=[f"{a.filename}: HTTP 500" for a in assets if a.id in s.fail_ids]
        if progress: progress(len(assets), len(assets))
        return ok, bad
class T(Adw.Application):
    def do_activate(self):
        prov=Gtk.CssProvider(); prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.fk=Fake13(); self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,700); w.present(); w.logged_in(save=False)
        self.toasts=[]; w.toast=lambda t:self.toasts.append(t); later(3500,self.a)
    def tiles(self): return [t for t in self.win.tiles if t.bound is not None and t.get_mapped()]
    def a(self):
        w=self.win; fk=self.fk; T_=self.tiles()
        step("trash_button_exists_disabled_without_selection", lambda: (w.del_btn.get_sensitive(), w.del_btn.has_css_class("destructive-action")))
        w.set_select_mode(True); w.selected=[T_[0].bound,T_[1].bound,T_[2].bound]; w._refresh_selection()
        step("trash_button_enabled_with_selection", lambda: w.del_btn.get_sensitive())
        n0=w.store.get_n_items(); self.n0=n0; self.ids3=[o.asset.id for o in w.selected]; w.total=750
        step("click_trash_asks_first_nothing_deleted_yet", lambda: (w._sel_delete(), fk.delete_calls, w.store.get_n_items()==n0)[1:])
        step("delete_key_in_select_mode_handled", lambda: (w._on_key(None, Gdk.KEY_Delete, 0, 0), fk.delete_calls)[1])
        for t in [t for t in Gtk.Window.list_toplevels() if "AlertDialog" in type(t).__name__ or "Dialog" in type(t).__name__]: pass
        # potwierdzenie (symulacja wyboru „Usuń”) - wywołanie tego, co robi przycisk w oknie
        w._do_delete([o.asset for o in w.selected]); later(900,self.b)
    def b(self):
        w=self.win; fk=self.fk
        step("backend_called_with_selected_ids", lambda: fk.delete_calls[-1]==self.ids3)
        step("removed_from_view", lambda: (self.n0, w.store.get_n_items()))
        step("deleted_ids_absent", lambda: not any(w.store.get_item(i).asset.id in self.ids3 for i in range(w.store.get_n_items())))
        step("selection_cleared", lambda: len(w.selected))
        step("total_and_counter_updated", lambda: (w.total, w.count.get_text()))
        step("toast_moved", lambda: self.toasts[-1])
        # częściowy błąd
        w.selected=[w.store.get_item(0), w.store.get_item(1)]; fk.fail_ids={w.store.get_item(1).asset.id}; n1=w.store.get_n_items(); self.n1=n1
        w._do_delete([o.asset for o in w.selected]); later(900,self.c)
    def c(self):
        w=self.win
        step("partial_failure_removes_only_confirmed", lambda: (self.n1, w.store.get_n_items()))
        step("partial_failure_toast_has_errors", lambda: self.toasts[-1])
        self.fk.fail_ids=set()
        # nic się nie udało
        a=w.store.get_item(0).asset; self.fk.fail_ids={a.id}; n=w.store.get_n_items(); w._do_delete([a]); self.n2=n; later(900,self.d)
    def d(self):
        w=self.win; fk=self.fk
        step("all_failed_nothing_removed_and_message", lambda: (self.n2, w.store.get_n_items(), self.toasts[-1]))
        fk.fail_ids=set()
        # album „Ostatnio usunięte”: bez usuwania
        w.cur_title=A.tr("Ostatnio usunięte"); w._refresh_selection()
        calls=len(fk.delete_calls)
        step("trash_album_confirm_refuses", lambda: (w.confirm_delete([w.store.get_item(0).asset]), len(fk.delete_calls)==calls, self.toasts[-1][:40])[1:])
        w.selected=[w.store.get_item(0)]; w._refresh_selection()
        step("trash_album_button_disabled", lambda: w.del_btn.get_sensitive())
        T_=self.tiles(); w.show_context_menu(T_[0],20,20,T_[0].bound)
        pop=[c for c in self.kids(T_[0]) if isinstance(c, Gtk.Popover)][-1]
        step("trash_album_context_menu_has_no_delete", lambda: [l for l in self.labels(pop.get_child()) if "Usuń" in l or "Delete" in l])
        w.cur_title="Wszystkie zdjęcia"; w.selected=[]; w._refresh_selection(); w.set_select_mode(False)
        w.show_context_menu(T_[1],20,20,T_[1].bound)
        pop=[c for c in self.kids(T_[1]) if isinstance(c, Gtk.Popover)][-1]
        step("normal_album_context_menu_has_delete_last", lambda: self.labels(pop.get_child())[-1])
        # podgląd
        v=A.Viewer(w, 3); v.present(); self.v=v; self.cur=w.store.get_item(3).asset.id; self.nxt=w.store.get_item(4).asset.id; later(700,self.e)
    def e(self):
        w=self.win; v=self.v
        step("viewer_trash_button_visible", lambda: v.trash_btn.get_visible())
        step("viewer_delete_key_asks_first", lambda: (v.on_key(None, Gdk.KEY_Delete,0,0), len(self.fk.delete_calls))[1]>=0)
        w._do_delete([w.store.get_item(3).asset]); later(1200,self.f)
    def f(self):
        w=self.win; v=self.v
        step("viewer_moves_to_next_after_delete", lambda: (v._cur_id==self.nxt, v.get_visible()))
        # rzędy
        w.layout_rows.set_active(True); later(1800,self.g)
    def g(self):
        w=self.win; rows=w.rows_store.get_n_items(); self.rows=rows
        T_=self.tiles(); items=w.store.get_n_items(); self.items=items
        w._do_delete([T_[0].bound.asset, T_[1].bound.asset, T_[2].bound.asset, T_[3].bound.asset]); later(1800,self.h)
    def h(self):
        w=self.win
        step("rows_view_updated_after_delete", lambda: (self.items, w.store.get_n_items(), sum(len(w.rows_store.get_item(i).items) for i in range(w.rows_store.get_n_items()))))
        for v in [self.v]: v.close()
        self.quit()
    @staticmethod
    def kids(w):
        out=[]; c=w.get_first_child()
        while c is not None: out.append(c); c=c.get_next_sibling()
        return out
    def labels(self, box):
        out=[]
        for c in self.kids(box):
            if isinstance(c, Gtk.Separator): out.append("---")
            elif isinstance(c, Gtk.Button):
                ch=c.get_child(); out.append(ch.get_text() if isinstance(ch, Gtk.Label) else "?")
        return out
T(application_id="t.del").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
