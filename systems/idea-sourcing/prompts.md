# idea-sourcing — example prompts

Prompts you'd give Claude (the orchestrating agent) in chat; each maps to a run of
`orchestrator.py`. Tiered by sophistication.

## Basic
1. **"Find me a few large-cap software names worth a look."**
   → `--sic-contains 7372 --min-mcap 1e10`. *Effective because it gives the screener
   a concrete SIC + size band; expect a 5–6 name shortlist with one-line theses.*
2. **"Compare MSFT, AAPL and NVDA as ideas right now."**
   → `--ticker-in MSFT AAPL NVDA`. *Bounds the universe to 3 names so every lens
   (DCF, comps, catalysts) runs on each; expect a ranked head-to-head.*

## Intermediate
3. **"Screen mid-cap semiconductors ($2–20B) and rank the top 6 by valuation upside and catalysts."**
   → `--sic-contains 3674 --min-mcap 2e9 --max-mcap 2e10 --max-candidates 6`.
   *Combines a size band with the SIC; the ranking weighs DCF upside + catalyst
   strength. Expect cheap names with live catalysts at the top.*
4. **"Build a watchlist of names with positive DCF upside and recent 8-K catalysts."**
   → run a broad screen, then read the shortlist's `dcf_upside` + `catalyst_signals`.
   *Shows the dossier's enrichment; verdicts (`pursue/watch/pass`) become the watchlist.*

## Advanced
5. **"Give me a contrarian shortlist: out-of-favor industrials that screen cheap on comps but still have a catalyst — explain why each could re-rate."**
   → `--sic-contains 35 --max-candidates 8`, then have the agent reason over
   `comps_median` vs each name + `top_headlines`. *Exercises the full dossier and
   the synthesis step's judgment; expect a thesis tying cheapness to a specific
   re-rating trigger per name.*
6. **"Source ideas in cloud software, then for the top pick hand off to the valuation system for a full range."**
   → idea-sourcing first, then feed the winner to `systems/valuation`. *Demonstrates
   chaining systems — sourcing's output is valuation's input.*

> Tip: keep `--max-candidates` small (≤6) for fast, deep runs; raise it for breadth
> at the cost of speed (every candidate triggers live fetches).
