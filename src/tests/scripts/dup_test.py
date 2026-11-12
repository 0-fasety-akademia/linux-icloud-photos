import os
import sys
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import backend
class A:
    def __init__(s, i): s.id=f"id{i}"; s.filename=f"IMG_{i:04d}.HEIC"
class Alb:
    def __init__(s, members, fail_listing=False, fail_add=()):
        s.members={f"id{i}" for i in members}; s.added=[]; s.fail_listing=fail_listing; s.fail_add=set(fail_add); s._direction=None
    def __iter__(s):
        if s.fail_listing: raise RuntimeError("sieć niedostępna")
        return (A(int(i[2:])) for i in sorted(s.members))
    def add_photo(s, a):
        if a.id in s.fail_add: raise RuntimeError("HTTP 500")
        s.added.append(a.id); s.members.add(a.id); return True
ic=backend.ICloud()
assets=[A(i) for i in (1,2,3,4,5)]
alb=Alb({2,4,9}); ok,already,err=ic.add_to_album(alb, assets)
print("część już jest   : dodane", ok, "| już w albumie", [a.id for a in already], "| dodano", alb.added, "| błędy", err)
alb=Alb({1,2,3,4,5}); ok,already,err=ic.add_to_album(alb, assets)
print("wszystkie już są : dodane", ok, "| już", len(already), "| add_photo wywołane:", alb.added)
alb=Alb(set()); ok,already,err=ic.add_to_album(alb, assets)
print("żadne nie jest   : dodane", ok, "| już", len(already), "| dodano", alb.added)
alb=Alb({2}, fail_listing=True); ok,already,err=ic.add_to_album(alb, assets)
print("lista albumu pada: dodane", ok, "| już", len(already), "| błędy", err)
alb=Alb({2}, fail_add={"id3"}); ok,already,err=ic.add_to_album(alb, assets)
print("jedno add pada   : dodane", ok, "| już", [a.id for a in already], "| błędy", err)
prog=[]; alb=Alb({1,2}); ic.add_to_album(alb, assets, lambda k,n: prog.append((k,n))); print("postęp liczy tylko dodawane:", prog)
