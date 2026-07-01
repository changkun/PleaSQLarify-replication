"""A self-contained offline demo (Filmmaking domain) for the interface.

Lets the visual interface and its tests run with no LLM and no dataset, by
building a tiny SQLite database and supplying canned GPT-4o-style completions for
the paper's running "review of the drama film" ambiguity.
"""

from __future__ import annotations

import sqlite3

DEMO_UTTERANCE = "What was the review of the drama film?"

DEMO_COMPLETIONS = [
    "SELECT Opinion FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
    "SELECT R.Opinion FROM Reviews R JOIN Film F ON R.FilmId=F.id WHERE F.Genre='Drama'",
    "SELECT Opinion FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
    "SELECT AudienceReviews FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
    "SELECT R.AudienceReviews FROM Reviews R JOIN Film F ON R.FilmId=F.id WHERE F.Genre='Drama'",
    "SELECT CriticName FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
    "SELECT DISTINCT Opinion FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
]


def build_demo_db(path: str) -> str:
    """Materialize the demo Filmmaking database at ``path`` and return it."""
    con = sqlite3.connect(path)
    con.executescript(
        """
        DROP TABLE IF EXISTS Film;
        DROP TABLE IF EXISTS Reviews;
        CREATE TABLE Film (id INTEGER, Title TEXT, Genre TEXT, Runtime INTEGER);
        CREATE TABLE Reviews (
            FilmId INTEGER, Opinion TEXT, AudienceReviews TEXT, CriticName TEXT
        );
        INSERT INTO Film VALUES
            (1, 'Pulp Fiction', 'Drama', 154),
            (2, 'Heat', 'Drama', 170),
            (3, 'Airplane', 'Comedy', 88);
        INSERT INTO Reviews VALUES
            (1, 'A masterpiece.', 'Five stars!', 'Ebert'),
            (2, 'Terrific acting.', 'Audience loved it!', 'Kael'),
            (3, 'Very funny.', 'Hilarious!', 'Ebert');
        """
    )
    con.commit()
    con.close()
    return path


__all__ = ["DEMO_UTTERANCE", "DEMO_COMPLETIONS", "build_demo_db"]
