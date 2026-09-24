"""Ecran N deg 4 - Gestion des listes de courses."""

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import config, db, mailer

bp = Blueprint("courses", __name__, url_prefix="/courses")


# Libelle du regroupement pour les articles sans distributeur renseigne.
SANS_DISTRIBUTEUR = "Sans distributeur"


def _nombre_poste(champ, defaut=0.0):
    """Lit un nombre du formulaire. Retourne -1 si la saisie est invalide,
    ce qui permet aux appelants de distinguer 'absent' de 'mal saisi'."""
    brut = request.form.get(champ, "").strip().replace(",", ".")
    if not brut:
        return defaut
    try:
        return round(float(brut), 2)
    except ValueError:
        return -1


def _grouper_par_distributeur(lignes):
    """Regroupe les lignes par distributeur d'article.

    Retourne une liste de (nom, lignes, sous_total), dans l'ordre du
    referentiel des distributeurs, les articles sans enseigne en dernier.
    """
    groupes = {}
    for ligne in lignes:
        groupes.setdefault(ligne["Distributeur"] or SANS_DISTRIBUTEUR, []).append(ligne)

    ordre = db.distributeurs() + [SANS_DISTRIBUTEUR]
    # Une enseigne absente du referentiel (donnee ancienne) reste affichee :
    # elle est simplement rangee apres celles qu'on connait.
    ordre += sorted(nom for nom in groupes if nom not in ordre)

    # Dans chaque groupe : ordre des rayons du distributeur (retenus puis
    # retires), les articles de base non ajoutes en fin, puis par libelle.
    # Sans distributeur connu, l'ordre par defaut du referentiel s'applique.
    rayons = db.categories_par_distributeur(avec_retirees=True)
    for nom, lignes_groupe in groupes.items():
        rang = {c: i for i, c in enumerate(rayons.get(nom, db.CATEGORIES))}
        lignes_groupe.sort(key=lambda l: (
            l["En_attente"], rang.get(l["Categorie"], len(rang)), l["Libelle"]
        ))

    return [(nom, groupes[nom], _cout(groupes[nom])) for nom in ordre if nom in groupes]


def _cout(lignes):
    """Cout des lignes achetees : les articles de base en attente n'y sont pas."""
    return sum(ligne["Cout"] or 0 for ligne in lignes if not ligne["En_attente"])


def _lignes_de(code_liste):
    # i.Quantite (conditionnement) et lci.Quantite (quantite a acheter) portent
    # le meme nom : les colonnes sont enumerees pour lever l'ambiguite.
    # Unites et cout sont calcules a chaque lecture, donc toujours a jour
    # apres une modification de quantite ou de conditionnement.
    return db.lister(
        f"""SELECT i.Code_unique_article, i.Libelle, i.Marque, i.EAN,
                   i.Categorie, i.Distributeur, i.Unite, i.Prix_euros, i.Base,
                   {db.EN_ATTENTE} AS En_attente,
                   i.Quantite AS Conditionnement,
                   lci.Quantite AS Quantite,
                   {db.PRIX_UNITAIRE} AS Prix_unitaire,
                   {db.UNITES_A_ACHETER} AS Unites_a_acheter,
                   {db.COUT_LIGNE} AS Cout
            FROM Liste_course_Article lci
            JOIN Articles i USING (Code_unique_article)
            WHERE lci.Code_unique_liste_course = ?
            ORDER BY i.Libelle""",
        (code_liste,),
    )


def _groupes_email(lignes):
    """Contenu de l'email, range comme l'ecran : distributeur, puis rayon dans
    l'ordre du distributeur. Sans prix : c'est un pense-bete de magasin.

    Retourne [(distributeur, [(rayon, [(libelle, a_prendre, detail)])])].
    Les articles de base non ajoutes n'y figurent pas : rien a acheter.
    """
    resultat = []
    for nom, lignes_groupe, _ in _grouper_par_distributeur(lignes):
        rayons = []
        for ligne in lignes_groupe:
            if ligne["En_attente"]:
                continue
            rayon = ligne["Categorie"] or "Sans categorie"
            if not rayons or rayons[-1][0] != rayon:
                rayons.append((rayon, []))
            symbole = db.UNITES.get(ligne["Unite"], ("", ""))[1]
            # En rayon, c'est le nombre de conditionnements qui compte ; sans
            # conditionnement connu, on donne le besoin brut.
            unites = ligne["Unites_a_acheter"]
            if unites is None:
                a_prendre, detail = f"{ligne['Quantite']:g} {symbole}".strip(), ""
            else:
                a_prendre = str(unites)
                detail = f"x {ligne['Conditionnement']:g} {symbole}".strip()
            rayons[-1][1].append((ligne["Libelle"], a_prendre, detail))
        if rayons:
            resultat.append((nom, rayons))
    return resultat


