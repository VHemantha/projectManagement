"""Embeddings run inside this service: no client text leaves it and no tokens are spent.

Claude has no embeddings endpoint, so there are two local options:
- "hash": a signed feature-hashing vector over words, numbers and character trigrams. No model
  download, deterministic, good at the exact terms accounting documents share (account names,
  codes, amounts). The default, and what the tests use.
- "fastembed": a small local ONNX sentence model (BAAI/bge-small-en-v1.5, 384 dimensions) that
  matches meaning, not only words: "who manages the property" finds the manager's statements.
  What production uses (12 Oct 2026). About 180 MB of memory once loaded, so it is loaded on
  first use, from a folder the deploy fills once (no download while the service runs).
"""
import hashlib
import math
import re
from functools import lru_cache

import numpy as np

from .config import get_settings

_WORD = re.compile(r"[a-z]+|\d+(?:\.\d+)?")


class HashEmbedder:
    name = "hash-v1"

    def __init__(self, dim: int):
        self.dim = dim

    def _features(self, text: str):
        words = _WORD.findall(text.lower())
        for w in words:
            yield w, 1.0
            if len(w) > 4 and w.isalpha():
                for i in range(len(w) - 2):
                    yield "#" + w[i : i + 3], 0.35
        for a, b in zip(words, words[1:]):
            yield a + "_" + b, 0.6

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts: dict[int, float] = {}
            for feat, weight in self._features(text):
                h = int.from_bytes(hashlib.blake2b(feat.encode(), digest_size=8).digest(), "big")
                idx, sign = h % self.dim, (1.0 if (h >> 63) & 1 else -1.0)
                counts[idx] = counts.get(idx, 0.0) + sign * weight
            for idx, value in counts.items():
                out[row, idx] = math.copysign(math.log1p(abs(value)), value)  # sublinear tf
            norm = np.linalg.norm(out[row])
            if norm:
                out[row] /= norm
        return out


class FastEmbedder:
    def __init__(self, model: str, cache_dir: str = ""):
        self.model_name, self.cache_dir = model, cache_dir or None
        self.name = "fastembed:" + model  # known without loading the model
        self._model = None

    def _loaded(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.array(list(self._loaded().embed(texts)), dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)


@lru_cache
def get_embedder():
    s = get_settings()
    if s.embedder == "fastembed":
        return FastEmbedder(s.fastembed_model, s.fastembed_cache)
    return HashEmbedder(s.embedding_dim)
