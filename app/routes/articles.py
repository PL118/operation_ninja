"""Ecran N deg 3 - Gestion des articles."""

import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import db

bp = Blueprint("articles", __name__, url_prefix="/articles")


@bp.context_processor
def _rayons():
    """Categories retenues par distributeur, pour le formulaire article."""
    return {"RAYONS": db.categories_par_distributeur()}


def _lire_formulaire():
    """Retourne (donnees, erreurs) a partir du formulaire poste.

    Les cles reprennent les noms des colonnes pour que le template puisse
    afficher indifferemment une ligne de la base ou une saisie a corriger.
    """
    donnees = {
        "Libelle": request.form.get("libelle", "").strip()[:50],
        "Marque": request.form.get("marque", "").strip()[:50],
        "Distributeur": request.form.get("distributeur", "").strip(),
        "Categorie": request.form.get("categorie", "").strip(),
        "Description": request.form.get("description", "").strip()[:255],
        "EAN": request.form.get("ean", "").strip(),
        "Prix_euros": request.form.get("prix", "").strip().replace(",", "."),
        "Quantite": request.form.get("quantite", "").strip().replace(",", "."),
        "Composition": request.form.get("composition", "").strip()[:255],
        "Unite": request.form.get("unite", "").strip(),
        "Alimentaire": 1 if request.form.get("alimentaire") else 0,
    }
    # Base n'existe que pour un article alimentaire.
    donnees["Base"] = 1 if donnees["Alimentaire"] and request.form.get("base") else 0
    erreurs = []

    if not donnees["Libelle"]:
        erreurs.append("Le libelle est obligatoire.")

    # Unite, categorie et distributeur : obligatoires et pris dans leur liste.
    for champ, intitule, referentiel in (
        ("Unite", "L'unite", db.UNITES),
        ("Categorie", "La categorie", db.CATEGORIES),
        ("Distributeur", "Le distributeur", db.distributeurs()),
    ):
        if not donnees[champ]:
            erreurs.append(f"{intitule} est obligatoire.")
        elif donnees[champ] not in referentiel:
            erreurs.append(f"{intitule} doit etre une valeur de la liste.")
            donnees[champ] = ""

    # La categorie doit etre un rayon retenu par le distributeur choisi.
    if donnees["Distributeur"] and donnees["Categorie"]:
        if donnees["Categorie"] not in db.categories_par_distributeur().get(donnees["Distributeur"], []):
            erreurs.append(
                f"La categorie « {donnees['Categorie']} » n'est pas retenue "
                f"pour {donnees['Distributeur']}."
            )
            donnees["Categorie"] = ""

    if donnees["EAN"] and len(donnees["EAN"]) not in (13, 14):
        erreurs.append("L'EAN doit comporter 13 ou 14 caracteres.")

    try:
        donnees["Prix_euros"] = round(float(donnees["Prix_euros"] or 0), 2)
        if donnees["Prix_euros"] < 0:
            erreurs.append("Le prix ne peut pas etre negatif.")
    except ValueError:
        erreurs.append("Le prix doit etre un nombre.")
        donnees["Prix_euros"] = 0

    if not donnees["Quantite"]:
        erreurs.append("La quantite de conditionnement est obligatoire.")
        donnees["Quantite"] = None
    else:
        try:
            donnees["Quantite"] = round(float(donnees["Quantite"]), 2)
            if donnees["Quantite"] <= 0:
                erreurs.append("La quantite doit etre superieure a zero.")
        except ValueError:
            erreurs.append("La quantite doit etre un nombre.")
            donnees["Quantite"] = None

    return donnees, erreurs


@bp.route("/")
def liste():
    recherche = request.args.get("q", "").strip()
    if recherche:
        motif = f"%{recherche}%"
        lignes = db.lister(
            """SELECT * FROM Articles
               WHERE Libelle LIKE ? OR Marque LIKE ? OR Distributeur LIKE ?
                  OR Categorie LIKE ? OR EAN LIKE ? OR Composition LIKE ?
               ORDER BY Libelle""",
            (motif,) * 6,
        )
    else:
        lignes = db.lister("SELECT * FROM Articles ORDER BY Libelle")
    return render_template("articles/liste.html", articles=lignes, q=recherche)


