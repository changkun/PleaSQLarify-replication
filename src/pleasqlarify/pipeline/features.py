"""Step 3a - Atomic feature extraction: AST -> z in {0,1}^d (spec 05).

Each candidate query is parsed to an AST and encoded as the set of atomic
features it contains. We use ``sqlglot`` for both parsing and alias resolution
(``qualify``), so ``F.Opinion`` and ``Opinion`` map to the same base
``table.column`` atom (spec 05, A7).

DEVIATION FROM PAPER (documented gap-fill, spec 05 A9 / spec 01): the paper names
the Spider ``process_sql`` parser. That parser is a single vendored file that
handles only a SQL subset and needs a bespoke schema object. We use ``sqlglot``
instead: it is maintained, pip-installable, produces a richer AST, and includes a
column qualifier. The *atoms produced* (clause elements) are the same; only the
parser backend differs. This is an authorized best-choice decision, flagged here.
"""

from __future__ import annotations

from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify

from ..model.types import ActionSpace, Candidate, DbSchema, FeatureVocabulary

_AGG_FUNCS = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)


def _sqlglot_schema(schema: DbSchema) -> dict:
    return {
        t: {c: (schema.column_types.get(f"{t}.{c}") or "TEXT") for c in cols}
        for t, cols in schema.tables.items()
    }


def _alias_map(ast: exp.Expression) -> dict[str, str]:
    """Map each table alias (lowercased) to its base table name (spec 05, A7)."""
    amap: dict[str, str] = {}
    for tbl in ast.find_all(exp.Table):
        base = tbl.name
        amap[base.lower()] = base
        if tbl.alias:
            amap[tbl.alias.lower()] = base
    return amap


def _col_name(col: exp.Column, amap: dict[str, str]) -> str:
    """Canonical ``base_table.column`` (or bare column if the table is unknown)."""
    name = col.name
    table = col.table
    if not table:
        return name
    base = amap.get(table.lower(), table)
    return f"{base}.{name}"


def _lit(node: exp.Expression) -> str:
    """Normalize a literal: strip quotes, casefold string values."""
    if isinstance(node, exp.Literal):
        if node.is_string:
            return node.this.strip().casefold()
        return node.this
    if isinstance(node, exp.Boolean):
        return str(node.this)
    if isinstance(node, exp.Null):
        return "NULL"
    return node.sql(dialect="sqlite").casefold()


def _render_predicate(pred: exp.Expression, amap: dict[str, str]) -> str:
    """Canonical rendering of a WHERE/HAVING predicate atom (spec 05, A6)."""
    if isinstance(pred, exp.Binary) and isinstance(pred.left, exp.Column):
        op = pred.key.upper()
        col = _col_name(pred.left, amap)
        right = pred.right
        rendered_right = (
            _col_name(right, amap) if isinstance(right, exp.Column) else _lit(right)
        )
        symbol = {
            "EQ": "=", "NEQ": "!=", "GT": ">", "GTE": ">=", "LT": "<", "LTE": "<=",
            "LIKE": "LIKE", "ILIKE": "ILIKE",
        }.get(op, op)
        return f"{col} {symbol} {rendered_right}"
    # Fall back to normalized SQL for anything exotic (IN, BETWEEN, functions...).
    return pred.sql(dialect="sqlite").casefold()


def _split_and(node: Optional[exp.Expression]) -> list[exp.Expression]:
    if node is None:
        return []
    if isinstance(node, exp.And):
        return _split_and(node.left) + _split_and(node.right)
    return [node]


def _render_where(node: Optional[exp.Expression], amap: dict[str, str]) -> str:
    """Serialize a whole WHERE clause, preserving boolean structure (A6, authors').

    AND/OR are uppercased and their operands parenthesised, so that
    ``a AND (b OR c)`` and ``(a AND b) OR c`` are *different* atoms. The authors
    rely on this: their attachment heuristics inspect operator ordering inside the
    serialized clause.
    """
    if node is None:
        return ""
    if isinstance(node, exp.Paren):
        return _render_where(node.this, amap)
    if isinstance(node, (exp.And, exp.Or)):
        op = "AND" if isinstance(node, exp.And) else "OR"
        return f"({_render_where(node.left, amap)} {op} {_render_where(node.right, amap)})"
    return _render_predicate(node, amap)


_SET_OPS = (exp.Union, exp.Intersect, exp.Except)


def _from_node(select: exp.Select):
    """FROM clause across sqlglot versions (30.x renamed the arg ``from`` -> ``from_``)."""
    return select.args.get("from_") or select.args.get("from")


def _depth_suffix(depth: int) -> str:
    return f" @{depth}" if depth else ""


