-- Operation_ninja - schema de la base SQLite
-- Les prix et quantites sont stockes en REAL et arrondis a 2 decimales
-- a l'affichage (SQLite ne possede pas de type DECIMAL natif).

-- Definition de reference : db._rebatir_articles() relit ce bloc tel quel
-- pour reconstruire la table d'une base anterieure. Ne pas renommer la table
-- ni changer la premiere ligne sans adapter cette fonction.
CREATE TABLE IF NOT EXISTS Articles (
    Code_unique_article TEXT PRIMARY KEY,
    Libelle                TEXT NOT NULL CHECK (length(Libelle) <= 50),
    Marque                 TEXT CHECK (Marque IS NULL OR length(Marque) <= 50),
    Description            TEXT CHECK (Description IS NULL OR length(Description) <= 255),
    EAN                    TEXT CHECK (EAN IS NULL OR EAN = '' OR length(EAN) IN (13, 14)),
    Prix_euros             REAL NOT NULL DEFAULT 0 CHECK (Prix_euros >= 0),
    -- Quantite de conditionnement correspondant a Prix_euros.
    Quantite               REAL CHECK (Quantite IS NULL OR Quantite >= 0),
    Composition            TEXT CHECK (Composition IS NULL OR length(Composition) <= 255),
    -- Referentiels tenus dans db.UNITES et db.CATEGORIES : la base ne
    -- contraint que la longueur, la validation se fait cote application,
    -- pour pouvoir faire evoluer les listes sans reconstruire la table.
    Categorie              TEXT CHECK (Categorie IS NULL OR length(Categorie) <= 50),
    Distributeur           TEXT CHECK (Distributeur IS NULL OR length(Distributeur) <= 50),
    Unite                  TEXT CHECK (Unite IS NULL OR length(Unite) <= 10),
    -- Indicateurs 0/1. Base n'a de sens que pour un article alimentaire.
    Alimentaire            INTEGER NOT NULL DEFAULT 1 CHECK (Alimentaire IN (0, 1)),
    Base                   INTEGER NOT NULL DEFAULT 0 CHECK (Base IN (0, 1))
);

CREATE TABLE IF NOT EXISTS Recettes (
    Code_unique_recette TEXT PRIMARY KEY,
    Libelle             TEXT NOT NULL CHECK (length(Libelle) <= 50),
    Description         TEXT CHECK (Description IS NULL OR length(Description) <= 255),
    Nombre_personnes    INTEGER NOT NULL DEFAULT 1 CHECK (Nombre_personnes > 0),
    -- Categories cumulables, separees par ';' (referentiel db.CATEGORIES_RECETTE).
    Categories          TEXT CHECK (Categories IS NULL OR length(Categories) <= 255)
);

-- Table de liaison : une recette contient N articles, chacun avec sa quantite.
CREATE TABLE IF NOT EXISTS Recette_Article (
    Code_unique_recette    TEXT NOT NULL
        REFERENCES Recettes (Code_unique_recette) ON DELETE CASCADE,
    Code_unique_article TEXT NOT NULL
        REFERENCES Articles (Code_unique_article) ON DELETE RESTRICT,
    Quantite               REAL NOT NULL DEFAULT 0 CHECK (Quantite >= 0),
    PRIMARY KEY (Code_unique_recette, Code_unique_article)
);

CREATE TABLE IF NOT EXISTS Liste_course (
    Code_unique_liste_course TEXT PRIMARY KEY,
    Date_edition             TEXT NOT NULL,
    Distributeur             TEXT CHECK (Distributeur IS NULL
                                         OR length(Distributeur) <= 50),
    -- 1 des qu'un envoi par email a reussi.
    Emise                    INTEGER NOT NULL DEFAULT 0 CHECK (Emise IN (0, 1))
);

-- Table de liaison : une liste de courses contient N articles.
CREATE TABLE IF NOT EXISTS Liste_course_Article (
    Code_unique_liste_course TEXT NOT NULL
        REFERENCES Liste_course (Code_unique_liste_course) ON DELETE CASCADE,
    Code_unique_article   TEXT NOT NULL
        REFERENCES Articles (Code_unique_article) ON DELETE RESTRICT,
    Quantite                 REAL NOT NULL DEFAULT 0 CHECK (Quantite >= 0),
    -- Article de base : 0 tant qu'il n'est pas ajoute aux achats (hors cout).
    Ajoute                   INTEGER NOT NULL DEFAULT 0 CHECK (Ajoute IN (0, 1)),
    PRIMARY KEY (Code_unique_liste_course, Code_unique_article)
);

-- Enseignes. Articles et Liste_course les designent par leur libelle
-- (colonne Distributeur) : un renommage est reporte par l'application.
CREATE TABLE IF NOT EXISTS Distributeurs (
    Code_unique_distributeur TEXT PRIMARY KEY,
    Libelle                  TEXT NOT NULL UNIQUE CHECK (length(Libelle) <= 50)
);

-- Ordre des rayons (categories d'article) propre a chaque distributeur.
CREATE TABLE IF NOT EXISTS Distributeur_Categorie (
    Code_unique_distributeur TEXT NOT NULL
        REFERENCES Distributeurs (Code_unique_distributeur) ON DELETE CASCADE,
    Categorie                TEXT NOT NULL CHECK (length(Categorie) <= 50),
    Ordre                    INTEGER NOT NULL,
    -- 0 : rayon absent chez ce distributeur, non propose pour ses articles.
    Retenue                  INTEGER NOT NULL DEFAULT 1 CHECK (Retenue IN (0, 1)),
    PRIMARY KEY (Code_unique_distributeur, Categorie)
);

CREATE INDEX IF NOT EXISTS idx_articles_libelle ON Articles (Libelle);
CREATE INDEX IF NOT EXISTS idx_recettes_libelle    ON Recettes (Libelle);
CREATE INDEX IF NOT EXISTS idx_rec_art_article  ON Recette_Article (Code_unique_article);
CREATE INDEX IF NOT EXISTS idx_lic_art_article  ON Liste_course_Article (Code_unique_article);
