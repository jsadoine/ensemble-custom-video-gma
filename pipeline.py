#!/usr/bin/env python
"""Pipeline vidéos -> BIDS, à relancer à chaque nouvelle vidéo.

À chaque lancement :
  1. repère les vidéos brutes pas encore traitées (grâce au journal) ;
  2. trouve leur identifiant vidéo (fichier de correspondance, ou saisie au clavier) ;
  3. affiche ce qui va être fait et demande confirmation ;
  4. pour chaque vidéo : conversion MP4 sans métadonnées -> contrôle ->
     rangement BIDS -> copie dans l'archive -> inscription au journal.

Une vidéo n'est inscrite au journal que si tout s'est bien passé ; sinon elle sera
retentée au lancement suivant. Les vidéos d'origine ne sont jamais modifiées.

Usage :
  pixi run python pipeline.py               -> les chemins sont demandés au clavier
  pixi run python pipeline.py config.toml   -> les chemins sont lus dans le fichier
"""
import csv
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from bidsify_videos import NUMERO_RUN, SESSION, TACHE
from check_metadata import problemes
from convert_mp4 import EXTENSIONS, convertir, framerate, lire_infos
from rename_ids import (ID_QUELCONQUE, ID_VIDEO, ajouter_correspondance,
                        demander_id_video, lire_correspondance)

DOSSIER_SCRIPTS = Path(__file__).resolve().parent
NOM_JOURNAL = "journal_videos_traitees.tsv"

# Réglages obligatoires (dans le fichier de config ou demandés au clavier)
QUESTIONS = {
    "videos_brutes": "Dossier des vidéos brutes",
    "correspondance": "Fichier de correspondance des identifiants (CSV ou TSV)",
    "projet": "Dossier du projet (ex. nom_du_projet-videos)",
}


# --- Dialogue avec l'utilisateur ------------------------------------------------
def titre(texte):
    print(f"\n{'=' * 70}\n{texte}\n{'=' * 70}")


def confirmer(question):
    try:
        reponse = input(f"\n{question} [o/N] : ")
    except EOFError:                                  # pas de clavier disponible
        return False
    return reponse.strip().lower() in ("o", "oui", "y", "yes")


def lire_config(fichier):
    """Lit les chemins dans le fichier de config (format TOML)."""
    import tomllib
    with open(fichier, "rb") as f:
        config = tomllib.load(f)
    manquants = [cle for cle in QUESTIONS if cle not in config]
    if manquants:
        sys.exit(f"Réglage(s) manquant(s) dans {fichier} : {', '.join(manquants)}")
    base = Path(fichier).resolve().parent         # chemin relatif = relatif au fichier de config
    chemins = {cle: base / config[cle] for cle in QUESTIONS}
    archive = config.get("archive_mp4", "")
    chemins["archive_mp4"] = base / archive if archive else None
    return chemins


def demander_config():
    """Demande les chemins au clavier."""
    print("Astuce : glisser-déposer un dossier ou un fichier dans cette fenêtre écrit son chemin.\n")
    chemins = {}
    for cle, question in QUESTIONS.items():
        reponse = ""
        while not reponse:
            reponse = input(f"{question} : ").strip().strip('"').strip("'")
        chemins[cle] = Path(reponse)
    archive = input("Dossier d'archive des MP4 (vide = pas d'archive) : ").strip().strip('"').strip("'")
    chemins["archive_mp4"] = Path(archive) if archive else None
    return chemins


def verifier_ffmpeg():
    """Vérifie que ffmpeg est installé et contient l'encodeur H.264."""
    try:
        encodeurs = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                                   capture_output=True, text=True, check=True).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit("ffmpeg est introuvable. Dans le dossier du dépôt, lancer : pixi add ffmpeg")
    if "libx264" not in encodeurs:
        sys.exit("Cette version de ffmpeg ne contient pas l'encodeur H.264 (libx264).\n"
                 'Essayer : pixi add "ffmpeg[build=gpl*]"')


