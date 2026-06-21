"""Tests for the stdlib VectorIndex (Tier-2 semantic fallback)."""

from __future__ import annotations

import json
import math
from array import array
from pathlib import Path

from cricket.lore import vector as vec_mod
from cricket.lore.vector import VectorIndex


def _unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _make_index(root: Path, rows):
    """rows = [(meta_dict, vector_list)]."""
    flat = array("f")
    meta = []
    dim = len(rows[0][1])
    for m, v in rows:
        flat.extend(_unit(v))
        meta.append(m)
    (root / "embeddings.f32").write_bytes(flat.tobytes())
    with open(root / "embeddings.meta.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"dim": dim, "count": len(meta)}) + "\n")
        for m in meta:
            fh.write(json.dumps(m) + "\n")


def test_load_and_search(tmp_path, monkeypatch):
    _make_index(tmp_path, [
        ({"title": "RPlog:A", "path": "p/a.txt", "ns_name": "RPlog"}, [1.0, 0.0, 0.0]),
        ({"title": "Bespin", "path": "p/b.txt", "ns_name": "Main"}, [0.0, 1.0, 0.0]),
    ])
    vi = VectorIndex(tmp_path)
    assert vi.loaded and vi.dim == 3 and len(vi.meta) == 2
    # Query embeds close to row 0 -> row 0 ranks first.
    # Query leans toward row 0 but keeps row 1 above min_score so both rank.
    monkeypatch.setattr(vec_mod, "embed_query", lambda q, model="nomic-embed-text": _unit([0.8, 0.6, 0.0]))
    hits = vi.search("anything", k=2)
    assert len(hits) == 2
    assert hits[0]["title"] == "RPlog:A"
    assert hits[0]["score"] > hits[1]["score"]


def test_min_score_filters(tmp_path, monkeypatch):
    _make_index(tmp_path, [({"title": "X", "path": "x", "ns_name": "Main"}, [1.0, 0.0])])
    vi = VectorIndex(tmp_path)
    # Orthogonal query -> score 0 -> filtered by default min_score.
    monkeypatch.setattr(vec_mod, "embed_query", lambda q, model="nomic-embed-text": [0.0, 1.0])
    assert vi.search("q") == []


def test_failed_embed_returns_empty(tmp_path, monkeypatch):
    _make_index(tmp_path, [({"title": "X", "path": "x", "ns_name": "Main"}, [1.0, 0.0])])
    vi = VectorIndex(tmp_path)
    monkeypatch.setattr(vec_mod, "embed_query", lambda q, model="nomic-embed-text": [])
    assert vi.search("q") == []


def test_missing_index_graceful(tmp_path):
    vi = VectorIndex(tmp_path)  # empty dir
    assert not vi.loaded
    assert vi.search("anything") == []


def test_dim_mismatch_unusable(tmp_path):
    # meta says 2 rows but the binary has only 1 row of dim 2 -> unusable, not a crash.
    (tmp_path / "embeddings.f32").write_bytes(array("f", [1.0, 0.0]).tobytes())
    with open(tmp_path / "embeddings.meta.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"dim": 2, "count": 2}) + "\n")
        fh.write(json.dumps({"title": "A"}) + "\n")
        fh.write(json.dumps({"title": "B"}) + "\n")
    vi = VectorIndex(tmp_path)
    assert not vi.loaded
