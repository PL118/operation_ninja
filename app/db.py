"""Acces a la base SQLite.

La connexion est ouverte une fois par requete HTTP et fermee automatiquement
a la fin de celle-ci. Toutes les requetes utilisent des parametres (?) pour
eviter toute injection SQL.
"""

import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app, g

from . import config

SCHEMA = Path(__file__).resolve().parent / "schema.sql"

# Colonnes ajoutees apres la mise en service : (table, colonne, definition SQL).
# Elles figurent aussi dans schema.sql pour les nouvelles installations ;
# cette liste sert a mettre a jour une base deja remplie.
COLONNES_AJOUTEES = [
    ("Articles", "Marque", "TEXT CHECK (Marque IS NULL OR length(Marque) <= 50)"),
    ("Articles", "Quantite", "REAL CHECK (Quantite IS NULL OR Quantite >= 0)"),
    ("Articles", "Categorie",
     "TEXT CHECK (Categorie IS NULL OR length(Categorie) <= 50)"),
    ("Articles", "Distributeur",
     "TEXT CHECK (Distributeur IS NULL OR length(Distributeur) <= 50)"),
    # DEFAULT 1 : les articles deja saisis sont tous marques alimentaires.
    ("Articles", "Alimentaire",
     "INTEGER NOT NULL DEFAULT 1 CHECK (Alimentaire IN (0, 1))"),
    ("Articles", "Base", "INTEGER NOT NULL DEFAULT 0 CHECK (Base IN (0, 1))"),
    ("Liste_course", "Distributeur",
     "TEXT CHECK (Distributeur IS NULL OR length(Distributeur) <= 50)"),
    ("Recettes", "Categories",
     "TEXT CHECK (Categories IS NULL OR length(Categories) <= 255)"),
    ("Distributeur_Categorie", "Retenue",
     "INTEGER NOT NULL DEFAULT 1 CHECK (Retenue IN (0, 1))"),
    ("Liste_course_Article", "Ajoute",
     "INTEGER NOT NULL DEFAULT 0 CHECK (Ajoute IN (0, 1))"),
    ("Liste_course", "Emise", "INTEGER NOT NULL DEFAULT 0 CHECK (Emise IN (0, 1))"),
]

# Prefixes des cles primaires, par table.
PREFIXES = {
    "Recettes": "REC",
    "Articles": "ART",
    "Liste_course": "LIC",
    "Distributeurs": "DIS",
}

# Referentiel des unites : code stocke en base -> (libelle, symbole affiche).
UNITES = {
    "gramme": ("Gramme", "gr"),
    "millilitre": ("Millilitre", "ml"),
    "piece": ("Piece", "u"),
}

# Enseignes reprises dans la table Distributeurs a sa creation. Ensuite, la
# liste se gere depuis l'ecran Distributeurs (DIS-6) : voir distributeurs().
DISTRIBUTEURS_INITIAUX = (
    "Carrefour",
    "Otera",
)

# Categories de recette, cumulables (ex. Plat + Sale). Stockees dans
# Recettes.Categories, separees par SEPARATEUR_CATEGORIES.
CATEGORIES_RECETTE = (
    "Petit-dejeuner",
    "Brunch",
    "Entree",
    "Plat",
    "Dessert",
    "Aperitif",
    "Boisson",
    "Sauce",
    "Accompagnement",
    "Snack",
    "Sucre",
    "Sale",
)
SEPARATEUR_CATEGORIES = ";"


def categories_recette(valeur):
    """Liste des categories d'une recette a partir de la colonne stockee."""
    return [c for c in (valeur or "").split(SEPARATEUR_CATEGORIES) if c]


# Rayons de supermarche, dans l'ordre d'un parcours de magasin.
# Referentiel libre : ajouter ou retirer une ligne suffit, la base ne
# contraint que la longueur (50 caracteres), la validation se fait ici.
CATEGORIES = (
    "Fruits",
    "Legumes",
    "Boucherie",
    "Volaille",
    "Poissonnerie",
    "Charcuterie et traiteur",
    "Cremerie et oeufs",
    "Fromagerie",
    "Boulangerie et patisserie",
    "Epicerie salee",
    "Epicerie sucree",
    "Conserves et bocaux",
    "Pates, riz et feculents",
    "Condiments et sauces",
    "Petit-dejeuner",
    "Aperitif et snacks",
    "Surgeles",
    "Boissons sans alcool",
    "Boissons alcoolisees",
    "Bebe",
    "Hygiene et beaute",
    "Entretien et maison",
    "Animalerie",
)