# --- Journal des vidéos déjà traitées ------------------------------------------------
# Il ne contient aucun identifiant : seulement l'empreinte (SHA-256) de chaque vidéo
# brute, sa taille et sa date de modification, et le fichier BIDS produit.
def signature(video):
    """Taille + date de modification : permet de reconnaître vite une vidéo déjà vue."""
    infos = video.stat()
    return f"{infos.st_size}-{infos.st_mtime_ns}"


def empreinte(video):
    """Empreinte SHA-256 du contenu : identique même si la vidéo est renommée ou déplacée."""
    h = hashlib.sha256()
    with open(video, "rb") as f:
        for bloc in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def lire_journal(fichier):
    if not fichier.exists():
        return []
    with fichier.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def inscrire_journal(fichier, empreinte_video, signature_video, fichier_bids):
    nouveau = not fichier.exists()
    with fichier.open("a", newline="", encoding="utf-8") as f:
        ecrivain = csv.writer(f, delimiter="\t")
        if nouveau:
            ecrivain.writerow(["empreinte", "signature", "fichier_bids", "date"])
        ecrivain.writerow([empreinte_video, signature_video, fichier_bids,
                           datetime.now().isoformat(timespec="seconds")])


# --- BIDS -----------------------------------------------------------------------------
def nom_bids(id_video, run):
    return f"sub-{id_video}_ses-{SESSION}_task-{TACHE}_run-{run}_raw.mp4"


def dernier_run(rawdata, id_video, journal):
    """Plus grand numéro de run déjà utilisé pour ce sujet (dans rawdata ou dans le journal),
    pour ne jamais réattribuer le numéro d'une vidéo supprimée."""
    noms = [f.name for f in (rawdata / f"sub-{id_video}").rglob("*.mp4")]
    noms += [ligne["fichier_bids"] for ligne in journal if f"sub-{id_video}_" in ligne["fichier_bids"]]
    return max((int(m.group(1)) for nom in noms if (m := NUMERO_RUN.search(nom))), default=0)


