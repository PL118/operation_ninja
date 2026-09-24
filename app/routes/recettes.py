"""Ecran N deg 2 - Gestion des recettes."""

import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db

bp = Blueprint("recettes", __name__, url_prefix="/recettes")


def _lire_formulaire():
    """Cles nommees comme les colonnes : le template affiche indifferemment
    une ligne de la base ou une saisie a corriger."""
    donnees = {
        "Libelle": request.form.get("libelle", "").strip()[:50],
        "Description": request.form.get("description", "").strip()[:255],
        "Nombre_personnes": request.form.get("nombre_personnes", "").strip(),
        # Seules les valeurs du referentiel sont retenues, dans son ordre.
        "Categories": db.SEPARATEUR_CATEGORIES.join(
            c for c in db.CATEGORIES_RECETTE if c in request.form.getlist("categories")
        ),
    }
    erreurs = []

    if not donnees["Libelle"]:
        erreurs.append("Le libelle est obligatoire.")

    if not donnees["Nombre_personnes"]:
        erreurs.append("Le nombre de personnes est obligatoire.")
        donnees["Nombre_personnes"] = 1
    else:
        try:
            donnees["Nombre_personnes"] = int(donnees["Nombre_personnes"])
            if donnees["Nombre_personnes"] < 1:
                erreurs.append("Le nombre de personnes doit etre au moins 1.")
        except ValueError:
            erreurs.append("Le nombre de personnes doit etre un entier.")
            donnees["Nombre_personnes"] = 1

    return donnees, erreurs


def _articles_de(code_recette):
    # i.Quantite (conditionnement) et ri.Quantite (besoin de la recette) portent
    # le meme nom : les colonnes sont enumerees pour lever l'ambiguite.
    return db.lister(
        f"""SELECT i.Code_unique_article, i.Libelle, i.Marque, i.Unite,
                   i.Prix_euros, i.Quantite AS Conditionnement,
                   ri.Quantite AS Quantite,
                   {db.PRIX_UNITAIRE} AS Prix_unitaire,
                   ri.Quantite * ({db.PRIX_UNITAIRE}) AS Cout
            FROM Recette_Article ri
            JOIN Articles i USING (Code_unique_article)
            WHERE ri.Code_unique_recette = ?
            ORDER BY i.Libelle""",
        (code_recette,),
    )


@bp.route("/")
def liste():
    recherche = request.args.get("q", "").strip()
    categorie = request.args.get("categorie", "").strip()
    if categorie not in db.CATEGORIES_RECETTE:
        categorie = ""

    conditions, parametres = [], []
    if recherche:
        conditions.append("(r.Libelle LIKE ? OR r.Description LIKE ?)")
        parametres += [f"%{recherche}%", f"%{recherche}%"]
    if categorie:
        # Separateurs ajoutes aux deux bouts : "Plat" ne doit pas trouver "Plateau".
        sep = db.SEPARATEUR_CATEGORIES
        conditions.append("(? || IFNULL(r.Categories, '') || ?) LIKE ?")
        parametres += [sep, sep, f"%{sep}{categorie}{sep}%"]

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    lignes = db.lister(
        f"""SELECT r.*,
                   (SELECT COUNT(*) FROM Recette_Article ri
                    WHERE ri.Code_unique_recette = r.Code_unique_recette)
                       AS Nb_articles
            FROM Recettes r{where}
            ORDER BY r.Libelle""",
        parametres,
    )
    return render_template(
        "recettes/liste.html", recettes=lignes, q=recherche, categorie=categorie
    )


