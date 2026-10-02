"""The agent's own storage: file manifest, chunks with embeddings, and the exact-match caches.

Postgres with pgvector in production; SQLite for dev and tests (vectors compared in numpy).
Both run the same queries, and every chunk query carries `client_id = ? AND job_id = ?` in the
SQL itself (token rule 2 and the no-cross-client guardrail): one client's pre-check cannot
retrieve another client's text, whatever a prompt says.
"""
import json
import time
from collections.abc import Mapping, Sequence
from functools import lru_cache

import numpy as np
import sqlalchemy as sa
from langgraph.cache.base import BaseCache

from .config import get_settings

metadata = sa.MetaData()


def _tables(is_pg: bool, dim: int):
    if is_pg:
        from pgvector.sqlalchemy import Vector

        vector = Vector(dim)
    else:
        vector = sa.LargeBinary

    manifest = sa.Table(
        "pc_manifest",
        metadata,
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("file_id", sa.String(400), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("mime_type", sa.Text, nullable=False, default=""),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("document_class", sa.String(40), nullable=False),
        sa.Column("web_url", sa.Text, nullable=False, default=""),
        sa.Column("path", sa.Text, nullable=False, default=""),
        sa.Column("n_blocks", sa.Integer, nullable=False, default=0),
        sa.Column("error", sa.Text, nullable=False, default=""),
        sa.Column("indexed_at", sa.Float, nullable=False),
        extend_existing=True,
    )
    chunks = sa.Table(
        "pc_chunks",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("file_id", sa.String(400), nullable=False),
        sa.Column("file_version", sa.String(128), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("location", sa.Text, nullable=False),
        sa.Column("document_class", sa.String(40), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("blocks", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("tokens", sa.Integer, nullable=False),
        sa.Column("embedding", vector, nullable=False),
        sa.Index("pc_chunks_scope", "client_id", "job_id"),
        extend_existing=True,
    )
    parsed = sa.Table(
        "pc_parsed_cache",
        metadata,
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("payload", sa.Text, nullable=False),
        extend_existing=True,
    )
    emb = sa.Table(
        "pc_embedding_cache",
        metadata,
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("vector", sa.LargeBinary, nullable=False),
        extend_existing=True,
    )
    node_cache = sa.Table(
        "pc_node_cache",
        metadata,
        sa.Column("ns", sa.String(200), primary_key=True),
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("enc", sa.String(40), nullable=False),
        sa.Column("value", sa.LargeBinary, nullable=False),
        sa.Column("expires_at", sa.Float, nullable=True),
        extend_existing=True,
    )
    runs = sa.Table(
        "pc_runs",
        metadata,
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.Float, nullable=False),
        sa.Column("finished_at", sa.Float, nullable=True),
        sa.Column("result", sa.Text, nullable=False, default=""),
        extend_existing=True,
    )
    return manifest, chunks, parsed, emb, node_cache, runs


class Store:
    def __init__(self, url: str, dim: int):
        self.is_pg = url.startswith("postgresql")
        kwargs = {} if self.is_pg else {"connect_args": {"check_same_thread": False, "timeout": 30}}
        self.engine = sa.create_engine(url, **kwargs)
        self.dim = dim
        (self.manifest, self.chunks, self.parsed, self.emb, self.node_cache, self.runs) = _tables(self.is_pg, dim)
        with self.engine.begin() as conn:
            if not self.is_pg:
                conn.execute(sa.text("PRAGMA journal_mode=WAL"))
        if self.is_pg:
            # Creating the extension needs a privileged role; in production the deploy script
            # has already done it, so a refusal here is fine as long as the extension exists.
            try:
                with self.engine.begin() as conn:
                    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
            except sa.exc.DBAPIError:
                pass
        metadata.create_all(self.engine, tables=[self.manifest, self.chunks, self.parsed, self.emb, self.node_cache, self.runs])

    # -- vectors ---------------------------------------------------------------------------
    def _to_db(self, vec: np.ndarray):
        vec = np.asarray(vec, dtype=np.float32)
        return vec.tolist() if self.is_pg else vec.tobytes()

    # -- manifest ---------------------------------------------------------------------------
    def get_manifest(self, client_id: str, job_id: str) -> dict[str, dict]:
        m = self.manifest
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(m).where(m.c.client_id == client_id, m.c.job_id == job_id)).mappings()
            return {r["file_id"]: dict(r) for r in rows}

    def upsert_manifest(self, row: dict) -> None:
        m = self.manifest
        with self.engine.begin() as conn:
            conn.execute(sa.delete(m).where(m.c.job_id == row["job_id"], m.c.file_id == row["file_id"]))
            conn.execute(sa.insert(m).values(**row, indexed_at=time.time()))

    def delete_file(self, client_id: str, job_id: str, file_id: str) -> None:
        with self.engine.begin() as conn:
            for t in (self.manifest, self.chunks):
                conn.execute(sa.delete(t).where(t.c.client_id == client_id, t.c.job_id == job_id, t.c.file_id == file_id))

    # -- chunks -----------------------------------------------------------------------------
    def replace_chunks(self, client_id: str, job_id: str, file_id: str, rows: list[dict]) -> None:
        c = self.chunks
        with self.engine.begin() as conn:
            conn.execute(sa.delete(c).where(c.c.client_id == client_id, c.c.job_id == job_id, c.c.file_id == file_id))
            if rows:
                conn.execute(
                    sa.insert(c),
                    [
                        {**r, "client_id": client_id, "job_id": job_id, "file_id": file_id,
                         "blocks": json.dumps(r["blocks"]), "embedding": self._to_db(r["embedding"])}
                        for r in rows
                    ],
                )

    _COLS = ("id", "file_id", "file_version", "seq", "location", "document_class", "text", "blocks", "content_hash", "tokens")

    def _row(self, r) -> dict:
        d = {k: r[k] for k in self._COLS}
        d["blocks"] = json.loads(d["blocks"])
        return d

    def search(
        self,
        client_id: str,
        job_id: str,
        query: np.ndarray,
        k: int,
        classes: Sequence[str] | None = None,
        token_cap: int | None = None,
    ) -> list[dict]:
        """Top-k chunks for this job only. The scope filter is part of the query, not the prompt."""
        c = self.chunks
        where = [c.c.client_id == client_id, c.c.job_id == job_id]
        if classes:
            where.append(c.c.document_class.in_(list(classes)))
        cols = [getattr(c.c, name) for name in self._COLS]
        with self.engine.connect() as conn:
            if self.is_pg:
                distance = c.c.embedding.cosine_distance(self._to_db(query)).label("distance")
                rows = conn.execute(sa.select(*cols, distance).where(*where).order_by(distance).limit(k)).mappings().all()
                scored = [(1.0 - float(r["distance"]), self._row(r)) for r in rows]
            else:
                rows = conn.execute(sa.select(*cols, c.c.embedding).where(*where)).mappings().all()
                q = np.asarray(query, dtype=np.float32)
                scored = sorted(
                    ((float(np.frombuffer(r["embedding"], dtype=np.float32) @ q), self._row(r)) for r in rows),
                    key=lambda pair: (-pair[0], pair[1]["id"]),
                )[:k]
        out, used = [], 0
        for score, row in scored:
            if token_cap is not None and out and used + row["tokens"] > token_cap:
                continue
            used += row["tokens"]
            out.append({**row, "score": round(score, 4)})
        return out

    def get_chunks(self, client_id: str, job_id: str, ids: Sequence[str]) -> list[dict]:
        c = self.chunks
        cols = [getattr(c.c, name) for name in self._COLS]
        with self.engine.connect() as conn:
            rows = conn.execute(
                sa.select(*cols).where(c.c.client_id == client_id, c.c.job_id == job_id, c.c.id.in_(list(ids)))
            ).mappings().all()
        by_id = {r["id"]: self._row(r) for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    def count_chunks(self, client_id: str, job_id: str) -> int:
        c = self.chunks
        with self.engine.connect() as conn:
            return conn.execute(
                sa.select(sa.func.count()).select_from(c).where(c.c.client_id == client_id, c.c.job_id == job_id)
            ).scalar_one()

    # -- exact-match caches (token rule 6) -----------------------------------------------------
    def _get_blob(self, table, key: str):
        with self.engine.connect() as conn:
            return conn.execute(sa.select(table).where(table.c.key == key)).mappings().first()

    def get_parsed(self, key: str) -> dict | None:
        row = self._get_blob(self.parsed, key)
        return json.loads(row["payload"]) if row else None

    def set_parsed(self, key: str, payload: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(sa.delete(self.parsed).where(self.parsed.c.key == key))
            conn.execute(sa.insert(self.parsed).values(key=key, payload=json.dumps(payload)))

    def get_embeddings(self, keys: Sequence[str]) -> dict[str, np.ndarray]:
        if not keys:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(sa.select(self.emb).where(self.emb.c.key.in_(list(keys)))).mappings().all()
        return {r["key"]: np.frombuffer(r["vector"], dtype=np.float32) for r in rows}

    def set_embeddings(self, pairs: Mapping[str, np.ndarray]) -> None:
        if not pairs:
            return
        with self.engine.begin() as conn:
            conn.execute(sa.delete(self.emb).where(self.emb.c.key.in_(list(pairs))))
            conn.execute(sa.insert(self.emb), [{"key": k, "vector": np.asarray(v, dtype=np.float32).tobytes()} for k, v in pairs.items()])

    # -- runs (the agent's own copy; the PM application keeps the history people see) -----------
    def save_run(self, run_id: str, job_id: str, status: str, result: dict | None = None, started: bool = False) -> None:
        r = self.runs
        with self.engine.begin() as conn:
            exists = conn.execute(sa.select(r.c.run_id).where(r.c.run_id == run_id)).first()
            if not exists:
                conn.execute(sa.insert(r).values(run_id=run_id, job_id=job_id, status=status, started_at=time.time(), result=""))
            else:
                values = {"status": status}
                if result is not None:
                    values.update(result=json.dumps(result), finished_at=time.time())
                conn.execute(sa.update(r).where(r.c.run_id == run_id).values(**values))

    def get_run(self, run_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(sa.select(self.runs).where(self.runs.c.run_id == run_id)).mappings().first()
        if not row:
            return None
        d = dict(row)
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return d


class StoreCache(BaseCache):
    """LangGraph node cache kept in the same database, so cached reader results survive restarts
    and are shared by every worker. Keys are exact hashes; nothing here is semantic."""

    def __init__(self, store: Store):
        super().__init__()
        self.store = store

    @staticmethod
    def _split(full_key) -> tuple[str, str]:
        ns, key = full_key
        return "/".join(ns), key

    def get(self, keys):
        t = self.store.node_cache
        out = {}
        now = time.time()
        with self.store.engine.connect() as conn:
            for full_key in keys:
                ns, key = self._split(full_key)
                row = conn.execute(sa.select(t).where(t.c.ns == ns, t.c.key == key)).mappings().first()
                if row and (row["expires_at"] is None or row["expires_at"] > now):
                    out[full_key] = self.serde.loads_typed((row["enc"], row["value"]))
        return out

    async def aget(self, keys):
        return self.get(keys)

    def set(self, pairs):
        t = self.store.node_cache
        now = time.time()
        with self.store.engine.begin() as conn:
            for full_key, (value, ttl) in pairs.items():
                ns, key = self._split(full_key)
                enc, blob = self.serde.dumps_typed(value)
                conn.execute(sa.delete(t).where(t.c.ns == ns, t.c.key == key))
                conn.execute(sa.insert(t).values(ns=ns, key=key, enc=enc, value=blob, expires_at=(now + ttl) if ttl else None))

    async def aset(self, pairs):
        self.set(pairs)

    def clear(self, namespaces=None):
        t = self.store.node_cache
        with self.store.engine.begin() as conn:
            if namespaces is None:
                conn.execute(sa.delete(t))
            else:
                conn.execute(sa.delete(t).where(t.c.ns.in_(["/".join(ns) for ns in namespaces])))

    async def aclear(self, namespaces=None):
        self.clear(namespaces)

    # Plain get/set for nodes that cache by hand (judge, escalate).
    def get_value(self, ns: str, key: str):
        return self.get([((ns,), key)]).get(((ns,), key))

    def set_value(self, ns: str, key: str, value) -> None:
        self.set({((ns,), key): (value, None)})


@lru_cache
def get_store() -> Store:
    s = get_settings()
    return Store(s.database_url, s.embedding_dim)
