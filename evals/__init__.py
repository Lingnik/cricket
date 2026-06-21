"""Generation eval harness for the cricket bot.

Feeds Turn-specs (evals/cases/*.json) through a pluggable persona, scores the output
with deterministic gates (scorers.py) and an out-of-band LLM judge (judge.py), and writes
a report. See run.py for the entry point.
"""