@bp.route("/nouvelle", methods=["GET", "POST"])
def nouvelle():
    if request.method == "POST":
        donnees, erreurs = _lire_formulaire()
        source = request.form.get("copie", "").strip()
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "erreur")
            return render_template(
                "recettes/form.html", recette=donnees, copie=source,
                copie_libelle=request.form.get("copie_libelle", ""),
            )

        code = db.nouvelle_cle("Recettes")
        db.executer(
            """INSERT INTO Recettes
               (Code_unique_recette, Libelle, Description, Nombre_personnes, Categories)
               VALUES (?, ?, ?, ?, ?)""",
            (code, donnees["Libelle"], donnees["Description"], donnees["Nombre_personnes"],
             donnees["Categories"] or None),
        )

        if source:
            db.executer(
                """INSERT INTO Recette_Article
                   (Code_unique_recette, Code_unique_article, Quantite)
                   SELECT ?, Code_unique_article, Quantite
                   FROM Recette_Article WHERE Code_unique_recette = ?""",
                (code, source),
            )
            flash("Recette creee avec les articles de la recette copiee.", "succes")
        else:
            flash("Recette creee. Ajoutez maintenant ses articles.", "succes")
        return redirect(url_for("recettes.modifier", code=code))

    code_source = request.args.get("copie", "").strip()
    modele = None
    libelle_source = ""
    if code_source:
        source = db.un(
            "SELECT * FROM Recettes WHERE Code_unique_recette = ?", (code_source,)
        )
        if source is None:
            flash("Recette a copier introuvable.", "erreur")
            code_source = ""
        else:
            libelle_source = source["Libelle"]
            modele = dict(source)
            modele["Libelle"] = f"{libelle_source} (copie)"[:50]

    return render_template(
        "recettes/form.html", recette=modele, copie=code_source,
        copie_libelle=libelle_source,
    )


@bp.route("/<code>/modifier", methods=["GET", "POST"])
def modifier(code):
    recette = db.un("SELECT * FROM Recettes WHERE Code_unique_recette = ?", (code,))
    if recette is None:
        flash("Recette introuvable.", "erreur")
        return redirect(url_for("recettes.liste"))

    if request.method == "POST":
        donnees, erreurs = _lire_formulaire()
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "erreur")
        else:
            db.executer(
                """UPDATE Recettes
                   SET Libelle = ?, Description = ?, Nombre_personnes = ?, Categories = ?
                   WHERE Code_unique_recette = ?""",
                (
                    donnees["Libelle"],
                    donnees["Description"],
                    donnees["Nombre_personnes"],
                    donnees["Categories"] or None,
                    code,
                ),
            )
            flash("Recette modifiee.", "succes")
        return redirect(url_for("recettes.modifier", code=code))

    composition = _articles_de(code)
    return render_template(
        "recettes/modifier.html",
        recette=recette,
        composition=composition,
        cout_total=sum(ligne["Cout"] or 0 for ligne in composition),
        catalogue=db.catalogue(),
        marques=db.marques(),
    )


@bp.route("/<code>/articles/ajouter", methods=["POST"])
def ajouter_article(code):
    code_article = request.form.get("code_article", "").strip()
    quantite = request.form.get("quantite", "").strip().replace(",", ".")

    try:
        quantite = round(float(quantite or 0), 2)
    except ValueError:
        quantite = -1

    if not code_article:
        flash("Choisissez un article a ajouter.", "erreur")
    elif quantite <= 0:
        flash("La quantite doit etre un nombre superieur a zero.", "erreur")
    else:
        # Un article deja present voit sa quantite remplacee.
        db.executer(
            """INSERT INTO Recette_Article
               (Code_unique_recette, Code_unique_article, Quantite)
               VALUES (?, ?, ?)
               ON CONFLICT (Code_unique_recette, Code_unique_article)
               DO UPDATE SET Quantite = excluded.Quantite""",
            (code, code_article, quantite),
        )
        flash("Article ajoute a la recette.", "succes")

    return redirect(url_for("recettes.modifier", code=code))


@bp.route("/<code>/articles/<code_article>/supprimer", methods=["POST"])
def supprimer_article(code, code_article):
    db.executer(
        """DELETE FROM Recette_Article
           WHERE Code_unique_recette = ? AND Code_unique_article = ?""",
        (code, code_article),
    )
    flash("Article retire de la recette.", "succes")
    return redirect(url_for("recettes.modifier", code=code))


@bp.route("/<code>/supprimer", methods=["POST"])
def supprimer(code):
    try:
        db.executer("DELETE FROM Recettes WHERE Code_unique_recette = ?", (code,))
        flash("Recette supprimee.", "succes")
    except sqlite3.IntegrityError:
        flash("Suppression impossible : la recette est referencee ailleurs.", "erreur")
    return redirect(url_for("recettes.liste"))
