import os
import sys, random
sys.path.insert(0, os.environ["PROJECT_ROOT"])
import backend as B
random.seed(2); asp=[random.choice([0.56,0.75,1.0,1.33,1.5,1.78,2.4]) for _ in range(500)]
W=1100; H=180; rows=B.justify_rows(asp, W, H, 4)
print("rzędów:", len(rows), "| pokryte zdjęcia:", sum(r[1] for r in rows), "z", len(asp), "| ciągłe:", all(rows[k][0]+rows[k][1]==rows[k+1][0] for k in range(len(rows)-1)))
full=rows[:-1]
print("pełne rzędy wypełniają szerokość:", all(sum(r[3])+4*(r[1]-1)==W for r in full), "| odchyłka max (px):", max(abs(sum(r[3])+4*(r[1]-1)-W) for r in full))
print("wysokości pełnych rzędów (min/śr/max):", min(r[2] for r in full), round(sum(r[2] for r in full)/len(full)), max(r[2] for r in full), "(cel", H, ")")
print("ostatni rząd: wysokość =", rows[-1][2], "| szerokość", sum(rows[-1][3])+4*(rows[-1][1]-1), "<=", W)
print("kształt zachowany (w/h ≈ aspekt):", all(abs(r[3][k]/r[2]-asp[r[0]+k])<0.06*asp[r[0]+k]+0.02 for r in full for k in range(r[1])))
r=B.justify_rows([3.0], 1000, 180, 4); print("jedno bardzo szerokie zdjęcie:", r)
r=B.justify_rows([0.5]*3, 1000, 180, 4); print("kilka wąskich (niepełny rząd):", r)
print("pusta lista:", B.justify_rows([], 800, 180))
print("bardzo wąskie okno:", B.justify_rows([1.5,1.5], 50, 180)[0][:3])
# aspekt z orientacją
class A:
    def __init__(s,w,h,o): s.dimensions=(w,h); s._asset_record={"fields":{"orientation":{"value":o}}}
import types
print("poziome 4000x3000:", round(B.asset_aspect(A(4000,3000,1)),3), "| pionowe zapisane jako 4000x3000 (orient 6):", round(B.asset_aspect(A(4000,3000,6)),3), "| brak wymiarów:", round(B.asset_aspect(types.SimpleNamespace(dimensions=(None,None))),3), "| błąd:", round(B.asset_aspect(object()),3))
