"""Ecran N deg 1 - Accueil."""

from flask import Blueprint, render_template

from .. import db

bp = Blueprint("accueil", __name__)


@bp.route("/")
def index():
    compteurs = {
        "recettes": db.un("SELECT COUNT(*) AS n FROM Recettes")["n"],
        "articles": db.un("SELECT COUNT(*) AS n FROM Articles")["n"],
        "listes": db.un("SELECT COUNT(*) AS n FROM Liste_course")["n"],
        "distributeurs": db.un("SELECT COUNT(*) AS n FROM Distributeurs")["n"],
    }
    return render_template("accueil.html", compteurs=compteurs)
