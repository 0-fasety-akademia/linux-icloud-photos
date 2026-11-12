import os, sys, time
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import backend

# Regresja z wersji 0.11.0: potwierdzanie usunięcia przez album.get() przeglądało całą bibliotekę (setki zapytań),
# więc usuwanie „wisiało”. Teraz: jedno zapytanie o rekordy na paczkę, a biblioteka nie jest dotykana wcale.
class Asset:
    def __init__(s, i):
        s.id = f"id{i}"; s.filename = f"IMG_{i}.HEIC"
        s._asset_record = {"recordName": s.id, "zoneID": {"zoneName": "PrimarySync"}}
    def delete(s): s.sent = True; return True
class Resp:
    def __init__(s, records): s.records = records
class Client:
    def __init__(s, deleted_ids=(), fail=False, drop=()):
        s.calls = []; s.deleted = set(deleted_ids); s.fail = fail; s.drop = set(drop)
    def lookup(s, names, zone_id, desired_keys=None):
        s.calls.append(len(list(names)))
        if s.fail: raise RuntimeError("sieć niedostępna")
        recs = []
        for n in names:
            if n in s.drop: recs.append(object())          # rekord błędu (bez recordName)
            else: recs.append({"recordName": n, "fields": {"isDeleted": {"value": 1 if n in s.deleted else 0}}})
        return Resp(recs)
class Library:
    def __getattr__(s, n): raise AssertionError("dotknięto biblioteki (get/photos) - to przegląda wszystkie zdjęcia!")
def make(n, client, fail_delete=()):
    assets = [Asset(i) for i in range(n)]
    for a in assets:
        if a.id in fail_delete:
            def boom(a=a): raise RuntimeError("HTTP 500")
            a.delete = boom
    class Photos:
        private_client = client; all = Library()
    class Api: photos = Photos()
    ic = backend.ICloud(); ic.api = Api(); return ic, assets
ids = lambda l: [a.id for a in l]
def step(name, fn):
    try: r = fn()
    except Exception as e: r = "EXC " + repr(e)
    print(name, "->", r, flush=True)

c = Client(deleted_ids={f"id{i}" for i in range(4)}); ic, A = make(4, c); prog = []
t0 = time.time(); d, e = ic.delete_assets(A, lambda k, n: prog.append((k, n)))
step("all_confirmed", lambda: (len(d), e, prog[-1], c.calls))
step("fast_no_library_scan", lambda: time.time() - t0 < 2)
c = Client(deleted_ids={"id0", "id2", "id3"}); ic, A = make(4, c, fail_delete=("id1",)); d, e = ic.delete_assets(A)
step("one_delete_fails", lambda: (ids(d), e, c.calls))
c = Client(deleted_ids={"id0", "id1"}); ic, A = make(3, c); d, e = ic.delete_assets(A)
step("apple_did_not_confirm_one", lambda: (ids(d), e))
c = Client(fail=True); ic, A = make(2, c); d, e = ic.delete_assets(A)
step("lookup_fails_trust_delete", lambda: (len(d), e))
c = Client(deleted_ids={"id0"}, drop={"id1"}); ic, A = make(2, c); d, e = ic.delete_assets(A)
step("error_record_not_confirmed", lambda: (ids(d), e))
c = Client(deleted_ids={f"id{i}" for i in range(250)}); ic, A = make(250, c); d, e = ic.delete_assets(A)
step("batches_of_100", lambda: (len(d), e, c.calls))
c = Client(); ic, A = make(0, c); d, e = ic.delete_assets(A)
step("empty_list_no_requests", lambda: (d, e, c.calls))
