# video-gma : vidéos → MP4 anonymisés → BIDS

Ce dépôt automatise les étapes la SOP HandBrake. **À chaque nouvelle vidéo, on la dépose dans le dossier des vidéos brutes et on double-clique sur `lancer_pipeline.bat`.** Pour chaque vidéo pas encore traitée, le pipeline :

1. **convertit** la vidéo en MP4 (mêmes réglages que le preset HandBrake « Fast 1080p30 ») et **supprime ses métadonnées** (date, lieu GPS, appareil, titre…) ;
2. lui donne l'**identifiant vidéo** (`101V…`) à la place de l'identifiant général (`101E…`) ;
3. la **range** au format BIDS dans le dossier du projet ;
4. **vérifie** qu'aucune métadonnée identifiante ne reste.

Les vidéos déjà traitées sont reconnues et **ne sont jamais refaites**. Les vidéos d'origine ne sont **jamais modifiées**.

---

## 1. Installation (une seule fois par ordinateur)

### Installer pixi

Pixi installe automatiquement tout ce dont le pipeline a besoin (Python, ffmpeg…). Il ne demande **pas de droits administrateur**.

Sous Windows, ouvrir **PowerShell** (menu Démarrer → taper « PowerShell ») et coller :

```powershell
powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

Puis **fermer et rouvrir** PowerShell (ou se déconnecter / reconnecter) pour que la commande `pixi` soit reconnue.

### Récupérer ce dossier

Copier le dossier du dépôt sur l'ordinateur (via `git clone` ou en téléchargeant l'archive du dépôt).
Le premier lancement télécharge les outils nécessaires : il prend quelques minutes, les suivants sont immédiats.

---

## 2. Préparer le fichier de correspondance des identifiants

Les vidéos sont souvent nommées avec l'identifiant général (ex. `101E100011.mov`). Le pipeline a besoin de savoir quel identifiant vidéo lui correspond.

Créer un fichier CSV (Excel → *Enregistrer sous* → CSV) avec **une ligne d'en-tête** et **deux colonnes** :

| id_general | id_video   |
|------------|------------|
| 101E100011 | 101V555011 |
| 102E100022 | 102V555022 |

- Les séparateurs `;` (Excel français), `,` et tabulation sont acceptés.
- Si un identifiant manque dans le fichier, le pipeline le **demande au clavier** et l'ajoute au fichier.
- Si le fichier n'existe pas encore, il est créé au fur et à mesure des saisies.

> ⚠️ **Ce fichier permet de ré-identifier les participants.** Le garder dans un espace sécurisé, ne jamais l'envoyer par mail ni le mettre dans le dépôt git (il est exclu par le `.gitignore`).

---

## 3. Indiquer les dossiers à utiliser (facultatif mais recommandé)

1. Faire une copie de `config_exemple.toml` et la renommer **`config.toml`**.
2. L'ouvrir avec le Bloc-notes et remplacer les chemins :

```toml
videos_brutes  = 'C:\Etude\videos_brutes'           # où déposer les vidéos d'origine
correspondance = 'C:\Etude\correspondance_ids.csv'
projet         = 'C:\Etude\nom_du_projet-videos'    # dossier BIDS final
archive_mp4    = 'C:\Etude\archive_mp4'             # facultatif : copie de chaque MP4 produit
```

- Garder les **apostrophes simples** `'…'` autour des chemins Windows.
- Astuce : dans l'Explorateur Windows, clic droit sur un dossier → *Copier en tant que chemin d'accès*.

Sans `config.toml`, le pipeline pose ces questions au lancement : il suffit alors de **glisser-déposer** chaque dossier dans la fenêtre puis d'appuyer sur Entrée.

---

## 4. Lancer le pipeline

**Double-cliquer sur `lancer_pipeline.bat`.**

Une fenêtre s'ouvre et déroule les étapes :

| Étape | Ce qui se passe | Ce qu'on vous demande |
|---|---|---|
| 1. Recherche | Le pipeline repère les vidéos pas encore traitées | Rien |
| 2. Identifiants | Il cherche l'identifiant vidéo de chaque nouvelle vidéo | L'identifiant vidéo s'il manque dans le fichier de correspondance |
| 3. Vidéos à traiter | Un tableau `vidéo -> nom BIDS` s'affiche | **o** pour lancer |
| 4. Traitement | Une barre de progression avance vidéo par vidéo | Rien |
| 5. Contrôle final | Toutes les vidéos du projet sont vérifiées | Rien |

S'il n'y a aucune nouvelle vidéo, le pipeline affiche « Rien à faire » et s'arrête.
Répondre autre chose que **o** arrête le pipeline sans rien modifier.

### Résultat

```
nom_du_projet-videos
├── journal_videos_traitees.tsv       ← liste des vidéos déjà traitées (ne pas supprimer)
├── controle_metadonnees.tsv          ← rapport du contrôle final
└── rawdata
    ├── dataset_description.json
    └── sub-101V555011
        └── ses-m4
            ├── sub-101V555011_ses-m4_task-gma_run-1_raw.mp4
            └── sub-101V555011_ses-m4_task-gma_run-2_raw.mp4
