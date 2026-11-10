#!/usr/bin/env python
"""Convertit les vidéos d'un dossier en MP4 (preset HandBrake « Fast 1080p30 »)
et supprime leurs métadonnées.

Usage : pixi run python convert_mp4.py DOSSIER_SOURCE DOSSIER_SORTIE
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".wmv", ".mpg"}

# Tags techniques que le format mp4 écrit toujours (aucune info sur le participant)
TAGS_TECHNIQUES = {"major_brand", "minor_version", "compatible_brands",
                   "handler_name", "vendor_id", "language", "encoder"}


def lire_infos(video):
    """Lit les infos de la vidéo avec ffprobe (pistes, framerate, métadonnées)."""
    sortie = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams",
         "-show_chapters", "-of", "json", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return json.loads(sortie.stdout)


def framerate(infos):
    """Nombre d'images par seconde de la piste vidéo (0 si inconnu)."""
    piste = next(p for p in infos["streams"] if p["codec_type"] == "video")
    num, den = piste["avg_frame_rate"].split("/")
    return float(num) / float(den) if float(den) else 0


def convertir(source, destination, fps):
    """Équivalent des réglages HandBrake de la SOP, en une commande ffmpeg."""
    commande = [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?",              # 1re piste vidéo + 1re piste audio
        "-map_metadata", "-1", "-map_chapters", "-1",   # supprime métadonnées et chapitres
        "-fflags", "+bitexact",                         # n'ajoute pas de métadonnées ffmpeg
        "-vf", "bwdif=mode=send_frame:deint=interlaced,"  # filtre Decomb
               "scale=w='min(1920,iw)':h='min(1080,ih)'"  # 1080p maximum
               ":force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "libx264", "-crf", "22", "-preset", "fast",  # H.264, qualité RF 22
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "2", "-b:a", "160k",      # audio AAC stéréo
    ]
    if fps > 30:
        commande += ["-r", "30"]                        # 30 FPS max ; en dessous, inchangé
    commande.append(str(destination))
    subprocess.run(commande, check=True)


def metadonnees_restantes(video):
    """Liste les métadonnées encore présentes (liste vide = OK)."""
    infos = lire_infos(video)
    restantes = [t for t in infos["format"].get("tags", {}) if t not in TAGS_TECHNIQUES]
    for piste in infos["streams"]:
        restantes += [t for t in piste.get("tags", {}) if t not in TAGS_TECHNIQUES]
    if infos.get("chapters"):
        restantes.append("chapitres")
    return restantes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="dossier des vidéos originales")
    parser.add_argument("sortie", type=Path, help="nouveau dossier pour les MP4")
    args = parser.parse_args()

    if args.sortie.resolve() == args.source.resolve():
        sys.exit("Le dossier de sortie doit être différent du dossier source.")
    args.sortie.mkdir(parents=True, exist_ok=True)

    videos = sorted(f for f in args.source.iterdir() if f.suffix.lower() in EXTENSIONS)
    problemes = []

    for video in tqdm(videos, desc="Conversion", unit="vidéo"):
        destination = args.sortie / (video.stem + ".mp4")
        if destination.exists():
            continue                                    # déjà convertie lors d'un lancement précédent
        try:
            convertir(video, destination, framerate(lire_infos(video)))
        except subprocess.CalledProcessError:
            destination.unlink(missing_ok=True)
            problemes.append(f"{video.name} : échec de la conversion")
            continue
        except KeyboardInterrupt:
            destination.unlink(missing_ok=True)         # pas de fichier à moitié converti
            raise
        restantes = metadonnees_restantes(destination)
        if restantes:
            problemes.append(f"{video.name} : métadonnées restantes {restantes}")

    print(f"\n{len(videos)} vidéo(s) trouvée(s), {len(problemes)} problème(s)")
    for probleme in problemes:
        print(" -", probleme)


if __name__ == "__main__":
    main()
