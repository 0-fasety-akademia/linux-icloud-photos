import contextlib, io, json, os, sys, tempfile
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.environ["PROJECT_ROOT"])

# 0.16.0: most --drive-upload (kopie zapasowe innych aplikacji w iCloud Drive). Bez sieci:
# udawany iCloud Drive z folderami, plikami, datami i koszem.
import bridge

clock = [datetime(2026, 11, 1, tzinfo=timezone.utc)]
trash = []
class Node:
    def __init__(s, name, typ, parent=None, data=b""):
        s.name, s.type, s.children, s.data, s.parent = name, typ, [], data, parent
        clock[0] += timedelta(hours=1); s.date_modified = clock[0]; s.date_changed = clock[0]
    def get_children(s, force=False): return list(s.children)
    def mkdir(s, name): s.children.append(Node(name, "folder", s))
    def upload(s, f): s.children.append(Node(f.name, "file", s, f.read()))
    def delete(s): s.parent.children.remove(s); trash.append(s.name)
class Drive:
    def __init__(s): s.root = Node("root", "folder")
    def refresh_root(s): pass
drive = Drive()
class IC:
    api = type("A", (), {"drive": drive})()
bridge.connect = lambda: IC()

def call(*args):
    out = tempfile.mktemp(suffix=".json")
    with contextlib.redirect_stdout(io.StringIO()):
        rc = bridge.main(["x", *args, "--json", out])
    return rc, json.load(open(out))

d = tempfile.mkdtemp()
def make(name, content):
    p = os.path.join(d, name); open(p, "wb").write(content); return p

rc, r = call("--drive-upload", make("skytrack-kopia-2026-11-01.skytrack", b"A" * 10), "--drive-folder", "SkyTrack",
             "--prefix", "skytrack-kopia-", "--keep", "3"); print(rc, r)
for day in ("02", "03", "04"):
    rc, r = call("--drive-upload", make(f"skytrack-kopia-2026-11-{day}.skytrack", b"B"), "--drive-folder", "SkyTrack",
                 "--prefix", "skytrack-kopia-", "--keep", "3"); print(rc, r["name"], r["removed"])
# ten sam dzień jeszcze raz: zastępuje plik zamiast tworzyć drugi
rc, r = call("--drive-upload", make("skytrack-kopia-2026-11-04.skytrack", b"CC"), "--drive-folder", "SkyTrack",
             "--prefix", "skytrack-kopia-", "--keep", "3"); print(rc, r["replaced"], r["size"], r["removed"])
folder = [c for c in drive.root.children if c.name == "SkyTrack"][0]
print(sorted(c.name for c in folder.children), [c.data for c in folder.children if c.name.endswith("04.skytrack")])
print("trash", trash)
# inne pliki w folderze nie są ruszane (inny prefiks)
folder.children.append(Node("moje-notatki.txt", "file", folder))
rc, r = call("--drive-upload", make("skytrack-kopia-2026-11-05.skytrack", b"D"), "--drive-folder", "SkyTrack",
             "--prefix", "skytrack-kopia-", "--keep", "2"); print(rc, r["removed"], sorted(c.name for c in folder.children))
# błędy
print(call("--drive-upload", "/nie/ma/takiego/pliku", "--drive-folder", "SkyTrack"))
print(call("--drive-upload", make("x.skytrack", b"x"), "--drive-folder", "a/b")[1]["error"])
print(call("--drive-upload", make("x.skytrack", b"x"), "--keep", "dużo")[1]["error"])
class Broken:
    @property
    def api(s):
        class A:
            @property
            def drive(s): raise RuntimeError("Drive disabled (ADP)")
        return A()
bridge.connect = lambda: Broken()
print(call("--drive-upload", make("y.skytrack", b"y"), "--drive-folder", "SkyTrack"))
print(bridge.is_bridge_call(["a", "--drive-upload", "p"]))
