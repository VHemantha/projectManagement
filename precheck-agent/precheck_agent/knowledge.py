"""The knowledge store: everything the AI searches, kept in ChromaDB (open source, running inside
this service, data on the server's disk).

Every entry carries tags saying where it belongs — team (the Workspace), vendor (the
Sub-workspace, i.e. the client), project and task — and what it is: a document chunk, an
assumption or judgement, a finding, feedback, a learned skill, an answer. A search works the way
a person finds a card: it filters on the tags first, starting from the task card's own place, and
only then compares meaning among what is left. The filter is part of the query, never of a
prompt, so one client's text cannot reach another client's task.

Documents never leave their vendor. Wider levels (team, firm) exist only for what is meant to be
shared: learned skills a lead approved.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

import numpy as np

from .config import get_settings
from .embeddings import get_embedder

SOURCE_TYPES = ("document", "assumption", "finding", "feedback", "skill", "answer")
# From narrowest to widest. A search starts at one level and may widen; documents stop at vendor.
LEVELS = ("task", "project", "vendor", "team", "firm")
_SHARED_ACROSS_VENDORS = {"skill"}
COLLECTION = "afit_knowledge"


class ScopeError(ValueError):
    """A search was asked to look further than its kind of entry may go."""


@dataclass(frozen=True)
class Scope:
    """Where a task card sits: Workspace (team) > Sub-workspace (vendor) > Project > Task."""

    team: str
    vendor: str
    project: str
    task: str

    @classmethod
    def of(cls, job: dict) -> "Scope":
        return cls(team=job.get("team_id") or "", vendor=job["client_id"], project=job.get("project_id") or "", task=str(job["job_id"]))

    def tags(self) -> dict:
        return {"team": self.team, "vendor": self.vendor, "project": self.project, "task": self.task}


def _eq(key: str, value) -> dict:
    if isinstance(value, (list, tuple, set)):
        return {key: {"$in": list(value)}}
    return {key: value}


def where_for(scope: Scope, level: str, source_types: Iterable[str], **filters) -> dict:
    """The tag filter for a search at `level` from `scope`. `filters` narrow further (doc_class,
    year_role, status, …); a list value means any of them."""
    if level not in LEVELS:
        raise ScopeError(f"Unknown level {level!r}.")
    types = list(source_types)
    wide = LEVELS.index(level) > LEVELS.index("vendor")
    if wide and set(types) - _SHARED_ACROSS_VENDORS:
        raise ScopeError(f"Only {sorted(_SHARED_ACROSS_VENDORS)} may be searched beyond the vendor, not {sorted(set(types))}.")
    conds = [_eq("source_type", types)]
    if level == "task":
        conds += [_eq("vendor", scope.vendor), _eq("task", scope.task)]
    elif level == "project":
        conds += [_eq("vendor", scope.vendor), _eq("project", scope.project)]
    elif level == "vendor":
        conds += [_eq("vendor", scope.vendor)]
    elif level == "team":
        conds += [_eq("team", scope.team)]
    conds += [_eq(k, v) for k, v in filters.items() if v is not None and v != []]
    return conds[0] if len(conds) == 1 else {"$and": conds}


def _clean_meta(meta: dict) -> dict:
    """Chroma keeps str, int, float and bool; None is left out, anything else becomes JSON."""
    out = {}
    for k, v in meta.items():
        if v is None:
            continue
        out[k] = v if isinstance(v, (str, int, float, bool)) else json.dumps(v)
    return out


class Knowledge:
    def __init__(self, path: str):
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self.client = chromadb.PersistentClient(path=path, settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False))
        # Embeddings are made by this service (embeddings.py), so Chroma is given vectors, not text to embed.
        self.col = self.client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None)

    # -- writing ------------------------------------------------------------------------------
    def put(self, scope: Scope, source_type: str, entries: list[dict]) -> None:
        """Add or replace entries: each {"id", "text", "embedding", "meta"}; the scope's tags and
        the source type are added to every one."""
        if source_type not in SOURCE_TYPES:
            raise ValueError(f"Unknown source type {source_type!r}.")
        if not entries:
            return
        self.col.upsert(
            ids=[e["id"] for e in entries],
            documents=[e["text"] for e in entries],
            embeddings=[np.asarray(e["embedding"], dtype=np.float32).tolist() for e in entries],
            metadatas=[_clean_meta({**e.get("meta", {}), **scope.tags(), "source_type": source_type, "embedder": get_embedder().name})
                       for e in entries],
        )

    def replace_file(self, scope: Scope, file_id: str, rows: list[dict]) -> None:
        """A document's chunks, replacing whatever this task held for the file before."""
        self.delete_file(scope, file_id)
        self.put(scope, "document", [{
            "id": r["id"], "text": r["text"], "embedding": r["embedding"],
            "meta": {"file_id": file_id, "file_version": r["file_version"], "seq": r["seq"], "location": r["location"],
                     "doc_class": r["document_class"], "year": r.get("year"), "year_role": r.get("year_role"),
                     "content_hash": r["content_hash"], "tokens": r["tokens"], "blocks": r["blocks"]},
        } for r in rows])

    def delete_file(self, scope: Scope, file_id: str) -> None:
        self.col.delete(where={"$and": [{"source_type": "document"}, {"vendor": scope.vendor}, {"task": scope.task}, {"file_id": file_id}]})

    def tag_years(self, scope: Scope, by_file: dict) -> None:
        """Tag a task's document chunks with each document's year and whether it is this year's
        or last year's (periods.assign_years), once those are known."""
        res = self.col.get(where=where_for(scope, "task", ["document"]), include=["metadatas"])
        ids, metas = [], []
        for entry_id, meta in zip(res["ids"], res["metadatas"]):
            info = by_file.get(meta.get("file_id"), {})
            year, role = info.get("year"), info.get("role", "unknown")
            if meta.get("year") != year or meta.get("year_role") != role:
                fresh = {k: v for k, v in meta.items() if k != "year"}
                fresh["year_role"] = role
                if year is not None:
                    fresh["year"] = year
                ids.append(entry_id)
                metas.append(fresh)
        if ids:
            self.col.update(ids=ids, metadatas=metas)

    def delete(self, ids: list[str]) -> None:
        if ids:
            self.col.delete(ids=ids)

    # -- reading ------------------------------------------------------------------------------
    def search(self, scope: Scope, query: np.ndarray, k: int, level: str = "task", source_types: Iterable[str] = ("document",),
               token_cap: int | None = None, contains: str | None = None, **filters) -> list[dict]:
        """Filter on the tags first, then the k entries closest in meaning among what is left. The
        same text held twice (a statement saved in two folders) counts once. `contains`: only
        entries whose text has these exact words (a name, an address, an amount)."""
        where = where_for(scope, level, source_types, **filters)
        extra = {"where_document": {"$contains": contains}} if contains else {}
        res = self.col.query(query_embeddings=[np.asarray(query, dtype=np.float32).tolist()], n_results=k * 3, where=where,
                             include=["documents", "metadatas", "distances"], **extra)
        out, used, seen = [], 0, set()
        for i, text, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            # A copy: the same text in the same task (the first line names the file and place,
            # which differ between copies). The same words in another task are another task's.
            body = (meta.get("source_type"), meta.get("task"), text.split("\n", 1)[-1])
            if body in seen:
                continue
            seen.add(body)
            if len(out) == k:
                break
            tokens = int(meta.get("tokens", 0) or 0)
            if token_cap is not None and out and used + tokens > token_cap:
                continue
            used += tokens
            out.append(self._entry(i, text, meta, score=round(1.0 - float(dist), 4)))
        return out

    def get(self, scope: Scope, level: str = "task", source_types: Iterable[str] = ("document",), limit: int | None = None,
            **filters) -> list[dict]:
        """Entries by their tags alone, no meaning involved (e.g. every assumption on a task)."""
        res = self.col.get(where=where_for(scope, level, source_types, **filters), limit=limit, include=["documents", "metadatas"])
        return [self._entry(i, t, m) for i, t, m in zip(res["ids"], res["documents"], res["metadatas"])]

    def file_ids(self, scope: Scope) -> set[str]:
        """The files whose chunks this task holds: what is really in the store, whatever a marker
        elsewhere says (the folder may have been restored from an older backup)."""
        res = self.col.get(where=where_for(scope, "task", ["document"]), include=["metadatas"])
        return {m.get("file_id") for m in res["metadatas"]}

    def count(self, scope: Scope, level: str = "task", source_types: Iterable[str] = ("document",), **filters) -> int:
        return len(self.col.get(where=where_for(scope, level, source_types, **filters), include=[])["ids"])

    @staticmethod
    def _entry(entry_id: str, text: str, meta: dict, **extra) -> dict:
        meta = dict(meta)
        if "blocks" in meta:
            meta["blocks"] = json.loads(meta["blocks"])
        return {"id": entry_id, "text": text, **meta, **extra}


@lru_cache
def get_knowledge() -> Knowledge:
    return Knowledge(get_settings().chroma_path)
