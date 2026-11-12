"""Kontrola tłumaczeń: uruchom `python3 tools/check_i18n.py` po każdej zmianie tekstów w kodzie.
Sprawdza: czy każdy tr(...) ma wpis w i18n.EN, czy nie ma nieużywanych wpisów, czy tłumaczenie ma te
same miejsca na podstawienia ({0}, {1}...) i czy w kodzie nie został polski napis poza tr()."""
import ast, os, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import i18n
PLCH = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
files = ["app.py", "backend.py", "cast.py", "cast_gc.py", "airplay.py", "exif.py", "pick.py"]
used, problems = {}, []
def is_log(a):
    return isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute) and isinstance(a.func.value, ast.Name) and a.func.value.id == 'log'
for f in files:
    try: src = open(f, encoding='utf-8').read()
    except FileNotFoundError: continue
    tree = ast.parse(src); parents = {}
    for n in ast.walk(tree):
        for c in ast.iter_child_nodes(n): parents[id(c)] = n
    def anc(n):
        p = parents.get(id(n))
        while p is not None: yield p; p = parents.get(id(p))
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], 'value', None), ast.Constant) and isinstance(n.body[0].value.value, str): doc.add(id(n.body[0].value))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'tr':
            a = n.args[0] if n.args else None
            if isinstance(a, ast.Constant) and isinstance(a.value, str): used.setdefault(a.value, []).append(f"{f}:{n.lineno}")
            else: problems.append(f"{f}:{n.lineno}: tr() z nie-stałym argumentem")
    # pozostałe polskie napisy poza tr() i log
    for n in ast.walk(tree):
        s = None
        if isinstance(n, ast.JoinedStr): s = ''.join(v.value if isinstance(v, ast.Constant) else '{}' for v in n.values)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in doc and not isinstance(parents.get(id(n)), ast.JoinedStr): s = n.value
        if s is None: continue
        if any(is_log(a) for a in anc(n)): continue
        if any(isinstance(a, ast.Call) and isinstance(a.func, ast.Name) and a.func.id == 'tr' for a in anc(n)): continue
        if any(isinstance(a, ast.JoinedStr) for a in anc(n)) and not isinstance(n, ast.JoinedStr): continue
        if s in ('zdjęcie','zdjęcia','zdjęć','paź'): continue
        if PLCH.search(s) and not re.search(r"\[a-z", s):      # pomiń wyrażenia regularne
            problems.append(f"{f}:{n.lineno}: polski napis poza tr(): {s[:70]!r}")
missing = [k for k in used if k not in i18n.EN]
for k in missing: problems.append(f"brak tłumaczenia EN dla {k[:70]!r} ({used[k][0]})")
unused = [k for k in i18n.EN if k not in used]
for k in unused: problems.append(f"nieużywany wpis EN: {k[:70]!r}")
ph = lambda s: sorted(set(re.findall(r"\{(\d+)\}", s)))
for k, v in i18n.EN.items():
    if ph(k) != ph(v): problems.append(f"różne miejsca na podstawienia: {k[:60]!r} vs {v[:60]!r}")
    if re.search(r"[ąćęłńóśźż]", v): problems.append(f"polskie znaki w tłumaczeniu EN: {v[:70]!r}")
    if "|" in v and "|" not in k: problems.append(f"kreska w EN: {v[:50]!r}")
# --- niemiecki i ukraiński: tabele kluczowane angielskim tekstem ---
from i18n_de import DE
from i18n_uk import UK
en_values = set(i18n.EN.values())
for name, table in (("DE", DE), ("UK", UK)):
    for k in sorted(en_values - set(table)):
        problems.append(f"brak tłumaczenia {name} dla {k[:70]!r}")
    for k in sorted(set(table) - en_values):
        problems.append(f"{name}: klucz bez angielskiego odpowiednika (literówka?): {k[:70]!r}")
    for k, v in table.items():
        if ph(k) != ph(v): problems.append(f"{name}: różne miejsca na podstawienia: {k[:60]!r} vs {v[:60]!r}")
        if re.search(r"[ąćęłńóśźż]", v): problems.append(f"{name}: polskie znaki w tłumaczeniu: {v[:70]!r}")
        if not v.strip(): problems.append(f"{name}: puste tłumaczenie dla {k[:60]!r}")
cyr = sum(1 for v in UK.values() if re.search(r"[а-яіїєґ]", v, re.I))
if cyr < len(UK) * 0.9: problems.append(f"UK: tylko {cyr} z {len(UK)} tłumaczeń ma cyrylicę")
same = [k for k, v in DE.items() if v == k and len(k) > 12]
print(f"DE: {len(DE)} wpisów, UK: {len(UK)} wpisów (długie napisy identyczne z angielskim w DE: {len(same)})")
print(f"użyte klucze: {len(used)} | wpisów EN: {len(i18n.EN)} | problemów: {len(problems)}")
for p in problems: print(" -", p)

sys.exit(1 if problems else 0)
