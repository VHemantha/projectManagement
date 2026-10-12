"""The agent's own records: file manifest, parsed documents, embeddings and the exact-match
caches, and its copy of each run. Postgres in production; SQLite for dev and tests.

What the AI searches — document chunks and everything tagged with them — is in the knowledge
store (knowledge.py, ChromaDB). Every manifest query carries `client_id = ? AND job_id = ?`.
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


def _tables():
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
    return manifest, parsed, emb, node_cache, runs


class Store:
    def __init__(self, url: str):
        self.is_pg = url.startswith("postgresql")
        kwargs = {} if self.is_pg else {"connect_args": {"check_same_thread": False, "timeout": 30}}
        self.engine = sa.create_engine(url, **kwargs)
        (self.manifest, self.parsed, self.emb, self.node_cache, self.runs) = _tables()
        with self.engine.begin() as conn:
            if not self.is_pg:
                conn.execute(sa.text("PRAGMA journal_mode=WAL"))
        metadata.create_all(self.engine, tables=[self.manifest, self.parsed, self.emb, self.node_cache, self.runs])

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
        m = self.manifest
        with self.engine.begin() as conn:
            conn.execute(sa.delete(m).where(m.c.client_id == client_id, m.c.job_id == job_id, m.c.file_id == file_id))

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

    # Plain get/set for steps that cache by hand (the pre-check, drafting).
    def get_value(self, ns: str, key: str):
        return self.get([((ns,), key)]).get(((ns,), key))

    def set_value(self, ns: str, key: str, value) -> None:
        self.set({((ns,), key): (value, None)})


@lru_cache
def get_store() -> Store:
    s = get_settings()
    return Store(s.database_url)
