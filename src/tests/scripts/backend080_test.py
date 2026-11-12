import sys, os, random
sys.path.insert(0, os.environ["PROJECT_ROOT"])
from datetime import datetime, timedelta, timezone
import backend
from pyicloud.services.photos import DirectionEnum as D
# --- is_auth_error
class PyiCloudFailedLoginException(Exception): pass
class CloudKitAuthError(Exception): pass
print("auth:", [backend.is_auth_error(e) for e in (PyiCloudFailedLoginException("x"), CloudKitAuthError("HTTP 403: unauthorized"), Exception("Invalid global session"), RuntimeError("HTTP 500"), ValueError("brak wersji"))])
# --- parser dat
for q in ("2024","08.2024","2024-08","15.08.2024","2024-08-15","sierpień 2024","15 sie 2024","sie 2024","aug 2024","paź 2023","32.01.2024","abc","1850"):
    r=backend.parse_date_query(q); print(f"{q!r:18} ->", (r[2], r[0].date(), r[1].date()) if r else None)
# --- find_start na atrapie albumu (naśladuje _get_photos_at)
N=12000; BASE=datetime(2015,1,1,tzinfo=timezone.utc)
dates=sorted(BASE+timedelta(minutes=int(random.Random(5).random()*0)+i*400) for i in range(N))   # rosnąco
class A:
    def __init__(s,i): s.id=f"i{i}"; s.asset_date=dates[i]
class Alb:
    page_size=100; probes=0
    def __len__(s): return N
    def _get_photos_at(s, idx, direction, ps):
        s.probes+=1
        idx=max(0,idx)
        rng = range(idx, min(N, idx+ps*2)) if direction==D.ASCENDING else range(idx, max(-1, idx-ps*2), -1)
        for i in rng: yield A(i)
def expected_rank(ts):  # pierwsza pozycja z datą >= ts
    return next((i for i,d in enumerate(dates) if d.timestamp()>=ts), N-1)
ic=backend.ICloud()
for label, dt in (("środek", dates[6000]+timedelta(minutes=10)), ("początek", dates[3]), ("przed 2015", datetime(2010,1,1,tzinfo=timezone.utc)), ("po końcu", dates[-1]+timedelta(days=9))):
    alb=Alb(); ts=dt.timestamp()
    rank, desc = ic.find_start(alb, ts, True)
    print(f"{label:11s} newest_first -> rank={rank} desc={desc} data_pozycji={dates[rank].date()} (cel {dt.date()}) zapytań={alb.probes}")
alb=Alb(); ts=(dates[6000]+timedelta(minutes=10)).timestamp()
it=ic.iter_jump(alb, ts, True); first=[next(it) for _ in range(250)]
print("iter_jump newest-first: pierwsza ≤ cel:", first[0].asset_date.timestamp()<=ts, "| malejąco:", all(first[i].asset_date>=first[i+1].asset_date for i in range(249)))
alb=Alb(); it=ic.iter_jump(alb, ts, False); first=[next(it) for _ in range(250)]
print("iter_jump oldest-first: pierwsza ≥ cel:", first[0].asset_date.timestamp()>=ts, "| rosnąco:", all(first[i].asset_date<=first[i+1].asset_date for i in range(249)))
# --- album z datami MALEJĄCYMI po pozycji (np. sortowanie wg daty dodania)
dates_desc=list(reversed(dates))
class Alb2(Alb):
    def _get_photos_at(s, idx, direction, ps):
        idx=max(0,idx); rng = range(idx, min(N, idx+ps*2)) if direction==D.ASCENDING else range(idx, max(-1, idx-ps*2), -1)
        for i in rng:
            a=A(i); a.asset_date=dates_desc[i]; yield a
alb=Alb2(); r=ic.find_start(alb, dates[6000].timestamp()+60, True); it=ic.iter_jump(Alb2(), dates[6000].timestamp()+60, True); f=[next(it) for _ in range(5)]
print("album malejący po pozycji: pierwsza ≤ cel:", f[0].asset_date.timestamp()<=dates[6000].timestamp()+60, "| malejąco:", all(f[i].asset_date>=f[i+1].asset_date for i in range(4)))
# --- cache
os.makedirs(backend.THUMB_DIR, exist_ok=True); open(backend.THUMB_DIR/"x.img","wb").write(b"1"*1000)
print("cache_size>=1000:", backend.cache_size()>=1000, "| clear zwolnił:", backend.clear_cache()>=1000, "| po:", backend.cache_size())
