"""View payload builders for the three interface panels (specs 12-14).

Pure functions ``Session -> dict`` so they are unit-testable without HTTP. The
FastAPI layer (spec 11) just serializes these.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..model.types import ResultTable
from ..pipeline.decision_vars import cooccurrence
from ..pipeline.project import project_2d
from ..session import Session

_REDS = ["#7a1f1f", "#a83232", "#c85a5a", "#e08a8a", "#f0b8b8", "#f7d4d4"]
_BLUES = ["#1f3a7a", "#3255a8", "#5a7ec8", "#8aa8e0", "#b8cef0", "#d4e2f7"]


def _atom_view(session: Session, index: int) -> dict:
    f = session.vocab.features[index]
    return {"index": index, "kind": f.kind, "keyword": f.keyword, "value": f.value}


def _cluster_colors(session: Session) -> dict[int, str]:
    """Red shades = clusters carrying the current decision variable, blue = not (spec 12)."""
    top = session.next_variable()
    contains = top.contains_cluster_ids if top else frozenset()
    colors: dict[int, str] = {}
    red_i = blue_i = 0
    for cl in session.intents:
        if top is not None and cl.id in contains:
            colors[cl.id] = _REDS[red_i % len(_REDS)]
            red_i += 1
        else:
            colors[cl.id] = _BLUES[blue_i % len(_BLUES)]
            blue_i += 1
    return colors


def action_space_view(session: Session, use_umap: bool | None = None) -> dict:
    """Action Space payload: 2-D glyphs colored by cluster / decision (spec 12)."""
    if use_umap is None:
        use_umap = getattr(session, "use_umap", False)
    survivors = session._survivors()
    idx = session.surviving_indices()
    if idx:
        sub = session.sim[np.ix_(idx, idx)]
        coords = project_2d(sub, use_umap=use_umap)
    else:
        coords = []
    colors = _cluster_colors(session)
    queries = []
    for pos, cand in enumerate(survivors):
        rt = cand.result or ResultTable()
        queries.append(
            {
                "id": cand.id,
                "x": float(coords[pos][0]),
                "y": float(coords[pos][1]),
                "cluster_id": cand.cluster_id,
                "color": colors.get(cand.cluster_id, "#999999"),
                "rows": rt.n_rows,
                "cols": rt.n_cols,
                "sql": cand.sql,
            }
        )
    return {
        "queries": queries,
        "clusters": [{"id": cl.id, "color": colors.get(cl.id, "#999")} for cl in session.intents],
    }


def decision_space_view(session: Session) -> dict:
    """Decision Space payload: ranked variables + example query (spec 13)."""
    survivors = session._survivors()
    by_id = {c.id: c for c in session.candidates}
    variables = []
    for v in session.ranked:
        # example query: representative of a cluster that carries this variable
        example_cluster = next(
            (cl for cl in session.intents if cl.id in v.contains_cluster_ids), None
        )
        example = None
        if example_cluster is not None:
            rep = by_id[example_cluster.representative_id]
            implicit = [
                a
                for a in sorted(rep.z)
                if a not in v.group
                and cooccurrence(frozenset({a}), v.group, survivors) >= 0.999
            ]
            example = {
                "id": rep.id,
                "sql": rep.sql,
                "atoms": [_atom_view(session, a) for a in sorted(rep.z)],
                "group": sorted(v.group),
                "implicit": implicit,
            }
        variables.append(
            {
                "id": v.id,
                "label": v.label,
                "atoms": [_atom_view(session, a) for a in sorted(v.group)],
                "ig": v.ig,
                "example": example,
            }
        )
    top = session.next_variable()
    return {
        "variables": variables,
        "top_id": top.id if top else None,
        "terminated": session.terminated,
    }


def predicted_query_view(session: Session) -> dict:
    """Predicted Query + Predicted Output payload (spec 14)."""
    probs = session.predicted_query_atoms()
    features = []
    for index, p in sorted(probs.items(), key=lambda kv: (-kv[1], kv[0])):
        if p >= 0.999:
            state = "determined"
        else:
            state = "likely"
        fv = _atom_view(session, index)
        fv.update({"prob": p, "state": state})
        features.append(fv)

    out: Optional[ResultTable] = session.predicted_output()
    output = None
    if out is not None and not out.is_error:
        output = {"columns": out.columns, "rows": [list(r) for r in out.rows[:50]]}
    final = session.final_query()
    return {
        "features": features,
        "output": output,
        "final_sql": final.sql if final else None,
    }


def state_view(session: Session) -> dict:
    """Bundle used by the API to refresh all linked views at once (spec 11)."""
    return {
        "turn": session.turn,
        "terminated": session.terminated,
        "utterance": session.utterance,
        "n_candidates": len(session.surviving_ids),
        "action_space": action_space_view(session),
        "decision_space": decision_space_view(session),
        "predicted_query": predicted_query_view(session),
    }


__all__ = [
    "action_space_view",
    "decision_space_view",
    "predicted_query_view",
    "state_view",
]
