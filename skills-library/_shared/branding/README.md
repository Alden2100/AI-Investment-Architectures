# branding (`imbrand`) — Avenoth Advisory PDF theme

Produces clean, concise, **slide-deck-ready** PDFs from any system's output, in the
Avenoth Advisory brand. Used **only when the user explicitly asks for a PDF** in the
prompt (the front door, `ask.py`, decides) — default output stays plain text.

## Brand fidelity
- **Colors** load from the vendored [`colors.json`](colors.json) (the brand's single
  source of truth): navy `#0E2841` dominant, steel `#2E5B8A` support, azure `#4E95D9`
  accent (~10%, the header rule), muted semantic colors for data
  (positive `#2F8F6B` · negative `#C24A3A` · caution `#C99A3C`).
- **60/30/10 weighting**, dark header band + light content, **one accent moment**.
- **Type**: Times (≈ Georgia) serif headers, Helvetica (≈ Arial) body — reportlab
  built-ins, so it renders identically everywhere with no font substitution.

## Layout
Navy header band with the **AVENOTH ADVISORY** wordmark + section tag and an azure
accent rule; a serif title + steel subtitle; organized sections with branded tables
(navy header rows, alternating fills, mist rules); a filled status pill for the
headline call (BUY/SELL, RED/GREEN); a slate footer (Confidential · generated date ·
page). Concise by design — typically one page.

## Use
```python
from imbrand import build_report
build_report("valuation", result_dict, "out.pdf")   # -> branded PDF
```
Per-system layouts exist for all five full systems; scaffolds use a generic layout.
Engine: `imbrand/pdf.py` (reportlab); palette: `imbrand/colors.py`.

> Vendored copy of the brand tokens; the upstream source of truth is the
> `avenoth-brand` repo. Update `colors.json` here to re-sync.
