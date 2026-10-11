# 🎓 Moodle Everything Scraper & Générateur de Notes Markdown

> **Conçu à l'origine pour l'EPITA, mais 100% universel et compatible avec N'IMPORTE QUELLE école ou université sous Moodle !**

Outil d'extraction et de synchronisation complète des cours Moodle.  
Il transforme l'intégralité de vos cours Moodle en un **environnement de travail hors-ligne en Markdown**, prêt pour la révision et la prise de notes dans **Obsidian**, **VS Code** ou **Typora**.

---

### 🌐 Compatibilité Universelle (Toute Université sous Moodle)
Bien qu'optimisé avec des exemples et configurations par défaut pour l'EPITA (support de Forge ID SSO, Pod vidéo EPITA, etc.), ce scraper repose sur le cœur standard de **Moodle 3.x et Moodle 4.x**.

**Il fonctionne avec n'importe quel établissement (Sorbonne, Paris-Saclay, Polytechnique, Centrale, Lyon, McGill, etc.) :**
- Il vous suffit de remplacer l'URL par celle de votre Moodle (`URL=https://moodle.votre-etablissement.fr`).
- Fonctionne avec tous les types d'authentification :
  - **SSO / Ent / 2FA (Microsoft, Google, CAS, Shibboleth, SAML) :** via le cookie standard `MoodleSession`.
  - **Token API WebService Moodle :** via `MOODLE_TOKEN` ou `--token`.
  - **Identifiants classiques (Nom d'utilisateur + Mot de passe) :** via `MOODLE_USERNAME` et `MOODLE_PASSWORD` ou `-u` / `-p`.

---

## ✨ Ce que cet outil extrait

Contrairement à l'ancien script qui ne téléchargeait que les fichiers PDF bruts, cette version optimisée extrait **absolument tout** :

1. **Textes & Descriptions complètes de chaque chapitre** :
   - Titres, sous-catégories et arborescence exacte de Moodle.
   - Tous les textes descriptifs (par exemple : *"Le dénombrement est l'acte de compter ou d'énumérer les éléments d'un ensemble fini..."*).
   - Préservation fidèle des **formules mathématiques LaTeX** (`$...$` et `$$...$$`) sans corruption d'indices ou de fractions.

2. **Pages de cours (`mod_page`)** :
   - Converties en fichiers Markdown complets dans un sous-dossier `pages/`.
   - Liées directement depuis le chapitre correspondant.

3. **Vidéos & Contenus interactifs (`mod_url`, H5P, Pod EPITA)** :
   - Extraction des liens directs vers les vidéos (Pod EPITA, YouTube, Vimeo, Panopto).
   - Liens cliquables et intégration directe dans les notes.

4. **Tests & QCM (`mod_quiz`)** :
   - Fiche dédiée dans `qcms/` avec les consignes, barème et temps disponible.
   - **Extraction des questions, réponses et corrigés** dès qu'une tentative a été effectuée sur Moodle !

5. **Documents & Dossiers de TD (`mod_resource`, `mod_folder`)** :
   - Téléchargement automatique de tous les documents (énoncés, corrections d'examens, fiches de synthèse).
   - Pour les dossiers (ex: *TD Séminaire*, *TD du semestre 1*), création d'un sous-dossier dédié avec tous les fichiers.
   - Liens relatifs Markdown cliquables vers chaque fichier téléchargé.

6. **Devoirs maisons & Travaux à rendre (`mod_assign`)** :
   - Consignes, dates limites et énoncés joints.

7. **Prise de notes pérenne (`## ✍️ Mes Notes Personnelles`)** :
   - Chaque fiche de cours et chaque QCM possède une zone dédiée à vos notes personnelles.
   - **Vos notes ne sont JAMAIS écrasées** lors des prochaines synchronisations !

---

## 🗂️ Structure des notes générées

```text
EPITA_Moodle_Notes/
├── README.md                                          <- Index global de tous vos cours
└── Mathématiques en prépa à l'EPITA/                   <- Dossier du cours
    ├── README.md                                      <- Sommaire complet du cours
    ├── 00_Consignes/
    │   └── README.md
    ├── 01_Documents de travail - TD, examens/
    │   ├── README.md
    │   └── fichiers/
    │       ├── TD_Seminaire/
    │       │   └── TD_Seminaire.pdf
    │       └── TD_du_semestre_1/
    │           ├── TD1_Enonce.pdf
    │           └── TD1_Corrige.pdf
    └── 04_Cours 1 - Dénombrement - ECUE DP/
        ├── README.md                                  <- Fiche principale du chapitre
        │                                                 - Textes de présentation & LaTeX
        │                                                 - Liens vers pages, vidéos, QCM, docs
        │                                                 - Zone "Mes Notes Personnelles"
        ├── pages/
        │   └── 01_Dénombrement en informatique.md      <- Contenu complet de la page de cours
        ├── qcms/
        │   ├── 01_✅ QCM Dénombrements de référence.md <- Questions, options et corrigé
        │   └── 02_✅ QCM Coefficients binomiaux.md
        └── fichiers/
            └── Fiche_de_synthese.pdf                  <- Document téléchargé en local
```

---

## 🚀 Installation & Utilisation

### 1. Prérequis

Assurez-vous d'avoir Python 3.8+ installé. Dans le dossier du projet :

```bash
# Activer l'environnement virtuel existant ou en créer un :
source .venv/bin/activate

# Ou installer les dépendances :
pip install -r requirements.txt
```

---

### 2. Authentification avec Forge ID (CRI EPITA)

Moodle EPITA utilisant le SSO **Forge ID**, la méthode la plus rapide et 100% fiable consiste à renseigner votre cookie de session `MoodleSession`.

#### Comment récupérer votre cookie en 15 secondes :
1. Connectez-vous sur **[https://moodle.epita.fr](https://moodle.epita.fr)** avec votre compte Forge ID sur Chrome, Firefox ou Brave.
2. Appuyez sur **F12** (Outils de développement).
3. Allez dans l'onglet **Application** (ou **Stockage** sur Firefox) ➔ **Cookies** ➔ `https://moodle.epita.fr`.
4. Cliquez sur le cookie nommé `MoodleSession` et copiez sa valeur (ex: `82dglt0rpd4iss8jgngqm8eqla`).

Vous pouvez soit :
- Le coller dans `config.py` à la ligne `MOODLE_SESSION = "VOTRE_COOKIE"`.
- Ou le passer directement en ligne de commande avec `--cookie`.
- Ou lancer simplement `python main.py` : le script vous le demandera et vous proposera de le sauvegarder automatiquement !

---

### 3. Lancer la synchronisation

#### Télécharger tous les cours :
```bash
python main.py
```

#### Télécharger uniquement le cours de Mathématiques :
```bash
python main.py --course "Mathématiques"
```

#### Lister uniquement les cours disponibles :
```bash
python main.py --list
```

#### Générer uniquement les notes Markdown sans télécharger les gros fichiers :
```bash
python main.py --no-files
```

#### Télécharger également les vidéos en local (MP4) :
```bash
python main.py --download-videos
```

---

## ⚙️ Configuration avancée (`config.py`)

Vous pouvez personnaliser les réglages par défaut dans `config.py` :

| Variable | Description | Valeur par défaut |
|---|---|---|
| `MOODLE_URL` | URL de la plateforme Moodle | `"https://moodle.epita.fr"` |
| `MOODLE_SESSION` | Cookie de session Forge ID | `""` |
| `OUTPUT_DIR` | Dossier de destination des notes | `"EPITA_Moodle_Notes"` |
| `DOWNLOAD_FILES` | Télécharger les PDF et documents | `True` |
| `DOWNLOAD_VIDEOS` | Télécharger les vidéos avec yt-dlp | `False` *(liens en markdown)* |
| `COURSES_FILTER` | Liste de cours ciblés par défaut | `[]` *(tous les cours)* |

---

## 📝 Utilisation avec Obsidian ou VS Code

1. Lancez le scraper : vos cours sont générés dans `EPITA_Moodle_Notes/`.
2. Ouvrez **Obsidian** ➔ *Open folder as vault* ➔ Sélectionnez `EPITA_Moodle_Notes`.
3. Vous disposez d'un espace de travail complet :
   - Tous les liens entre chapitres, pages et corrigés fonctionnent instantanément.
   - Les formules de mathématiques s'affichent avec MathJax/KaTeX.
   - Vos notes personnelles sous `## ✍️ Mes Notes Personnelles` restent intactes même après de futures synchronisations.
