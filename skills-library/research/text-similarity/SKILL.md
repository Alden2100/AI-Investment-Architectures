---
name: text-similarity
version: 1.0.0
description: Scores how closely each surviving company's business description matches an
  investment mandate and a set of seed (exemplar) companies, using a hand-rolled TF-IDF
  cosine over numpy — fully deterministic, no model calls, no network. Use when someone
  wants to rank or filter candidates by textual/business similarity to a thesis or to
  known comparables, "which of these look like the seed names", "score survivors against
  the mandate text", or Stage 3 of the idea-sourcing v2 funnel.
---
# Text Similarity (TF-IDF cosine)

Computes everything deterministically in Python — there is no model judgment step. Given
business descriptions already fetched upstream, it builds a TF-IDF vector space, then scores
each survivor by cosine similarity to (a) the mandate text and (b) the seed companies, and
blends the two into a single `text_score`. Identical inputs always produce identical output.

This skill does NOT fetch any data: descriptions are supplied by the caller (Stage 2 output).
It imports `numpy` only — no sklearn, no scipy, no Ollama, no `imrouter`.

## How it scores
- Tokenize: lowercase, split on non-alphanumeric, keep alphanumeric tokens of length >= 3,
  drop a small inline English stoplist.
- Fit vocab + IDF on the COMPANY corpus only (survivors u seed_companies descriptions — NOT
  the mandate). `min_df=2`, `max_features=20000` (most-frequent-by-document-frequency).
  `idf(t) = log(N / (1 + df(t))) + 1`, N = number of company docs.
- Vectorize mandate / each seed / each survivor in that fitted space: `tf = 1 + log(count)`
  for present terms, component = `tf * idf`, then L2-normalize. All-zero vectors stay zero.
- `sim_mandate = cosine(survivor, mandate)`; `sim_seeds = mean cosine(survivor, each seed)`
  (None when there are no seeds).
- Blend: with seeds `text_score = w_seed*sim_seeds + w_mandate*sim_mandate`; without seeds
  `text_score = sim_mandate`. All cosines and scores are asserted to land in [0, 1].

## Run
```
# Stage-2 artifact with everything in one file:
python run.py --file stage2.json
#   stage2.json = {"mandate_text": "...", "seed_companies": [{ticker,description}...],
#                  "survivors": [{ticker,description}...]}

# Or split inputs:
python run.py --mandate-text "..." --survivors-file survivors.json [--seeds-file seeds.json]

# Optional blend weights (defaults 0.6 / 0.4):
python run.py --file stage2.json --w-seed 0.6 --w-mandate 0.4
```

## Inputs
- `mandate_text` (str, required, non-empty — empty raises a clear error).
- `seed_companies`: list of `{ticker, description}` (may be empty).
- `survivors`: list of `{ticker, description}` (`description` already fetched upstream).

## Output (JSON)
`{ version, results: [{ticker, text_score, sim_mandate, sim_seeds (null if no seeds),
missing_description}], summary, params }`. A survivor with an empty/missing description gets
`text_score = 0.0` and `missing_description = true` (flagged, never silent).

## Dependencies
numpy only.

## Documented decision — IDF fit scope
IDF is fit on the in-run survivor + seed set, so `text_score` values are **comparable WITHIN a
single run but not across runs** with different survivor sets (the vocabulary and IDF weights
shift). The principled TNIC-style version fits IDF on a fixed broad universe so scores are
stable across runs; that is the upgrade path. We ship the in-run version for v1 because it is
self-contained, needs no universe snapshot, and is sufficient for ranking within one screen.

## Deferred upgrades (do NOT build now)
Both are gated on observing Stage 3 actually send the wrong companies into Stage 4:
- (a) BM25 for the mandate-query direction (length-normalized term saturation instead of raw
  TF-IDF cosine for the short mandate query).
- (b) Local Ollama embeddings for semantic (non-lexical) similarity.
Build either only after a concrete miss is observed downstream.