# Article de base present dans une liste mais pas encore ajoute aux achats :
# affiche pour verification, hors cout. lci = Liste_course_Article, i = Articles.
EN_ATTENTE = "(i.Base = 1 AND lci.Ajoute = 0)"

# Prix d'une unite d'article : Prix_euros vaut pour la quantite de
# conditionnement (ex. 1,20 EUR les 1000 g). Quantite absente ou nulle :
# le prix est pris tel quel.
PRIX_UNITAIRE = "i.Prix_euros / COALESCE(NULLIF(i.Quantite, 0), 1)"

# Nombre de conditionnements a prendre en rayon : on ne vend pas 150 g de
# sucre, il faut un paquet entier. i.Quantite est le conditionnement,
# lci.Quantite le besoin cumule de la liste. NULL si le conditionnement est
# inconnu : sans lui le calcul n'a pas de sens.
UNITES_A_ACHETER = """CASE WHEN IFNULL(i.Quantite, 0) > 0
                           THEN PLAFOND(lci.Quantite / i.Quantite)
                           END"""

# Cout reel : on paie des conditionnements entiers, pas le prorata. Sans
# conditionnement connu on retombe sur le prorata, faute de mieux.
COUT_LIGNE = f"""CASE WHEN IFNULL(i.Quantite, 0) > 0
                      THEN ({UNITES_A_ACHETER}) * i.Prix_euros
                      ELSE lci.Quantite * ({PRIX_UNITAIRE})
                      END"""


def plafond(valeur):
    """Arrondi au superieur, tolerant aux miettes du calcul flottant.

    Sans l'arrondi prealable, un besoin cumule a 1000.0000000000001 g
    reclamerait deux paquets de 1000 g au lieu d'un.
    """
    if valeur is None:
        return None
    return math.ceil(round(valeur, 6))


