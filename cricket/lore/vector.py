"""VectorIndex: stdlib-only semantic search over the wiki cache (Tier-2 fallback).

Loads the unit vectors built by tools/build_embeddings.py and does cosine search (dot of
normalized vectors via math.sumprod, fast in 3.13) to find pages relevant to a query, even
when no curated dossier and no exact wiki title match exist. The query is embedded at call
time with the same local Ollama embedding model. Missing index -> not loaded, search -> [].
"""

from __future__ import annotations

import json
import math
import os
import urllib.request
from array import array
from pathlib import Path
from typing import Union

_OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def embed_query(text: str, model: str = "nomic-embed-text", timeout: float = 20.0) -> list:
    """Embed and L2-normalize one string via Ollama. [] on any failure."""
    try:
        req = urllib.request.Request(
            _OLLAMA + "/api/embeddings",
            # keep_alive keeps the small embed model resident so a fallback mid-conversation
            # does not pay a ~2s cold load each time.
            data=json.dumps({"model": model, "prompt": text, "keep_alive": "30m"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            v = json.loads(resp.read().decode("utf-8")).get("embedding") or []
    except Exception:  # noqa: BLE001
        return []
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


class VectorIndex:
    def __init__(self, cache_dir: Union[str, Path] = "wiki-cache",
                 model: str = "nomic-embed-text") -> None:
        self.dir = Path(cache_dir)
        self.model = model
        self.dim = 0
        self.meta: list = []
        self._vecs: Union[memoryview, None] = None
        self._load()

    def _load(self) -> None:
        meta_p = self.dir / "embeddings.meta.jsonl"
        bin_p = self.dir / "embeddings.f32"
        if not (meta_p.exists() and bin_p.exists()):
            return
        try:
            lines = meta_p.read_text(encoding="utf-8").splitlines()
            header = json.loads(lines[0])
            self.dim = int(header.get("dim", 0))
            self.meta = [json.loads(x) for x in lines[1:] if x.strip()]
            arr = array("f")
            with open(bin_p, "rb") as fh:
                arr.frombytes(fh.read())
        except (ValueError, OSError, IndexError):
            self.dim = 0
            self.meta = []
            return
        if self.dim and len(arr) == self.dim * len(self.meta):
            self._vecs = memoryview(arr)
        else:  # mismatch -> unusable
            self.meta = []
            self.dim = 0

    @property
    def loaded(self) -> bool:
        return bool(self._vecs is not None and self.meta)

    def search(self, query: str, k: int = 3, min_score: float = 0.55) -> list:
        """Top-k pages semantically closest to `query`, each {title, path, ns_name, score},
        score = cosine similarity in [-1,1]. Empty if not loaded or the query fails to embed."""
        if not self.loaded or not query.strip():
            return []
        qv = embed_query(query, self.model)
        if not qv or len(qv) != self.dim:
            return []
        mv = self._vecs
        dim = self.dim
        scored = []
        for i, m in enumerate(self.meta):
            row = mv[i * dim:(i + 1) * dim]
            s = math.sumprod(qv, row)
            if s >= min_score:
                scored.append((s, i))
        scored.sort(key=lambda si: -si[0])
        out = []
        for s, i in scored[:k]:
            m = self.meta[i]
            out.append({"title": m.get("title", ""), "path": m.get("path"),
                        "ns_name": m.get("ns_name"), "score": round(s, 3)})
        return out
