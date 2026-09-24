"""Point d'entree Operation_ninja.

Demarre le serveur web local puis ouvre Chrome sur l'application, dans une
fenetre dediee sans onglets ni barre d'adresse (mode application).
La fermeture de Chrome arrete le serveur.

    python run.py                 # serveur + fenetre Chrome
    python run.py --plein-ecran   # idem en kiosk plein ecran
    python run.py --serveur-seul  # serveur seul (developpement)
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from waitress import serve

from app import config, creer_app

# Emplacements habituels de Chrome sous Windows.
CHEMINS_CHROME = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LocalAppData", ""))
    / "Google/Chrome/Application/chrome.exe",
]


def trouver_chrome():
    """Retourne le chemin de chrome.exe, ou None s'il est introuvable."""
    force = os.environ.get("CHROME_PATH")
    if force and Path(force).exists():
        return Path(force)
    for chemin in CHEMINS_CHROME:
        if chemin.exists():
            return chemin
    return None


def lancer_chrome(url, plein_ecran=False):
    """Ouvre Chrome sur l'application.

    Par defaut, fenetre dediee redimensionnable, sans onglets ni barre
    d'adresse (--app). Avec plein_ecran, kiosk occupant tout l'ecran.
    Retourne le processus, ou None si Chrome est introuvable.
    """
    chrome = trouver_chrome()
    if chrome is None:
        print("Chrome introuvable. Ouvrez manuellement :", url)
        print("Astuce : definissez CHROME_PATH pour indiquer le chemin de chrome.exe.")
        return None

    # Profil dedie : evite de reutiliser une fenetre Chrome deja ouverte,
    # qui rouvrirait l'application dans un simple onglet.
    profil = config.DOSSIER_DATA / "profil_chrome"
    profil.mkdir(parents=True, exist_ok=True)

    arguments = [
        str(chrome),
        f"--user-data-dir={profil}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if plein_ecran:
        arguments += ["--kiosk", url]
    else:
        arguments += [f"--app={url}", "--window-size=1280,900"]

    return subprocess.Popen(arguments)


def main():
    # --no-kiosk : ancien nom de --serveur-seul, conserve pour compatibilite.
    ouvrir_chrome = not {"--serveur-seul", "--no-kiosk"} & set(sys.argv)
    plein_ecran = "--plein-ecran" in sys.argv
    hote = config.valeur("serveur", "hote") or "127.0.0.1"
    port = config.entier("serveur", "port", 5000)
    url = f"http://{hote}:{port}/"

    app = creer_app()
    print(f"Operation_ninja demarre sur {url}")
    print(f"Base de donnees : {config.FICHIER_BASE}")

    if not ouvrir_chrome:
        serve(app, host=hote, port=port)
        return

    # Le serveur tourne en tache de fond ; le programme se termine avec Chrome.
    serveur = threading.Thread(
        target=serve, args=(app,), kwargs={"host": hote, "port": port}, daemon=True
    )
    serveur.start()
    time.sleep(1)  # laisse le temps au socket d'etre en ecoute

    navigateur = lancer_chrome(url, plein_ecran)
    if navigateur is None:
        print("Ctrl+C pour arreter le serveur.")
        serveur.join()
        return

    try:
        navigateur.wait()
    except KeyboardInterrupt:
        navigateur.terminate()
    print("Chrome ferme, arret d'Operation_ninja.")


if __name__ == "__main__":
    main()
