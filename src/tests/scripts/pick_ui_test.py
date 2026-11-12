import sys, os, json, traceback, tempfile
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); gi.require_version("GdkPixbuf","2.0")
from gi.repository import Gtk, Adw, GLib, Gio, Gdk, GdkPixbuf
from datetime import datetime, timedelta, timezone
import app as A
import backend, pick

# Okno w trybie wyboru (--pick, wersja 0.14.0): pasek „Wybierz”, limit plików, brak usuwania,
# Esc/Anuluj, eksport do folderu i wynik JSON. Biblioteka jest tylko do odczytu.

def jpeg(w,h,color):
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h); pb.fill(color)
    ok, data = pb.save_to_bufferv("jpeg", ["quality"], ["80"]); return bytes(data)
BASE = datetime(2020,1,1,tzinfo=timezone.utc)
class FA:
    def __init__(s,i,video=False,live=False):
        s.id=f"id{i}"; s.i=i; s.video=video; s.live=live
        s.filename=f"IMG_{i:04d}.{'MOV' if video else ('HEIC' if i%2 else 'JPG')}"
        s.asset_date = BASE+timedelta(days=i)
        s.versions = {"original":{}, "medium":{}, "thumb":{}}
class Fake:
    def __init__(s): s.delete_calls=[]; s.fail=False; s.saved=[]
    def albums(self): return [("All Photos","A"),("Favorites","F"),("Videos","V"),("Podróż 2024","P")]
    def total(self, album): return {"A":750}.get(album, 40)
    def iter_assets(self, album, newest_first=True, flip=False):
        n={"A":750}.get(album,40); desc=(newest_first!=flip)
        for i in (range(n-1,-1,-1) if desc else range(n)):
            yield FA(i, video=(i==3), live=(i==5))
    is_video=staticmethod(lambda a:a.video); is_live=staticmethod(lambda a:a.live)
    asset_date=staticmethod(lambda a:a.asset_date)
    live_version=staticmethod(lambda a:"medium_video" if a.live else None)
    video_version=staticmethod(lambda a,c:"medium")
    def fetch(s,a,kind): return jpeg(240 if kind=="thumb" else 1200, 240 if kind=="thumb" else 800, 0x3070b0ff)
    def fetch_original(s,a): return jpeg(2400,1600,0x2288ccff)
    def album_cover(s,key,album): return jpeg(120,120,0xc06030ff)
    def probe(s): return 750
    def delete_assets(s, assets, progress=None): s.delete_calls.append([a.id for a in assets]); return list(assets), []
    def save_version(s, asset, ver, path):
        if s.fail: raise IOError("HTTP 500")
        s.saved.append((asset.filename, ver))
        with open(path, "wb") as f: f.write(f"{asset.filename}:{ver}".encode())
class KR:
    @staticmethod
    def get_password(svc, aid): return "pw"
    @staticmethod
    def set_password(*a): pass
R={}
def step(name, fn):
    try: R[name]=fn()
    except Exception: R[name]="EXC "+traceback.format_exc().splitlines()[-1]
    print(name,"->",R[name],flush=True)
def later(ms, fn): GLib.timeout_add(ms, lambda: (fn(), False)[1])

TMP = os.environ["TEST_TMP"]
OUT = os.path.join(TMP, "pick-result.json"); DIR = os.path.join(TMP, "pick-files"); os.makedirs(DIR, exist_ok=True)
A.PICK = {"out": OUT, "dir": DIR, "max": 3}
backend.READ_ONLY = True

