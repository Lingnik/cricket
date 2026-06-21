"""WikiIndex: stdlib-only runtime access to the bundled wiki cache.

`wiki-cache/index.jsonl` has one record per page: {title, ns, ns_name, path, last_edit,
characters[], rl_date, aby_year, factions[], summary}. RPlog pages carry an AI summary;
Main-namespace articles (characters/places/factions) do not, so for those we read the page
file's lead paragraph on demand.

This powers Cricket's "rogue wiki search engine": given a name or topic mentioned in OOC
chat, surface a short factual blurb the persona can deliver with attitude; and given his own
name, surface his logged misadventures for IC history. No embeddings -- token-overlap ranking
over titles + summaries, which is plenty for a 7.4k-page cache and keeps the runtime
dependency-light (stdlib only). Missing cache -> every method returns empty, like LoreStore.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Union

# Namespaces worth surfacing as topics/answers (skip Talk/File/Category/User noise).
_USEFUL_NS = {"Main", "RPlog", "Report"}
_WORD = re.compile(r"[A-Za-z0-9']+")
# Tokens too common to help ranking (and a few wiki-structural words).
_STOP = {
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "at", "is", "was", "for",
    "with", "by", "his", "her", "their", "its", "he", "she", "they", "it", "as", "rplog",
    "report", "part", "the", "from", "into", "who", "what", "about", "you", "do", "know",
}
# Connecting particles allowed inside a Capitalized topic phrase ("Battle of Coruscant",
# "Johanna te Danaan"). NOT "and" -- that joins two distinct topics.
_PARTICLES = {"of", "the", "te", "van", "von", "de", "la", "du"}


def _tokens(text: str) -> set:
    return {t.lower() for t in _WORD.findall(text or "") if t.lower() not in _STOP and len(t) > 1}


def _strip_wikitext(text: str) -> str:
    """Best-effort markup cleanup for a page lead -> plain ASCII-ish prose."""
    t = text
    t = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", t, flags=re.IGNORECASE)  # images
    for _ in range(2):                                          # {{templates}} (simple nesting)
        t = re.sub(r"\{\{[^{}]*\}\}", "", t)
    t = re.sub(r"\[\[[^\]|]*\|([^\]]+)\]\]", r"\1", t)          # [[Link|Shown]] -> Shown
    t = re.sub(r"\[\[([^\]]+)\]\]", r"\1", t)                   # [[Link]] -> Link
    t = re.sub(r"'''?", "", t)                                  # bold/italic ticks
    t = re.sub(r"<[^>]+>", "", t)                               # stray html
    # leading image-placement keywords left after a stripped File link
    t = re.sub(r"^\s*(?:thumb|thumbnail|right|left|upright|\d+px)\b[\s|]*", "", t, flags=re.I)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&")
    return " ".join(t.split())


class WikiIndex:
    def __init__(self, cache_dir: Union[str, Path] = "wiki-cache") -> None:
        self.dir = Path(cache_dir)
        self._recs: list = []
        self._by_title: dict = {}          # normalized title -> record
        self._by_char: dict = {}           # character name (lower) -> [records]
        self._lead_cache: dict = {}        # path -> lead text
        self._load()

    # -- loading ---------------------------------------------------------------
    def _load(self) -> None:
        p = self.dir / "index.jsonl"
        if not p.exists():
            return
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("ns_name") not in _USEFUL_NS:
                continue
            r["_ttok"] = _tokens(self._bare_title(r.get("title", "")))
            r["_stok"] = _tokens(r.get("summary", ""))
            self._recs.append(r)
            self._by_title.setdefault(self._norm(r.get("title", "")), r)
            for c in r.get("characters") or []:
                self._by_char.setdefault(c.strip().lower(), []).append(r)

    @staticmethod
    def _bare_title(title: str) -> str:
        """Drop a namespace prefix like 'RPlog:' / 'Report:' for matching/tokens."""
        return title.split(":", 1)[1] if ":" in title else title

    def _norm(self, title: str) -> str:
        return re.sub(r"[^a-z0-9 ]+", "", self._bare_title(title).lower()).strip()

    @property
    def loaded(self) -> bool:
        return bool(self._recs)

    # -- lead text for articles without an index summary -----------------------
    def lead(self, rec: dict, max_len: int = 400) -> str:
        """The record's summary if present, else the page file's first real paragraph."""
        s = (rec.get("summary") or "").strip()
        if s:
            return s[:max_len]
        path = rec.get("path")
        if not path:
            return ""
        if path in self._lead_cache:
            return self._lead_cache[path][:max_len]
        f = self.dir / path
        lead = ""
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        if raw:
            # Content starts after the '====' separator that follows the metadata header.
            m = re.search(r"={6,}\s*\n", raw)
            body = raw[m.end():] if m else raw
            for block in re.split(r"\n\s*\n", body):
                stripped = block.strip()
                # Skip section headers, categories, infobox/table rows, bare templates.
                if stripped.startswith(("==", "Category:", "[[Category", "{{", "|", "!", "*", "#")):
                    continue
                cleaned = _strip_wikitext(block)
                low = cleaned.lower()
                if low.startswith(("category", "thumb", "title", "namespace")):
                    continue
                if len(cleaned) >= 60 and " " in cleaned:
                    lead = cleaned
                    break
        self._lead_cache[path] = lead
        return lead[:max_len]

    # -- lookup / search -------------------------------------------------------
    def lookup(self, title: str) -> Union[dict, None]:
        return self._by_title.get(self._norm(title))

    def search(self, query: str, limit: int = 5, ns: Union[str, None] = None) -> list:
        """Records ranked by token overlap (title weighted 3x over summary). ns filters
        by namespace name (e.g. 'RPlog'). Returns at most `limit` records."""
        q = _tokens(query)
        if not q:
            return []
        scored = []
        for r in self._recs:
            if ns is not None and r.get("ns_name") != ns:
                continue
            score = 3 * len(q & r["_ttok"]) + len(q & r["_stok"])
            if score:
                scored.append((score, r))
        scored.sort(key=lambda sr: (-sr[0], sr[1].get("title", "")))
        return [r for _, r in scored[:limit]]

    def summary_for(self, topic: str, max_len: int = 360) -> str:
        """A short blurb for a name/topic: exact title hit -> its lead; else best search hit
        whose title shares a token with the query. '' if nothing decent matches."""
        rec = self.lookup(topic)
        if rec is None:
            qt = _tokens(topic)
            for cand in self.search(topic, limit=3):
                if qt & cand["_ttok"]:
                    rec = cand
                    break
        if rec is None:
            return ""
        return self.lead(rec, max_len=max_len)

    def logs_for_character(self, name: str, limit: int = 6) -> list:
        """RPlog records whose cast includes `name`, newest in-universe first, summary-bearing.
        Returns [{title, summary, aby_year, rl_date}] -- used for Cricket's own IC history."""
        recs = self._by_char.get((name or "").strip().lower(), [])
        recs = [r for r in recs if (r.get("summary") or "").strip()]
        recs.sort(key=lambda r: (r.get("aby_year") or 0, r.get("rl_date") or ""), reverse=True)
        out = []
        for r in recs[:limit]:
            out.append({
                "title": self._bare_title(r.get("title", "")),
                "summary": (r.get("summary") or "").strip(),
                "aby_year": r.get("aby_year"),
                "rl_date": r.get("rl_date"),
            })
        return out

    # -- topic extraction for OOC injection ------------------------------------
    def topics(self, text: str, limit: int = 2, exclude: Union[set, None] = None) -> list:
        """Capitalized topic phrases in `text` that resolve to a wiki page, as
        [(title, summary)]. `exclude` is a set of lowercased names already covered (e.g. by a
        dossier) so we do not double up. Deterministic: longest phrases first."""
        exclude = {e.lower() for e in (exclude or set())}
        out = []
        seen = set()
        for phrase in _capitalized_phrases(text):
            if phrase.lower() in exclude:
                continue
            blurb = self.summary_for(phrase)
            if not blurb:
                continue
            rec = self.lookup(phrase) or (self.search(phrase, limit=1) or [None])[0]
            title = self._bare_title(rec.get("title", phrase)) if rec else phrase
            key = title.lower()
            if key in seen or key in exclude:
                continue
            seen.add(key)
            out.append((title, blurb))
            if len(out) >= limit:
                break
        return out


