# ==============================================================================
# PARAMÈTRES CONFIGURABLES
# Modifiez ces variables directement ici ou surchargez-les en ligne de commande :
# Ex: make run COOKIE="votre_cookie"
#     make maths COOKIE="votre_cookie"
# ==============================================================================

# Cookie MoodleSession (obtenu via DevTools F12 après connexion Forge ID SSO)
COOKIE ?=

# URL du Moodle EPITA
URL ?= https://moodle.epita.fr

# Dossier d'exportation des cours en Markdown
OUTPUT ?= EPITA_Moodle_Notes

# Filtre de cours par défaut (laisser vide pour tout télécharger)
COURSE ?=

# Téléchargement des vidéos via yt-dlp (0 = désactivé, 1 = activé)
DOWNLOAD_VIDEOS ?= 0

# Environnement Python
VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
PIP ?= $(VENV)/bin/pip

# Options dynamiques passées au script
ARGS := --url "$(URL)" --output "$(OUTPUT)"
ifneq ($(strip $(COOKIE)),)
	ARGS += --cookie "$(COOKIE)"
endif
ifneq ($(strip $(COURSE)),)
	ARGS += --course "$(COURSE)"
endif
ifeq ($(DOWNLOAD_VIDEOS),1)
	ARGS += --download-videos
endif

.PHONY: all help setup install run sync maths math list no-files clean

all: run

help:
	@echo "========================================================================"
	@echo "🎓 Moodle Everything Scrapper - Guide d'utilisation Make"
	@echo "========================================================================"
	@echo "Commandes disponibles :"
	@echo "  make setup          : Crée le venv et installe les dépendances"
	@echo "  make run            : Lance l'extraction complète (COOKIE=\"...\")"
	@echo "  make maths          : Télécharge uniquement les cours de Mathématiques"
	@echo "  make list           : Liste les cours sans rien télécharger"
	@echo "  make no-files       : Génère uniquement le Markdown (sans gros fichiers)"
	@echo "  make clean          : Supprime les fichiers temporaires et caches Python"
	@echo ""
	@echo "Exemples d'utilisation :"
	@echo "  make run COOKIE=\"abc123...\""
	@echo "  make maths COOKIE=\"abc123...\""
	@echo "  make run COOKIE=\"abc123...\" COURSE=\"Algorithmique\""
	@echo "  make run COOKIE=\"abc123...\" OUTPUT=\"Mes_Notes_EPITA\""
	@echo "========================================================================"

setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	@echo "📦 Création du venv et installation des dépendances..."
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@echo "✅ Environnement prêt !"

install: setup

run: setup
	$(PYTHON) main.py $(ARGS)

sync: run

maths: setup
	$(PYTHON) main.py $(ARGS) --course "Mathématiques"

math: maths

list: setup
	$(PYTHON) main.py $(ARGS) --list

no-files: setup
	$(PYTHON) main.py $(ARGS) --no-files

clean:
	rm -rf __pycache__ *.pyc *.pyo *.tmp state.json
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "🧹 Cache nettoyé !"
