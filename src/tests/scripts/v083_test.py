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
DIMS={0:((4000,3000),1,1.333),1:((4000,3000),6,0.75),2:((4000,2250),1,1.778),3:((3000,3000),1,1.0),4:((4000,3000),1,0.75)}  # [4]: metadane kłamią, miniatura jest pionowa
class FA2(FA):
    def __init__(s,i,video=False,live=False):
        super().__init__(i,video,live); d=DIMS[i%5]; s.dimensions=d[0]; s._asset_record={"fields":{"orientation":{"value":d[1]}}}; s.real=d[2]
class Fake10(Fake8):
    def iter_assets(self, album, newest_first=True, flip=False):
        n={"A":750}.get(album,40)
        for i in (range(n-1,-1,-1) if newest_first else range(n)): yield FA2(i, video=(i==3), live=(i==5))
    def fetch(s,a,kind):
        h=200 if kind=="thumb" else 800; w=max(40,int(h*getattr(a,"real",1.0)))
        return jpeg(w,h,0x3070b0ff)
def tl(cls): return [t for t in Gtk.Window.list_toplevels() if isinstance(t, cls)]
class T(Adw.Application):
    def do_activate(self):
        prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.win=w=A.MainWindow(self, icloud=Fake10(), autologin=False); w.set_default_size(1300,700); w.present(); w.logged_in(save=False)
        w.toast=lambda t:None; self.toasts=[]; later(3500,self.a)
    def tiles(self):
        w=self.win; out=[]
        for t in w.tiles:
            if t.bound is not None and t.get_mapped():
                ok,r=t.compute_bounds(w.grid)
                if ok: out.append((round(r.origin.y), round(r.origin.x), t, r))
        out.sort(key=lambda a:(a[0],a[1])); return out
    def centre(self, rec):
        w=self.win; r=rec[3]; return w._pt(w.grid, w.grid_sw, r.origin.x+r.size.width/2, r.origin.y+r.size.height/2)
    # ===== A) tryb zaznaczania gaśnie =====
    def a(self):
        w=self.win; T_=self.tiles(); self.T0=T_
        c0=self.centre(T_[0]); c1=self.centre(T_[1])
        g=G(CTRL); w._rb_begin(g,*c0); w._rb_end(g,0,0)
        step("A1_ctrl_click_on", lambda: (w.select_mode, len(w.selected)))
        g=G(CTRL); w._rb_begin(g,*c0); w._rb_end(g,0,0)
        step("A2_ctrl_click_off_last_exits_mode", lambda: (w.select_mode, len(w.selected), w.sel_revealer.get_reveal_child(), w.select_btn.get_active()))
        w.select_btn.set_active(True); step("A3_button_mode_empty_stays", lambda: (w.select_mode, len(w.selected)))
        for c in (c0,c1): g=G(); w._rb_begin(g,*c); w._rb_end(g,0,0)
        step("A4_two_selected", lambda: len(w.selected))
        g=G(); w._rb_begin(g,*c0); w._rb_end(g,0,0); step("A5_one_off_mode_stays", lambda: (w.select_mode, len(w.selected)))
        g=G(); w._rb_begin(g,*c1); w._rb_end(g,0,0); step("A6_last_off_exits", lambda: (w.select_mode, len(w.selected)))
        # ctrl-przeciągnięcie, które odznacza wszystko
        w.select_btn.set_active(True); a_,b_=self.centre(T_[0]), self.centre(T_[2])
        g=G(); w._rb_begin(g,*a_); w._rb_update(g,b_[0]-a_[0],b_[1]-a_[1]); w._rb_end(g,0,0)
        n=len(w.selected); step("A7_drag_selected", lambda: n)
        g=G(CTRL); w._rb_begin(g,*a_); w._rb_update(g,b_[0]-a_[0],b_[1]-a_[1]); w._rb_end(g,0,0)
        step("A8_ctrl_drag_unselects_all_exits", lambda: (w.select_mode, len(w.selected)))
        w.select_btn.set_active(True); w.selected=[T_[0][2].bound]; w._refresh_selection(); w._sel_none()
        step("A9_clear_button_keeps_mode", lambda: (w.select_mode, len(w.selected)))
        w.set_select_mode(False)
        # ===== B) układ rzędów =====
        w.layout_rows.set_active(True); later(2200,self.b)
    def b(self):
        w=self.win
        step("B1_mode_and_cfg", lambda: (w.layout_mode, w.grid is w.rows_view, A.load_cfg().get("layout"), w.fit_check.get_sensitive()))
        step("B2_rows_built", lambda: w.rows_store.get_n_items())
        T_=self.tiles(); ys=sorted({r[0] for r in T_}); W=w.grid_sw.get_width()-14
        rows={y:[r for r in T_ if r[0]==y] for y in ys}
        full=[rows[y] for y in ys[:-2]]    # pełne rzędy (bez ostatnich, mogących być ucięte)
        step("B3_row_heights_equal", lambda: all(len({round(r[3].size.height) for r in row})==1 for row in full))
        step("B4_rows_fill_width", lambda: [round(sum(r[3].size.width for r in row)+4*(len(row)-1)) for row in full][:3] + [W])
        step("B5_aspect_matches_objects", lambda: all(abs((r[3].size.width/r[3].size.height)/r[2].bound.aspect-1)<0.1 for row in full for r in row))
        step("B6_differing_widths", lambda: len({round(r[3].size.width) for row in full for r in row})>3)
        # korekta proporcji, gdy metadane kłamią ([4]) - obiekt i-ty z i%5==4 ma real=0.75
        bad=[r[2].bound for r in T_ if r[2].bound.asset.i%5==4]
        step("B7_aspect_corrected_from_thumbnail", lambda: [round(o.aspect,2) for o in bad[:3]])
        self.first_row=w.rows_store.get_item(0); self.n_rows=w.rows_store.get_n_items(); self.n_items=w.store.get_n_items()
        adj=w.grid_sw.get_vadjustment(); adj.set_value(adj.get_upper()); later(2500,self.c)
    def c(self):
        w=self.win
        step("C1_incremental_append", lambda: (w.store.get_n_items()>self.n_items, w.rows_store.get_n_items()>self.n_rows, w.rows_store.get_item(0) is self.first_row))
        w.grid_sw.get_vadjustment().set_value(0)
        self.h0=w.rows_store.get_item(0).h; self.rows0=w.rows_store.get_n_items()
        w.set_tile_size(280); later(1800,self.d)
    def d(self):
        w=self.win
        step("D1_bigger_target_bigger_rows", lambda: w.rows_store.get_item(0).h>self.h0)
        w0=w.grid_sw.get_width(); w.sidebar_btn.set_active(False); later(1800, lambda: self.e(w0))
    def e(self, w0):
        w=self.win
        step("E1_width_change_relayouts", lambda: (w0, w.grid_sw.get_width(), w._rows_W, w.grid_sw.get_width()-14-w._rows_W))
        T_=self.tiles(); rec=T_[2]
        step("E2_tile_activate_opens_viewer", lambda: (w._tile_activate(rec[2]), len(tl(A.Viewer)))[1])
        for v in tl(A.Viewer): v.close()
        # zaznaczanie w rzędach: klik i ramka
        w.select_btn.set_active(True); c=self.centre(rec); g=G(); w._rb_begin(g,*c); w._rb_end(g,0,0)
        step("E3_click_selects_in_rows", lambda: len(w.selected))
        a_,b_=self.centre(T_[0]), self.centre(T_[min(5,len(T_)-1)]); g=G(); w._rb_begin(g,*a_); w._rb_update(g,b_[0]-a_[0],b_[1]-a_[1]); w._rb_end(g,0,0)
        step("E4_rubberband_in_rows", lambda: len(w.selected)>1)
        w.set_select_mode(False)
        w.sidebar_btn.set_active(True)
        w.layout_grid.set_active(True); later(1800,self.f)
    def f(self):
        w=self.win
        step("F1_back_to_grid", lambda: (w.layout_mode, w.grid is w.grid_view, A.load_cfg().get("layout"), w.fit_check.get_sensitive()))
        tl_=[t for t in w.tiles if t.bound is not None and t.get_mapped()]
        step("F2_squares_restored", lambda: {t.pic.get_size_request() for t in tl_})
        self.quit()
T(application_id="t.v83").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
