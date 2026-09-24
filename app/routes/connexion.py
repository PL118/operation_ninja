"""Connexion par mot de passe unique, active seulement s'il est configure.

En local (pas de mot de passe dans config.ini ni dans ON_MOT_DE_PASSE),
l'application reste ouverte comme avant.
"""

import hmac

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from .. import config

bp = Blueprint("connexion", __name__)


def _mot_de_passe():
    return config.valeur("acces", "mot_de_passe")


def exiger_connexion():
    """Avant chaque requete : renvoie vers la connexion si necessaire."""
    if not _mot_de_passe() or session.get("connecte"):
        return None
    if request.endpoint in ("connexion.connexion", "static"):
        return None
    return redirect(url_for("connexion.connexion", suivant=request.full_path))


def _cible_sure(cible):
    # Uniquement un chemin interne, pour ne pas rediriger vers un autre site.
    return cible if cible.startswith("/") and not cible.startswith("//") else "/"


@bp.route("/connexion", methods=["GET", "POST"])
def connexion():
    suivant = _cible_sure(request.values.get("suivant", "/"))
    if request.method == "POST":
        saisi = request.form.get("mot_de_passe", "")
        if hmac.compare_digest(saisi.encode(), _mot_de_passe().encode()):
            session.clear()
            session["connecte"] = True
            session.permanent = True
            return redirect(suivant)
        flash("Mot de passe incorrect.", "erreur")
    return render_template("connexion.html", suivant=suivant)


@bp.route("/deconnexion", methods=["POST"])
def deconnexion():
    session.clear()
    return redirect(url_for("connexion.connexion"))
