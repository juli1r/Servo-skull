"""Simule 5 rounds de parties dans le suiveur de tours : chaque phase de chaque tour doit produire exactement un événement."""
import sys,collections
sys.path.insert(0,'app')
from core import TurnTracker, PHASE_ORDER
def st(r,t,ph,ig=True):
    return {"inGame":ig,"round":r,"turn":t,"phase":ph,"phaseName":PHASE_ORDER[ph-1] if ph else ""}
def run(seq):
    tr=TurnTracker(my_color="Red");seen=collections.Counter()
    for s in seq:
        for e in tr.update(s):
            if e[0]=="phase_ended": seen[(e[1],e[2])]+=1
    return seen
def full(skip=lambda r,t,ph:False):
    seq=[st(0,"Blue",0,False),st(1,"Blue",1)]
    for r in range(1,6):
        for t in ("Blue","Red"):
            for ph in range(1,6):
                if not skip(r,t,ph): seq.append(st(r,t,ph))
    seq.append(st(5,"Red",5,False))   # fin de partie
    return seq
need={((r,t),n) for r in range(1,6) for t in("Blue","Red") for n in PHASE_ORDER}
for name,sk in [("toutes les phases lues",lambda r,t,p:False),("Charge et Combat sautés tous les tours",lambda r,t,p:p in(4,5)),
                ("Tir sauté + Combat sauté au tour 3",lambda r,t,p:(p==3) or (r==3 and p==5)),("Commandement sauté (lu en retard)",lambda r,t,p:p==1)]:
    seen=run(full(sk));missing=sorted(need-set(seen));dup=[k for k,v in seen.items() if v>1]
    print(f"{name:45s} manquantes: {len(missing):2d}  doublons: {len(dup)}",missing[:4])
