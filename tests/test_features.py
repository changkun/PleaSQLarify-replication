from pleasqlarify.model.types import Candidate, DbSchema
from pleasqlarify.pipeline.features import extract_features, is_parseable


def _payloads(vocab, cand):
    return {vocab.features[i].payload for i in cand.z}


def test_alias_invariance(schema):
    a = Candidate("a", "SELECT Opinion FROM Reviews WHERE FilmId = 1")
    b = Candidate("b", "SELECT R.Opinion FROM Reviews R WHERE R.FilmId = 1")
    vocab = extract_features([a, b], schema)
    assert a.z == b.z  # F.Opinion and Opinion collapse (A7)


def test_eq_vs_like_are_distinct_atoms(schema):
    a = Candidate("a", "SELECT Opinion FROM Reviews WHERE Opinion = 'good'")
    b = Candidate("b", "SELECT Opinion FROM Reviews WHERE Opinion LIKE '%good%'")
    vocab = extract_features([a, b], schema)
    assert a.z != b.z  # reproduces Figure 4 (= vs LIKE are separate)


def test_star_is_single_atom(schema):
    c = Candidate("c", "SELECT * FROM Film")
    vocab = extract_features([c], schema)
    payloads = _payloads(vocab, c)
    # SELECT * stays one atom, not expanded per column (A8) ...
    assert "SELECT *" in payloads
    assert not any(p.startswith("SELECT Film.") for p in payloads)
    # ... alongside the FROM atom (absent before the sqlglot 30 'from_' fix)
    assert any(p.startswith("FROM ") for p in payloads)


def test_distinct_atom(schema):
    c = Candidate("c", "SELECT DISTINCT Opinion FROM Reviews")
    vocab = extract_features([c], schema)
    assert any(f.kind == "DISTINCT" for f in vocab.features)


def test_encode_is_index_stable(schema):
    a = Candidate("a", "SELECT Title FROM Film")
    b = Candidate("b", "SELECT Title FROM Film")
    vocab = extract_features([a, b], schema)
    assert a.z == b.z


def test_is_parseable():
    assert is_parseable("SELECT 1")
    assert not is_parseable("SELECT SELECT FROM WHERE")
