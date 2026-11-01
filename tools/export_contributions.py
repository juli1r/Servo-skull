"""Lit les contributions reçues dans Firestore (avec TON compte, pas depuis l'application) et les range en local.

Prérequis (une fois) : pip install google-cloud-firestore ; dans Firebase > Paramètres du projet > Comptes de service,
« Générer une nouvelle clé privée », puis : set GOOGLE_APPLICATION_CREDENTIALS=C:\\chemin\\cle.json
Usage : python tools/export_contributions.py [dossier_sortie]      (par défaut : donnees_contributions)
Supprimer une partie à la demande d'un joueur : python tools/export_contributions.py --supprimer <id_de_partie>
Ne mets JAMAIS la clé privée dans le dépôt Git."""
import base64
import csv
import gzip
import json
import sys
from pathlib import Path

COLLECTION = "servoskull_contributions"


def decode(doc: dict) -> dict:
    """Document Firestore -> contribution complète (le fichier .json.gz d'origine, décodé)."""
    return json.loads(gzip.decompress(base64.b64decode(doc["payload"])))


def summary(gid: str, d: dict) -> dict:
    last = (d.get("caps") or [{}])[-1].get("score") or {}
    return {"id": gid, "mois": d.get("month"), "mode": d.get("mode"), "layout": d.get("layout"),
            "unites": len(d.get("squads") or []), "captures": len(d.get("caps") or []),
            "pv_A": (last.get("A") or {}).get("total"), "pv_B": (last.get("B") or {}).get("total"),
            "version": d.get("app")}


def main(argv):
    from google.cloud import firestore  # import tardif : le reste du fichier se teste sans
    db = firestore.Client()
    if len(argv) == 3 and argv[1] == "--supprimer":
        db.collection(COLLECTION).document(argv[2]).delete()
        print("supprimée :", argv[2])
        return
    out = Path(argv[1] if len(argv) > 1 else "donnees_contributions")
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for snap in db.collection(COLLECTION).stream():
        d = decode(snap.to_dict())
        (out / f"{snap.id}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        rows.append(summary(snap.id, d))
    if rows:
        with open(out / "resume.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter=";")
            w.writeheader()
            w.writerows(rows)
    print(f"{len(rows)} partie(s) exportée(s) dans {out}")


if __name__ == "__main__":
    main(sys.argv)
