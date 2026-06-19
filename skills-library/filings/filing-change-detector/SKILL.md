---
name: filing-change-detector
version: 1.0.0
description: Find the material changes between two filings of the same type (e.g. this
  year's 10-K vs last year's, or two 10-Qs). Use whenever someone wants to know what
  changed in a filing, compare filings across periods, spot new or removed risk
  factors, or track year-over-year disclosure changes — even "what's different in the
  new 10-K".
---
# Filing Change Detector

Hybrid skill. `run.py` does a **deterministic** paragraph-level diff (difflib)
between two same-type filings and surfaces the substantive added/removed/changed
blocks (filtering boilerplate). The model then labels each block's section and
significance.

## Hybrid model skill
If the output contains `_needs_model: true`, the calling agent must read `prompt`
and return JSON matching `schema` (the diff blocks are in the prompt). With
`ANTHROPIC_API_KEY` set, run.py fills it automatically. The deterministic diff
(`diff_blocks`, `raw_change_count`) is always present regardless.

## Run
```
python run.py --ticker MSFT --form 10-K            # latest two 10-Ks
python run.py --ticker AAPL --form 10-Q
python run.py --ticker MSFT --accession-new <accn> --accession-old <accn>
```

Flags: `--ticker` (required), `--form` (default 10-K), `--accession-new`/
`--accession-old` (override which two filings), `--max-blocks` (default 25).

## Output (JSON)
`{ ticker, form, new:{accession,date}, old:{accession,date}, raw_change_count,
diff_blocks:[{type,old,new}], changes:[{section,old,new,significance}], summary }`
