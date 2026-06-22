"""LlmPersona: turns a Turn into a prompt, calls an InferenceClient, returns a Response.

The message ASSEMBLY follows the cache-stable layout from docs/INFERENCE_BACKEND.md
(most-stable first: system + character bio -> memories/context -> the new turn), so the
Ollama prefix cache stays warm. The prompt CONTENT -- the real character sheet, voice, and
memory weaving -- is owned by phase 2 (the persona session) and lives in the active
profile's `prompts` block; this provides a functional default so a dry-run produces text.

The persona reads the active profile live via `profile_getter`, so edits made through the
HTTP panel take effect without restarting the bot.
"""

from __future__ import annotations

import re
from typing import Callable, Union

from .base import Persona, Response, Turn
from .inference import InferenceClient

# Ollama option keys passed straight through from the profile's inference block.
# Inference keys forwarded verbatim to Ollama options. Includes the small-model-RP sampling
# toolkit (min_p, repeat_penalty/repeat_last_n, top_k, ...) -- without these in the whitelist the
# backend never sees them even if the profile sets them. (DRY is omitted: Ollama 0.30.x ignores
# dry_* options, verified by an extreme-value honor probe.)
_PASSTHROUGH = (
    "num_ctx", "num_predict", "temperature", "top_p", "stop", "seed",
    "top_k", "min_p", "typical_p", "repeat_penalty", "repeat_last_n",
    "presence_penalty", "frequency_penalty", "tfs_z",
    "mirostat", "mirostat_tau", "mirostat_eta",
)

# Standing guard against the 8B model's confabulation: it engages well but invents canon
# (fake events/names/roles). Better to deflect than fabricate. Applied to every system prompt.
_NO_FABRICATION = (
    "Hard rule: do not invent canon. If you do not actually know a specific fact -- a name, "
    "date, event, place, or your own role in it -- do NOT make one up. Bluster, insult, and "
    "change the subject instead. Crude bravado is fine; fabricated facts are not. This applies "
    "to the SCENE in front of you too: react only to who and what is ACTUALLY present in the "
    "lines above -- do not invent characters, titles, costumes, or props, do not misname who is "
    "there, and do not drag in a thread from some other scene. When unsure, react to the plain "
    "words of the most recent line."
)

# The 8B blends several terse memory bullets into one garbled run-on when asked to narrate.
_RECOUNT_RULE = (
    "When asked to recount a memory or tell a story, pick ONE specific event and tell it "
    "straight through; never blend several separate events into a single garbled run-on."
)

# The model parrots example/self-history catchphrases ("FUCK THE POLICE") as non-sequiturs.
_NOVELTY_RULE = (
    "Your example poses and logged exploits show your VOICE, your fixations, and the KIND of "
    "thing you say -- they are NOT a script. Invent FRESH, scene-specific lines, insults, and "
    "threats every turn that fit THIS exact moment. Do NOT recycle a stock catchphrase from the "
    "examples verbatim, and never drop one as a non-sequitur that ignores the scene."
)


def _looks_like_name(a: str) -> bool:
    """A distillation-extracted 'actor' is a plausible character name: 1-3 words, each
    capitalized and alphabetic. Filters descriptive phrases ('Herglic technician') and junk
    ('none.') so the do-not-puppet set stays clean."""
    a = a.strip().rstrip(".")
    words = a.split()
    if not (1 <= len(words) <= 3) or a.lower() in ("none", "nobody", "narration", "scene"):
        return False
    return all(w[:1].isupper() and w.replace("'", "").replace("-", "").isalpha() for w in words)


# Strip a leaked speech-verb/name prefix the @emit/say wrapper re-adds. Deliberately NOT
# matching "Cricket's ..." or "Cricket whirs ..." -- those are valid third-person @emit openings.
_NAME_PREFIX_RE = re.compile(
    r"^\s*cricket(?:\s+mckenzie)?(?:\s+(?:says?|poses?|emits?|exclaims?)\b[,:]?|\s*:)\s*",
    re.I,
)


