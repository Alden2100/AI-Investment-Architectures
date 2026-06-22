"""Macro data — risk-free rate (US Treasury, public/keyless) and FRED series (keyed).

The US Treasury daily par-yield curve is public-domain and keyless; it gives the
official risk-free rate the DCF needs (no more hardcoded constant). FRED needs a
free key (FRED_API_KEY) and serves the broader macro backbone (CPI, spreads, etc.);
without a key, risk_free_rate() still works off Treasury.

Best-effort: every accessor returns None on any failure (network, schema drift) so a
skill degrades to a sensible default rather than crashing. Cached via the kv store
(TTL_MACRO). Rate limits: Treasury is a static daily file; FRED is very generous.
"""
from __future__ import annotations

import time
from typing import Optional
from xml.etree import ElementTree as ET

from . import config, store

_TREASURY = ("https://home.treasury.gov/resource-center/data-chart-center/"
             "interest-rates/pages/xml?data=daily_treasury_yield_curve"
             "&field_tdr_date_value_month={ym}")
_TENORS = {"1m": "BC_1MONTH", "3m": "BC_3MONTH", "6m": "BC_6MONTH", "1y": "BC_1YEAR",
           "2y": "BC_2YEAR", "5y": "BC_5YEAR", "7y": "BC_7YEAR", "10y": "BC_10YEAR",
           "20y": "BC_20YEAR", "30y": "BC_30YEAR"}
_NS = {"d": "http://schemas.microsoft.com/ado/2007/08/dataservices",
       "a": "http://www.w3.org/2005/Atom"}


def _parse_treasury(xml: str, field: str):
    """Return (latest_value_pct, date_str) for `field` from a Treasury Atom feed."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None, None
    best_val, best_date = None, None
    for props in root.iter():
        if not props.tag.endswith("}properties"):
            continue
        date = None
        val = None
        for ch in props:
            tag = ch.tag.split("}")[-1]
            if tag == "NEW_DATE":
                date = (ch.text or "")[:10]
            elif tag == field and ch.text:
                try:
                    val = float(ch.text)
                except ValueError:
                    val = None
        if val is not None and date and (best_date is None or date > best_date):
            best_val, best_date = val, date
    return best_val, best_date


def risk_free_rate(tenor: str = "10y", *, force: bool = False) -> Optional[float]:
    """Latest US Treasury par yield for `tenor`, as a DECIMAL (e.g. 0.0425). Keyless,
    public-domain. Returns None if the feed can't be reached (caller falls back)."""
    field = _TENORS.get(tenor.lower(), "BC_10YEAR")
    key = f"treasury:{field}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_MACRO)
        if cached is not None:
            return cached.get("rate")
    val, asof = None, None
    now = time.gmtime()
    for back in range(0, 3):  # current month, then fall back if not yet published
        y, mo = now.tm_year, now.tm_mon - back
        while mo <= 0:
            y -= 1; mo += 12
        try:
            body = store.cached_get(_TREASURY.format(ym=f"{y}{mo:02d}"),
                                    ttl=config.TTL_MACRO,
                                    headers={"User-Agent": config.SEC_USER_AGENT},
                                    timeout=30, force=force)
            v, d = _parse_treasury(body, field)
            if v is not None:
                val, asof = v, d
                break
        except Exception:
            continue
    rate = round(val / 100.0, 5) if isinstance(val, (int, float)) else None
    store.kv_put(key, {"rate": rate, "as_of": asof, "source": "treasury"})
    return rate