class T(Adw.Application):
    def do_activate(self):
        prov=Gtk.CssProvider(); prov.load_from_data(A.CSS); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        A.keyring=KR; self.fk=Fake(); self.picked=False
        self.win=w=A.MainWindow(self, icloud=self.fk, autologin=False); w.set_default_size(1300,700); w.present(); w.logged_in(save=False)
        self.toasts=[]; w.toast=lambda t:self.toasts.append(t); later(3500,self.a)
    def tiles(self): return [t for t in self.win.tiles if t.bound is not None and t.get_mapped()]
    def a(self):
        w=self.win; T_=self.tiles()
        step("select_mode_always_on", lambda: (w.select_mode, w.sel_revealer.get_reveal_child()))
        step("header_buttons_hidden", lambda: (w.add_btn.get_visible(), w.select_btn.get_visible()))
        step("hint_when_nothing_selected", lambda: w.sel_label.get_text())
        step("pick_button_disabled_without_selection", lambda: (w.pick_btn.get_sensitive(), w.pick_btn.get_label(), w.pick_btn.has_css_class("suggested-action")))
        step("no_delete_or_album_buttons", lambda: hasattr(w, "del_btn"))
        w._toggle_tile(T_[0]); w._toggle_tile(T_[1])
        step("two_selected_label_and_button", lambda: (w.sel_label.get_text(), w.pick_btn.get_sensitive(), w.pick_btn.get_label()))
        w._toggle_tile(T_[2]); w._toggle_tile(T_[3]); w._toggle_tile(T_[4])
        step("limit_three_enforced", lambda: (len(w.selected), "najwyżej 3" in self.toasts[-1]))
        step("deselecting_last_keeps_mode_on", lambda: (w._sel_none(), w.select_mode)[1])
        w.selected=[w.store.get_item(0)]; w._refresh_selection()
        step("delete_blocked_in_pick_mode", lambda: (w._sel_delete(), self.fk.delete_calls)[1])
        step("delete_key_not_handled", lambda: (w._on_key(None, Gdk.KEY_Delete, 0, 0), self.fk.delete_calls)[1])
        step("drop_upload_refused", lambda: w._on_drop(None, None, 0, 0))
        step("set_select_mode_false_keeps_mode_clears_selection", lambda: (w.set_select_mode(False), w.select_mode, len(w.selected)))
        w._on_key(None, Gdk.KEY_a, 0, Gdk.ModifierType.CONTROL_MASK)
        step("ctrl_a_selects_only_max", lambda: len(w.selected))
        step("escape_with_selection_clears", lambda: (w._on_key(None, Gdk.KEY_Escape, 0, 0), len(w.selected), w.select_mode))
        closed=[]; w.close=lambda: closed.append(1)
        step("escape_without_selection_cancels", lambda: (w._on_key(None, Gdk.KEY_Escape, 0, 0), closed))
        del w.close
        # eksport nieudany: okno zostaje, brak pliku wyniku
        self.fk.fail=True; w.selected=[w.store.get_item(0), w.store.get_item(1)]; w._refresh_selection(); w._pick_confirm(); later(1500,self.b)
    def b(self):
        w=self.win
        step("failed_export_keeps_window_and_reenables", lambda: (os.path.exists(OUT), w._pick_busy, w.pick_btn.get_sensitive(), "przygotować" in self.toasts[-1]))
        # eksport udany: HEIC -> (konwersja się nie uda na atrapie) podgląd medium, JPG bez zmian
        self.fk.fail=False; w.selected=[w.store.get_item(0), w.store.get_item(1)]; w._refresh_selection()
        step("pick_button_label_two", lambda: w.pick_btn.get_label())
        w._pick_confirm()   # kończy aplikację po zapisaniu wyniku

app = T(application_id="t.pick"); app.run([])
step("app_marked_picked", lambda: app.picked)
step("result_json", lambda: (lambda d: (d["cancelled"], d["errors"], [(f["name"], f["kind"], f["source"]) for f in d["files"]]))(json.load(open(OUT))))
step("files_written", lambda: sorted(os.listdir(DIR)))
step("backend_calls", lambda: app.fk.saved)
step("library_untouched", lambda: app.fk.delete_calls)
print("EXCEPTIONS:", {k:v for k,v in R.items() if isinstance(v,str) and v.startswith("EXC")} or "none")
