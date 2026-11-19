"""Vérifie que infer_sides ne fait pas converger les deux camps vers une seule couleur en
partie miroir (même codex des deux côtés, donc aucune règle d'armée ne peut servir d'ancrage).
Reproduit le cas signalé : quelques unités en réserve d'un seul camp se verrouillent tôt (vote
de position fort), puis sans correctif leur règle d'armée/teinte partagée « contaminait » le
score des unités suivantes au point d'écraser leur propre position — tout le plateau finissait
du même côté. Avec le correctif, has_groups=False se fie uniquement à la position de chaque
unité (cf. docstring de infer_sides : « partie miroir : position seule »)."""
import sys
sys.path.insert(0, "app")
from core import infer_sides

ABILITIES = "Nom de l'unité\nOath of Moment"  # même règle d'armée des deux côtés : mirror match
TINT = {"r": 0.5, "g": 0.5, "b": 0.5}  # même teinte des deux côtés aussi


def unit(guid, z, abilities=ABILITIES):
    return {"guid": guid, "pos": {"x": 0.0, "z": z}, "abilities": abilities}


units = (
    [unit(f"rr{i}", 200.0) for i in range(3)]      # réserve Rouge (vote de position fort, verrouillée tôt)
    + [unit(f"rn{i}", 20.0) for i in range(3)]      # Rouge normal (moitié z > 0 du plateau)
    + [unit(f"bn{i}", -20.0) for i in range(3)]     # Bleu normal (moitié z < 0 du plateau), AUCUNE réserve Bleu
)
tints = {u["guid"]: (TINT["r"], TINT["g"], TINT["b"]) for u in units}
doubt = set()

result = infer_sides(units, {}, board_hd=50.0, red_positive_z=True, tints=tints, doubt=doubt)

for i in range(3):
    assert result[f"rr{i}"] == "Red", f"rr{i} (réserve, position claire) doit rester Rouge"
    assert result[f"rn{i}"] == "Red", f"rn{i} (z>0) doit être Rouge"
    assert result[f"bn{i}"] == "Blue", (
        f"bn{i} (z<0, moitié Bleu du plateau) a été classé {result[f'bn{i}']} : "
        "la règle d'armée/teinte partagée par le miroir a écrasé sa propre position "
        "au lieu de s'effacer devant elle (has_groups=False doit ignorer by_line/by_tint)."
    )

print("OK : infer_sides ne fait pas converger les deux camps d'un miroir vers une seule couleur")
