"""Business-segment & geographic KPIs from SEC XBRL (public domain, keyless).

companyfacts only returns CONSOLIDATED values — segment breakdowns live in the
filing's XBRL INSTANCE as facts reported in dimensional contexts (an explicitMember
on the business-segment or geography axis). This parses the latest 10-K's instance
for those dimensional revenue facts, giving revenue-by-segment for moat / sum-of-parts
work. Best-effort: returns [] on any failure; kv-cached. Tier: public.
"""
from __future__ import annotations

from typing import Optional
from xml.etree import ElementTree as ET

from . import config, store, edgar, universe

_BIZ_AXES = ("StatementBusinessSegmentsAxis", "SubsegmentsAxis")
_PROD_AXES = ("ProductOrServiceAxis",)
_GEO_AXES = ("StatementGeographicalAxis",)
_REV_TAGS = ("RevenueFromContractWithCustomerExcludingAssessedTax",
             "RevenueFromContractWithCustomerIncludingAssessedTax",
             "Revenues", "SalesRevenueNet")
# Linkbases/schemas to skip. The inline-XBRL instance is the `*_htm.xml` file, so it
# is NOT skipped (modern filings embed the data there).
_XBRL_SKIP = ("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml", ".xsd")


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _instance_doc(cik: int, accession: str) -> Optional[str]:
    """The XBRL instance document body for a filing (the data .xml, not the linkbases)."""
    idx = edgar._filing_index(cik, accession)
    if not idx:
        return None
    items = (idx.get("directory", {}) or {}).get("item", []) or []
    names = [it.get("name", "") for it in items
             if it.get("name", "").lower().endswith(".xml")
             and not it.get("name", "").lower().endswith(_XBRL_SKIP)
             and "filingsummary" not in it.get("name", "").lower()]
    # the data instance is the inline-XBRL doc (<ticker>-<date>_htm.xml) on modern
    # filings, or a classic <ticker>-<date>.xml on older ones.
    names.sort(key=lambda n: (0 if n.lower().endswith("_htm.xml") else 1, -len(n)))
    for name in names[:3]:
        url = edgar._ARCHIVE.format(cik=cik, acc_nodash=accession.replace("-", ""), doc=name)
        try:
            body = store.cached_get(url, ttl=config.TTL_FILING_TEXT,
                                    headers=edgar._doc_headers(), min_interval=edgar._MIN_INTERVAL)
            if "context" in body[:30000] or "xbrl" in body[:5000].lower():
                return body
        except Exception:
            continue
    return None


def _parse_segments(xml: str, axes) -> list:
    """Extract [{member, value, period_end}] for revenue facts on the given axes."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    # contexts: id -> (member_label, period_end) when a single explicit member on `axes`
    ctx = {}
    for c in root.iter():
        if _local(c.tag) != "context":
            continue
        cid = c.get("id")
        member = None
        period_end = None
        multi = 0
        for sub in c.iter():
            lt = _local(sub.tag)
            if lt == "explicitMember":
                multi += 1
                dim = sub.get("dimension", "")
                if any(ax in dim for ax in axes) and sub.text:
                    member = sub.text.split(":")[-1].replace("Member", "")
            elif lt == "endDate" or lt == "instant":
                period_end = (sub.text or "").strip()
        # only single-dimension contexts (clean segment slices)
        if member and multi == 1:
            ctx[cid] = (member, period_end)
    if not ctx:
        return []
    out = {}
    for f in root.iter():
        lt = _local(f.tag)
        if lt == "nonFraction":                       # inline XBRL fact
            nm = (f.get("name") or "").split(":")[-1]
        elif lt in _REV_TAGS:                          # classic instance fact
            nm = lt
        else:
            continue
        cref = f.get("contextRef")
        if nm not in _REV_TAGS or cref not in ctx or not (f.text and f.text.strip()):
            continue
        member, pend = ctx[cref]
        try:
            val = float(f.text.strip().replace(",", ""))
        except ValueError:
            continue
        scale = f.get("scale")                         # iXBRL decimal scaling
        if scale:
            try:
                val *= 10 ** int(scale)
            except ValueError:
                pass
        if f.get("sign") == "-":
            val = -val
        # keep the largest (most recent FY) period per member
        prev = out.get(member)
        if prev is None or (pend or "") >= prev[1]:
            out[member] = (val, pend or "")
    rows = [{"member": _humanize(m), "value": v, "period_end": p} for m, (v, p) in out.items()]
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows


def _humanize(member: str) -> str:
    import re
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", member).strip()


def segments(ticker: str, *, force: bool = False) -> dict:
    """Revenue by business segment and by geography from the latest 10-K. Best-effort."""
    key = f"segments:{ticker.upper()}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_DAMODARAN)  # filings annual; long TTL
        if cached is not None:
            return cached
    out = {"business": [], "product": [], "geographic": []}
    try:
        info = universe.resolve(ticker)
        row = edgar.latest_filing(ticker, "10-K")
        if row:
            xml = _instance_doc(info["cik"], row["accession"])
            if xml:
                out["business"] = _parse_segments(xml, _BIZ_AXES)
                out["product"] = _parse_segments(xml, _PROD_AXES)
                out["geographic"] = _parse_segments(xml, _GEO_AXES)
                out["filing_date"] = row["filing_date"]
    except Exception:
        pass
    store.kv_put(key, out)
    return out