def fred_series(series_id: str, *, force: bool = False) -> Optional[dict]:
    """Latest observation for a FRED series, or None. Needs FRED_API_KEY (the keyed
    branch); without it, returns None. Use government-published series only."""
    import os
    api = os.environ.get("FRED_API_KEY")
    if not api:                       # FRED is public-tier; just needs a free key
        return None
    key = f"fred:{series_id}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_MACRO)
        if cached is not None:
            return cached
    url = (f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}"
           f"&api_key={api}&file_type=json&sort_order=desc&limit=1")
    out = None
    try:
        data = store.cached_get_json(url, ttl=config.TTL_MACRO, timeout=30, force=force)
        obs = (data.get("observations") or [])
        if obs:
            v = obs[0].get("value")
            out = {"series": series_id, "value": float(v) if v not in (".", None) else None,
                   "as_of": obs[0].get("date"), "source": "fred"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out


def world_bank(indicator: str = "NY.GDP.MKTP.KD.ZG", country: str = "US",
               *, force: bool = False) -> Optional[dict]:
    """Latest World Bank indicator (keyless, public). Default = real GDP growth %."""
    key = f"wb:{country}:{indicator}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_MACRO)
        if cached is not None:
            return cached
    out = None
    try:
        url = (f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
               "?format=json&mrv=1")
        data = store.cached_get_json(url, ttl=config.TTL_MACRO, timeout=30, force=force)
        recs = data[1] if isinstance(data, list) and len(data) > 1 else []
        if recs:
            out = {"indicator": indicator, "country": country,
                   "value": recs[0].get("value"), "as_of": recs[0].get("date"),
                   "source": "world_bank"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out


def cot_positioning(market: str = "S&P 500", *, force: bool = False) -> Optional[dict]:
    """CFTC Commitments of Traders — non-commercial (speculative) net positioning for a
    financial futures market (crowding signal). Keyless, public. Best-effort."""
    key = f"cot:{market.lower()}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_MACRO)
        if cached is not None:
            return cached
    out = None
    try:
        import csv
        import io
        body = store.cached_get("https://www.cftc.gov/dea/newcot/FinFutWk.txt",
                                ttl=config.TTL_MACRO,
                                headers={"User-Agent": config.SEC_USER_AGENT}, timeout=60, force=force)
        m = market.lower()
        for r in csv.reader(io.StringIO(body)):
            if r and m in (r[0] or "").lower():
                def _i(x):
                    try:
                        return int(float(x))
                    except (ValueError, TypeError):
                        return None
                # Financial COT layout: noncommercial long/short are cols 8/9
                nlong, nshort = (_i(r[8]) if len(r) > 8 else None,
                                 _i(r[9]) if len(r) > 9 else None)
                net = (nlong - nshort) if (nlong is not None and nshort is not None) else None
                out = {"market": r[0].strip(), "noncommercial_long": nlong,
                       "noncommercial_short": nshort, "noncommercial_net": net,
                       "source": "cftc_cot"}
                break
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out


def bls_series(series_id: str = "CUUR0000SA0", *, force: bool = False) -> Optional[dict]:
    """Latest BLS observation (default = CPI-U, all items) + YoY. Public; the keyless
    v1 endpoint works (low daily limit), BLS_API_KEY raises the limit via v2."""
    import os
    key = f"bls:{series_id}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_MACRO)
        if cached is not None:
            return cached or None
    out = None
    api = os.environ.get("BLS_API_KEY")
    ver = "v2" if api else "v1"
    url = f"https://api.bls.gov/publicAPI/{ver}/timeseries/data/{series_id}"
    if api:
        url += f"?registrationkey={api}"
    try:
        data = store.cached_get_json(url, ttl=config.TTL_MACRO,
                                     headers={"User-Agent": config.SEC_USER_AGENT}, timeout=30, force=force)
        ser = (data.get("Results", {}).get("series") or [])
        pts = ser[0].get("data") if ser else []
        if pts:
            latest = pts[0]
            yago = next((p for p in pts if p.get("year") == str(int(latest["year"]) - 1)
                         and p.get("period") == latest.get("period")), None)
            v = float(latest["value"])
            yoy = round((v / float(yago["value"]) - 1) * 100, 2) if yago and float(yago["value"]) else None
            out = {"series": series_id, "value": v, "yoy_pct": yoy,
                   "period": f"{latest.get('periodName')} {latest.get('year')}", "source": "bls"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out


def ecb_series(flow: str = "FM", series_key: str = "B.U2.EUR.4F.KR.MRR_FR.LEV",
               *, force: bool = False) -> Optional[dict]:
    """Latest ECB SDW observation (default = main refinancing rate). Keyless, public.
    CSV format is parsed for robustness."""
    import csv
    import io
    key = f"ecb:{flow}:{series_key}"
    if not force:
        cached = store.kv_get(key, ttl=config.TTL_MACRO)
        if cached is not None:
            return cached or None
    out = None
    try:
        url = (f"https://data-api.ecb.europa.eu/service/data/{flow}/{series_key}"
               "?lastNObservations=1&format=csvdata")
        body = store.cached_get(url, ttl=config.TTL_MACRO,
                                headers={"User-Agent": config.SEC_USER_AGENT}, timeout=30, force=force)
        rows = list(csv.DictReader(io.StringIO(body)))
        if rows:
            r = rows[-1]
            val = r.get("OBS_VALUE")
            out = {"series": series_key, "value": float(val) if val else None,
                   "as_of": r.get("TIME_PERIOD"), "source": "ecb"}
    except Exception:
        out = None
    store.kv_put(key, out or {})
    return out


def snapshot(*, force: bool = False) -> dict:
    """Compact macro backdrop for portfolio/reporting overlays. Best-effort."""
    out = {"risk_free_10y": risk_free_rate("10y", force=force),
           "risk_free_3m": risk_free_rate("3m", force=force)}
    rf10, rf3 = out["risk_free_10y"], out["risk_free_3m"]
    if isinstance(rf10, (int, float)) and isinstance(rf3, (int, float)):
        out["yield_curve_10y_3m"] = round(rf10 - rf3, 5)  # <0 = inverted
    return {k: v for k, v in out.items() if v is not None}