def _clean_output(text: str, mode: str) -> str:
    """Format-hygiene pass on a generated line (the scene-replay judge + live smoke tests both
    flagged the 8B doing these): drop a leaked 'Cricket says,' prefix, remove `*asterisk*`
    stage-directions (it's @emit prose / channel speech, never a script direction), and for
    channel chat strip surrounding quotes so the 'X says, "..."' wrapper does not nest quotes."""
    t = (text or "").strip()
    t = _NAME_PREFIX_RE.sub("", t).strip()
    # Asterisk action-beats (*the dome swivels*) are markdown the model should not emit. Strip the
    # markers, but where a beat stands at a sentence/quote boundary (the common case) promote it to
    # its own sentence -- capitalize + end-punctuate -- so removing the asterisks does not leave a
    # lowercase fragment wedged between two quotes (the cleanup bug).
    if "*" in t:
        src = t

        def _beat(m):
            inner = m.group(1).strip()
            if not inner:
                return " "
            pre = src[:m.start()].rstrip()
            if not pre or pre[-1] in '.!?"':
                inner = inner[0].upper() + inner[1:]
                if inner[-1] not in ".!?":
                    inner += "."
            return " " + inner + " "

        t = re.sub(r"\*+([^*]+?)\*+", _beat, src)
        t = t.replace("*", "")  # any stray unmatched asterisk
        t = re.sub(r"\s{2,}", " ", t).strip()
        t = re.sub(r"\s+([.!?,;:])", r"\1", t)  # no space before punctuation
    # Channel speech renders as `Cricket says, "..."`; a wrapping quote pair would nest.
    if mode != "rp" and len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        t = t[1:-1].strip()
    # Balance an odd number of double-quotes: a dangling close at the end -> drop it; an
    # unclosed opener -> close it at the end. Either way the 8B's broken quoting is repaired.
    if t.count('"') % 2 == 1:
        t = t[:-1].rstrip() if t.endswith('"') else t + '"'
    return t


def _to_mush_markup(text: str) -> str:
    """Render the literal newlines/tabs PennMUSH delivered (it evaluated the players' %r/%t
    server-side) back into MUSH markup before showing a pose to the model -- so he sees scenes in
    the same notation he must emit, and is primed to write multi-paragraph %r%t poses himself."""
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\n", "%r").replace("\t", "%t")


