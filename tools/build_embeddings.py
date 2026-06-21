"""Build the Tier-2 semantic index for the wiki cache (offline).

Embeds the meaningful text of each useful wiki page -- RPlog summaries and Main-namespace
article leads -- with a local Ollama embedding model, normalizes to unit vectors, and writes:

    wiki-cache/embeddings.f32        -- raw float32 rows (count * dim), row-major
    wiki-cache/embeddings.meta.jsonl -- one {path,title,ns_name,dim,count?} line per row,
                                        first line is a header {"dim":D,"count":N}

The runtime (cricket/lore/vector.py) loads these with the stdlib only and does cosine search
(dot product of unit vectors via math.sumprod). Re-run after the wiki cache changes.

    uv run --python <py313> python tools/build_embeddings.py [--model nomic-embed-text]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.request
from array import array

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cricket.lore.wiki import WikiIndex  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def embed(text: str, model: str) -> list:
    req = urllib.request.Request(
        OLLAMA + "/api/embeddings",
        data=json.dumps({"model": model, "prompt": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8")).get("embedding") or []


def normalize(vec: list) -> list:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else vec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_embeddings")
    ap.add_argument("--cache", default=os.path.join(_ROOT, "wiki-cache"))
    ap.add_argument("--model", default="nomic-embed-text")
    ap.add_argument("--max-chars", type=int, default=900)
    args = ap.parse_args(argv)

    wi = WikiIndex(args.cache)
    if not wi.loaded:
        print("no wiki cache at %s" % args.cache)
        return 1

    # Build the (text, meta) work list: RPlog summaries + Main-article leads.
    items = []
    for r in wi._recs:
        ns = r.get("ns_name")
        if ns == "RPlog":
            text = (r.get("summary") or "").strip()
        elif ns == "Main":
            text = wi.lead(r, max_len=args.max_chars).strip()
        else:
            continue
        if len(text) < 40:
            continue
        title = r.get("title", "")
        items.append((text[: args.max_chars], {"path": r.get("path"), "title": title, "ns_name": ns}))

    print("embedding %d pages with %s ..." % (len(items), args.model))
    vecs = array("f")
    meta = []
    dim = 0
    for i, (text, m) in enumerate(items):
        try:
            v = embed(text, args.model)
        except Exception as e:  # noqa: BLE001
            print("  skip %s: %s" % (m["title"], e))
            continue
        if not v:
            continue
        if dim == 0:
            dim = len(v)
        if len(v) != dim:
            continue
        vecs.extend(normalize(v))
        meta.append(m)
        if (i + 1) % 500 == 0:
            print("  %d/%d" % (i + 1, len(items)))

    count = len(meta)
    out_bin = os.path.join(args.cache, "embeddings.f32")
    out_meta = os.path.join(args.cache, "embeddings.meta.jsonl")
    with open(out_bin, "wb") as fh:
        vecs.tofile(fh)
    with open(out_meta, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"dim": dim, "count": count}) + "\n")
        for m in meta:
            fh.write(json.dumps(m) + "\n")
    print("wrote %s (%d rows x %d dim) and %s" % (out_bin, count, dim, out_meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
