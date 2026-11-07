"""Vérifie le signal de fin de partie probable : fin de la phase de Combat (dernière phase)
du DEUXIÈME tour (seq pair) d'un round >= 5 (missions LCT = 5 rounds, cf. score_summary)."""
import sys
sys.path.insert(0, "app")
from core import is_final_phase_end

# round 5, tour de Rouge (2e tour du round, seq pair) : fin de partie probable
assert is_final_phase_end((5, "Red"), "Fight", 10) is True
# round 5, tour de Bleu (1er tour du round, seq impair) : pas encore, l'autre joueur n'a pas joué
assert is_final_phase_end((5, "Blue"), "Fight", 9) is False
# bonne phase/round mais pas la dernière phase
assert is_final_phase_end((5, "Red"), "Movement", 10) is False
# round trop tôt
assert is_final_phase_end((4, "Red"), "Fight", 8) is False
# partie plus longue que la normale (round 6) : le signal reste valable
assert is_final_phase_end((6, "Red"), "Fight", 12) is True
# pas de clé (hors partie) : jamais de signal
assert is_final_phase_end(None, "Fight", 10) is False

print("OK : is_final_phase_end détecte la fin probable de partie (round >= 5, Combat, 2e tour)")
