import json, os, subprocess, sys, tempfile, threading, time, types
sys.path.insert(0, os.environ["PROJECT_ROOT"])
R = {}
def step(name, fn):
    try: R[name] = fn()
    except Exception as e: R[name] = "EXC %r" % (e,)
    print(name, "->", R[name])

def tree(base):
    out = []
    for r, _d, fs in os.walk(base):
        for f in fs: out.append(os.path.relpath(os.path.join(r, f), base))
    return sorted(out)

def scenario(old=None, new=None):
    """Uruchamia import backendu w świeżym procesie z czystym XDG; zwraca stan katalogów po imporcie."""
    home = tempfile.mkdtemp(prefix="mig-")
    cfg, cache = os.path.join(home, "cfg"), os.path.join(home, "cache")
    for base, spec, sub in ((cfg, old, "icloud-photos-linux"), (cache, old, "icloud-photos-linux"),
                            (cfg, new, "linux-icloud-photos"), (cache, new, "linux-icloud-photos")):
        pass
    def make(parent, name, files):
        d = os.path.join(parent, name); os.makedirs(d, exist_ok=True)
        for rel, txt in files.items():
            p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(txt)
    if old: make(cfg, "icloud-photos-linux", old["cfg"]); make(cache, "icloud-photos-linux", old["cache"])
    if new: make(cfg, "linux-icloud-photos", new["cfg"]); make(cache, "linux-icloud-photos", new["cache"])
    env = {"PATH": os.environ["PATH"], "HOME": home, "XDG_CONFIG_HOME": cfg, "XDG_CACHE_HOME": cache,
           "PYTHONPATH": os.environ["PROJECT_ROOT"], "ICLOUD_PHOTOS_LANG": "pl"}
    code = "import backend, json; print(json.dumps(backend.migrate_old_data()))"
    p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=home)
    res = {"rc": p.returncode, "old_cfg": os.path.isdir(os.path.join(cfg, "icloud-photos-linux")),
           "old_cache": os.path.isdir(os.path.join(cache, "icloud-photos-linux")),
           "new_cfg": tree(os.path.join(cfg, "linux-icloud-photos")) if os.path.isdir(os.path.join(cfg, "linux-icloud-photos")) else None,
           "new_cache": tree(os.path.join(cache, "linux-icloud-photos")) if os.path.isdir(os.path.join(cache, "linux-icloud-photos")) else None}
    cj = os.path.join(cfg, "linux-icloud-photos", "config.json")
    res["config_text"] = open(cj).read() if os.path.exists(cj) else None
    return res, home

OLD = {"cfg": {"config.json": '{"language": "de", "apple_id": "a@b.c"}', "session/cookies.txt": "S"}, "cache": {"thumbs/a.jpg": "T", "debug.log": "L"}}
NEW = {"cfg": {"config.json": '{"language": "uk"}'}, "cache": {"thumbs/n.jpg": "N"}}

r, _ = scenario(old=OLD)
step("old_dirs_are_moved_to_new_names", lambda: (r["rc"], r["old_cfg"], r["old_cache"]))
step("config_session_and_cache_content_kept", lambda: (r["new_cfg"], r["new_cache"]))
step("config_text_unchanged", lambda: r["config_text"])
r, _ = scenario(old=OLD, new=NEW)
step("existing_new_dirs_are_never_overwritten", lambda: (r["old_cfg"], r["old_cache"], r["new_cfg"], r["new_cache"], r["config_text"]))
r, _ = scenario(new=NEW)
step("only_new_dirs_nothing_to_do", lambda: (r["rc"], r["old_cfg"], r["new_cfg"]))
r, _ = scenario()
step("fresh_install_import_creates_no_config_and_only_the_log", lambda: (r["rc"], r["new_cfg"], r["new_cache"]))

# język z ustawień zapisanych pod starą nazwą (i18n ładuje się przed backendem)
home = tempfile.mkdtemp(prefix="mig-lang-"); d = os.path.join(home, "cfg", "icloud-photos-linux"); os.makedirs(d)
open(os.path.join(d, "config.json"), "w").write('{"language": "de"}')
env = {"PATH": os.environ["PATH"], "HOME": home, "XDG_CONFIG_HOME": os.path.join(home, "cfg"), "PYTHONPATH": os.environ["PROJECT_ROOT"], "LANG": "pl_PL.UTF-8"}
p = subprocess.run([sys.executable, "-c", "import i18n; print(i18n.LANG)"], env=env, capture_output=True, text=True)
step("language_read_from_old_config_dir", lambda: p.stdout.strip())

# hasła w keyringu zapisane pod starą nazwą
class FakeKeyring:
    def __init__(s, data): s.data = dict(data); s.sets = []
    def get_password(s, svc, user): return s.data.get((svc, user))
    def set_password(s, svc, user, pw): s.sets.append((svc, user, pw)); s.data[(svc, user)] = pw
import airplay
fk = FakeKeyring({("icloud-photos-linux-airplay", "tv1"): "CREDS"}); sys.modules["keyring"] = fk
step("airplay_creds_found_under_old_service", lambda: airplay.load_creds("tv1"))
step("airplay_creds_copied_to_new_service", lambda: fk.sets)
step("airplay_new_service_preferred", lambda: (fk.data.update({("linux-icloud-photos-airplay", "tv1"): "NEW"}), airplay.load_creds("tv1"))[1])
step("service_names", lambda: (airplay.KEYRING_SERVICE, airplay.OLD_KEYRING_SERVICE))

import app as A
cfgfile = os.path.join(tempfile.mkdtemp(prefix="mig-cfg-"), "config.json"); open(cfgfile, "w").write('{"apple_id": "jan@example.com"}')
A.CONFIG_FILE = type("P", (), {"read_text": lambda s: open(cfgfile).read()})()
def autologin(kr):
    A.keyring = kr; calls = []
    st = types.SimpleNamespace(_expired=False, e_id=types.SimpleNamespace(set_text=lambda t: None), e_pw=types.SimpleNamespace(set_text=lambda t: calls.append(("pw", t))),
        stack=types.SimpleNamespace(set_visible_child_name=lambda n: None), say=lambda t: None, _after_login=lambda *a: None,
        icloud=types.SimpleNamespace(login=lambda a, p: calls.append(("login", a, p))))
    A.MainWindow._autologin(st); time.sleep(0.3); return calls
kr = FakeKeyring({("icloud-photos-linux", "jan@example.com"): "oldpw"})
step("app_uses_password_saved_under_old_name", lambda: autologin(kr))
step("app_copies_it_to_new_service", lambda: kr.sets)
kr2 = FakeKeyring({("linux-icloud-photos", "jan@example.com"): "newpw", ("icloud-photos-linux", "jan@example.com"): "oldpw"})
step("app_prefers_new_service", lambda: (autologin(kr2), kr2.sets))
step("app_service_names", lambda: (A.KEYRING_SERVICE, A.OLD_KEYRING_SERVICE))
print("EXCEPTIONS:", {k: v for k, v in R.items() if isinstance(v, str) and v.startswith("EXC")} or "none")