def _capitalized_phrases(text: str) -> list:
    """Maximal runs of Capitalized words (allowing inner particles), longest first.
    'tell me about the Golden Bantha Group and Coruscant' -> ['Golden Bantha Group',
    'Coruscant']. Skips a leading sentence-capital single word heuristically by keeping only
    phrases whose first word is Capitalized AND not a common sentence-opener."""
    if not text:
        return []
    words = re.findall(r"[A-Za-z0-9']+|[^A-Za-z0-9']+", text)
    phrases = []
    cur = []
    for w in words:
        tok = w.strip()
        if not tok:
            continue
        if tok[:1].isupper():
            cur.append(tok)
        elif tok.lower() in _PARTICLES and cur:
            cur.append(tok.lower())
        else:
            if cur:
                phrases.append(" ".join(cur).strip())
                cur = []
    if cur:
        phrases.append(" ".join(cur).strip())
    # Trim trailing particles; drop empties / single common openers.
    cleaned = []
    openers = {"What", "Who", "Tell", "Do", "Hey", "So", "I", "The", "A", "An", "And", "But"}
    for p in phrases:
        toks = p.split()
        while toks and toks[-1] in _PARTICLES:
            toks.pop()
        if not toks:
            continue
        if len(toks) == 1 and toks[0] in openers:
            continue
        cleaned.append(" ".join(toks))
    cleaned.sort(key=lambda s: -len(s))
    return cleaned
