"""Ecran N deg 6 - Gestion des distributeurs."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db

bp = Blueprint("distributeurs", __name__, url_prefix="/distributeurs")


def _lire_formulaire(code=None):
    """Retourne (libelle, retenues ordonnees, retirees, erreurs).

    Les categories arrivent dans l'ordre ou le glisser-deposer les a laissees ;
    seules les valeurs du referentiel sont gardees, une oubliee est retenue.
    """
    libelle = request.form.get("libelle", "").strip()[:50]
    retirees = list(dict.fromkeys(
        c for c in request.form.getlist("retirees") if c in db.CATEGORIES
    ))
    retenues = list(dict.fromkeys(
        c for c in request.form.getlist("categories") if c in db.CATEGORIES and c not in retirees
    ))
    retenues += [c for c in db.CATEGORIES if c not in retenues and c not in retirees]

    erreurs = []
    if not retenues:
        erreurs.append("Gardez au moins une categorie.")
    if not libelle:
        erreurs.append("Le libelle est obligatoire.")
    elif db.un(
        """SELECT 1 FROM Distributeurs
           WHERE Libelle = ? COLLATE NOCASE AND Code_unique_distributeur IS NOT ?""",
        (libelle, code),
    ):
        erreurs.append(f"Le distributeur « {libelle} » existe deja.")
    return libelle, retenues, retirees, erreurs


def _enregistrer_ordre(code, retenues, retirees):
    db.executer("DELETE FROM Distributeur_Categorie WHERE Code_unique_distributeur = ?", (code,))
    lignes = [(c, 1) for c in retenues] + [(c, 0) for c in retirees]
    connexion = db.connexion()
    connexion.executemany(
        """INSERT INTO Distributeur_Categorie
           (Code_unique_distributeur, Categorie, Ordre, Retenue) VALUES (?, ?, ?, ?)""",
        [(code, categorie, ordre, retenue) for ordre, (categorie, retenue) in enumerate(lignes)],
    )
    connexion.commit()


def _afficher(libelle, retenues, retirees, **contexte):
    return render_template(
        "distributeurs/form.html", libelle=libelle, retenues=retenues,
        retirees=retirees, **contexte,
    )


@bp.route("/")
def liste():
    lignes = db.lister(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM Articles a WHERE a.Distributeur = d.Libelle)
                      AS Nb_articles
           FROM Distributeurs d ORDER BY d.Libelle"""
    )
    return render_template("distributeurs/liste.html", distributeurs=lignes)


@bp.route("/nouveau", methods=["GET", "POST"])
def nouveau():
    if request.method == "POST":
        libelle, retenues, retirees, erreurs = _lire_formulaire()
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "erreur")
            return _afficher(libelle, retenues, retirees, creation=True)

        code = db.nouvelle_cle("Distributeurs")
        db.executer(
            "INSERT INTO Distributeurs (Code_unique_distributeur, Libelle) VALUES (?, ?)",
            (code, libelle),
        )
        _enregistrer_ordre(code, retenues, retirees)
        flash(f"Distributeur « {libelle} » cree.", "succes")
        return redirect(url_for("distributeurs.liste"))

    # Copie : libelle et classement des rayons repris de la source.
    libelle, retenues, retirees, copie = "", list(db.CATEGORIES), [], ""
    code_source = request.args.get("copie", "").strip()
    if code_source:
        source = db.un(
            "SELECT * FROM Distributeurs WHERE Code_unique_distributeur = ?", (code_source,)
        )
        if source is None:
            flash("Distributeur a copier introuvable.", "erreur")
        else:
            copie = source["Libelle"]
            libelle = f"{copie} (copie)"[:50]
            retenues, retirees = db.categories_distributeur(code_source)
    return _afficher(libelle, retenues, retirees, creation=True, copie=copie)


@bp.route("/<code>/modifier", methods=["GET", "POST"])
def modifier(code):
    distributeur = db.un(
        "SELECT * FROM Distributeurs WHERE Code_unique_distributeur = ?", (code,)
    )
    if distributeur is None:
        flash("Distributeur introuvable.", "erreur")
        return redirect(url_for("distributeurs.liste"))

    if request.method == "POST":
        libelle, retenues, retirees, erreurs = _lire_formulaire(code)
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "erreur")
            return _afficher(libelle, retenues, retirees, code=code, creation=False)

        ancien = distributeur["Libelle"]
        db.executer(
            "UPDATE Distributeurs SET Libelle = ? WHERE Code_unique_distributeur = ?",
            (libelle, code),
        )
        # Articles et listes designent l'enseigne par son libelle.
        if libelle != ancien:
            for table in ("Articles", "Liste_course"):
                db.executer(
                    f"UPDATE {table} SET Distributeur = ? WHERE Distributeur = ?",
                    (libelle, ancien),
                )
        _enregistrer_ordre(code, retenues, retirees)
        flash("Distributeur modifie.", "succes")
        return redirect(url_for("distributeurs.liste"))

    retenues, retirees = db.categories_distributeur(code)
    return _afficher(distributeur["Libelle"], retenues, retirees, code=code, creation=False)


@bp.route("/<code>/supprimer", methods=["POST"])
def supprimer(code):
    distributeur = db.un(
        "SELECT * FROM Distributeurs WHERE Code_unique_distributeur = ?", (code,)
    )
    if distributeur is None:
        flash("Distributeur introuvable.", "erreur")
    elif db.un(
        "SELECT 1 FROM Articles WHERE Distributeur = ? LIMIT 1", (distributeur["Libelle"],)
    ):
        # Pas de cle etrangere sur le libelle : la protection est faite ici.
        flash(
            "Suppression impossible : ce distributeur est utilise par des articles.",
            "erreur",
        )
    else:
        db.executer("DELETE FROM Distributeurs WHERE Code_unique_distributeur = ?", (code,))
        flash("Distributeur supprime.", "succes")
    return redirect(url_for("distributeurs.liste"))