def _copie_de(code_source):
    """Valeurs d'un article existant, pour prerenseigner une creation."""
    source = db.un(
        "SELECT * FROM Articles WHERE Code_unique_article = ?", (code_source,)
    )
    if source is None:
        flash("Article a copier introuvable.", "erreur")
        return None, ""
    valeurs = dict(source)
    valeurs["Libelle"] = f"{valeurs['Libelle']} (copie)"[:50]
    return valeurs, source["Libelle"]


@bp.route("/nouveau", methods=["GET", "POST"])
def nouveau():
    if request.method == "POST":
        donnees, erreurs = _lire_formulaire()
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "erreur")
            return render_template("articles/form.html", article=donnees, creation=True)

        code = db.nouvelle_cle("Articles")
        db.executer(
            """INSERT INTO Articles
               (Code_unique_article, Libelle, Marque, Distributeur, Categorie,
                Description, EAN, Prix_euros, Quantite, Composition, Unite,
                Alimentaire, Base)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                code,
                donnees["Libelle"],
                donnees["Marque"],
                donnees["Distributeur"] or None,
                donnees["Categorie"] or None,
                donnees["Description"],
                donnees["EAN"] or None,
                donnees["Prix_euros"],
                donnees["Quantite"],
                donnees["Composition"],
                donnees["Unite"] or None,
                donnees["Alimentaire"],
                donnees["Base"],
            ),
        )
        flash(f"Article « {donnees['Libelle']} » cree.", "succes")
        return redirect(url_for("articles.liste"))

    code_source = request.args.get("copie", "").strip()
    modele, libelle_source = _copie_de(code_source) if code_source else (None, "")
    return render_template(
        "articles/form.html", article=modele, creation=True, copie=libelle_source
    )


@bp.route("/<code>/modifier", methods=["GET", "POST"])
def modifier(code):
    article = db.un(
        "SELECT * FROM Articles WHERE Code_unique_article = ?", (code,)
    )
    if article is None:
        flash("Article introuvable.", "erreur")
        return redirect(url_for("articles.liste"))

    if request.method == "POST":
        donnees, erreurs = _lire_formulaire()
        if erreurs:
            for erreur in erreurs:
                flash(erreur, "erreur")
            return render_template(
                "articles/form.html", article=donnees, code=code, creation=False
            )

        db.executer(
            """UPDATE Articles
               SET Libelle = ?, Marque = ?, Distributeur = ?, Categorie = ?,
                   Description = ?, EAN = ?, Prix_euros = ?, Quantite = ?,
                   Composition = ?, Unite = ?, Alimentaire = ?, Base = ?
               WHERE Code_unique_article = ?""",
            (
                donnees["Libelle"],
                donnees["Marque"],
                donnees["Distributeur"] or None,
                donnees["Categorie"] or None,
                donnees["Description"],
                donnees["EAN"] or None,
                donnees["Prix_euros"],
                donnees["Quantite"],
                donnees["Composition"],
                donnees["Unite"] or None,
                donnees["Alimentaire"],
                donnees["Base"],
                code,
            ),
        )
        flash("Article modifie.", "succes")
        return redirect(url_for("articles.liste"))

    return render_template(
        "articles/form.html", article=article, code=code, creation=False
    )


@bp.route("/<code>/supprimer", methods=["POST"])
def supprimer(code):
    try:
        db.executer("DELETE FROM Articles WHERE Code_unique_article = ?", (code,))
        flash("Article supprime.", "succes")
    except sqlite3.IntegrityError:
        # ON DELETE RESTRICT : l'article est reference par une recette
        # ou une liste de courses.
        flash(
            "Suppression impossible : cet article est utilise par une recette "
            "ou une liste de courses.",
            "erreur",
        )
    return redirect(url_for("articles.liste"))
