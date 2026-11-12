import io, json, os, sys, tempfile, contextlib
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import backend, pick

# Tryb wyboru (--pick, wersja 0.14.0): opcje, eksport plików pod WhatsApp (JPEG/PNG/GIF bez zmian, HEIC -> JPEG
# albo podgląd medium, wideo H.264, Live Photo jako zdjęcie), wynik JSON i biblioteka tylko do odczytu.

class Asset:
    def __init__(s, name, versions, live=False, movie=False, i=0):
        s.id = f"id{i}"; s.filename = name; s.versions = {v: {} for v in versions}
        s.is_live_photo = live; s.item_type = "movie" if movie else "image"

class FakeICloud(backend.ICloud):
    def __init__(s, fail=()):
        s.saved = []; s.fail = set(fail)
    def save_version(s, asset, ver, path):
        if asset.filename in s.fail: raise IOError("HTTP 500")
        s.saved.append((asset.filename, ver))
        with open(path, "wb") as f: f.write(f"{asset.filename}:{ver}".encode())

def step(name, fn):
    try: r = fn()
    except Exception as e: r = "EXC " + repr(e)
    print(name, "->", r, flush=True)

tmp = tempfile.mkdtemp(prefix="pick-")
def names(items): return [(i["name"], i["kind"], i["source"], i["mime"], i["live"]) for i in items]
def one(ic, a, conv=None, folder=None):
    return names([pick.export_asset(ic, a, folder or tempfile.mkdtemp(dir=tmp), conv)])[0]

# --- opcje wiersza poleceń ---
step("cli_no_pick", lambda: pick.parse_cli(["app.py", "--foo"]))
def cli(args):
    opts, rest = pick.parse_cli(args)
    return (opts["out"], os.path.isdir(opts["dir"]), opts["max"], rest)
step("cli_basic", lambda: cli(["app.py", "--pick", "--pick-out", "/x/r.json", "--pick-dir", tmp + "/d1"]))
step("cli_equals_form", lambda: cli(["a", "--pick", "--pick-max=5", "--pick-dir=" + tmp + "/d2"]))
step("cli_max_clamped_high", lambda: cli(["a", "--pick", "--pick-max", "500", "--pick-dir", tmp + "/d3"])[2])
step("cli_max_clamped_low", lambda: cli(["a", "--pick", "--pick-max", "0", "--pick-dir", tmp + "/d4"])[2])
step("cli_default_max", lambda: cli(["a", "--pick", "--pick-dir", tmp + "/d5"])[2])
step("cli_missing_value", lambda: pick.parse_cli(["a", "--pick", "--pick-out"]))
step("cli_unknown_option", lambda: pick.parse_cli(["a", "--pick", "--pick-wat", "1"]))
step("cli_bad_max", lambda: pick.parse_cli(["a", "--pick", "--pick-max", "abc"]))
step("cli_temp_dir_when_missing", lambda: os.path.isdir(pick.parse_cli(["a", "--pick"])[0]["dir"]))

# --- eksport pojedynczych plików ---
ic = FakeICloud()
step("jpg_passthrough", lambda: one(ic, Asset("IMG_1.JPG", ["thumb", "medium", "original"])))
step("png_passthrough", lambda: one(ic, Asset("shot.png", ["medium", "original"])))
step("heic_converted", lambda: one(ic, Asset("IMG_2.HEIC", ["medium", "original"]), lambda d: b"JPEG:" + d))
def conv_fail(d): raise RuntimeError("no heic loader")
d = tempfile.mkdtemp(dir=tmp)
step("heic_converter_fails_uses_medium", lambda: (one(ic, Asset("IMG_3.HEIC", ["medium", "original"]), conv_fail, d), sorted(os.listdir(d))))
step("heic_no_converter_uses_medium", lambda: one(ic, Asset("IMG_4.HEIC", ["medium", "original"])))
step("heic_without_medium_fails", lambda: one(ic, Asset("IMG_5.HEIC", ["original"]), conv_fail))
step("live_photo_is_photo", lambda: one(ic, Asset("IMG_6.HEIC", ["medium", "original", "medium_video"], live=True), lambda d: d))
step("video_uses_h264_medium", lambda: one(ic, Asset("MOV_1.MOV", ["thumb_image", "medium", "original"], movie=True)))
step("video_only_original_keeps_ext", lambda: one(ic, Asset("MOV_2.MOV", ["original"], movie=True)))
step("video_without_versions_fails", lambda: one(ic, Asset("MOV_3.MOV", [], movie=True)))
d = tempfile.mkdtemp(dir=tmp)
step("name_collision_numbered", lambda: (one(ic, Asset("IMG_7.JPG", ["original"]), None, d)[0],
                                          one(ic, Asset("IMG_7.JPG", ["original"]), None, d)[0],
                                          sorted(os.listdir(d))))
step("converted_file_content", lambda: open(pick.export_asset(
    ic, Asset("IMG_8.HEIC", ["original", "medium"]), d, lambda b: b"J:" + b)["path"], "rb").read())

# --- eksport listy ---
progress, ic2 = [], FakeICloud(fail={"BAD.JPG"})
assets = [Asset("A.JPG", ["original"], i=1), Asset("BAD.JPG", ["original"], i=2), Asset("C.JPG", ["original"], i=3)]
items, errors = pick.export_assets(ic2, assets, tempfile.mkdtemp(dir=tmp), lambda k, n: progress.append((k, n)))
step("list_one_failure_continues", lambda: ([i["name"] for i in items], errors, progress))
calls = []
def cancel_after_one(): calls.append(1); return len(calls) > 1
items, errors = pick.export_assets(FakeICloud(), assets, tempfile.mkdtemp(dir=tmp), cancel=cancel_after_one)
step("list_cancel_stops", lambda: ([i["name"] for i in items], errors))
step("list_empty", lambda: pick.export_assets(FakeICloud(), [], tempfile.mkdtemp(dir=tmp)))

# --- wynik JSON ---
out = os.path.join(tmp, "result.json")
pick.write_result(out, [{"name": "a.jpg"}], ["err"], False)
step("result_file", lambda: (json.load(open(out)), os.path.exists(out + ".tmp")))
pick.write_result(out, [], [], True)
step("result_cancelled", lambda: json.load(open(out)))
buf = io.StringIO()
with contextlib.redirect_stdout(buf): pick.write_result(None, [{"name": "z.jpg"}], [])
step("result_stdout", lambda: json.loads(buf.getvalue()))

# --- biblioteka tylko do odczytu ---
class Dummy(backend.ICloud):
    def __init__(s): pass
backend.READ_ONLY = True
dm = Dummy()
for name, fn in (("upload", lambda: dm.upload("/x/a.jpg")), ("add_to_album", lambda: dm.add_to_album(object(), [])),
                 ("set_favorite", lambda: dm.set_favorite([], True)), ("delete_assets", lambda: dm.delete_assets([]))):
    step("readonly_blocks_" + name, fn)
backend.READ_ONLY = False
