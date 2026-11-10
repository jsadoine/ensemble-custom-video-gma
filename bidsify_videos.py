#!/usr/bin/env python
"""Range les vidéos renommées dans l'arborescence BIDS du projet :

    <projet>/rawdata/sub-<ID>/ses-m4/sub-<ID>_ses-m4_task-gma_run-<N>_raw.mp4

Les vidéos d'un même sujet sont numérotées run-1, run-2... dans l'ordre alphabétique
de leur nom. Si le sujet a déjà des vidéos dans rawdata, la numérotation continue,
et une vidéo identique à une vidéo déjà rangée est ignorée.

Par défaut, le script affiche seulement ce qu'il ferait. Ajouter --apply pour copier
les fichiers, ou --apply --move pour les déplacer.

Usage : pixi run python bidsify_videos.py DOSSIER_MP4 DOSSIER_PROJET [--apply] [--move]
"""
import argparse
import filecmp
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from tqdm import tqdm

SESSION = "m4"
TACHE = "gma"
ID_VIDEO = re.compile(r"\d{3}V\d{6}")   # ex. 101V100011
NUMERO_RUN = re.compile(r"_run-(\d+)_")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dossier", type=Path, help="dossier des MP4 renommés (identifiant en V)")
    parser.add_argument("projet", type=Path, help="dossier du projet, ex. nom_du_projet-videos")
    parser.add_argument("--apply", action="store_true", help="copier vraiment les fichiers")
    parser.add_argument("--move", action="store_true", help="déplacer au lieu de copier")
    args = parser.parse_args()

    rawdata = args.projet / "rawdata"
    ignores = []

    # 1. Regrouper les vidéos par sujet
    par_sujet = defaultdict(list)
    for video in sorted(args.dossier.glob("*.mp4")):
        trouve = ID_VIDEO.search(video.stem)
        if trouve:
            par_sujet[trouve.group()].append(video)
        else:
            ignores.append(f"{video.name} : pas d'identifiant vidéo (lancer d'abord rename_ids.py)")

    # 2. Calculer le chemin BIDS de chaque vidéo
    plan = []
    for sujet, videos in par_sujet.items():
        dossier_session = rawdata / f"sub-{sujet}" / f"ses-{SESSION}"
        deja_ranges = sorted(dossier_session.glob("*.mp4"))
        run = max((int(m.group(1)) for f in deja_ranges if (m := NUMERO_RUN.search(f.name))),
                  default=0)                                    # dernier run déjà présent
        for video in videos:
            if any(filecmp.cmp(video, f, shallow=False) for f in deja_ranges):
                ignores.append(f"{video.name} : déjà présente dans rawdata")
                continue
            run += 1
            nom = f"sub-{sujet}_ses-{SESSION}_task-{TACHE}_run-{run}_raw.mp4"
            plan.append((video, dossier_session / nom))

    # 3. Afficher le tableau
    verbe, action = ("déplacer", "déplacées") if args.move else ("copier", "copiées")
    print(f"\nVidéos à {verbe} :" if plan else "\nAucune vidéo à ranger.")
    for video, destination in plan:
        print(f"  {video.name:<35} -> {destination.relative_to(args.projet)}")
    if ignores:
        print("\nFichiers non traités :")
        for raison in ignores:
            print("  -", raison)

    if not args.apply:
        print("\nRien n'a été modifié. Relancer avec --apply"
              + (" --move" if args.move else "") + " pour le faire.")
        return

    # 4. Copier ou déplacer
    for video, destination in tqdm(plan, desc="Rangement BIDS", unit="vidéo"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.move:
            shutil.move(video, destination)
        else:
            shutil.copy2(video, destination)

    # Fichier obligatoire à la racine d'un dataset BIDS (créé s'il manque)
    description = rawdata / "dataset_description.json"
    if plan and not description.exists():
        description.write_text(json.dumps(
            {"Name": args.projet.name, "BIDSVersion": "1.10.0", "DatasetType": "raw"},
            indent=2), encoding="utf-8")

    print(f"\n{len(plan)} vidéo(s) {action} dans {rawdata}")


if __name__ == "__main__":
    main()
