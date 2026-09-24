"""Configuration de l'application.

Les valeurs sont lues dans config.ini a la racine du projet, puis surchargees
par les variables d'environnement. Le mot de passe SMTP ne doit jamais etre
ecrit en dur dans le code.
"""

import configparser
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_DATA = RACINE / "data"
FICHIER_BASE = DOSSIER_DATA / "operation_ninja.db"
FICHIER_CONFIG = RACINE / "config.ini"

# Valeurs par defaut, utilisees si ni config.ini ni l'environnement ne les fournissent.
DEFAUTS = {
    "serveur": {
        "hote": "127.0.0.1",
        "port": "5000",
    },
    # Identifiant et cle SMTP : dans config.ini ou l'environnement, jamais ici.
    "smtp": {
        "hote": "",
        "port": "587",
        "utilisateur": "",
        "mot_de_passe": "",
        # Doit etre declaree comme expediteur verifie dans Brevo, sinon
        # l'envoi est refuse.
        "expediteur": "mailpub117@gmail.com",
        # Pre-rempli dans le formulaire d'envoi de l'ecran liste de courses.
        "destinataire": "antoine.lassale@gmail.com",
        "tls": "oui",
        # A ne mettre a "non" que pour un serveur local de confiance presentant
        # un certificat auto-signe, jamais pour un SMTP distant.
        "verifier_certificat": "oui",
    },
}

# Correspondance section/cle -> variable d'environnement.
ENVIRONNEMENT = {
    ("serveur", "hote"): "ON_HOTE",
    ("serveur", "port"): "ON_PORT",
    ("smtp", "hote"): "SMTP_HOST",
    ("smtp", "port"): "SMTP_PORT",
    ("smtp", "utilisateur"): "SMTP_USER",
    ("smtp", "mot_de_passe"): "SMTP_PASSWORD",
    ("smtp", "expediteur"): "SMTP_FROM",
    ("smtp", "destinataire"): "SMTP_TO",
    ("smtp", "tls"): "SMTP_TLS",
    ("smtp", "verifier_certificat"): "SMTP_VERIFY_CERT",
}


def _lire_config():
    lecteur = configparser.ConfigParser()
    lecteur.read_dict(DEFAUTS)
    if FICHIER_CONFIG.exists():
        lecteur.read(FICHIER_CONFIG, encoding="utf-8")

    for (section, cle), variable in ENVIRONNEMENT.items():
        valeur = os.environ.get(variable)
        if valeur is not None:
            lecteur.set(section, cle, valeur)

    return lecteur


_CONFIG = _lire_config()


def valeur(section, cle):
    return _CONFIG.get(section, cle, fallback="").strip()


def entier(section, cle, defaut=0):
    try:
        return int(valeur(section, cle))
    except ValueError:
        return defaut


def booleen(section, cle):
    return valeur(section, cle).lower() in ("oui", "yes", "true", "1", "on")


def smtp_configure():
    """Vrai si les parametres minimum d'envoi d'email sont renseignes."""
    return bool(valeur("smtp", "hote") and valeur("smtp", "expediteur"))
