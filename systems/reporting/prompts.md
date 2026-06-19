# reporting — example prompts

Each maps to a run of `orchestrator.py --memo …` or `--letter …`.

## Basic
1. **"Write an IC memo for Microsoft."**
   → `--memo MSFT`. *Gathers DCF + comps + moat + fundamentals, then drafts a
   6-section memo (thesis, business, financials, valuation, risks, recommendation).*
2. **"Draft our Q2 2026 investor letter."**
   → `--letter "Q2 2026" --performance "fund=+4.2%,bench=+2.1%"`. *Produces a
   measured period letter from the supplied performance.*

## Intermediate
3. **"Write the IC memo for Nvidia and make the recommendation explicit."**
   → `--memo NVDA`. *The recommendation section is required; expect a clear
   buy/hold/sell tied to the gathered DCF upside and comps.*
4. **"Investor letter for Q2 with our top holdings and attribution."**
   → `--letter "Q2 2026" --performance "fund=+4.2%,bench=+2.1%" --holdings MSFT=0.20 AAPL=0.15 NVDA=0.10`.
   *Holdings feed positioning/attribution commentary.*

## Advanced
5. **"Run a full valuation on AMD, then turn it into an IC memo I can present."**
   → `systems/valuation` first, then `--memo AMD`. *Chains systems; the memo quotes
   the valuation's range + rationale rather than recomputing.*
6. **"Draft the quarterly letter, keep the tone honest about the drawdown, and log it for compliance."**
   → `--letter "Q2 2026" --performance "fund=-3.1%,bench=-1.0%"`. *Tests the
   drafting step's restraint on a down quarter; the run is auto-logged to the audit
   trail (governance-audit can replay it).*

> Memos/letters are drafted by the model from computed numbers. A Claude key
> produces client-grade prose; keyless, qwen drafts all six memo sections (verified
> by the smoke test) — just less polished.