def _atoms_for(
    ast: exp.Expression, where_granularity: str = "clause", depth: int = 0
) -> list[tuple[str, str]]:
    """Return ``(kind, payload)`` atoms for a parsed statement.

    Set operations (UNION/INTERSECT/EXCEPT) recurse into **both** branches at
    ``depth + 1``, and the depth is part of the atom payload, so the same column at
    a different nesting level is a different atom. This mirrors the authors'
    ``recursively_extract`` with ``include_depth=True`` and matters enormously on
    AMBROSIA: its attachment and scope ambiguities are UNIONs that differ only in
    *which branch* carries the filter. Visiting one branch would make the two
    interpretations atom-identical, leaving no decision variable able to separate
    them.
    """
    atoms: list[tuple[str, str]] = []
    if isinstance(ast, _SET_OPS):
        atoms.append(("SETOP", f"SETOP {ast.key.upper()}"))
        for branch in (ast.this, ast.expression):
            if branch is not None:
                atoms.extend(_atoms_for(branch, where_granularity, depth + 1))
        return atoms

    select = ast if isinstance(ast, exp.Select) else ast.find(exp.Select)
    if select is None:
        return atoms
    # a subquery inside FROM may itself be a set operation
    amap = _alias_map(select)

    # SELECT projections (incl. DISTINCT and aggregates).
    distinct = select.args.get("distinct") is not None
    for proj in select.expressions:
        target = proj.unalias() if isinstance(proj, exp.Alias) else proj
        if isinstance(target, exp.Star):
            atoms.append(("SELECT_STAR", f"SELECT *{_depth_suffix(depth)}"))
        elif isinstance(target, _AGG_FUNCS):
            inner = target.this
            arg = (
                _col_name(inner, amap)
                if isinstance(inner, exp.Column)
                else ("*" if isinstance(inner, exp.Star) else inner.sql(dialect="sqlite"))
            )
            atoms.append(("AGG", f"AGG {target.key.upper()}({arg}){_depth_suffix(depth)}"))
        elif isinstance(target, exp.Column):
            col = _col_name(target, amap)
            if distinct:
                atoms.append(("DISTINCT", f"SELECT DISTINCT {col}{_depth_suffix(depth)}"))
            else:
                atoms.append(("SELECT_COL", f"SELECT {col}{_depth_suffix(depth)}"))
        else:
            atoms.append(
                ("SELECT_COL", f"SELECT {target.sql(dialect='sqlite')}{_depth_suffix(depth)}")
            )

    # FROM tables.
    from_ = _from_node(select)
    if from_ is not None:
        for tbl in from_.find_all(exp.Table):
            atoms.append(("FROM_TABLE", f"FROM {tbl.name}{_depth_suffix(depth)}"))

    # JOINs.
    for join in select.args.get("joins", []) or []:
        tbl = join.this
        tname = tbl.name if isinstance(tbl, exp.Table) else tbl.sql(dialect="sqlite")
        on = join.args.get("on")
        on_txt = f" ON {_render_predicate(on, amap)}" if on is not None else ""
        atoms.append(("JOIN", f"JOIN {tname}{on_txt}{_depth_suffix(depth)}"))

    # WHERE. Two granularities (assumption A6):
    #  * "clause" (the authors' rule): the ENTIRE where clause is a single atom,
    #    with its boolean structure preserved and parenthesised. This is what makes
    #    "filter on the left side" vs "filter on the right side" a single yes/no
    #    decision -- exactly the attachment ambiguity the paper targets.
    #  * "predicate" (our original gap-fill): one atom per AND-separated predicate.
    where = select.args.get("where")
    if where is not None:
        if where_granularity == "clause":
            atoms.append(
                ("WHERE_CLAUSE", f"WHERE {_render_where(where.this, amap)}{_depth_suffix(depth)}")
            )
        else:
            for pred in _split_and(where.this):
                atoms.append(
                    ("WHERE_PRED", f"WHERE {_render_predicate(pred, amap)}{_depth_suffix(depth)}")
                )

    # GROUP BY.
    group = select.args.get("group")
    if group is not None:
        for g in group.expressions:
            key = _col_name(g, amap) if isinstance(g, exp.Column) else g.sql(dialect="sqlite")
            atoms.append(("GROUP_BY", f"GROUP BY {key}{_depth_suffix(depth)}"))

    # HAVING.
    having = select.args.get("having")
    if having is not None:
        for pred in _split_and(having.this):
            atoms.append(("HAVING", f"HAVING {_render_predicate(pred, amap)}{_depth_suffix(depth)}"))

    # ORDER BY.
    order = select.args.get("order")
    if order is not None:
        for o in order.expressions:
            direction = "DESC" if o.args.get("desc") else "ASC"
            key = (
                _col_name(o.this, amap)
                if isinstance(o.this, exp.Column)
                else o.this.sql(dialect="sqlite")
            )
            atoms.append(("ORDER_BY", f"ORDER BY {key} {direction}{_depth_suffix(depth)}"))

    # LIMIT.
    limit = select.args.get("limit")
    if limit is not None:
        atoms.append(
            ("LIMIT", f"LIMIT {limit.expression.sql(dialect='sqlite')}{_depth_suffix(depth)}")
        )

    return atoms


def parse_and_qualify(sql: str, schema: DbSchema) -> Optional[exp.Expression]:
    """Parse ``sql`` and resolve aliases to base ``table.column`` (spec 05, A7).

    Returns ``None`` if the query cannot be parsed at all (spec 03, A2 treats
    that as an invalid candidate).
    """
    try:
        ast = sqlglot.parse_one(sql, dialect="sqlite")
    except Exception:
        return None
    if ast is None:
        return None
    try:
        ast = qualify(
            ast,
            schema=_sqlglot_schema(schema),
            dialect="sqlite",
            expand_stars=False,
            validate_qualify_columns=False,
        )
    except Exception:
        # Alias resolution failed; fall back to name-only atoms (spec 05, A9).
        pass
    return ast


def extract_features(
    candidates: ActionSpace, schema: DbSchema, where_granularity: str = "clause"
) -> FeatureVocabulary:
    """Build the session vocabulary and set ``candidate.z`` for each candidate."""
    vocab = FeatureVocabulary()
    for cand in candidates:
        ast = parse_and_qualify(cand.sql, schema)
        if ast is None:
            cand.z = frozenset()
            continue
        indices = {
            vocab.intern(kind, payload)
            for kind, payload in _atoms_for(ast, where_granularity)
        }
        cand.z = frozenset(indices)
    return vocab


def is_parseable(sql: str) -> bool:
    """Spider/parse validity check used by candidate generation (spec 03, A2)."""
    try:
        return sqlglot.parse_one(sql, dialect="sqlite") is not None
    except Exception:
        return False


__all__ = ["extract_features", "parse_and_qualify", "is_parseable"]
