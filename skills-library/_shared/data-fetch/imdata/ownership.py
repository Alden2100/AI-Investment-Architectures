"""Ownership & insider signals from SEC EDGAR (public domain, keyless).

- Form 4 insider transactions (officers/directors buying/selling) — the highest-
  signal public ownership data; parsed from the filing's ownership XML.
- SC 13D / 13G beneficial-ownership (>5%) filings — activist / large-holder events.
- Form 13F is filed by MANAGER, not by stock, so a by-stock holder list needs the
  bulk datasets; we expose the recent-filing lister and leave aggregation to bulk.py.
- Short interest reuses the yfinance figure already in `estimates` (FINRA's bi-monthly
  file is the authoritative source; wired as a planned upgrade).

Everything best-effort (returns []/{} on failure), kv-cached (TTL_OWNERSHIP), and
SEC-rate-limited via the shared edgar helpers. Tier: public (resellable).
"""
from __future__ import annotations

from typing import Optional
from xml.etree import ElementTree as ET

from . import config, store, edgar, universe

_XBRL_SUFFIX = ("_htm.xml", "_cal.xml", "_def.xml", "_lab.xml", "_pre.xml", ".xsd")


def _ownership_xml(cik: int, accession: str) -> Optional[str]:
    """Fetch the Form 4 ownership XML body for a filing, or None."""
    idx = edgar._filing_index(cik, accession)
    if not idx:
        return None
    items = (idx.get("directory", {}) or {}).get("item", []) or []
    cands = [it.get("name", "") for it in items
             if it.get("name", "").lower().endswith(".xml")
             and not it.get("name", "").lower().endswith(_XBRL_SUFFIX)]
    # prefer a name that looks like a form-4/ownership doc
    cands.sort(key=lambda n: (0 if ("form4" in n.lower() or "ownership" in n.lower()
                                    or n.lower().startswith(("wf-", "wk-", "doc4"))) else 1, n))
    for name in cands[:3]:
        url = edgar._ARCHIVE.format(cik=cik, acc_nodash=accession.replace("-", ""), doc=name)
        try:
            body = store.cached_get(url, ttl=config.TTL_FILING_TEXT,
                                    headers=edgar._doc_headers(), min_interval=edgar._MIN_INTERVAL)
            if "<ownershipDocument" in body:
                return body
        except Exception:
            continue
    return None


def _f(node, path):
    el = node.find(path)
    return el.text.strip() if el is not None and el.text else None


def _parse_form4(xml: str) -> list:
    """Return a list of transaction dicts from one Form 4 ownership XML."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    owner = _f(root, ".//reportingOwner/reportingOwnerId/rptOwnerName")
    rel = root.find(".//reportingOwner/reportingOwnerRelationship")
    title = None
    if rel is not None:
        if _f(rel, "isDirector") in ("1", "true"):
            title = "Director"
        if _f(rel, "isOfficer") in ("1", "true"):
            title = _f(rel, "officerTitle") or "Officer"
        if _f(rel, "isTenPercentOwner") in ("1", "true"):
            title = (title + " / 10% owner") if title else "10% owner"
    out = []
    for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        date = _f(tx, "transactionDate/value")
        code = _f(tx, "transactionCoding/transactionCode")
        shares = _f(tx, "transactionAmounts/transactionShares/value")
        price = _f(tx, "transactionAmounts/transactionPricePerShare/value")
        ad = _f(tx, "transactionAmounts/transactionAcquiredDisposedCode/value")
        try:
            sh = float(shares) if shares else None
            px = float(price) if price else None
        except ValueError:
            sh = px = None
        out.append({"date": date, "owner": owner, "title": title, "code": code,
                    "acquired_disposed": ad, "shares": sh, "price": px,
                    "value": round(sh * px, 2) if (sh and px) else None})
    return out


def insider_transactions(ticker: str, *, limit: int = 12, force: bool = False) -> list:
    """Recent insider (Form 4) transactions, newest first. Best-effort."""
    key = f"insider:{ticker.upper()}:{limit}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_OWNERSHIP)
        if cached is not None:
            return cached
    out = []
    try:
        info = universe.resolve(ticker)
        rows = edgar.list_filings(ticker, form="4", limit=limit) or []
        for r in rows:
            xml = _ownership_xml(info["cik"], r["accession"])
            if xml:
                for tx in _parse_form4(xml):
                    tx["filing_date"] = r["filing_date"]
                    out.append(tx)
    except Exception:
        out = []
    store.kv_put(key, out)
    return out


def insider_summary(ticker: str, *, force: bool = False) -> dict:
    """Aggregate the recent insider signal: net shares, buy/sell counts, $ flow.
    Open-market codes P (purchase) and S (sale) are the meaningful signal."""
    txns = insider_transactions(ticker, force=force)
    buys = [t for t in txns if t.get("code") == "P"]
    sells = [t for t in txns if t.get("code") == "S"]
    net_val = sum((t.get("value") or 0) for t in buys) - sum((t.get("value") or 0) for t in sells)
    out = {
        "transactions": len(txns),
        "open_market_buys": len(buys), "open_market_sells": len(sells),
        "net_open_market_usd": round(net_val, 2) if (buys or sells) else None,
        "recent": txns[:6],
        "signal": ("net buying" if net_val > 0 else "net selling" if net_val < 0
                   else "balanced/none") if (buys or sells) else "no open-market activity",
    }
    return out


def beneficial_ownership_filings(ticker: str, *, limit: int = 10) -> list:
    """Recent SC 13D / 13G (>5% holder) filings — activist / large-holder events."""
    out = []
    try:
        for form in ("SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"):
            for r in (edgar.list_filings(ticker, form=form, limit=limit) or []):
                r = dict(r)
                out.append({"form": r.get("form"), "date": r.get("filing_date"),
                            "accession": r.get("accession"), "url": r.get("url")})
    except Exception:
        pass
    out.sort(key=lambda x: x.get("date") or "", reverse=True)
    return out[:limit]


def short_interest(ticker: str) -> dict:
    """Short interest. Sourced from yfinance (in `estimates`); FINRA's bi-monthly
    consolidated file is the authoritative upgrade (planned)."""
    try:
        from . import estimates
        own = estimates.get_ownership(ticker)
        sh = (own or {}).get("short") or {}
        return {"pct_of_float": sh.get("pct_of_float"), "short_ratio": sh.get("short_ratio"),
                "shares_short": sh.get("shares_short"), "source": "yfinance"}
    except Exception:
        return {}
