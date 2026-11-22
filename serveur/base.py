"""SQLite : connexion et migrations (numéro de version dans PRAGMA user_version)."""
import sqlite3
from contextlib import contextmanager

from . import config

MIGRATIONS = [
    """
    CREATE TABLE defis (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL,
        carte TEXT NOT NULL,
        contrainte TEXT NOT NULL,
        chrono INTEGER NOT NULL,
        lieux_json TEXT NOT NULL,
        cree_le REAL NOT NULL
    );
    CREATE TABLE parties (
        id TEXT PRIMARY KEY,
        joueur_id TEXT NOT NULL,
        pseudo TEXT NOT NULL,
        mode TEXT NOT NULL,
        carte TEXT NOT NULL,
        contrainte TEXT NOT NULL,
        chrono INTEGER NOT NULL,
        defi_id TEXT REFERENCES defis(id),
        lieux_json TEXT NOT NULL,
        nb_manches INTEGER,
        manche INTEGER NOT NULL DEFAULT 1,
        statut TEXT NOT NULL DEFAULT 'en_cours',
        total INTEGER NOT NULL DEFAULT 0,
        cree_le REAL NOT NULL
    );
    CREATE INDEX parties_defi ON parties(defi_id, joueur_id);
    CREATE TABLE manches (
        partie_id TEXT NOT NULL REFERENCES parties(id),
        numero INTEGER NOT NULL,
        lieu_json TEXT NOT NULL,
        debut_le REAL NOT NULL,
        repondu_le REAL,
        rep_lat REAL,
        rep_lon REAL,
        pays_choisi TEXT,
        distance_m REAL,
        points INTEGER NOT NULL DEFAULT 0,
        juste INTEGER,
        temps_ecoule INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (partie_id, numero)
    );
    CREATE TABLE records (
        joueur_id TEXT NOT NULL,
        cle TEXT NOT NULL,
        valeur INTEGER NOT NULL,
        PRIMARY KEY (joueur_id, cle)
    );
    """,
    # 2 : comptes (identifiants YunoHost, jamais de mot de passe), succès, cartes personnalisées
    """
    CREATE TABLE comptes (
        identifiant TEXT PRIMARY KEY,
        pseudo TEXT NOT NULL,
        cree_le REAL NOT NULL,
        xp INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE succes (
        identifiant TEXT NOT NULL REFERENCES comptes(identifiant),
        code TEXT NOT NULL,
        obtenu_le REAL NOT NULL,
        PRIMARY KEY (identifiant, code)
    );
    ALTER TABLE parties ADD COLUMN compte TEXT REFERENCES comptes(identifiant);
    CREATE INDEX parties_compte ON parties(compte);
    CREATE TABLE cartes_perso (
        id TEXT PRIMARY KEY,
        nom TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        bbox_json TEXT NOT NULL,
        diagonale_km REAL NOT NULL,
        auteur TEXT NOT NULL,
        cree_le REAL NOT NULL,
        archivee INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE lieux_perso (
        carte_id TEXT NOT NULL REFERENCES cartes_perso(id) ON DELETE CASCADE,
        pano_id TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        pays TEXT,
        PRIMARY KEY (carte_id, pano_id)
    );
    """,
]


def _migrer(c: sqlite3.Connection) -> None:
    version = c.execute("PRAGMA user_version").fetchone()[0]
    for i in range(version, len(MIGRATIONS)):
        c.executescript(MIGRATIONS[i])
        c.execute(f"PRAGMA user_version = {i + 1}")


@contextmanager
def connexion():
    chemin = config.chemin_base()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(chemin, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA foreign_keys = ON")
        _migrer(c)
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()
