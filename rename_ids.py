#!/usr/bin/env python
"""Renomme les vidéos avec leur identifiant vidéo (format 101V100011).

Les fichiers portent souvent l'identifiant général (ex. 101E100011). L'identifiant
vidéo correspondant est lu dans un fichier de correspondance (CSV ou TSV, avec une
ligne d'en-tête et 2 colonnes : identifiant général, identifiant vidéo).
S'il n'y figure pas, il est demandé au clavier puis ajouté au fichier.

Par défaut, le script affiche seulement ce qu'il ferait. Ajouter --apply pour renommer.

Usage : pixi run python rename_ids.py DOSSIER --correspondance ids.tsv [--apply]
"""
import argparse
import csv
import re
from pathlib import Path

from tqdm import tqdm

ID_QUELCONQUE = re.compile(r"\d{3}[A-Z]\d{6}", re.IGNORECASE)  # ex. 101E100011
ID_VIDEO = re.compile(r"\d{3}V\d{6}")                          # ex. 101V100011


def lire_correspondance(fichier):
    """Retourne ({identifiant général: identifiant vidéo}, séparateur du fichier)."""
    if not fichier.exists():
        return {}, "\t"
    with fichier.open(newline="", encoding="utf-8-sig") as f:
        separateur = csv.Sniffer().sniff(f.read(2048), delimiters=",;\t").delimiter
        f.seek(0)
        lignes = list(csv.reader(f, delimiter=separateur))[1:]   # saute l'en-tête
    table = {l[0].strip().upper(): l[1].strip().upper() for l in lignes if len(l) >= 2}
    return table, separateur


def ajouter_correspondance(fichier, separateur, id_general, id_video):
    """Ajoute une ligne au fichier de correspondance (le crée si besoin)."""
    nouveau = not fichier.exists()
    with fichier.open("a", newline="", encoding="utf-8") as f:
        ecrivain = csv.writer(f, delimiter=separateur)
        if nouveau:
            ecrivain.writerow(["id_general", "id_video"])
        ecrivain.writerow([id_general, id_video])


def demander_id_video(id_general):
    """Demande l'identifiant vidéo au clavier, jusqu'à ce qu'il ait le bon format."""
    while True:
        try:
            saisie = input(f"Identifiant vidéo pour {id_general} (vide = passer) : ").strip().upper()
        except EOFError:                                     # pas de clavier disponible
            return ""
        if not saisie or ID_VIDEO.fullmatch(saisie):
            return saisie
        print("  Format attendu : 3 chiffres, V, 6 chiffres (ex. 101V100011)")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dossier", type=Path, help="dossier des MP4 à renommer")
    parser.add_argument("--correspondance", type=Path, required=True,
                        help="fichier CSV/TSV identifiant général -> identifiant vidéo")
    parser.add_argument("--apply", action="store_true", help="renommer vraiment les fichiers")
    args = parser.parse_args()

    table, separateur = lire_correspondance(args.correspondance)
    renommages, ignores = [], []

    # 1. Trouver le nouveau nom de chaque vidéo
    for video in sorted(args.dossier.glob("*.mp4")):
        trouve = ID_QUELCONQUE.search(video.stem)
        if not trouve:
            ignores.append(f"{video.name} : aucun identifiant reconnu")
            continue
        id_lu = trouve.group().upper()

        if ID_VIDEO.fullmatch(id_lu):
            id_video = id_lu                                 # déjà un identifiant vidéo
        elif id_lu in table:
            id_video = table[id_lu]
        else:
            id_video = demander_id_video(id_lu)
            if not id_video:
                ignores.append(f"{video.name} : identifiant vidéo non fourni")
                continue
            table[id_lu] = id_video
            ajouter_correspondance(args.correspondance, separateur, id_lu, id_video)

        nouveau = video.with_name(video.name.replace(trouve.group(), id_video))  # garde le reste du nom
        if nouveau != video:
            renommages.append((video, nouveau))

    # 2. Écarter les conflits (deux vidéos vers le même nom, ou nom déjà pris)
    cibles = [nouveau for _, nouveau in renommages]
    valides = []
    for video, nouveau in renommages:
        if cibles.count(nouveau) > 1 or nouveau.exists():
            ignores.append(f"{video.name} : conflit, {nouveau.name} existe déjà ou est en double")
        else:
            valides.append((video, nouveau))

    # 3. Afficher le tableau, puis renommer si --apply
    print("\nRenommages prévus :" if valides else "\nAucun renommage à faire.")
    for video, nouveau in valides:
        print(f"  {video.name:<35} -> {nouveau.name}")
    if ignores:
        print("\nFichiers non traités :")
        for raison in ignores:
            print("  -", raison)

    if not args.apply:
        print("\nRien n'a été modifié. Relancer avec --apply pour renommer.")
        return
    for video, nouveau in tqdm(valides, desc="Renommage", unit="fichier"):
        video.rename(nouveau)
    print(f"\n{len(valides)} fichier(s) renommé(s).")


if __name__ == "__main__":
    main()
