# Postmortem — inverted citation grounding check

## Summary

The Ask/Agent “is this answer grounded?” check looked for the literal string
`[cite:]` (empty citation id). Real model answers emit markers like
`[cite:c12]`. The gate therefore treated **every correctly cited answer as
ungrounded**.

This is a real regression we introduced and fixed in-tree (see git history
around safety hardening / `feat(safety): tighten guards and fix answer-cache
writes`). It is **not** a hypothetical.

## Timeline

1. Early safety helpers added an `output_ok(answer)` structural check intended to
   require citation markers before treating an answer as grounded.
2. The implementation used `if "[cite:]" not in answer`.
3. Downstream Ask (`answer_stream`) and later Agent soft-warnings called
   `output_ok`. Users (and evals using the same citation convention) always
   looked “ungrounded” even when citations were present.
4. Fix: require the prefix `[cite:` instead of the empty-id form `[cite:]`.
5. Regression tests + offline eval gates now pin both “bare answer fails” and
   “`[cite:c12]` passes.”

## Root cause

A one-character / empty-id mistake: the sentinel string described the *template*
`[cite:ID]` incorrectly. Code searched for a marker that production answers
never produce.

```python
# Broken (conceptual)
if "[cite:]" not in answer:   # never true for [cite:c12]
    return False, "ungrounded"

# Fixed (current)
if "[cite:" not in answer:
    return False, "Answer was not grounded in sources."
```

Current code: `backend/app/safety/guards.py` → `output_ok`.

## Impact

- Soft grounding notes / ungrounded warnings fired incorrectly on good answers.
- Any automation or eval that reused `output_ok` inherited the inverted signal.
- Trust in the “citation-grounded” product claim was undermined until fixed —
  exactly the kind of silent logic bug that looks fine in a demo (“there are
  cites in the text!”) while the machine check disagrees.

## Detection

Caught during an independent review pass of the safety layer (author vs
reviewer mindset), not by eyeballing UI. The mismatch between prompt
instructions (`[cite:cN]`) and the checker string is obvious once you read both
side-by-side.

## Fix and verification

- Changed the membership test to `[cite:`.
- Unit test: `tests/test_guards.py::test_output_ok_requires_cite_marker`.
- Offline gates: `output_ok_requires_cite`, `output_ok_rejects_bare` in
  `app/evals/offline.py` (part of the 24-gate PR suite).

```bash
cd backend && pytest -q tests/test_guards.py
python -m app.evals.run --offline-only
```

## Lesson

Assert on **structural invariants the product actually emits**, not on a
plausible-looking substring. Pair every safety helper with a golden string that
matches prompt/output format. Prefer independent review that assumes the
implementation is wrong — this bug survived “the code looks clean.”

## Related (not this incident)

Other real fixes with tests (see eval report): buyback ≠ advice HITL; benign
“you are now” research queries must not trip `input_ok`; Ask `prior_turns`
signature mismatch; answer-cache `INSERT` column list. Those are separate
postmortems if needed.

We **do not** claim a “table overlap chunker” production incident here: the
chunker is designed so tables are atomic and overlap carry applies only to
**text** blocks (`backend/app/ingest/chunker.py`), but that design was not
documented as a found-and-fixed CI failure in this repo’s history.