def connexion():
    """Retourne la connexion SQLite de la requete en cours."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["FICHIER_BASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        # SQLite n'expose CEIL que s'il a ete compile avec les fonctions
        # mathematiques : on fournit la notre, qui porte en plus la tolerance
        # au flottant et reste l'unique implementation de la regle.
        g.db.create_function("PLAFOND", 1, plafond)
    return g.db


def fermer_connexion(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ddl_table_provisoire():
    """Extrait de schema.sql la definition de Articles, renommee.

    La relire evite d'en tenir une seconde copie ici, qui finirait par
    diverger de la definition de reference.
    """
    texte = SCHEMA.read_text(encoding="utf-8")
    entete = "CREATE TABLE IF NOT EXISTS Articles ("
    debut = texte.index(entete)
    fin = texte.index(");", debut) + 2
    return texte[debut:fin].replace(entete, "CREATE TABLE Articles_nouveau (", 1)


def _rebatir_articles(db):
    """Reconstruit Articles si elle porte l'ancienne contrainte fermee
    sur Unite, que SQLite ne sait pas modifier en place.

    Les donnees sont conservees et l'unite 'entier' devient 'piece'.
    """
    ligne = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'Articles'"
    ).fetchone()
    if ligne is None or "'entier'" not in ligne[0]:
        return

    db.execute("PRAGMA foreign_keys = OFF")
    db.execute(_ddl_table_provisoire())

    anciennes = {l[1] for l in db.execute("PRAGMA table_info(Articles)")}
    nouvelles = [l[1] for l in db.execute("PRAGMA table_info(Articles_nouveau)")]
    # Unite est reprise a part, pour convertir l'ancien code au passage.
    communes = [c for c in nouvelles if c in anciennes and c != "Unite"]
    colonnes = ", ".join(communes)

    db.execute(
        f"INSERT INTO Articles_nouveau ({colonnes}, Unite)"
        f" SELECT {colonnes},"
        f" CASE WHEN Unite = 'entier' THEN 'piece' ELSE Unite END"
        f" FROM Articles"
    )
    db.execute("DROP TABLE Articles")
    db.execute("ALTER TABLE Articles_nouveau RENAME TO Articles")

    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        db.rollback()
        raise RuntimeError(f"Reconstruction annulee, references cassees : {violations}")

    db.commit()
    db.execute("PRAGMA foreign_keys = ON")
    print("Base mise a jour : table Articles reconstruite, 'entier' -> 'piece'.")


def _renommer_en_articles(db):
    """Convertit une base de l'epoque "Ingredients" au vocabulaire "Articles".

    Tables et colonnes sont renommees en place (SQLite reporte le nouveau nom
    dans les cles etrangeres), puis les codes ING_ deviennent ART_ dans la
    table et ses deux tables de liaison.
    """
    tables = {l[0] for l in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "Ingredients" not in tables or "Articles" in tables:
        return

    db.commit()
    db.execute("PRAGMA foreign_keys = OFF")
    for ancienne, nouvelle in (
        ("Ingredients", "Articles"),
        ("Recette_Ingredient", "Recette_Article"),
        ("Liste_course_Ingredient", "Liste_course_Article"),
    ):
        db.execute(f"ALTER TABLE {ancienne} RENAME TO {nouvelle}")
        db.execute(
            f"ALTER TABLE {nouvelle} RENAME COLUMN Code_unique_ingredient TO Code_unique_article"
        )
    # Recrees sous leur nouveau nom par schema.sql.
    for index in ("idx_ingredients_libelle", "idx_rec_ing_ingredient", "idx_lic_ing_ingredient"):
        db.execute(f"DROP INDEX IF EXISTS {index}")

    for table in ("Articles", "Recette_Article", "Liste_course_Article"):
        db.execute(
            f"UPDATE {table} SET Code_unique_article = 'ART_' || substr(Code_unique_article, 5)"
            f" WHERE Code_unique_article LIKE 'ING\\_%' ESCAPE '\\'"
        )

    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        db.rollback()
        raise RuntimeError(f"Renommage annule, references cassees : {violations}")

    db.commit()
    db.execute("PRAGMA foreign_keys = ON")
    print("Base mise a jour : Ingredients -> Articles, codes ING_ -> ART_.")


def _completer_colonnes(db):
    """Ajoute les colonnes apparues apres la creation d'une base existante.

    CREATE TABLE IF NOT EXISTS laisse intactes les tables deja presentes :
    sans cela, une base creee avant l'ajout d'une colonne resterait incomplete.
    """
    for table, colonne, definition in COLONNES_AJOUTEES:
        presentes = {ligne[1] for ligne in db.execute(f"PRAGMA table_info({table})")}
        if presentes and colonne not in presentes:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {colonne} {definition}")
            print(f"Base mise a jour : colonne {table}.{colonne} ajoutee.")


def initialiser(app):
    """Cree le fichier de base et les tables si besoin, puis les met a jour."""
    config.DOSSIER_DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(app.config["FICHIER_BASE"])
    try:
        db.execute("PRAGMA foreign_keys = ON")
        _renommer_en_articles(db)
        _rebatir_articles(db)
        _completer_colonnes(db)
        db.executescript(SCHEMA.read_text(encoding="utf-8"))
        _amorcer_distributeurs(db)
        _scinder_fruits_legumes(db)
        db.commit()
    finally:
        db.close()


def _scinder_fruits_legumes(db):
    """Remplace l'ancienne categorie "Fruits et legumes" par "Fruits" puis
    "Legumes".

    Les articles existants etaient tous des legumes : ils passent en
    "Legumes". Chez chaque distributeur, les deux rayons prennent la place
    de l'ancien, avec le meme statut retenu/retire.
    """
    ancienne = "Fruits et legumes"
    db.execute("UPDATE Articles SET Categorie = 'Legumes' WHERE Categorie = ?", (ancienne,))
    lignes = db.execute(
        """SELECT Code_unique_distributeur, Ordre, Retenue FROM Distributeur_Categorie
           WHERE Categorie = ?""",
        (ancienne,),
    ).fetchall()
    for code, ordre, retenue in lignes:
        db.execute(
            """UPDATE Distributeur_Categorie SET Ordre = Ordre + 1
               WHERE Code_unique_distributeur = ? AND Ordre > ?""",
            (code, ordre),
        )
        db.execute(
            """UPDATE Distributeur_Categorie SET Categorie = 'Fruits'
               WHERE Code_unique_distributeur = ? AND Categorie = ?""",
            (code, ancienne),
        )
        db.execute(
            """INSERT INTO Distributeur_Categorie
               (Code_unique_distributeur, Categorie, Ordre, Retenue)
               VALUES (?, 'Legumes', ?, ?)""",
            (code, ordre + 1, retenue),
        )
    if lignes:
        print("Base mise a jour : 'Fruits et legumes' scinde en 'Fruits' et 'Legumes'.")


def _amorcer_distributeurs(db):
    """Remplit la table Distributeurs a sa creation.

    Reprend les enseignes de l'ancienne liste en dur et celles deja saisies
    sur des articles ou des listes, avec les categories dans l'ordre par
    defaut du referentiel.
    """
    if db.execute("SELECT 1 FROM Distributeurs LIMIT 1").fetchone():
        return
    noms = set(DISTRIBUTEURS_INITIAUX)
    for table in ("Articles", "Liste_course"):
        noms.update(
            l[0] for l in db.execute(
                f"SELECT DISTINCT Distributeur FROM {table} WHERE IFNULL(Distributeur, '') <> ''"
            )
        )
    # nouvelle_cle() passe par la connexion de requete, absente ici : les
    # codes sont decales d'une seconde par enseigne pour rester uniques.
    horodatage = datetime.now().replace(microsecond=0)
    for rang, nom in enumerate(sorted(noms)):
        code = f"{PREFIXES['Distributeurs']}_{horodatage + timedelta(seconds=rang):%y%m%d%H%M%S}"
        db.execute(
            "INSERT INTO Distributeurs (Code_unique_distributeur, Libelle) VALUES (?, ?)",
            (code, nom),
        )
        db.executemany(
            """INSERT INTO Distributeur_Categorie
               (Code_unique_distributeur, Categorie, Ordre) VALUES (?, ?, ?)""",
            [(code, categorie, ordre) for ordre, categorie in enumerate(CATEGORIES)],
        )
    print(f"Base mise a jour : {len(noms)} distributeur(s) repris dans la table Distributeurs.")


def lister(requete, parametres=()):
    return connexion().execute(requete, parametres).fetchall()


def un(requete, parametres=()):
    return connexion().execute(requete, parametres).fetchone()


def executer(requete, parametres=()):
    db = connexion()
    curseur = db.execute(requete, parametres)
    db.commit()
    return curseur


def marques():
    """Marques deja saisies, pour alimenter le filtre de choix d'un article."""
    lignes = lister(
        """SELECT DISTINCT Marque FROM Articles
           WHERE Marque IS NOT NULL AND Marque <> '' ORDER BY Marque"""
    )
    return [ligne["Marque"] for ligne in lignes]


