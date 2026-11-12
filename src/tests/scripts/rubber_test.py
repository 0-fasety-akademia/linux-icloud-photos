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
    def add_to_album(s, album, assets, progress=None): s.added=(album,[a.id for a in assets]); return len(assets), []
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
class T(Adw.Application):
    def do_activate(self):
        prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.win=w=A.MainWindow(self, icloud=Fake8(), autologin=False); w.set_default_size(1300,700); w.present(); w.logged_in(save=False)
        w.toast=lambda t:None; later(3500,self.a)
    def grid_tiles(self):
        w=self.win
        ts=[t for t in w.tiles if t.bound is not None and t.get_mapped()]
        out=[]
        for t in ts:
            ok,r=t.compute_bounds(w.grid); out.append((round(r.origin.y), round(r.origin.x), t, r))
        out.sort(key=lambda a:(a[0],a[1])); return out
    def centre(self, rec):
        w=self.win; r=rec[3]; return w._pt(w.grid, w.grid_sw, r.origin.x+r.size.width/2, r.origin.y+r.size.height/2)
    def drag(self, a, b, ctrl=False, end=True):
        w=self.win; g=G(CTRL if ctrl else 0)
        w._rb_begin(g, *a); w._rb_update(g, b[0]-a[0], b[1]-a[1])
        if end: w._rb_end(g, b[0]-a[0], b[1]-a[1])
        return g
    def a(self):
        w=self.win; T_=self.grid_tiles()
        ys=sorted({r[0] for r in T_}); xs=sorted({r[1] for r in T_})
        step("layout_rows_cols", lambda: (len(ys), len(xs)))
        cell=lambda row,col: [r for r in T_ if r[0]==ys[row] and r[1]==xs[col]][0]
        A_,D_=cell(0,0), cell(1,2)
        # 1) przeciągnięcie w trybie zwykłym: 2 wiersze x 3 kolumny
        g=G(); w._rb_begin(g, *self.centre(A_))
        step("begin_normal_not_claimed", lambda: g.claimed is None)
        a_,d_=self.centre(A_), self.centre(D_)
        w._rb_update(g, d_[0]-a_[0], d_[1]-a_[1])
        step("drag_enters_select_mode_and_claims", lambda: (w.select_mode, g.claimed is not None, w.sel_revealer.get_reveal_child()))
        step("rubber_visible_during_drag", lambda: (w.rubber.get_visible(), w.rubber.get_width()>0))
        step("selected_2x3", lambda: len(w.selected))
        step("check_marks_match", lambda: sum(1 for r in T_ if r[2].check.get_active()))
        # 2) zmniejszenie ramki zmniejsza zaznaczenie
        b_=self.centre(cell(0,1)); w._rb_update(g, b_[0]-a_[0], b_[1]-a_[1])
        step("shrink_rect_shrinks_selection", lambda: len(w.selected))
        w._rb_update(g, d_[0]-a_[0], d_[1]-a_[1]); w._rb_end(g, 0, 0)
        step("rubber_hidden_after_end", lambda: (w.rubber.get_visible(), len(w.selected)))
        # 3) dodawanie drugą ramką (bez Ctrl)
        E_,F_=cell(2,0), cell(2,1); self.drag(self.centre(E_), self.centre(F_))
        step("second_drag_adds", lambda: len(w.selected))
        # 4) Ctrl-przeciągnięcie odwraca: obejmij (1,1),(1,2) [zaznaczone] i (3,1),(3,2) [nowe]
        G1,G2=cell(1,1),cell(3,2); self.drag(self.centre(G1), self.centre(G2), ctrl=True)
        step("ctrl_drag_xor", lambda: len(w.selected))
        # 5) klik w trybie zaznaczania przełącza jedno zdjęcie (przez pick)
        w._sel_none(); H_=cell(2,3); hc=self.centre(H_)
        g=G(); w._rb_begin(g, *hc); w._rb_end(g,0,0)
        step("click_in_select_mode_toggles_on", lambda: (len(w.selected), g.claimed is not None))
        g=G(); w._rb_begin(g, *hc); w._rb_end(g,0,0)
        step("click_again_toggles_off", lambda: len(w.selected))
        # 6) Ctrl+klik w zwykłym trybie: włącza zaznaczanie
        w.set_select_mode(False)
        g=G(CTRL); w._rb_begin(g, *hc); w._rb_end(g,0,0)
        step("ctrl_click_enters_mode", lambda: (w.select_mode, len(w.selected), g.claimed is not None))
        w.set_select_mode(False)
        # 7) zwykłe kliknięcie bez przeciągania: nie claimuje, nie zaznacza (otwarcie podglądu zostaje)
        g=G(); w._rb_begin(g, *hc); w._rb_end(g,0,0)
        step("plain_click_untouched", lambda: (w.select_mode, len(w.selected), g.claimed is None))
        # 8) pasek przewijania ignorowany
        g=G(); w._rb_begin(g, w.grid_sw.get_width()-5, 100)
        step("scrollbar_press_ignored", lambda: w._rb is None)
        # 9) autoprzewijanie przy dolnej krawędzi
        w.set_select_mode(False); sh=w.grid_sw.get_height(); g=G(CTRL)
        w._rb_begin(g, 100, 100); w._rb_update(g, 50, sh-30-100)
        adj=w.grid_sw.get_vadjustment(); v0=adj.get_value(); n0=len(w.selected); rb=w._rb
        for _ in range(8): w._rb_tick(rb)
        step("autoscroll_moves_and_selects_more", lambda: (adj.get_value()>v0, len(w.selected)>=n0, len(w.selected)))
        w._rb_end(g,0,0)
        w.set_select_mode(False); w.grid_sw.get_vadjustment().set_value(0)
        g=G(); self.g=g; a_=self.centre(cell(0,0)); d_=self.centre(cell(1,2)); w._rb_begin(g,*a_); w._rb_update(g,d_[0]-a_[0],d_[1]-a_[1]); later(400,self.z)
    def z(self):
        w=self.win; r=w.rubber
        step("rubber_has_size_after_layout", lambda: (r.get_visible(), r.get_width()>50, r.get_height()>50))
        w._rb_end(self.g,0,0); step("rubber_hidden_at_end", lambda: r.get_visible()); self.quit()
T(application_id="t.rb").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