```

Si un dossier d'archive est indiqué, une copie de chaque MP4 y est aussi enregistrée sous son nom BIDS.

La fenêtre se termine par un **résumé** : vidéos rangées, et éventuellement vidéos non traitées avec la raison. Une vidéo non traitée (identifiant manquant, fichier abîmé…) sera **reproposée automatiquement** au lancement suivant.
Une vidéo dont les métadonnées n'ont pas pu être supprimées n'est **jamais rangée** dans le projet.

---

## 5. Bon à savoir

- **Plusieurs vidéos pour un même participant** : elles deviennent `run-1`, `run-2`… dans l'**ordre alphabétique** de leur nom. Pour garder l'ordre chronologique, nommer les fichiers d'origine en conséquence (ex. `101E100011_essai1.mov`, `101E100011_essai2.mov`).
- **Comment le pipeline sait ce qui est déjà fait** : le fichier `journal_videos_traitees.tsv` garde l'empreinte numérique de chaque vidéo traitée. Une vidéo renommée, déplacée ou copiée deux fois est donc reconnue. Ce journal ne contient **aucun identifiant de participant**. **Ne pas le supprimer** : sans lui, toutes les vidéos seraient retraitées.
- **Une nouvelle vidéo d'un participant existant** reçoit le numéro de run suivant.
- **Une vidéo rejetée** (supprimée de `rawdata`, par exemple après le contrôle qualité) n'est **pas** retraitée au clic suivant, et son numéro de run n'est jamais réattribué.
- **La date incrustée dans l'image** (affichée par certains caméscopes) n'est pas une métadonnée : le pipeline ne peut pas la supprimer. Vérifier visuellement quelques vidéos si le matériel d'enregistrement change.
- **Formats acceptés** : `.mp4 .mov .avi .mkv .m4v .mts .wmv .mpg`.

## 6. En cas de problème

| Message | Que faire |
|---|---|
| `'pixi' n'est pas reconnu…` | Pixi n'est pas installé, ou la session n'a pas été rouverte après l'installation (voir §1). |
| `Dossier des vidéos brutes introuvable` | Vérifier le chemin dans `config.toml` (apostrophes simples, dossier existant). |
| `… : identifiant vidéo non fourni` | Ajouter la ligne dans le fichier de correspondance, puis relancer. |
| `… : aucun identifiant reconnu` | Le nom du fichier ne contient pas d'identifiant de la forme `101E100011` : le renommer à la main, puis relancer. |
| `… : échec de la conversion` | Le fichier vidéo est probablement abîmé ou incomplet : vérifier qu'il se lit dans un lecteur vidéo. |

Pour toute autre erreur, faire une capture de la fenêtre et l'envoyer au responsable du dépôt.

---

## Pour les utilisateurs avancés

Lancement en ligne de commande (Linux ou Windows) :

```bash
pixi run pipeline                 # pose les questions
pixi run pipeline config.toml     # lit le fichier de config
```

Les scripts ci-dessous peuvent aussi être lancés seuls, sur un dossier entier (sans journal). Sans `--apply`, `rename_ids.py` et `bidsify_videos.py` n'affichent que ce qu'ils feraient :

```bash
pixi run python convert_mp4.py    videos_brutes/ videos_mp4/
pixi run python rename_ids.py     videos_mp4/ --correspondance ids.csv [--apply]
pixi run python bidsify_videos.py videos_mp4/ nom_du_projet-videos/ [--apply] [--move]
pixi run python check_metadata.py nom_du_projet-videos/rawdata [--rapport controle.tsv]
```

| Fichier | Rôle |
|---|---|
| `pipeline.py` | Pipeline incrémental : traite uniquement les nouvelles vidéos, une par une, en réutilisant les fonctions des scripts ci-dessous |
| `convert_mp4.py` | Conversion MP4 (réglages HandBrake « Fast 1080p30 » : H.264 RF 22, AAC stéréo 160 kb/s, 1080p et 30 i/s maximum, désentrelacement) et suppression des métadonnées |
| `rename_ids.py` | Remplacement de l'identifiant général par l'identifiant vidéo |
| `bidsify_videos.py` | Rangement en `rawdata/sub-<ID>/ses-m4/sub-<ID>_ses-m4_task-gma_run-<N>_raw.mp4` |
| `check_metadata.py` | Contrôle des métadonnées restantes (tags, chapitres, pistes de sous-titres ou de données GPS) |
| `config_exemple.toml` | Modèle de fichier de configuration |
| `lancer_pipeline.bat` | Lanceur Windows (double-clic) |
