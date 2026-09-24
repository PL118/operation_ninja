"""Operation_ninja - application Flask locale."""

import os
from datetime import timedelta

from flask import Flask

from . import config, db
from .routes import accueil, connexion, courses, articles, distributeurs, recettes

# Version affichee en pied de page. Une seule ligne a changer pour la faire
# evoluer : le code d'ecran, lui, est pose par chaque template.
VERSION = "V1"


def creer_app():
    app = Flask(__name__)
    app.config["FICHIER_BASE"] = str(config.FICHIER_BASE)
    # Cle de session : fixe en ligne (config ou ON_SECRET_KEY) ; en local,
    # une cle aleatoire par demarrage suffit.
    app.config["SECRET_KEY"] = config.valeur("acces", "cle_secrete") or os.urandom(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

    db.initialiser(app)
    app.teardown_appcontext(db.fermer_connexion)

    app.register_blueprint(connexion.bp)
    app.before_request(connexion.exiger_connexion)
    app.register_blueprint(accueil.bp)
    app.register_blueprint(recettes.bp)
    app.register_blueprint(articles.bp)
    app.register_blueprint(courses.bp)
    app.register_blueprint(distributeurs.bp)
    app.jinja_env.filters["euros"] = lambda v: f"{(v or 0):.2f} €"
    app.jinja_env.filters["quantite"] = lambda v: f"{(v or 0):g}"
    # Code d'unite -> symbole affiche ("gramme" -> "gr").
    app.jinja_env.filters["unite"] = lambda code: db.UNITES.get(code, ("", ""))[1]
    app.jinja_env.globals["VERSION"] = VERSION
    app.jinja_env.globals["UNITES"] = db.UNITES
    app.jinja_env.globals["CATEGORIES"] = db.CATEGORIES
    # Liste tenue en base : relue a chaque page, pour refleter les ajouts
    # faits depuis l'ecran Distributeurs.
    app.context_processor(lambda: {"DISTRIBUTEURS": db.distributeurs()})
    app.jinja_env.globals["CATEGORIES_RECETTE"] = db.CATEGORIES_RECETTE
    app.jinja_env.filters["categories_recette"] = db.categories_recette

    return app
