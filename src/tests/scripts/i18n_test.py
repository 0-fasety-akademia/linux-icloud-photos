import importlib, os, sys
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import i18n, backend

def lang(**env):
    for v in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG", "ICLOUD_PHOTOS_LANG"): os.environ.pop(v, None)
    os.environ.update(env); importlib.reload(i18n); return i18n.LANG
def cfg(value):
    d = os.path.join(os.environ["XDG_CONFIG_HOME"], "linux-icloud-photos"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "config.json"), "w").write('{"language": "%s"}' % value)
def step(name, fn):
    try: r = fn()
    except Exception as e: r = "EXC " + repr(e)
    print(name, "->", r, flush=True)

step("system_pl", lambda: lang(LANG="pl_PL.UTF-8"))
step("system_en", lambda: lang(LANG="en_US.UTF-8"))
step("system_de_is_english_by_default", lambda: lang(LANG="de_DE.UTF-8"))
step("system_uk_is_english_by_default", lambda: lang(LANG="uk_UA.UTF-8"))
step("language_list_first_wins", lambda: (lang(LANGUAGE="pl:en", LANG="en_US.UTF-8"), lang(LANGUAGE="en:pl", LANG="pl_PL.UTF-8")))
step("no_env_is_english", lambda: lang())
cfg("de"); step("config_de_beats_system", lambda: lang(LANG="pl_PL.UTF-8"))
cfg("uk"); step("config_uk", lambda: lang(LANG="en_US.UTF-8"))
cfg("auto"); step("config_auto_follows_system", lambda: lang(LANG="pl_PL.UTF-8"))
cfg("de"); step("env_beats_config", lambda: lang(ICLOUD_PHOTOS_LANG="uk", LANG="pl_PL.UTF-8"))
cfg("xx"); step("bad_config_ignored", lambda: lang(LANG="pl_PL.UTF-8"))
cfg("auto")
SAMPLES = ("Anuluj", "Wszystkie zdjęcia", "Wideo", "Wideo|typ", "Usuń", "Zapisano: {0}")
for L in ("pl", "en", "de", "uk"):
    lang(ICLOUD_PHOTOS_LANG=L); step(f"tr_{L}", lambda: [i18n.tr(x) for x in SAMPLES])
lang(ICLOUD_PHOTOS_LANG="uk"); step("tr_unknown_text_falls_back", lambda: i18n.tr("Tekst, którego nie ma w tabelach"))
FORMS = dict(pl=("zdjęcie", "zdjęcia", "zdjęć"), en=("photo", "photos"), de=("Foto", "Fotos"), uk=("фото", "фото", "фото"))
for L in ("pl", "en", "de", "uk"):
    lang(ICLOUD_PHOTOS_LANG=L); step(f"plural_{L}", lambda: [i18n.plural(n, **FORMS) for n in (1, 2, 5, 12, 22, 25, 101)])
for L in ("pl", "en", "de", "uk"):
    lang(ICLOUD_PHOTOS_LANG=L); step(f"months_{L}", lambda: (i18n.month_names()[7], i18n.month_abbr()[2], len(i18n.month_names()), len(i18n.month_abbr())))
lang(ICLOUD_PHOTOS_LANG="en"); importlib.reload(backend)
for q in ("sierpień 2024", "August 2024", "märz 2023", "15 dez 2022", "червень 2021", "5 жов 2020", "08.2024", "лис 2019", "foo 2020"):
    step("date_" + q.replace(" ", "_"), lambda: (lambda r: (r[0].strftime("%Y-%m-%d"), r[1].strftime("%Y-%m-%d")) if r else None)(backend.parse_date_query(q)))
