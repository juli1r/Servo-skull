"""Déduit la faction d'un camp à partir des noms d'unités (le fichier anonyme ne contient pas la faction).

Approximation à base de mots-clés : à remplacer par la vraie faction dès qu'elle sera ajoutée à l'export.
Une unité générique (Chaos Rhino...) ne vote pour personne ; la faction qui a le plus d'unités reconnues l'emporte."""
from collections import Counter

KEYWORDS = {
    "World Eaters": ["angron", "khârn", "kharn", "jakhal", "goremonger", "slaughterbound", "eightbound", "berzerker",
                     "juggernaut", "daemon prince of khorne", "red butcher", "world eaters"],
    "Grey Knights": ["grey knight", "strike squad", "interceptor", "purifier", "brotherhood", "castellan crowe",
                     "nemesis", "grand master", "paladin"],
    "Space Marines": ["scout squad", "deathwatch", "sicarius", "calgar", "sternguard", "victrix", "terminator assault",
                      "librarian", "wardens of ultramar", "intercessor", "ultramarines"],
    "Orks": ["boyz", "meganobz", "warboss", "nazdreg", "deffkopta", "trukk", "painboy", "flash gitz", "gretchin",
             "stormboyz", "ghazghkull", "nob", "lootas", "kommandos"],
    "Death Guard": ["poxwalker", "mortarion", "typhus", "plaguecaster", "blightbringer", "blight-hauler", "plague marine",
                    "death guard", "foetid"],
    "Adeptus Custodes": ["custodes", "custodian", "allarus", "trajann", "shield-captain", "telemon", "contemptor-galatus",
                         "venatari", "witchseeker", "prosecutor", "vigilator"],
    "Adeptus Mechanicus": ["skitarii", "kastelan", "skorpius", "onager", "cawl", "enginseer", "datasmith", "dragoon",
                           "tech-priest", "ironstrider", "sicarian", "ballistarius"],
    "Chaos Daemons": ["plaguebearer", "flesh hound", "daemonette", "poxbringer", "skull cannon", "be'lakor", "bilepiper",
                      "bloodletter", "horror", "screamer", "fateskimmer"],
}


def faction_of(squads: list[dict], side: str) -> str:
    votes = Counter()
    for s in squads:
        if s.get("s") != side:
            continue
        name = s["n"].lower()
        for fac, words in KEYWORDS.items():
            if any(w in name for w in words):
                votes[fac] += 1
                break
    return votes.most_common(1)[0][0] if votes else "Inconnue"
