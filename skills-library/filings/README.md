# filings drawer

Reading SEC disclosures: retrieval, summarization, and year-over-year change.

| Skill | Kind | Does |
|---|---|---|
| filing-fetcher | deterministic | Fetch a filing (10-K/10-Q/8-K) or its full text from EDGAR. |
| filing-summarizer | hybrid | Structured key takeaways from a 10-K/10-Q. |
| filing-change-detector | hybrid | Material changes between two filings of the same type. |
| earnings-call-summarizer | hybrid | Guidance / highlights / surprises from a release or transcript. |

Each skill is documented by its own `SKILL.md`.
