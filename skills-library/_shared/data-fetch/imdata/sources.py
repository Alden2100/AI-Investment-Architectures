"""Source registry — provenance + commercial-license tier for every data source.

This makes licensing first-class. Each Avenoth free source is registered here with
its commercial tier, so (a) skill outputs can footnote where a number came from,
and (b) `IM_COMMERCIAL_MODE` can restrict a client-facing run to resellable data.
Nothing is excluded — non-resellable sources stay available for development and are
simply gated.

Tiers:
  public                  government / public-domain; resellable in client work.
  keyless_unofficial      free scrape / unofficial endpoint; dev-only for clients.
  free_key_noncommercial  free key, non-commercial license.
  free_key_eval           free key, eval/dev only; commercial use needs a paid deal.

`status`:  wired (live in imdata today) · building · planned (registered, module
to come) · skip (intentionally not used, e.g. IEX sandbox = fake data).
"""
from __future__ import annotations

from . import config

PUBLIC = "public"
KEYLESS = "keyless_unofficial"
KEY_NC = "free_key_noncommercial"
KEY_EVAL = "free_key_eval"

# key -> {name, module, tier, requires_key, env, attribution, status}
SOURCES: dict = {
    # --- Filings & ownership -------------------------------------------------
    "sec_edgar":       {"name": "SEC EDGAR (submissions/XBRL)", "module": "edgar", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR (public domain)"},
    "edgar_efts":      {"name": "SEC EDGAR full-text search",   "module": "edgar", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "edgar_rss":       {"name": "SEC EDGAR RSS/Atom alerts",    "module": "edgar", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "edgar_8k_ex991":  {"name": "8-K EX-99.1 earnings release", "module": "edgar", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "edgar_bulk":      {"name": "SEC bulk data (num/tag/sub)",  "module": "bulk", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "form4":           {"name": "SEC Form 4 insider (XML)",     "module": "ownership", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "sched_13dg":      {"name": "SEC SC 13D/13G ownership",     "module": "ownership", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "form_13f":        {"name": "SEC Form 13F institutional",   "module": "ownership", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "form_d_s1":       {"name": "SEC Form D / S-1 (private)",   "module": "forms", "tier": PUBLIC, "requires_key": False, "status": "planned", "attribution": "U.S. SEC EDGAR"},

    # --- Market data ---------------------------------------------------------
    "yfinance":        {"name": "yfinance (Yahoo)",   "module": "prices", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Yahoo Finance via yfinance (unofficial)"},
    "stooq":           {"name": "Stooq",              "module": "prices", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Stooq"},
    "polygon":         {"name": "Polygon.io (free)",  "module": "prices", "tier": KEY_EVAL, "requires_key": True, "env": "POLYGON_API_KEY", "status": "wired", "attribution": "Polygon.io"},
    "alpha_vantage":   {"name": "Alpha Vantage",      "module": "prices", "tier": KEY_EVAL, "requires_key": True, "env": "ALPHAVANTAGE_API_KEY", "status": "wired", "attribution": "Alpha Vantage"},
    "iex_sandbox":     {"name": "IEX sandbox",        "module": "prices", "tier": KEY_EVAL, "requires_key": True, "env": "IEX_API_KEY", "status": "skip", "attribution": "IEX Cloud (sandbox = simulated data)"},
    "cboe_vix":        {"name": "CBOE VIX (CSV)",     "module": "volatility", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "Cboe Global Markets"},
    "finra_short":     {"name": "FINRA short interest", "module": "ownership", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "FINRA"},

    # --- Fundamentals & valuation inputs ------------------------------------
    "sec_xbrl":        {"name": "SEC XBRL companyfacts", "module": "edgar", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "damodaran":       {"name": "Damodaran datasets (ERP/beta/WACC)", "module": "valinputs", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "Aswath Damodaran, NYU Stern (pages.stern.nyu.edu)"},
    "segments":        {"name": "Segment KPIs (XBRL dimensional)", "module": "segments", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. SEC EDGAR"},
    "estimates_yf":    {"name": "Consensus estimates (yfinance)", "module": "estimates", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Yahoo Finance via yfinance (unofficial)"},
    "stockanalysis":   {"name": "stockanalysis.com estimates", "module": "estimates", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "stockanalysis.com (unofficial)"},
    "fmp":             {"name": "Financial Modeling Prep",  "module": "fmp", "tier": KEY_EVAL, "requires_key": True, "env": "FMP_API_KEY", "status": "wired", "attribution": "Financial Modeling Prep"},
    "simfin":          {"name": "SimFin standardized stmts", "module": "fmp", "tier": KEY_EVAL, "requires_key": True, "env": "SIMFIN_API_KEY", "status": "wired", "attribution": "SimFin"},
    "finviz":          {"name": "Finviz screener/key stats", "module": "finviz", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Finviz (unofficial)"},
    "macrotrends":     {"name": "Macrotrends long history", "module": "valinputs", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Macrotrends (unofficial)"},
    "openbb":          {"name": "OpenBB SDK",               "module": "openbb", "tier": KEYLESS, "requires_key": False, "status": "planned", "attribution": "OpenBB (provider-dependent)"},

    # --- Macro ---------------------------------------------------------------
    "treasury":        {"name": "US Treasury yield curve",  "module": "macro", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. Department of the Treasury (public domain)"},
    "fred":            {"name": "FRED (St. Louis Fed)",     "module": "macro", "tier": PUBLIC, "requires_key": True, "env": "FRED_API_KEY", "status": "wired", "attribution": "Federal Reserve Bank of St. Louis (FRED); avoid 3rd-party S&P series"},
    "bls":             {"name": "BLS (CPI/PPI/jobs)",       "module": "macro", "tier": PUBLIC, "requires_key": True, "env": "BLS_API_KEY", "status": "wired", "attribution": "U.S. Bureau of Labor Statistics"},
    "world_bank":      {"name": "World Bank",               "module": "macro", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "World Bank Open Data"},
    "ecb":             {"name": "ECB SDW",                  "module": "macro", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "European Central Bank"},
    "cftc_cot":        {"name": "CFTC Commitments of Traders", "module": "macro", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. CFTC"},

    # --- News & alt-data -----------------------------------------------------
    "google_news":     {"name": "Google News RSS",          "module": "news", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Google News (RSS)"},
    "article_bodies":  {"name": "Article bodies (trafilatura)", "module": "articles", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "publisher pages via trafilatura"},
    "newsapi":         {"name": "NewsAPI",                  "module": "news", "tier": KEY_EVAL, "requires_key": True, "env": "NEWSAPI_KEY", "status": "wired", "attribution": "NewsAPI (content copyrighted)"},
    "gnews":           {"name": "GNews",                    "module": "news", "tier": KEY_EVAL, "requires_key": True, "env": "GNEWS_KEY", "status": "wired", "attribution": "GNews"},
    "reddit":          {"name": "Reddit (PRAW)",            "module": "altdata", "tier": KEY_EVAL, "requires_key": True, "env": "REDDIT_CLIENT_ID", "status": "wired", "attribution": "Reddit API"},
    "pytrends":        {"name": "Google Trends (pytrends)", "module": "altdata", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "Google Trends (unofficial)"},
    "twitter_nitter":  {"name": "Twitter/X via Nitter",     "module": "altdata", "tier": KEYLESS, "requires_key": False, "status": "wired", "attribution": "X/Twitter via Nitter (unofficial)"},

    # --- Governance ----------------------------------------------------------
    "ofac_sdn":        {"name": "OFAC SDN list",            "module": "sanctions", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "U.S. Treasury OFAC (public)"},
    "eu_sanctions":    {"name": "EU consolidated sanctions", "module": "sanctions", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "European Union (public)"},
    "un_sanctions":    {"name": "UN Security Council list",  "module": "sanctions", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "United Nations (public)"},
    "uk_sanctions":    {"name": "UK OFSI sanctions",         "module": "sanctions", "tier": PUBLIC, "requires_key": False, "status": "wired", "attribution": "UK OFSI (public)"},
    "opensanctions":   {"name": "OpenSanctions aggregated",  "module": "sanctions", "tier": KEY_NC, "requires_key": True, "env": "OPENSANCTIONS_API_KEY", "status": "wired", "attribution": "OpenSanctions (non-commercial license)"},
}


def get(key: str) -> dict:
    return SOURCES.get(key, {})


def allowed(key_or_tier: str) -> bool:
    """True if a source (by key) or a tier may be used in the current run.
    In IM_COMMERCIAL_MODE only `public`-tier sources are allowed."""
    tier = SOURCES.get(key_or_tier, {}).get("tier", key_or_tier)
    if config.COMMERCIAL_MODE:
        return tier == PUBLIC
    return True


def provenance(key: str, *, figure=None, as_of=None) -> dict:
    """Provenance row a skill can drop into its Report Contract: names the source
    and its license tier so a client deliverable can footnote sourcing."""
    s = SOURCES.get(key, {})
    return {"figure": figure, "source": s.get("name", key),
            "tier": s.get("tier"), "attribution": s.get("attribution"), "as_of": as_of}


def by_tier(tier: str) -> dict:
    return {k: v for k, v in SOURCES.items() if v.get("tier") == tier}


def by_status(status: str) -> dict:
    return {k: v for k, v in SOURCES.items() if v.get("status") == status}