# --- Programme principal ------------------------------------------------------------------
def main():
    chemins = lire_config(sys.argv[1]) if len(sys.argv) > 1 else demander_config()
    brutes, projet, archive = chemins["videos_brutes"], chemins["projet"], chemins["archive_mp4"]
    if not brutes.is_dir():
        sys.exit(f"Dossier des vidéos brutes introuvable : {brutes}")
    verifier_ffmpeg()
    rawdata = projet / "rawdata"
    fichier_journal = projet / NOM_JOURNAL
    journal = lire_journal(fichier_journal)

    # 1. Repérer les nouvelles vidéos
    titre("1. Recherche des nouvelles vidéos")
    signatures_connues = {ligne["signature"] for ligne in journal}
    empreintes_connues = {ligne["empreinte"] for ligne in journal}
    videos = sorted(f for f in brutes.rglob("*")
                    if f.is_file() and not f.name.startswith(".")
                    and f.suffix.lower() in EXTENSIONS)
    nouvelles = {}                                   # empreinte -> (vidéo, signature)
    for video in tqdm(videos, desc="Analyse", unit="vidéo"):
        sig = signature(video)
        if sig in signatures_connues:
            continue                                 # déjà vue, inutile de relire le fichier
        emp = empreinte(video)
        if emp not in empreintes_connues and emp not in nouvelles:
            nouvelles[emp] = (video, sig)
    print(f"{len(videos)} vidéo(s) dans le dossier, dont {len(nouvelles)} nouvelle(s).")
    if not nouvelles:
        titre("Rien à faire : toutes les vidéos ont déjà été traitées.")
        return

    # 2. Trouver l'identifiant vidéo de chaque nouvelle vidéo
    titre("2. Identifiants")
    table, separateur = lire_correspondance(chemins["correspondance"])
    a_traiter, non_traitees = [], []
    for emp, (video, sig) in nouvelles.items():
        trouve = ID_QUELCONQUE.search(video.stem)
        if not trouve:
            non_traitees.append(f"{video.name} : aucun identifiant reconnu dans le nom")
            continue
        id_lu = trouve.group().upper()
        if ID_VIDEO.fullmatch(id_lu):
            id_video = id_lu
        elif id_lu in table:
            id_video = table[id_lu]
        else:
            id_video = demander_id_video(id_lu)
            if not id_video:
                non_traitees.append(f"{video.name} : identifiant vidéo non fourni")
                continue
            table[id_lu] = id_video
            ajouter_correspondance(chemins["correspondance"], separateur, id_lu, id_video)
        a_traiter.append((emp, sig, video, id_video))

    # 3. Afficher le plan et demander confirmation
    titre("3. Vidéos à traiter")
    prochain = {}
    for _, _, video, id_video in a_traiter:
        prochain[id_video] = prochain.get(id_video, dernier_run(rawdata, id_video, journal)) + 1
        print(f"  {video.name:<35} -> {nom_bids(id_video, prochain[id_video])}")
    if non_traitees:
        print("\nVidéos mises de côté (elles seront reproposées au prochain lancement) :")
        for raison in non_traitees:
            print("  -", raison)
    if not a_traiter or not confirmer(f"Lancer le traitement de {len(a_traiter)} vidéo(s) ?"):
        titre("Arrêt : rien n'a été modifié.")
        return

    # 4. Traiter les vidéos une par une
    titre("4. Conversion, contrôle et rangement")
    projet.mkdir(parents=True, exist_ok=True)
    rangees, echecs = [], list(non_traitees)
    with tempfile.TemporaryDirectory(prefix=".tmp_conversion_", dir=projet) as dossier_tmp:
        for emp, sig, video, id_video in tqdm(a_traiter, desc="Traitement", unit="vidéo"):
            fichier_tmp = Path(dossier_tmp) / "video.mp4"
            try:
                convertir(video, fichier_tmp, framerate(lire_infos(video)))
            except Exception:
                fichier_tmp.unlink(missing_ok=True)
                echecs.append(f"{video.name} : échec de la conversion (fichier abîmé ?)")
                continue
            restes = problemes(fichier_tmp)
            if restes:
                fichier_tmp.unlink(missing_ok=True)
                echecs.append(f"{video.name} : métadonnées restantes {restes}")
                continue

            run = dernier_run(rawdata, id_video, journal) + 1
            destination = rawdata / f"sub-{id_video}" / f"ses-{SESSION}" / nom_bids(id_video, run)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(fichier_tmp, destination)
            if archive:
                archive.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, archive / destination.name)

            chemin_bids = destination.relative_to(projet).as_posix()
            inscrire_journal(fichier_journal, emp, sig, chemin_bids)
            journal.append({"empreinte": emp, "signature": sig, "fichier_bids": chemin_bids})
            rangees.append(f"{video.name:<35} -> {destination.name}")

    # Fichier obligatoire à la racine d'un dataset BIDS (créé s'il manque)
    description = rawdata / "dataset_description.json"
    if rangees and not description.exists():
        description.write_text(json.dumps(
            {"Name": projet.name, "BIDSVersion": "1.10.0", "DatasetType": "raw"},
            indent=2), encoding="utf-8")

    # 5. Contrôle de tout rawdata et résumé
    if rawdata.exists():
        titre("5. Contrôle final des métadonnées")
        subprocess.run([sys.executable, str(DOSSIER_SCRIPTS / "check_metadata.py"),
                        str(rawdata), "--rapport", str(projet / "controle_metadonnees.tsv")])

    titre("Résumé")
    print(f"{len(rangees)} vidéo(s) rangée(s) :")
    for ligne in rangees:
        print("  ", ligne)
    if echecs:
        print(f"\n{len(echecs)} vidéo(s) non traitée(s), reproposée(s) au prochain lancement :")
        for raison in echecs:
            print("  -", raison)
    titre("Terminé" if not echecs else "Terminé, mais certaines vidéos n'ont pas été traitées (voir ci-dessus)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrompu. Les vidéos déjà rangées sont conservées ; relancer pour continuer.")