def distributeurs():
    """Libelles des distributeurs, par ordre alphabetique."""
    return [l["Libelle"] for l in lister("SELECT Libelle FROM Distributeurs ORDER BY Libelle")]


def categories_distributeur(code_distributeur):
    """Retourne (retenues dans l'ordre de rayon, retirees) d'un distributeur.

    Une categorie ajoutee au referentiel apres le classement est retenue et
    placee en fin ; une categorie sortie du referentiel n'est plus proposee.
    """
    lignes = [
        l for l in lister(
            """SELECT Categorie, Retenue FROM Distributeur_Categorie
               WHERE Code_unique_distributeur = ? ORDER BY Ordre""",
            (code_distributeur,),
        )
        if l["Categorie"] in CATEGORIES
    ]
    connues = {l["Categorie"] for l in lignes}
    retenues = [l["Categorie"] for l in lignes if l["Retenue"]]
    retirees = [l["Categorie"] for l in lignes if not l["Retenue"]]
    return retenues + [c for c in CATEGORIES if c not in connues], retirees


def categories_par_distributeur(avec_retirees=False):
    """{libelle du distributeur: categories retenues dans l'ordre de rayon}.

    avec_retirees : les retirees suivent, pour ranger un article ancien
    dont la categorie a ete retiree depuis.
    """
    resultat = {}
    for l in lister("SELECT * FROM Distributeurs ORDER BY Libelle"):
        retenues, retirees = categories_distributeur(l["Code_unique_distributeur"])
        resultat[l["Libelle"]] = retenues + retirees if avec_retirees else retenues
    return resultat


def catalogue():
    """Articles selectionnables, avec leur prix unitaire.

    La liste est envoyee entiere : le tri par distributeur, marque ou
    categorie se fait dans le navigateur, sans recharger la page.
    """
    return lister(
        f"""SELECT *, {PRIX_UNITAIRE} AS Prix_unitaire
            FROM Articles i ORDER BY Libelle"""
    )


def nouvelle_cle(table):
    """Genere une cle unique du type REC_YYMMDDHHMMSS.

    Le format ne descend pas sous la seconde : en cas de collision, on decale
    d'une seconde jusqu'a trouver un code libre.
    """
    prefixe = PREFIXES[table]
    colonne = {
        "Recettes": "Code_unique_recette",
        "Articles": "Code_unique_article",
        "Liste_course": "Code_unique_liste_course",
        "Distributeurs": "Code_unique_distributeur",
    }[table]

    horodatage = datetime.now().replace(microsecond=0)
    for _ in range(60):
        code = f"{prefixe}_{horodatage:%y%m%d%H%M%S}"
        if un(f"SELECT 1 FROM {table} WHERE {colonne} = ?", (code,)) is None:
            return code
        horodatage += timedelta(seconds=1)

    raise RuntimeError(f"Impossible de generer une cle unique pour {table}")