def _texte_liste(liste, groupes):
    """Version texte de l'email, pour les messageries sans HTML."""
    entete = f"Liste de courses du {liste['Date_edition']}"
    corps = [entete, "=" * len(entete), ""]
    for nom, rayons in groupes:
        corps += [nom.upper(), ""]
        for rayon, articles in rayons:
            corps.append(f"  {rayon}")
            for libelle, a_prendre, detail in articles:
                quantite = f"{a_prendre} {detail}" if detail else a_prendre
                corps.append(f"    [ ] {quantite} : {libelle}")
        corps.append("")
    if not groupes:
        corps += ["(liste vide)", ""]
    corps += ["-- Operation_ninja"]
    return "\n".join(corps)


@bp.route("/")
def liste():
    listes = db.lister(
        f"""SELECT lc.*,
                  (SELECT COUNT(*) FROM Liste_course_Article lci
                   WHERE lci.Code_unique_liste_course = lc.Code_unique_liste_course)
                      AS Nb_articles,
                  (SELECT IFNULL(SUM({db.COUT_LIGNE}), 0)
                   FROM Liste_course_Article lci
                   JOIN Articles i USING (Code_unique_article)
                   WHERE lci.Code_unique_liste_course = lc.Code_unique_liste_course
                     AND NOT {db.EN_ATTENTE})
                      AS Cout_total
           FROM Liste_course lc
           ORDER BY lc.Date_edition DESC, lc.Code_unique_liste_course DESC"""
    )
    return render_template("courses/liste.html", listes=listes)


