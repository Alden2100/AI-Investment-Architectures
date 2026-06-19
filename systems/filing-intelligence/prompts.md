# filing-intelligence — example prompts

Each maps to a run of `orchestrator.py --ticker … --form …`.

## Basic
1. **"Give me the brief on Coca-Cola's latest 10-K."**
   → `--ticker KO --form 10-K`. *A single name + form is all the system needs;
   expect What-changed / Why-it-matters / What-to-watch with quoted figures.*
2. **"What changed in Microsoft's most recent 10-Q?"**
   → `--ticker MSFT --form 10-Q`. *Routes straight to the change-detector lens;
   expect new/removed risk factors and guidance deltas.*

## Intermediate
3. **"Read Apple's new 10-K and flag any new risk factors or changed guidance vs last year."**
   → `--ticker AAPL --form 10-K`. *The diff lens surfaces exactly these; the Brief
   ranks them by significance and ignores boilerplate.*
4. **"Summarize Nvidia's latest annual filing and tell me what it means for the moat."**
   → `--ticker NVDA --form 10-K`. *Combines the filing summary with the
   margin-backed moat read; expect a competitive-position paragraph.*

## Advanced
5. **"Analyze Tesla's latest 10-K: what materially changed, what it signals about the business, and the three things I should monitor next quarter."**
   → `--ticker TSLA --form 10-K`. *Pushes the synthesis step to prioritize — the
   model must weigh diff blocks against margins + news and produce a focused watch
   list, not a dump.*
6. **"Brief me on this 8-K and whether it's a catalyst worth acting on."**
   → `--ticker <T> --form 8-K`. *8-Ks are event filings; the Brief plus the
   catalyst lens (via news) tells you if it's actionable. Expect a clear
   act/ignore lean.*

> The model interprets; the numbers (diff counts, margins) are always computed and
> quoted. With `ANTHROPIC_API_KEY` set, the Brief prose is noticeably sharper.
