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
class T(Adw.Application):
    def do_activate(self):
        prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; A.save_cfg(apple_id="a@b.c")
        self.fk=Fake8(); self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,760); w.present(); w.logged_in(save=False)
        self.toasts=[]; w.toast=lambda t:self.toasts.append(t); later(3500,self.a)
    # ---------- 2) skok do daty ----------
    def a(self):
        w=self.win; w.search.set_text("rod"); later(500,self.a2)
    def a2(self):
        w=self.win
        step("search_nondate_hides_jump", lambda: w.list_jump.get_visible())
        w.search.set_text("08.2021"); later(500,self.a3)
    def a3(self):
        w=self.win
        step("search_date_shows_jump", lambda: (w.list_jump.get_visible(), w.jump_row.lbl.get_text()))
        step("select_jump_row_loads", lambda: (w.list_jump.select_row(w.jump_row), None)[1]); later(1500,self.b)
    def b(self):
        w=self.win; first=w.store.get_item(0).asset.asset_date
        step("jump_aug2021_first_item", lambda: (first.date().isoformat(), first.year==2021 and first.month==8))
        step("jump_subtitle", lambda: w.wtitle.get_subtitle())
        step("jump_row_unselected", lambda: w.list_jump.get_selected_row() is None)
        step("jump_descending", lambda: all(w.store.get_item(i).asset.asset_date>=w.store.get_item(i+1).asset.asset_date for i in range(20)))
        w.search.set_text("")
        step("calendar_jump", lambda: (w.cal.select_day(GLib.DateTime.new_local(2021,3,15,0,0,0)), w._jump_from_calendar(), None)[2]); later(1500,self.c)
    def c(self):
        w=self.win; first=w.store.get_item(0).asset.asset_date
        step("calendar_first_le_target", lambda: (first.date().isoformat(), first.date().isoformat()<="2021-03-15"))
        step("oldest_first_jump", lambda: (setattr(w,"newest_first",False), w._do_jump(__import__("datetime").datetime(2021,6,1), __import__("datetime").datetime(2021,6,30,23,59,59), "cze 2021"), None)[2]); later(1500,self.d)
    def d(self):
        w=self.win; first=w.store.get_item(0).asset.asset_date; w.newest_first=True
        step("oldest_first_ge_start", lambda: first.date().isoformat()>="2021-06-01")
        w.list_primary.select_row(w.list_primary.get_row_at_index(1)); later(1400,self.e)
    # ---------- 3) zaznaczanie ----------
    def e(self):
        w=self.win
        step("subtitle_cleared_on_normal_album", lambda: w.wtitle.get_subtitle())
        tiles=[t for t in w.tiles if t.bound is not None and t.get_mapped()][:4]; self.tiles=tiles
        g=G(); step("normal_click_not_claimed", lambda: (w._tile_press(tiles[0], g), g.claimed, w.select_mode)[1:])
        g=G(CTRL); step("ctrl_click_enters_mode_and_selects", lambda: (w._tile_press(tiles[0], g), w.select_mode, len(w.selected), g.claimed is not None, w.sel_revealer.get_reveal_child())[1:])
        step("toggle_more", lambda: ([w._tile_press(t, G()) for t in tiles[1:3]], len(w.selected), w.sel_label.get_text())[1:])
        step("checks_visible_and_set", lambda: ([t.check.get_visible() for t in tiles[:3]], [t.check.get_active() for t in tiles[:4]]))
        step("toggle_off", lambda: (w._tile_press(tiles[1], G()), len(w.selected))[1])
        step("select_all", lambda: (w._sel_all(), len(w.selected), w.store.get_n_items())[1:])
        step("clear", lambda: (w._sel_none(), len(w.selected))[1])
        step("empty_selection_toast", lambda: (w._sel_fav(True), self.toasts[-1])[1])
        w._tile_press(tiles[0], G()); w._tile_press(tiles[1], G())
        step("fav_add", lambda: (w._sel_fav(True), None)[1]); later(800,self.f)
    def f(self):
        w=self.win; fk=self.fk
        step("fav_called", lambda: (fk.fav[0], len(fk.fav[1])))
        step("fav_toast", lambda: self.toasts[-1])
        step("album_dialog", lambda: (w._sel_album(), len(tl(A.AddToAlbumDialog)))[1])
        d=tl(A.AddToAlbumDialog)[0]; d.list.select_row(d.rows[1]); d._go(); later(800,self.g)
    def g(self):
        w=self.win; fk=self.fk
        step("album_added", lambda: (fk.added[0], len(fk.added[1])))
        step("esc_exits_mode", lambda: (w._on_key(None, Gdk.KEY_Escape, 0, 0), w.select_mode, len(w.selected), w.sel_revealer.get_reveal_child())[1:])
        step("ctrl_a_selects_all", lambda: (w._on_key(None, Gdk.KEY_a, 0, CTRL), w.select_mode, len(w.selected)==w.store.get_n_items())[1:])
        w.set_select_mode(False)
        # ---------- 4) ustawienia ----------
        d=A.SettingsDialog(w); d.present(); self.sd=d
        step("settings_spin_saves", lambda: (d.spin.set_value(2.5), A.load_cfg().get("cache_gb"), w.cache_gb)[1:])
        step("settings_player_embedded", lambda: (d.dd.set_selected(2), w.video_player, w.external_video_ok(), A.load_cfg().get("video_player"))[1:])
        step("settings_player_auto", lambda: (d.dd.set_selected(0), w.video_player)[1])
        import backend as B; os.makedirs(B.THUMB_DIR, exist_ok=True); open(B.THUMB_DIR/"t.img","wb").write(b"x"*2048)
        step("settings_clear", lambda: (d._on_clear(None), None)[1]); later(700,self.h)
    # ---------- 1) wygasła sesja ----------
    def h(self):
        import backend as B; w=self.win; fk=self.fk
        step("cache_cleared", lambda: (B.cache_size(), self.sd.size_lbl.get_text()))
        n_user=len(w.user_albums)
        step("albums_before", lambda: (n_user, w.list_primary.get_first_child() is not None))
        step("non_auth_error_ignored", lambda: (A.bg(lambda: (_ for _ in ()).throw(RuntimeError("HTTP 500")), lambda r,e: None), None)[1]); later(900, self.i)
    def i(self):
        w=self.win; fk=self.fk
        step("still_main_after_500", lambda: w.stack.get_visible_child_name())
        step("auth_looking_but_probe_ok_ignored", lambda: (A.bg(lambda: (_ for _ in ()).throw(PyiCloudFailedLoginException("x")), lambda r,e: None), None)[1]); later(1000,self.j)
    def j(self):
        w=self.win; fk=self.fk
        step("still_main_when_session_valid", lambda: (w.stack.get_visible_child_name(), w._expired))
        fk.expired=True
        step("real_expiry", lambda: (A.bg(lambda: (_ for _ in ()).throw(PyiCloudFailedLoginException("401")), lambda r,e: None), None)[1]); later(1800,self.k)
    def k(self):
        w=self.win; fk=self.fk
        step("back_on_login_page", lambda: (w.stack.get_visible_child_name(), w._expired))
        step("message_says_expired", lambda: w.status.get_text())
        step("auto_relogin_asks_2fa_only", lambda: (fk.logins, w.pending_2fa, w.e_code.get_visible()))
        step("state_cleared", lambda: (w.store.get_n_items(), len(w.user_albums), [x.get_visible() for x in (w.zoom_box, w.jump_btn, w.select_btn)], w.sidebar_btn.get_visible()))
        fk.expired=False
        step("enter_code", lambda: (w.e_code.set_text("123456"), w.on_login(), None)[2]); later(2500,self.l)
    def l(self):
        w=self.win
        step("back_in_main", lambda: (w.stack.get_visible_child_name(), w._expired, w.btn.get_sensitive()))
        step("albums_reloaded_no_dupes", lambda: (len(w.user_albums), sum(1 for _ in iter(lambda c=[w.list_user.get_row_at_index(0)], i=[0]: None)) if False else None, [w.list_user.get_row_at_index(i) is not None for i in range(4)]))
        step("grid_loaded_again", lambda: w.store.get_n_items())
        step("controls_visible_again", lambda: [x.get_visible() for x in (w.zoom_box, w.jump_btn, w.select_btn, w.settings_btn)])
        self.quit()
T(application_id="t.v8").run([])
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