class LlmPersona(Persona):
    def __init__(
        self,
        client: InferenceClient,
        profile_getter: Union[Callable, None] = None,
        lore=None,
        wiki=None,
        vector=None,
        tracer=None,
    ) -> None:
        self._client = client
        # Optional turn tracer (cricket.trace.TurnTracer): writes a structured debug line per
        # generation -- what context was injected, whether reasoning ran, the raw/clean output.
        from ..trace import NullTracer
        self._tracer = tracer or NullTracer()
        # () -> active profile doc (dict) or None. Read on each turn so live edits apply.
        self._get_profile = profile_getter or (lambda: None)
        # Optional LoreStore: dossiers for the characters present are injected as a
        # memories block between the stable system prompt and the volatile scene.
        self._lore = lore
        # Optional WikiIndex: in OOC chat, factual blurbs for topics mentioned in the line are
        # injected so Cricket can play "rogue wiki search engine" -- summarize, but crassly.
        self._wiki = wiki
        # Optional VectorIndex: Tier-2 semantic fallback when Tier-1 (dossiers) + keyword wiki
        # lookup both miss -- finds the closest page by meaning.
        self._vector = vector

    async def respond(self, turn: Turn) -> Union[Response, None]:
        doc = self._get_profile() or {}
        prompts = doc.get("prompts", {}) if isinstance(doc, dict) else {}
        inference = doc.get("inference", {}) if isinstance(doc, dict) else {}

        trace = {
            "kind": "generate", "room": turn.location, "mode": turn.mode,
            "speaker": turn.speaker,
            "latest_beat": (turn.context[-1].text if (turn.mode == "rp" and turn.context)
                            else turn.text)[:300],
        }
        memories = self._retrieve_memories(turn, trace=trace)
        # Cricket's own logged history: stable "who you are" content, so it rides in the system
        # block (prefix-cached) rather than the volatile per-turn memories. He draws on it when
        # posing (IC) and brags about it (OOC).
        self_history = self._lore.self_history() if self._lore is not None else ""
        # The RP charter (rules) is injected on RP turns only.
        rp_charter = (self._lore.rp_charter()
                      if (self._lore is not None and turn.mode == "rp") else "")
        options = self._build_options(inference)
        # Optional hidden "thinking" pass: privately plan the response, then generate the
        # real line seeded by that plan. Gated by inference.thinking; off by default. The plan
        # is discarded (never posted). Measured via corpus-replay evals (thinking off vs on).
        plan = ""
        if inference.get("thinking"):
            # The planning pass is its own LLM call; it emits its own `generate` trace record
            # (pass="plan") so it is a first-class, listable/streamable step.
            plan = await self._think(turn, prompts, memories, options, inference,
                                     self_history, rp_charter)
        trace["thinking_enabled"] = bool(inference.get("thinking"))
        trace["plan"] = plan or None
        messages = self._build_messages(
            turn, prompts, memories, plan=plan, self_history=self_history,
            rp_charter=rp_charter,
        )
        trace["pass"] = "compose"
        trace["prompt_chars"] = sum(len(m["content"]) for m in messages)
        trace["message_count"] = len(messages)
        # Full prompt for after-the-fact inspection (the `prompt` ctl command). Kept in the JSONL
        # trace only -- TurnTracer strips it from the live bus event so the tail stays lean.
        trace["prompt"] = messages
        raw = await self._client.complete(
            messages, options=options, keep_alive=inference.get("keep_alive")
        )
        text = _clean_output(raw, turn.mode)
        trace["raw_output"] = raw or ""
        trace["clean_output"] = text
        trace["empty"] = not text
        self._tracer.emit(trace)
        if not text:
            return None
        action = "pose" if turn.mode == "rp" else "say"
        return Response(text=text, action=action)

    async def _think(self, turn: Turn, prompts: dict, memories: str, options: dict,
                     inference: dict, self_history: str = "", rp_charter: str = "") -> str:
        """One short, hidden planning pass. Returns terse private notes (or '' on failure). Emits
        its own `generate` trace record (pass="plan") so the planning call is a first-class step
        in the trace / `prompt` viewer / activity stream, separate from the compose call."""
        msgs = self._build_messages(turn, prompts, memories, thinking=True,
                                    self_history=self_history, rp_charter=rp_charter)
        topts = dict(options)
        topts["num_predict"] = int(inference.get("think_tokens", 160))
        try:
            out = await self._client.complete(
                msgs, options=topts, keep_alive=inference.get("keep_alive")
            )
        except Exception:
            return ""
        plan = (out or "").strip()
        self._tracer.emit({
            "kind": "generate", "pass": "plan", "room": turn.location, "mode": turn.mode,
            "speaker": turn.speaker, "prompt": msgs,
            "prompt_chars": sum(len(m["content"]) for m in msgs),
            "message_count": len(msgs),
            "raw_output": out or "", "clean_output": plan,
        })
        return plan

    def _retrieve_memories(self, turn: Turn, trace=None) -> str:
        """Dossiers for the characters present in this scene (name-based; channel and
        room speakers are matched against known lore characters). Empty if no LoreStore.

        Scope follows the mode: room RP (`rp`) gets the IC facet (canon-plausible knowledge
        only); channel chat gets the OOC facet (the wider meta/teasing suite).

        If `trace` is a dict, the retrieval breakdown is recorded into it for the debug log."""
        cast = []
        seen = set()

        def add(name: str) -> None:
            n = (name or "").strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                cast.append(n)

        # Speakers present in the scene.
        for line in turn.context:
            add(line.speaker)
        add(turn.speaker)

        blocks = []
        mentioned_names = []
        if self._lore is not None:
            # Characters NAMED in the live line or scene, even if absent -- so "what do you
            # know about Johanna?" pulls her dossier. Deterministic gazetteer match.
            mentioned_names = self._lore.mentioned(turn.text)
            for name in mentioned_names:
                add(name)
            for line in turn.context:
                for name in self._lore.mentioned(line.text):
                    add(name)
            # Resolve raw MUSH speaker names to their canonical lore name so PRESENT characters'
            # dossiers actually inject. A poser arrives as a first name / character name (e.g.
            # "Jessalyn", "Johanna"), but dossiers are keyed by the full canonical name
            # ("Jessalyn Valios", "Johanna Siri te Danaan"). Without this, a present character whose
            # pose-name is not their full name gets NO dossier -- the real cause of grounding drift.
            for raw in list(cast):
                for canon in self._lore.mentioned(raw):
                    add(canon)
            scope = "ic" if turn.mode == "rp" else "ooc"
            dossiers = self._lore.retrieve(cast, scope=scope)
            if dossiers.strip():
                blocks.append(dossiers)
            if trace is not None:
                trace["cast"] = list(cast)
                _dos = getattr(self._lore, "dossier", None)
                trace["dossiers_injected"] = [n for n in cast if _dos and _dos(n)]
                trace["scope"] = scope

        # RP only: Cricket's own logged history WITH the people present -- his perfect memory,
        # distilled to the scenes that involved this cast. Grounds callbacks in poses.
        if self._wiki is not None and turn.mode == "rp" and cast:
            shared = self._wiki.shared_history(cast)
            if shared:
                lines = ["What you remember from past scenes with these people:"]
                for h in shared:
                    lines.append("- with %s (%s): %s" % (h["with"], h["title"], h["summary"]))
                blocks.append("\n".join(lines))
            if trace is not None:
                trace["shared_history"] = ["%s/%s" % (h["with"], h["title"]) for h in (shared or [])]

        # RP only: the do-not-puppet set -- characters OTHER players control. A pose is an
        # ownership claim: a block's poser controls their own character (its dbref-attributed
        # speaker) AND any known character they name in an @emit (NPC puppeting). Cricket must
        # never pose for these. Deterministic + gazetteer; over-claiming is safe for the guard.
        if turn.mode == "rp":
            bot_name = (turn.bot_identity.name if turn.bot_identity else "").strip().lower()
            claimed = set()
            for line in turn.context:
                if not getattr(line, "dbref", None):
                    continue  # memory / scene-narration lines, not a real poser
                spk = (line.speaker or "").strip()
                if spk and spk.lower() != bot_name:
                    claimed.add(spk)
                if self._lore is not None:
                    for nm in self._lore.mentioned(line.text):
                        if nm.strip().lower() != bot_name:
                            claimed.add(nm)
            # Merge distillation-refined names (catches NPCs not in the gazetteer).
            for nm in getattr(turn, "claimed", None) or []:
                if nm and nm.strip().lower() != bot_name:
                    claimed.add(nm.strip())
            if claimed:
                blocks.append(
                    "These characters belong to other players -- react TO them but NEVER pose "
                    "their words, actions, thoughts, or outcomes: %s. You control ONLY yourself "
                    "(and any brand-new NPC you introduce)." % ", ".join(sorted(claimed)[:10])
                )
            if trace is not None:
                trace["do_not_puppet"] = sorted(claimed)

        # RP first-appearance prefetch: a brief wiki blurb for present cast who have NO curated
        # dossier, so a newcomer mid-scene is not a stranger.
        if self._wiki is not None and self._lore is not None and turn.mode == "rp":
            skip = {"memory", "scene", ""}
            unknown = []
            for name in cast:
                n = (name or "").strip()
                if (n.lower() in skip or len(n) < 3 or not n[0].isupper()
                        or self._lore.dossier(n) is not None):
                    continue
                blurb = self._wiki.summary_for(n)
                if blurb:
                    unknown.append("- %s: %s" % (n, blurb))
                if len(unknown) >= 3:
                    break
            if unknown:
                blocks.append("Who else is here (from the records):\n" + "\n".join(unknown))
            if trace is not None:
                trace["unknown_prefetch"] = [u.split(":")[0].lstrip("- ") for u in unknown]

        # OOC only: wiki blurbs for topics named in the line (the "rogue search engine"). IC
        # stays canon-grounded. Exclude the bot itself and anyone already covered by a dossier.
        topics = []
        if self._wiki is not None and turn.mode != "rp":
            bot = turn.bot_identity.name if turn.bot_identity else ""
            exclude = set(cast)
            if bot:
                exclude.add(bot)
            topics = self._wiki.topics(turn.text, exclude=exclude)
            if topics:
                lines = [
                    "What the records ACTUALLY say about this -- build your reply from THESE "
                    "facts and summarize them with contempt. Do NOT invent events, names, "
                    "dates, or your own involvement beyond what is written here; if they do not "
                    "cover what was asked, dodge with an insult rather than make something up:"
                ]
                for title, blurb in topics:
                    lines.append("- %s: %s" % (title, blurb))
                blocks.append("\n".join(lines))
        if trace is not None:
            trace["wiki_topics"] = [t for t, _ in topics]

        # Tier-2 semantic fallback (OOC): the line names a subject that matched no dossier and
        # no exact wiki title -- find the closest page by MEANING (embeddings). This is what
        # lets him answer about people/topics with no curated entry.
        if (self._vector is not None and self._wiki is not None and turn.mode != "rp"
                and not mentioned_names and not topics
                and self._wiki.topic_phrases(turn.text)):
            hits = self._vector.search(turn.text, k=1)
            if hits:
                blurb = self._wiki.summary_for(hits[0]["title"])
                if blurb:
                    blocks.append(
                        "Records (closest match) -- %s. Use ONLY what is written here; do not "
                        "fabricate details, events, or your own role. If it does not really "
                        "answer the question, deflect with contempt rather than invent:\n%s"
                        % (hits[0]["title"], blurb)
                    )
                    if trace is not None:
                        trace["vector_hit"] = hits[0]["title"]

        return "\n\n".join(b for b in blocks if b.strip())

    def _build_messages(self, turn: Turn, prompts: dict, memories: str = "",
                        plan: str = "", thinking: bool = False, self_history: str = "",
                        rp_charter: str = "") -> list:
        # Most-stable content first (system + bio), newest content last, so the prefix
        # cache only re-evaluates the tail. PHASE 2 owns the prompt text in prompts.system.
        name = turn.bot_identity.name if turn.bot_identity else "cricket"
        base = prompts.get("system") or "You are %s, a character on a MUSH." % name
        system = base
        # Cricket's own logged history is stable self-knowledge -> system block (cache-warm).
        if self_history.strip():
            system = "%s\n\n## Your own past exploits (real, yours -- draw on them and brag):\n%s" % (
                system, self_history.strip()
            )
        # RP charter (rules) -- RP turns only; outranks his own wants, so it goes high.
        if rp_charter.strip():
            system = "%s\n\n## RP rules (these OUTRANK your own desires):\n%s" % (
                system, rp_charter.strip()
            )
        if turn.directives:
            system = "%s\n\n%s" % (system, turn.directives)
        system = "%s\n\n%s\n%s\n%s" % (system, _NO_FABRICATION, _RECOUNT_RULE, _NOVELTY_RULE)
        messages = [{"role": "system", "content": system.strip()}]

        # Few-shot voice anchors as real turns (user prompt -> his actual pose). For an
        # instruction-tuned model this anchors STYLE far harder than describing it in the
        # system prompt -- it shows the model how Cricket specifically sounds, not just
        # "be unhinged". Absent/empty -> behaves exactly as before.
        for ex in prompts.get("fewshot") or []:
            u, a = ex.get("user", ""), ex.get("assistant", "")
            if u and a:
                messages.append({"role": "user", "content": u})
                messages.append({"role": "assistant", "content": a})

        # Live user message: memories block (changes only when the cast changes) first,
        # then prior history as its OWN block, then the live line called out explicitly.
        parts = []
        if memories.strip():
            # Mode-aware framing: in chat he may use this to ANSWER; in RP it is only
            # background seasoning -- reciting it instead of reacting to the beat was the
            # eval's main failure (lore-dump). Keep it subordinate to the scene in RP.
            if turn.mode == "rp":
                header = ("Background you may draw on ONLY if it fits this exact moment "
                          "(do NOT recite or info-dump it; react to the scene):")
            else:
                header = "What you know (use it to answer, in character):"
            parts.append("%s\n%s" % (header, memories.strip()))
        # History now includes the bot's own past replies (router feeds them back), so the
        # model sees the real back-and-forth and stops re-treading topics it already hit.
        history = ["%s: %s" % (line.speaker, _to_mush_markup(line.text)) for line in turn.context]
        if history:
            parts.append("Recent conversation (oldest first):\n" + "\n".join(history))
        # Chat: call out the latest line so the model engages IT, not the whole transcript.
        if turn.mode != "rp" and turn.text.strip():
            parts.append('%s just said: "%s"' % (turn.speaker, turn.text))
        # RP: call out the most recent beat so he reacts to THIS moment, not a generic rant
        # (the eval's top failure mode was reacting to the wrong beat).
        if turn.mode == "rp" and turn.context and turn.context[-1].text.strip():
            parts.append('The most recent beat to react to:\n"%s"'
                         % _to_mush_markup(turn.context[-1].text.strip()[:300]))
        # RP register/length matching: he defaults to a terse one-line quip regardless of the
        # scene's tone. Measure the OTHERS' recent poses and tell him concretely to match their
        # scale -- expand into prose for a slow descriptive scene, stay snappy for quick banter --
        # while staying unmistakably crass, scheming Cricket.
        if turn.mode == "rp":
            bn = (name or "").strip().lower()
            others = [(l.text or "") for l in turn.context
                      if (l.text or "").strip() and (l.speaker or "").strip().lower() not in (bn, "", "memory")]
            avg = (sum(len(t) for t in others[-4:]) // min(len(others), 4)) if others else 0
            if avg >= 350:
                reg = ("The others are writing LONG, multi-paragraph, descriptive poses. MATCH "
                       "them: 2-3 paragraphs of atmospheric self-describing prose, weighted toward "
                       "action and mood over dialogue -- but unmistakably crass, scheming Cricket.")
            elif avg >= 150:
                reg = ("Match the scene's register: a full paragraph with prose around the line, "
                       "not just a one-line quip.")
            else:
                reg = "The scene is trading quick lines -- stay snappy."
            parts.append("Match the scene's length and register. " + reg)

        if thinking:
            # Hidden planning pass: produce private notes, NOT the reply.
            parts.append(
                "Before replying, privately PLAN %s's response. In 2-4 terse bullet points "
                "note: who he is reacting to, what he knows or feels about them (from the notes "
                "above), and the single sharpest in-character beat to play. Do NOT write the "
                "actual reply -- only the private plan." % name
            )
        else:
            if plan.strip():
                parts.append("Your private plan (use it; do NOT print it):\n%s" % plan.strip())
            if turn.mode == "rp":
                parts.append(
                    "Compose %s's next pose: a specific, in-character reaction to the SINGLE "
                    "most-recent line quoted above -- react to THAT exact beat, not an earlier one "
                    "and not a generic rant. Draw on his history, grudges, and "
                    "the people present where they fit. Write it as a raw SW1 @emit -- "
                    "self-describing third-person prose (e.g. 'The little astromech's dome "
                    "swivels...'); do NOT prefix it with your name or 'Cricket says/poses'. "
                    "His wit lives in his MOUTH: land at least one SPOKEN line (in quotes), crude "
                    "and specific -- never a silent action-only pose. Crass and profane beats "
                    "polished and literary every time. "
                    "Write ONE coherent pose; close every quotation mark you open; it is prose, "
                    "so use NO *asterisks* or stage-directions. For a multi-paragraph pose, "
                    "separate paragraphs with %%r%%r%%t (MUSH newline+indent), exactly as the "
                    "scene above is written." % name
                )
            else:
                parts.append(
                    "Respond as %s to what was JUST said, in character. Engage the latest "
                    "message directly; do not rehash earlier lines or repeat yourself. This is "
                    "spoken on a channel (shown as '%s says, ...'), so give ONLY the words he "
                    "speaks -- no surrounding quotation marks, no *asterisk* actions or "
                    "stage-directions, no name prefix." % (name, name)
                )
        messages.append({"role": "user", "content": "\n\n".join(parts)})
        return messages

    @staticmethod
    def _build_options(inference: dict) -> dict:
        """Map the profile inference block to Ollama options. backend 'cpu' forces all
        layers onto CPU (num_gpu=0); 'gpu' (or unset) lets Ollama use the GPU."""
        options: dict = {}
        for key in _PASSTHROUGH:
            val = inference.get(key)
            if val is not None:
                options[key] = val
        if inference.get("backend") == "cpu":
            options["num_gpu"] = 0
        return options

    async def summarize_scene(self, lines, cast=None) -> str:
        """Summarize a finished RP scene into a short memory note (an LLM call). Used by
        the memory accretion loop; see cricket.persona.base. Returns '' for an empty scene.
        """
        scene = "\n".join(
            "%s: %s" % (getattr(ln, "speaker", "") or "scene", getattr(ln, "text", ""))
            for ln in (lines or [])
        ).strip()
        if not scene:
            return ""
        who = ", ".join(cast) if cast else "unknown"
        doc = self._get_profile() or {}
        inference = doc.get("inference", {}) if isinstance(doc, dict) else {}
        options = self._build_options(inference)
        options["num_predict"] = 160  # a memory note is short
        messages = [
            {
                "role": "system",
                "content": "You write a terse memory note for the astromech droid Cricket. "
                "Factual third person, no roleplay, no shouting.",
            },
            {
                "role": "user",
                "content": "RP scene:\n%s\n\nIn 2-3 sentences, note what Cricket would "
                "remember: who was present (%s), what happened, and any slights or wins."
                % (scene, who),
            },
        ]
        text = await self._client.complete(
            messages, options=options, keep_alive=inference.get("keep_alive")
        )
        return (text or "").strip()

    async def distill_block(self, block, prior_ledger: str = "", bot_name: str = "Cricket") -> dict:
        """Distill ONE completed pose-block. Returns {'ledger': <what happened | his read>,
        'actors': [characters who acted in it, excluding the bot]}. The ledger keeps the scene
        arc grounded as the verbatim tail is byte-trimmed; the actors refine the do-not-puppet
        set (catching NPCs a player puppets that are not in the gazetteer)."""
        text = (getattr(block, "text", "") or "").strip()
        if not text:
            return {"ledger": "", "actors": []}
        speaker = getattr(block, "speaker", "") or "someone"
        doc = self._get_profile() or {}
        inference = doc.get("inference", {}) if isinstance(doc, dict) else {}
        options = self._build_options(inference)
        options["num_predict"] = 140
        options["temperature"] = 0.3  # the ledger is factual, not theatrical
        # The 8B leaks framing ("Scene ledger updated:", "Here is the updated ledger:") as its
        # first line when the word "ledger" is salient in the prompt, so the live note is named
        # NOTE here and the model is told, twice and forcefully, to emit no preamble. The output
        # contract is two labelled lines (NOTE:/ACTORS:) so the parser keys off the labels rather
        # than positional "first non-empty line", which is what let preamble masquerade as content.
        messages = [
            {"role": "system", "content":
                "You maintain a terse private record of an RP scene for the droid %s. "
                "Factual third person; no roleplay, no shouting, no preamble. "
                "You output ONLY the two labelled lines you are asked for and nothing else -- "
                "never a sentence like 'Here is...' or 'Scene ledger updated:' before them." % bot_name},
            {"role": "user", "content":
                "Record so far (for context, do not repeat it):\n%s\n\n"
                "New pose from %s:\n%s\n\n"
                "Output EXACTLY these two lines and NOTHING before or after them -- no greeting, "
                "no 'Here is', no 'Scene ledger updated', no blank framing line:\n"
                "NOTE: <one brief factual sentence of what happened in THIS pose>, then ' | "
                "%s's read: ' then his terse private reaction\n"
                "ACTORS: <comma-separated names of the characters who acted or spoke in this "
                "pose, excluding %s; write 'none' if it is only narration>\n\n"
                "Begin your reply with 'NOTE:' immediately."
                % (prior_ledger or "(start of scene)", speaker, text, bot_name, bot_name)},
        ]
        out = await self._client.complete(
            messages, options=options, keep_alive=inference.get("keep_alive")
        )
        return self._parse_distill(out, bot_name)

    # Preamble/framing the 8B prepends to the ledger line despite instructions. Matched at the
    # start of the note (after label-stripping) and removed defensively, covering the observed
    # leaks ("Scene ledger updated:", "Here is the updated scene ledger:") plus the old format
    # echoes ("Line 1:", "New pose:", "Note:"). A leading table pipe from a markdown-table reflex
    # is dropped first so the rest of the pattern can match what follows it.
    _PREAMBLE_RE = re.compile(
        r"^(?:"
        r"(?:here\s+(?:is|are)|this\s+is)\b[^:]*:"          # "Here is the updated ledger:"
        r"|(?:the\s+)?(?:updated\s+|new\s+|current\s+)?(?:scene\s+)?ledger\b[^:]*:"  # "Scene ledger updated:"
        r"|(?:scene\s+)?(?:record|note|summary|entry|update)\b[^:]*:"
        r"|line\s*1\s*[:.\-]"
        r"|new\s+pose[:.]"
        r"|factual\s+note[:.]"
        r")\s*",
        re.IGNORECASE,
    )

    def _parse_distill(self, out: str, bot_name: str) -> dict:
        """Parse the two-line distillation output into {'ledger', 'actors'}. Defensive against
        the weak 8B: keys ledger/actors off their LABELS (not line position), strips any leaked
        framing preamble, and tolerates a missing NOTE label or a multi-line note."""
        ledger, actors = "", []
        note_lines = []
        seen_actors = False
        for ln in (out or "").splitlines():
            s = ln.strip().lstrip("|").strip()  # drop a leading markdown-table pipe
            if not s:
                continue
            upper = s.upper()
            if upper.startswith("ACTORS:"):
                seen_actors = True
                for a in s.split(":", 1)[1].split(","):
                    a = a.strip().rstrip(".")
                    if a and a.lower() != bot_name.lower() and _looks_like_name(a):
                        actors.append(a)
                continue
            if seen_actors:
                continue  # ignore any trailing chatter after the ACTORS line
            # Strip the NOTE label, then defensively strip any leaked framing preamble.
            s = re.sub(r"^note\s*[:.\-]\s*", "", s, flags=re.IGNORECASE)
            s = self._PREAMBLE_RE.sub("", s).strip()
            if s:
                note_lines.append(" ".join(s.split()))
        ledger = " ".join(note_lines).strip()
        # One more defensive pass: if a preamble survived as its own joined fragment, peel it.
        prev = None
        while ledger and ledger != prev:
            prev = ledger
            ledger = self._PREAMBLE_RE.sub("", ledger).strip()
        return {"ledger": ledger, "actors": actors[:6]}
