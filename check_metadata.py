#!/usr/bin/env python
"""Vérifie qu'aucune métadonnée identifiante ne reste dans les vidéos MP4.

Pour chaque vidéo (dossier parcouru avec ses sous-dossiers, donc aussi rawdata),
le script signale :
  - les tags de métadonnées (titre, date, auteur, lieu GPS, appareil...)
  - les chapitres
  - les pistes autres que la vidéo et l'audio (sous-titres, données GPS, images jointes)

Usage : pixi run python check_metadata.py DOSSIER [--rapport rapport.tsv]
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

# Tags techniques que le format mp4 écrit toujours (aucune info sur le participant)
TAGS_TECHNIQUES = {"major_brand", "minor_version", "compatible_brands",
                   "handler_name", "vendor_id", "language"}


def lire_infos(video):
    """Lit les infos de la vidéo avec ffprobe (pistes, métadonnées, chapitres)."""
    sortie = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-show_chapters", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return json.loads(sortie.stdout)


def tag_suspect(nom, valeur):
    if nom in TAGS_TECHNIQUES:
        return False
    if nom == "encoder" and valeur.startswith("Lavc"):    # nom du codec, ex. « Lavc libx264 »
        return False
    return True


def problemes(video):
    """Liste des problèmes trouvés dans la vidéo (liste vide = OK)."""
    try:
        infos = lire_infos(video)
    except subprocess.CalledProcessError:
        return ["fichier illisible"]

    trouves = [f"tag {nom} = {valeur}"
               for nom, valeur in infos["format"].get("tags", {}).items()
               if tag_suspect(nom, valeur)]
    for piste in infos["streams"]:
        numero, type_piste = piste["index"], piste.get("codec_type")
        if type_piste not in ("video", "audio"):
            trouves.append(f"piste {numero} de type {type_piste} ({piste.get('codec_name')})")
        elif piste.get("disposition", {}).get("attached_pic"):
            trouves.append(f"piste {numero} : image jointe (pochette)")
        trouves += [f"piste {numero} : tag {nom} = {valeur}"
                    for nom, valeur in piste.get("tags", {}).items()
                    if tag_suspect(nom, valeur)]
    if infos.get("chapters"):
        trouves.append(f"{len(infos['chapters'])} chapitre(s)")
    return trouves


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dossier", type=Path, help="dossier à vérifier (ex. rawdata)")
    parser.add_argument("--rapport", type=Path, help="enregistrer le résultat dans un fichier TSV")
    args = parser.parse_args()

    videos = sorted(args.dossier.rglob("*.mp4"))
    if not videos:
        sys.exit(f"Aucune vidéo MP4 trouvée dans {args.dossier}")

    resultats = {}
    for video in tqdm(videos, desc="Vérification", unit="vidéo"):
        resultats[video] = problemes(video)

    a_corriger = {v: p for v, p in resultats.items() if p}
    for video, liste in a_corriger.items():
        print(f"\n{video.relative_to(args.dossier)}")
        for probleme in liste:
            print("  -", probleme)
    print(f"\n{len(videos)} vidéo(s) vérifiée(s) : {len(videos) - len(a_corriger)} OK, "
          f"{len(a_corriger)} avec des métadonnées restantes")

    if args.rapport:
        with args.rapport.open("w", newline="", encoding="utf-8") as f:
            ecrivain = csv.writer(f, delimiter="\t")
            ecrivain.writerow(["fichier", "statut", "details"])
            for video, liste in resultats.items():
                ecrivain.writerow([video.relative_to(args.dossier),
                                   "A_CORRIGER" if liste else "OK", " | ".join(liste)])
        print(f"Rapport : {args.rapport}")

    sys.exit(1 if a_corriger else 0)


if __name__ == "__main__":
    main()