@bp.route("/nouvelle", methods=["GET", "POST"])
def nouvelle():
    if request.method == "POST":
        codes_recettes = request.form.getlist("recettes")
        source = request.form.get("copie", "").strip()
        retour = url_for("courses.nouvelle", copie=source or None)
        if not codes_recettes and not source:
            flash("Selectionnez au moins une recette.", "erreur")
            return redirect(retour)

        # Quantite saisie en face de chaque recette cochee : le nombre de fois
        # que la recette sera realisee. Absente, elle vaut 1.
        multiplicateurs = {
            code_recette: _nombre_poste(f"quantite_{code_recette}", 1)
            for code_recette in codes_recettes
        }
        if any(valeur <= 0 for valeur in multiplicateurs.values()):
            flash(
                "La quantite d'une recette doit etre un nombre superieur a zero.",
                "erreur",
            )
            return redirect(retour)

        code = db.nouvelle_cle("Liste_course")
        db.executer(
            "INSERT INTO Liste_course (Code_unique_liste_course, Date_edition) "
            "VALUES (?, ?)",
            (code, date.today().isoformat()),
        )

        reprises = 0
        if source:
            reprises = db.executer(
                """INSERT INTO Liste_course_Article
                   (Code_unique_liste_course, Code_unique_article, Quantite)
                   SELECT ?, Code_unique_article, Quantite
                   FROM Liste_course_Article WHERE Code_unique_liste_course = ?""",
                (code, source),
            ).rowcount

        # Les quantites d'un meme article present dans plusieurs recettes,
        # ou deja repris de la liste copiee, sont additionnees. Le cumul se
        # fait ici et non en SQL : chaque recette a son propre multiplicateur,
        # un GROUP BY unique ne saurait pas les appliquer.
        cumul = {}
        if codes_recettes:
            marqueurs = ",".join("?" for _ in codes_recettes)
            for ligne in db.lister(
                f"""SELECT Code_unique_recette, Code_unique_article, Quantite
                    FROM Recette_Article
                    WHERE Code_unique_recette IN ({marqueurs})""",
                tuple(codes_recettes),
            ):
                besoin = ligne["Quantite"] * multiplicateurs[ligne["Code_unique_recette"]]
                cumul[ligne["Code_unique_article"]] = (
                    cumul.get(ligne["Code_unique_article"], 0) + besoin
                )
        for code_article, quantite in cumul.items():
            db.executer(
                """INSERT INTO Liste_course_Article
                   (Code_unique_liste_course, Code_unique_article, Quantite)
                   VALUES (?, ?, ?)
                   ON CONFLICT (Code_unique_liste_course, Code_unique_article)
                   DO UPDATE SET Quantite = Quantite + excluded.Quantite""",
                (code, code_article, round(quantite, 2)),
            )

        if not cumul and not reprises:
            flash(
                "Liste creee, mais la source choisie ne contient aucun article.",
                "erreur",
            )
        elif source:
            flash(
                f"Liste creee : {reprises} article(s) repris de la liste copiee"
                + (f" et {len(codes_recettes)} recette(s) ajoutee(s)." if codes_recettes
                   else "."),
                "succes",
            )
        else:
            flash(
                f"Liste de courses creee a partir de {len(codes_recettes)} recette(s).",
                "succes",
            )
        return redirect(url_for("courses.detail", code=code))

    recettes = db.lister(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM Recette_Article ri
                   WHERE ri.Code_unique_recette = r.Code_unique_recette)
                      AS Nb_articles
           FROM Recettes r ORDER BY r.Libelle"""
    )

    code_source = request.args.get("copie", "").strip()
    modele = None
    if code_source:
        modele = db.un(
            """SELECT lc.*,
                      (SELECT COUNT(*) FROM Liste_course_Article lci
                       WHERE lci.Code_unique_liste_course = lc.Code_unique_liste_course)
                          AS Nb_articles
               FROM Liste_course lc WHERE lc.Code_unique_liste_course = ?""",
            (code_source,),
        )
        if modele is None:
            flash("Liste a copier introuvable.", "erreur")
            code_source = ""

    return render_template(
        "courses/nouvelle.html", recettes=recettes, copie=code_source, modele=modele
    )


@bp.route("/<code>")
def detail(code):
    liste_course = db.un(
        "SELECT * FROM Liste_course WHERE Code_unique_liste_course = ?", (code,)
    )
    if liste_course is None:
        flash("Liste de courses introuvable.", "erreur")
        return redirect(url_for("courses.liste"))

    lignes = _lignes_de(code)
    return render_template(
        "courses/detail.html",
        liste=liste_course,
        groupes=_grouper_par_distributeur(lignes),
        nb_lignes=len(lignes),
        cout_total=_cout(lignes),
        catalogue=db.catalogue(),
        marques=db.marques(),
        smtp_pret=config.smtp_configure(),
        destinataire=config.valeur("smtp", "destinataire"),
    )


@bp.route("/<code>/quantites", methods=["POST"])
def modifier_quantites(code):
    """Enregistre les quantites corrigees d'un groupe de distributeur.

    Seuls les champs postes sont touches : chaque groupe a son propre
    formulaire, les autres distributeurs ne doivent pas etre remis a zero.
    """
    modifiees, invalides = 0, []
    for champ, valeur in request.form.items():
        if not champ.startswith("quantite_"):
            continue
        code_article = champ[len("quantite_"):]
        quantite = _nombre_poste(champ, -1)
        if quantite < 0:
            invalides.append(code_article)
            continue
        modifiees += db.executer(
            """UPDATE Liste_course_Article SET Quantite = ?
               WHERE Code_unique_liste_course = ? AND Code_unique_article = ?""",
            (quantite, code, code_article),
        ).rowcount

    if invalides:
        flash(
            f"{len(invalides)} quantite(s) ignoree(s) : saisissez un nombre positif.",
            "erreur",
        )
    elif modifiees:
        flash(f"{modifiees} quantite(s) mise(s) a jour.", "succes")
    return redirect(url_for("courses.detail", code=code))


@bp.route("/<code>/articles/ajouter", methods=["POST"])
def ajouter_article(code):
    code_article = request.form.get("code_article", "").strip()
    quantite = _nombre_poste("quantite", -1)

    if not code_article:
        flash("Choisissez un article a ajouter.", "erreur")
    elif quantite <= 0:
        flash("La quantite doit etre un nombre superieur a zero.", "erreur")
    else:
        # Saisie en nombre d'articles (paquets) : stockee comme un besoin
        # dans l'unite de l'article, a l'image des quantites de recette.
        # Sans conditionnement connu, un article compte pour une unite.
        article = db.un(
            "SELECT Quantite FROM Articles WHERE Code_unique_article = ?", (code_article,)
        )
        conditionnement = (article["Quantite"] if article else None) or 1
        quantite = round(quantite * conditionnement, 2)
        # Un article deja present voit sa quantite cumulee. Ajout explicite :
        # un article de base est d'emblee compte dans les achats.
        db.executer(
            """INSERT INTO Liste_course_Article
               (Code_unique_liste_course, Code_unique_article, Quantite, Ajoute)
               VALUES (?, ?, ?, 1)
               ON CONFLICT (Code_unique_liste_course, Code_unique_article)
               DO UPDATE SET Quantite = Quantite + excluded.Quantite, Ajoute = 1""",
            (code, code_article, quantite),
        )
        flash("Article ajoute a la liste.", "succes")

    return redirect(url_for("courses.detail", code=code))


def _basculer_base(code, code_article, ajoute):
    """Passe un article de base de la liste dans les achats (1) ou l'en sort (0)."""
    return db.executer(
        """UPDATE Liste_course_Article SET Ajoute = ?
           WHERE Code_unique_liste_course = ? AND Code_unique_article = ?
             AND Code_unique_article IN (SELECT Code_unique_article FROM Articles
                                         WHERE Base = 1)""",
        (ajoute, code, code_article),
    ).rowcount


