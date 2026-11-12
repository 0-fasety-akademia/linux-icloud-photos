#!/usr/bin/env python3
"""Uruchamia testy aplikacji i porównuje ich wyniki ze wzorcami z tests/golden/.

    python3 tests/run_tests.py              # wszystkie testy
    python3 tests/run_tests.py base_test    # wybrane
    python3 tests/run_tests.py --update     # odnawia wzorce

Wzorzec zawiera tylko te linie wyniku, które były identyczne we WSZYSTKICH uruchomieniach przy
różnych warunkach (zwykły motyw, ciemny motyw + większa czcionka, powtórka). Wartości zależne od
motywu, czcionek czy czasu odpadają same, więc test nie zgłasza fałszywych alarmów na innej wersji
systemu. Skrypty z oknami wymagają xvfb (apt install xvfb). Kod wyjścia 0 = wszystko zgodne.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NOISE = re.compile(r"libEGL|dbus|Gtk-WARNING|Gtk-CRITICAL|GLib-GIO|GtkText|If you handle|GDK_EVENT|"
                   r"gets the event|^\(process|^\(python|Locale not|fallback|^\s*$|Warning|Gdk-")
STEP = re.compile(r"^[A-Za-z0-9_.\-]+ -> ")
VARIANTS = {
    "normal": {},
    # ciemny motyw + większa czcionka + klasyczne paski przewijania: zmienia rozmiary, więc
    # wartości zależne od wyglądu (a tym samym od wersji GTK/motywu) nie trafią do wzorca
    "stress": {"GTK_THEME": "Adwaita:dark", "GDK_DPI_SCALE": "1.3", "GTK_OVERLAY_SCROLLING": "0"},
}
ENV_FOR = {  # reszta testów działa po polsku
    "ui_lang_scan": {"ICLOUD_PHOTOS_LANG": "en"},
    "ui_lang_scan_de": {"ICLOUD_PHOTOS_LANG": "de"},
    "ui_lang_scan_uk": {"ICLOUD_PHOTOS_LANG": "uk"},
}


def uses_gtk(script: Path) -> bool:
    text = script.read_text(encoding="utf-8")
    return "gi.repository" in text or "GTK_SCRIPT" in text


def run_script(name: str, variant: str = "normal") -> dict:
    script = HERE / "scripts" / f"{name}.py"
    tmp = Path(tempfile.mkdtemp(prefix=f"icp-{name}-"))
    (tmp / "test.ogv").write_bytes(bytes((i * 7 + 3) % 256 for i in range(900_000)))
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "PYTHONPATH", "LD_LIBRARY_PATH")}
    env.update({
        "HOME": str(tmp / "home"), "XDG_CONFIG_HOME": str(tmp / "cfg"),
        "XDG_CACHE_HOME": str(tmp / "cache"), "XDG_DATA_HOME": str(tmp / "data"),
        "PROJECT_ROOT": str(ROOT), "TEST_TMP": str(tmp), "GSK_RENDERER": "cairo",
        "LC_ALL": "C.UTF-8", "ICLOUD_PHOTOS_LANG": "pl", "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": f"{HERE / 'bin'}:{env.get('PATH', '')}",
    })
    env.update(ENV_FOR.get(name, {}))
    env.update(VARIANTS[variant])
    cmd = [sys.executable, str(script)]
    if uses_gtk(script):
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1400x900x24"] + cmd
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300, cwd=str(tmp))
        out, rc = p.stdout + "\n" + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, rc = "Traceback: TIMEOUT", 124
    # komunikaty serwera HTTP o celowo zerwanych połączeniach (klient testowy) to nie błąd
    out = re.sub(r"-{40}\nException occurred during processing of request.*?-{40}\n", "", out, flags=re.S)
    out = out.replace(str(tmp), "<TMP>")
    out = re.sub(r"\(\d+\.\d+s\)", "(Ns)", out)   # czasy trwania różnią się między uruchomieniami
    # zrzut błędu serwera testowego po zerwaniu połączenia przez klienta to nie błąd aplikacji
    out = re.sub(r"-{20,}\nException occurred during processing of request.*?-{20,}\n", "", out, flags=re.S)
    lines = [re.sub(r"\d+\.\d+ ?s\b", "N s", l.rstrip()) for l in out.splitlines()
             if l.strip() and not NOISE.search(l)]
    return {"lines": lines, "rc": rc}


def problems_in(result: dict) -> list:
    bad = []
    if any(l.startswith("Traceback") or "Traceback (most recent call last)" in l for l in result["lines"]):
        bad.append("wyjątek/Traceback w wyniku")
    for l in result["lines"]:
        if l.startswith("EXCEPTIONS:") and "none" not in l:
            bad.append(l)
    return bad


def check(name: str) -> tuple:
    golden_file = HERE / "golden" / f"{name}.json"
    if not golden_file.exists():
        return False, ["brak wzorca - uruchom: python3 tests/run_tests.py --update"]
    golden = json.loads(golden_file.read_text(encoding="utf-8"))["lines"]
    res = run_script(name)
    problems = problems_in(res)
    have = set(res["lines"])
    for g in golden:
        if g not in have:
            key = g.split(" -> ")[0] if " -> " in g else g[:30]
            now = next((l for l in res["lines"] if l.startswith(key)), "(brak takiej linii)")
            problems.append(f"oczekiwano: {g[:110]}\n       jest:      {now[:110]}")
    return not problems, problems


def update(names: list) -> None:
    jobs = [(n, v) for n in names for v in VARIANTS]
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as ex:
        results = list(ex.map(lambda nv: (nv, run_script(*nv)), jobs))
    for name in names:
        runs = [r for (n, _v), r in results if n == name]
        bad = [b for r in runs for b in problems_in(r)]
        if bad:
            print(f"!! {name}: wyjątki przy odnawianiu wzorca: {bad[:2]} - wzorca nie zapisuję")
            continue
        stable = [l for l in runs[0]["lines"] if all(l in set(r["lines"]) for r in runs[1:])]
        dropped = len(runs[0]["lines"]) - len(stable)
        (HERE / "golden" / f"{name}.json").write_text(
            json.dumps({"lines": stable, "runs": len(runs), "dropped_unstable": dropped},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"   {name}: {len(stable)} stabilnych linii (odrzucono {dropped} zależnych od motywu/czasu)")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    all_names = sorted(p.stem for p in (HERE / "scripts").glob("*.py"))
    names = args or all_names
    if "--update" in sys.argv:
        update(names)
        return 0
    failed = 0
    for name in names:
        ok, problems = check(name)
        print(("PASS " if ok else "FAIL ") + name, flush=True)
        for p in problems[:12]:
            print("     " + p)
        failed += (not ok)
    if not args:  # kontrola tłumaczeń jako osobny test
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "check_i18n.py")], capture_output=True, text=True)
        print(("PASS " if r.returncode == 0 else "FAIL ") + "check_i18n  " + r.stdout.strip().splitlines()[-1] if r.stdout else "")
        failed += (r.returncode != 0)
    print(f"\nPodsumowanie: {len(names) - failed + (0 if args else 1)} zgodnych, {failed} niezgodnych")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
