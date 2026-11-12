import contextlib, io, json, os, sys, tempfile
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.environ["PROJECT_ROOT"])

# Most dla innych aplikacji (bridge.py, wersja 0.15.0): lista albumów, miniatury albumu,
# miniatury z zakresu dat, tworzenie albumu z dni podróży, błędy. Bez sieci (udawany ICloud).
import bridge

class A:
    def __init__(s, i, d): s.id=f"a{i}"; s.asset_date=d; s.filename=f"IMG_{i}.jpg"
base = datetime(2025,2,10,tzinfo=timezone.utc)
assets = [A(i, base+timedelta(hours=12*i)) for i in range(60)]   # 10.02 - 10.03
class Album(list):
    pass
created = {}
class Photos:
    all = Album(assets)
    def create_album(s, name): al=Album(); created[name]=al; return al
class FakeIC:
    api = type("X",(),{"photos":Photos()})()
    def albums(s): return [("All Photos", Photos.all), ("Dubaj 2025", Album(assets[5:9]))] + list(created.items())
    def iter_assets(s, album, newest_first=True): return iter(reversed(album) if newest_first else album)
    def iter_jump(s, album, ts, newest_first=True):
        return iter([a for a in album if a.asset_date.timestamp() >= ts - 1])
    asset_date = staticmethod(lambda a: a.asset_date)
    def fetch(s, a, kind): return b"\xff\xd8JPEG" + a.id.encode()
    def add_to_album(s, album, items, progress=None):
        new=[a for a in items if a not in album]; old=[a for a in items if a in album]
        for k,a in enumerate(new): album.append(a); progress and progress(k+1,len(new))
        return len(new), old, []
    def refresh_library(s): pass
bridge.connect = lambda: FakeIC()

def call(*args):
    out = tempfile.mktemp(suffix=".json")
    with contextlib.redirect_stdout(io.StringIO()):
        rc = bridge.main(["x", *args, "--json", out])
    return rc, json.load(open(out))
d = tempfile.mkdtemp()
print(call("--albums-json"))
rc, r = call("--album-thumbs", "Dubaj 2025", "--out-dir", d, "--max", "3"); print(rc, r["count"], len(r["files"]), open(r["files"][0],"rb").read(), [os.path.basename(f) for f in r["files"]])
rc, r = call("--range-thumbs", "--from", "2025-02-14T00:00:00+01:00", "--to", "2025-02-16T23:59:59+04:00", "--out-dir", d+"/r", "--max", "4"); print(rc, r["count"], len(r["files"]), r["first"], r["last"])
rc, r = call("--create-album", "✈ Dubaj · lut 2025", "--from", "2025-02-14T00:00:00+01:00", "--to", "2025-02-16T23:59:59+04:00"); print(rc, r)
rc, r = call("--create-album", "✈ Dubaj · lut 2025", "--from", "2025-02-14T00:00:00+01:00", "--to", "2025-02-17T23:59:59+04:00"); print(rc, r)
rc, r = call("--album-thumbs", "Nope", "--out-dir", d); print(rc, r)
# 0.15.1: pusty album (planowana podróż) i brak zdjęć w zakresie
rc, r = call("--create-album", "✈ Korfu · cze 2027", "--allow-empty"); print(rc, r)
rc, r = call("--create-album", "✈ Korfu · cze 2027", "--allow-empty"); print(rc, r["created"], r["added"])
rc, r = call("--create-album", "Pusto", "--from", "2030-01-01T00:00:00+01:00", "--to", "2030-01-02T00:00:00+01:00"); print(rc, r["created"], r["found"])
rc, r = call("--create-album", "Bez zakresu"); print(rc, r["error"])
print([n for n, _ in FakeIC().albums()])
rc, r = call("--range-thumbs", "--from", "x", "--to","y","--out-dir",d); print(rc, r)
print(bridge.is_bridge_call(["a","--open-album","x"]), bridge.is_bridge_call(["a","--albums-json"]))

# parse_open z app.py (bez uruchamiania GTK): --open-album / --open-date
import re
code = open(os.path.join(os.environ["PROJECT_ROOT"], "app.py"), encoding="utf-8").read()
m = re.search(r"\ndef parse_open\(argv\):.*?return req, rest\n", code, re.S)
ns = {}; exec(m.group(0), ns)
print(ns["parse_open"](["app.py", "--open-album", "Dubaj 2025", "--x"]))
print(ns["parse_open"](["app.py", "--open-date", "2025-02-14..2025-02-28"]))
try: ns["parse_open"](["app.py", "--open-album"])
except ValueError as e: print("ValueError", e)
