"""FastAPI session backend for the visual interface (spec 11).

In-memory, single-process session store (this is a research tool). Each mutation
returns the full ``state_view`` so the frontend can refresh all linked views from
one response (spec 11, A-be-2). Every request is appended to a per-session JSONL
event log for study-trace capture (spec 11, A-be-3).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..data.ambrosia import schema_from_sqlite
from ..llm.client import LLMClient, MockLLMClient
from ..model.types import DbSchema
from ..session import Session, build_session
from .views import (
    action_space_view,
    decision_space_view,
    predicted_query_view,
    state_view,
)

_FRONTEND = Path(__file__).parent / "static"
_LOG_DIR = Path(os.environ.get("PLEASQL_LOG_DIR", "data/sessions"))


class StartRequest(BaseModel):
    utterance: str
    db_path: str
    # For offline demos, completions can be supplied directly instead of a live LLM.
    completions: Optional[list[str]] = None
    mode: str = "grouped"


class AnswerRequest(BaseModel):
    variable_id: str
    value: bool


class SelectRequest(BaseModel):
    query_ids: list[str]


def _log(session_id: str, event: dict) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_DIR / f"{session_id}.jsonl", "a") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:  # pragma: no cover - logging must never break a request
        pass


def create_app(client_factory=None) -> FastAPI:
    """Build the app. ``client_factory(completions)->LLMClient`` is injectable for tests."""
    app = FastAPI(title="PleaSQLarify")
    sessions: dict[str, Session] = {}

    def make_client(completions: Optional[list[str]]) -> LLMClient:
        if client_factory is not None:
            return client_factory(completions)
        if completions is not None:
            return MockLLMClient(completions)
        from ..llm.client import OpenAIClient  # pragma: no cover

        return OpenAIClient()

    def get(session_id: str) -> Session:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="unknown session")
        return sessions[session_id]

    @app.post("/session")
    def start(req: StartRequest):
        schema: DbSchema = schema_from_sqlite(req.db_path)
        session = build_session(
            req.utterance,
            schema,
            req.db_path,
            make_client(req.completions),
            mode=req.mode,
        )
        sid = uuid.uuid4().hex
        sessions[sid] = session
        _log(sid, {"event": "start", "utterance": req.utterance})
        return {"session_id": sid, **state_view(session)}

    @app.post("/demo")
    def demo():
        """Start an offline demo session (Filmmaking review ambiguity)."""
        from ..data.demo import DEMO_COMPLETIONS, DEMO_UTTERANCE, build_demo_db

        db_path = str(_LOG_DIR / "demo.sqlite")
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        build_demo_db(db_path)
        schema = schema_from_sqlite(db_path)
        session = build_session(
            DEMO_UTTERANCE, schema, db_path, MockLLMClient(DEMO_COMPLETIONS)
        )
        sid = uuid.uuid4().hex
        sessions[sid] = session
        _log(sid, {"event": "demo"})
        return {"session_id": sid, **state_view(session)}

    @app.get("/session/{sid}/action_space")
    def action_space(sid: str):
        return action_space_view(get(sid))

    @app.get("/session/{sid}/decision_space")
    def decision_space(sid: str):
        return decision_space_view(get(sid))

    @app.get("/session/{sid}/predicted_query")
    def predicted_query(sid: str):
        return predicted_query_view(get(sid))

    @app.post("/session/{sid}/answer")
    def answer(sid: str, req: AnswerRequest):
        session = get(sid)
        session.answer(req.variable_id, req.value)
        _log(sid, {"event": "answer", "variable": req.variable_id, "value": req.value})
        return state_view(session)

    @app.post("/session/{sid}/undo")
    def undo(sid: str):
        session = get(sid)
        session.undo()
        _log(sid, {"event": "undo"})
        return state_view(session)

    @app.post("/session/{sid}/select")
    def select(sid: str, req: SelectRequest):
        session = get(sid)
        wanted = set(req.query_ids)
        kept = [cid for cid in session.surviving_ids if cid in wanted]
        if kept and len(kept) < len(session.surviving_ids):
            session.history.append(_snap(session))
            session.surviving_ids = kept
            session.turn += 1
            session._recompute()
        _log(sid, {"event": "select", "query_ids": req.query_ids})
        return state_view(session)

    if _FRONTEND.exists():
        app.mount("/static", StaticFiles(directory=str(_FRONTEND)), name="static")

        @app.get("/")
        def index():  # pragma: no cover - static file
            return FileResponse(str(_FRONTEND / "index.html"))

    return app


def _snap(session: Session):
    from ..session import _Snapshot

    return _Snapshot(list(session.surviving_ids), session.turn)


app = create_app()

__all__ = ["create_app", "app"]
