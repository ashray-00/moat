# Eval report

This page documents what Moat’s eval layer **actually** measures. It does not
invent live accuracy scores. When you run live evals, paste the JSON output and
commit SHA here so the report stays honest.

## Sets

| Set | Source | Size | What “pass” means |
|-----|--------|------|-------------------|
| **Offline gates** | Fixed strings in `app/evals/offline.py` + gold schema | **27+** cases | Every gate `ok`; `offline_pass_rate == 1.0` |
| **Factual (live)** | Auto from `facts` ⨝ `companies` where tag `LIKE '%Revenue%'` | **N = DB rows**; CLI/CI samples **40** | `numerical_match` **and** `citation_grounded` |
| **Qualitative (live)** | Hand-written in `app/evals/dataset.py` | **2** | Top-5 retrieve includes required `section` substring |
| **Recall@5 (live)** | `app/evals/gold_retrieval.json` | **10** | Gold `must_contain` in top-5 text or section; floor **0.70** |

Qualitative cases today:

1. AAPL supply-chain risks → section must mention **Risk Factors**
2. NVDA data-center segment → section must mention **Business**

## Metric definitions

### `numerical_match` (`app/evals/scorer.py`)

- Parses `$383.29B`-style magnitudes (requires a **leading digit** — see comma-matching note in scorer docstring).
- Pass if any parsed number is within **relative tolerance 0.01** (1%) of XBRL `expected_number`.

### `citation_grounded`

- Extract `[cite:ID]` markers from the answer.
- **Zero citations → fail** (ungrounded).
- Pass only if every cited ID is in the set of retrieved source ids for that turn.

### Offline suites (also pinned in pytest)

- Advice HITL phrases (`is_advice_like`) — including **no false positive on “buyback”**.
- Injection / delimiter sanitize on retrieved text.
- `input_ok` rejects jailbreak-like queries; allows benign research phrasing
  (“You are now looking at…”).
- Usage helper token merge for cost logging.

## CI behavior

| Workflow | Trigger | Gate |
|----------|---------|------|
| `unit-tests` | Every PR + push to `main`/`master` | `pytest` + `python -m app.evals.run --offline-only` |
| `eval-gate` offline | PR (backend paths) + dispatch | Same offline CLI |
| `eval-gate` live | **`workflow_dispatch` only** | `run_evals --sample=40`; needs seeded DB + API keys |

**Floors** (`app/evals/run.py`):

| Metric | Floor |
|--------|------:|
| `offline_pass_rate` | **1.0** |
| `factual_accuracy` (live) | **0.70** |
| `qualitative_accuracy` (live) | **1.0** |
| `recall_at_5` (live) | **0.70** |

Live evals are intentional opt-in so PRs do not burn provider spend.

## Current offline scores (reproducible)

Captured locally while writing this doc:

```bash
cd backend && python -m app.evals.run --offline-only
```

Expect `offline_pass_rate: 1.0` with gold-retrieval schema gates included
(`offline_n` ≥ 27). Replace this block after each meaningful eval change.

**Live factual/qualitative scores:** not checked into the repo. Run:

```bash
cd backend && python -m app.evals.run --sample=40
```

Then record `factual_accuracy`, `factual_n`, `qualitative_accuracy`, date, and
git SHA in a new subsection below.

### Live run log (fill when you have a seeded DB)

| Date | SHA | factual_n | factual_accuracy | qualitative_n | qualitative_accuracy |
|------|-----|----------:|-----------------:|--------------:|---------------------:|
| — | — | — | — | 2 | — |

## How changes moved the *offline* gate

We do not have a historical live accuracy table. We do have regression-hardening
that the offline suite now pins:

| Change | Effect on eval / safety layer |
|--------|-------------------------------|
| `output_ok` looked for `[cite:]` (empty id) | **Every** real `[cite:c12]` answer failed grounding → fixed to `[cite:` prefix; offline `output_ok_*` gates |
| Advice phrases included `"this is a buy"` | Matched **buyback** → HITL false positives; removed; gate `advice_not_buyback_false_positive` |
| Input pattern bare `you are now` | Blocked research phrasing → tightened for `input_ok`; gate `input_ok_allows_benign_you_are_now` |
| Usage helpers extracted from LiteLLM module | Offline cost/token gates can run without importing the full client |

That is the proof the eval layer is **structural and gated**, not decorative:
break a pin, PR fails before anyone pays for a live Ask run.