@bp.route("/<code>/articles/<code_article>/ajouter-base", methods=["POST"])
def ajouter_base(code, code_article):
    if _basculer_base(code, code_article, 1):
        flash("Article de base ajoute aux achats.", "succes")
    return redirect(url_for("courses.detail", code=code))


@bp.route("/<code>/articles/<code_article>/supprimer", methods=["POST"])
def supprimer_article(code, code_article):
    # Un article de base n'est pas supprime : il retourne dans sa rubrique,
    # hors achats, pour rester a verifier.
    if _basculer_base(code, code_article, 0):
        flash("Article de base remis dans les articles de base.", "succes")
    else:
        db.executer(
            """DELETE FROM Liste_course_Article
               WHERE Code_unique_liste_course = ? AND Code_unique_article = ?""",
            (code, code_article),
        )
        flash("Article retire de la liste.", "succes")
    return redirect(url_for("courses.detail", code=code))


@bp.route("/<code>/envoyer", methods=["POST"])
def envoyer(code):
    destinataire = request.form.get("email", "").strip()
    liste_course = db.un(
        "SELECT * FROM Liste_course WHERE Code_unique_liste_course = ?", (code,)
    )
    if liste_course is None:
        flash("Liste de courses introuvable.", "erreur")
        return redirect(url_for("courses.liste"))

    if "@" not in destinataire:
        flash("Adresse email invalide.", "erreur")
        return redirect(url_for("courses.detail", code=code))

    groupes = _groupes_email(_lignes_de(code))
    try:
        mailer.envoyer(
            destinataire,
            f"Liste de courses du {liste_course['Date_edition']}",
            _texte_liste(liste_course, groupes),
            html=render_template("courses/email.html", liste=liste_course, groupes=groupes),
        )
        # Marquee seulement une fois l'envoi reussi.
        db.executer(
            "UPDATE Liste_course SET Emise = 1 WHERE Code_unique_liste_course = ?", (code,)
        )
        flash(f"Liste envoyee a {destinataire}.", "succes")
    except mailer.ErreurEnvoi as erreur:
        flash(str(erreur), "erreur")

    return redirect(url_for("courses.detail", code=code))


@bp.route("/<code>/supprimer", methods=["POST"])
def supprimer(code):
    db.executer("DELETE FROM Liste_course WHERE Code_unique_liste_course = ?", (code,))
    flash("Liste de courses supprimee.", "succes")
    return redirect(url_for("courses.liste"))
