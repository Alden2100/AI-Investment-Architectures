# valuation — example prompts

Each maps to a run of `orchestrator.py --ticker … --peers …`.

## Basic
1. **"What's Microsoft worth?"**
   → `--ticker MSFT --peers AAPL GOOGL`. *Returns a DCF intrinsic, comps-implied,
   and bull/base/bear range plus a buy/hold/sell lean vs the current price.*
2. **"Give me a fair-value range for Nvidia."**
   → `--ticker NVDA --peers AMD AVGO`. *Expect low/base/high bracketing the three
   methods, not a single point estimate.*

## Intermediate
3. **"Value AMD against AVGO and INTC, assuming 12% growth and a 10% discount rate."**
   → `--ticker AMD --peers AVGO INTC --growth 0.12 --discount-rate 0.10`.
   *Custom DCF assumptions flow into both the base DCF and the scenario spread.*
4. **"Is Apple cheap or expensive relative to its peers and its own DCF?"**
   → `--ticker AAPL --peers MSFT GOOGL META`. *The reconciliation explicitly compares
   comps-implied vs DCF vs price — expect a cheap/expensive verdict with reasons.*

## Advanced
5. **"Stress-test Tesla's valuation: where do the DCF, comps, and bear case disagree, and what assumption drives the gap?"**
   → `--ticker TSLA --peers GM F`. *Pushes the reasoning step to explain divergence,
   not just average it — expect the model to name the swing assumption (growth or
   WACC) from the scenario spread.*
6. **"Value Meta and frame a recommendation I could drop straight into an IC memo."**
   → `--ticker META --peers GOOGL SNAP`, then hand the output to `systems/reporting`.
   *Chains valuation → reporting; the value_range + rationale become memo inputs.*

> Every figure is computed; the model's job is to triangulate and justify. With a
> Claude key the rationale is more rigorous; keyless, qwen still produces a sane
> range.
