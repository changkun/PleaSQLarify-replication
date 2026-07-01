"""Shared fixtures: an offline filmmaking DB + mock generations (specs 01, 03)."""

from __future__ import annotations

import sqlite3

import pytest

from pleasqlarify.data.ambrosia import schema_from_sqlite
from pleasqlarify.model.types import DbSchema


@pytest.fixture
def film_db(tmp_path):
    """A tiny AMBROSIA-like Filmmaking database (spec 01: ~5 tables, <10 rows)."""
    path = str(tmp_path / "film.sqlite")
    con = sqlite3.connect(path)
    con.executescript(
        """
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


@pytest.fixture
def schema(film_db) -> DbSchema:
    return schema_from_sqlite(film_db)


@pytest.fixture
def review_completions() -> list[str]:
    """Simulated GPT-4o samples for "What was the review of the drama film?".

    Two clear intents: critic Opinion vs AudienceReviews, plus textual variants
    (functional duplicates) and one unparseable string that must be dropped.
    """
    return [
        # intent A: critic opinion (3 textual variants -> functional duplicates)
        "SELECT Opinion FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
        "SELECT R.Opinion FROM Reviews R JOIN Film F ON R.FilmId=F.id WHERE F.Genre='Drama'",
        "SELECT Opinion FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
        # intent B: audience reviews
        "SELECT AudienceReviews FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
        "SELECT R.AudienceReviews FROM Reviews R JOIN Film F ON R.FilmId=F.id WHERE F.Genre='Drama'",
        # a third intent: critic name
        "SELECT CriticName FROM Reviews WHERE FilmId IN (SELECT id FROM Film WHERE Genre='Drama')",
        # unparseable -> dropped
        "SELECT SELECT FROM WHERE",
    ]
