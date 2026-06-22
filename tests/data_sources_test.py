#!/usr/bin/env python3
"""Smoke test for the broadened data layer: source registry, commercial gating,
macro risk-free (US Treasury, keyless), and Damodaran valuation inputs.

Run: ./.venv/bin/python tests/data_sources_test.py
Keyless. Network-dependent fetches are asserted leniently (None is acceptable on a
transient failure); deterministic logic (registry, ERP seed, gating) is hard."""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
os.environ.setdefault("IM_LIB_ROOT", str(HERE / "skills-library"))
_c = tempfile.mkdtemp()
os.environ.setdefault("TOOLBOX_DB_PATH", os.path.join(_c, "ds.db"))
os.environ.setdefault("TOOLBOX_CACHE_DIR", _c)
sys.path.insert(0, str(HERE / "skills-library" / "_shared" / "data-fetch"))

from imdata import sources, valinputs, macro  # noqa: E402

PASS, FAIL, WARN = "\033[32mPASS\033[0m", "\033[31mFAIL\033[0m", "\033[33mWARN\033[0m"
_hard = []


def hard(n, c):
    _hard.append(bool(c)); print(f"  [{PASS if c else FAIL}] {n}")


def soft(n, c):
    print(f"  [{PASS if c else WARN}] {n}")


def test_registry():
    print("\nSource registry:")
    hard("registry non-empty", len(sources.SOURCES) >= 30)
    bad = [k for k, v in sources.SOURCES.items()
           if not {"name", "module", "tier", "status"} <= set(v)]
    hard("every source has name/module/tier/status", not bad)
    tiers = {v["tier"] for v in sources.SOURCES.values()}
    hard("tiers are from the known set",
         tiers <= {sources.PUBLIC, sources.KEYLESS, sources.KEY_NC, sources.KEY_EVAL})
    hard("public tier covers SEC + Treasury + Damodaran",
         all(sources.get(k).get("tier") == sources.PUBLIC
             for k in ("sec_edgar", "treasury", "damodaran")))
    p = sources.provenance("treasury", figure="risk-free", as_of="today")
    hard("provenance names source + tier", p["source"] and p["tier"] == sources.PUBLIC)


def test_commercial_gating():
    print("\nCommercial-mode gating:")
    # default (dev) mode: everything allowed
    hard("dev mode allows keyless", sources.allowed("yfinance"))
    # simulate commercial mode
    sources.config.COMMERCIAL_MODE = True
    try:
        hard("commercial blocks keyless (yfinance)", not sources.allowed("yfinance"))
        hard("commercial blocks eval-key (fmp)", not sources.allowed("fmp"))
        hard("commercial allows public (sec_edgar)", sources.allowed("sec_edgar"))
        hard("commercial allows public (treasury)", sources.allowed("treasury"))
    finally:
        sources.config.COMMERCIAL_MODE = False


def test_valinputs():
    print("\nDamodaran valuation inputs:")
    erp = valinputs.equity_risk_premium()
    hard("ERP is a plausible decimal", isinstance(erp, float) and 0.02 <= erp <= 0.08)
    hard("sector beta known returns a float", isinstance(valinputs.sector_beta("semiconductor"), float))
    hard("sector beta unknown returns None", valinputs.sector_beta("zzz-not-a-sector") is None)
    ke = valinputs.cost_of_equity(1.2, risk_free=0.045)
    hard("CAPM cost of equity computes", isinstance(ke, float) and ke > 0.045)


def test_macro():
    print("\nMacro risk-free (US Treasury, network):")
    rf = macro.risk_free_rate("10y")
    soft(f"Treasury 10y risk-free fetched ({rf})",
         rf is None or (isinstance(rf, float) and 0.0 < rf < 0.12))
    hard("risk_free_rate never raises (None ok)", rf is None or isinstance(rf, float))
    rf2 = macro.risk_free_rate("10y")  # cached
    hard("cached re-fetch consistent", rf2 == rf)


def test_new_modules():
    print("\nNew source modules (shape + graceful, network):")
    from imdata import ownership, sanctions, segments, volatility, fmp, altdata, macro
    # all must return the right type without raising, even if empty
    s = ownership.insider_summary("MSFT")
    hard("insider_summary returns a dict with 'signal'", isinstance(s, dict) and "signal" in s)
    scr = sanctions.screen("Microsoft Corporation")
    hard("sanctions.screen returns clear/hits", isinstance(scr, dict) and "clear" in scr and "hits" in scr)
    seg = segments.segments("MSFT")
    hard("segments returns business/geographic lists",
         isinstance(seg.get("business"), list) and isinstance(seg.get("geographic"), list))
    soft(f"segments extracted MSFT business segments ({len(seg.get('business') or [])})",
         len(seg.get("business") or []) >= 1)
    v = volatility.vix()
    hard("vix() returns dict or None", v is None or isinstance(v, dict))
    # keyed modules must no-op cleanly without keys
    hard("fmp.enabled() False without key", fmp.enabled() is False)
    hard("fmp.ratios no-ops to {}", fmp.ratios("MSFT") == {})
    hard("altdata.reddit no-ops to None without key", altdata.reddit_mentions("MSFT") is None)
    wb = macro.world_bank()
    soft(f"World Bank GDP fetched ({(wb or {}).get('value')})", wb is None or "value" in wb)


def test_final8():
    print("\nFinal 8 sources (BLS/ECB/13F/Finviz/bulk + fragile scrapes):")
    from imdata import macro, ownership, finviz, bulk, estimates, valinputs, altdata
    bls = macro.bls_series()
    soft(f"BLS CPI ({(bls or {}).get('value')})", bls is None or "value" in bls)
    ecb = macro.ecb_series()
    soft(f"ECB rate ({(ecb or {}).get('value')})", ecb is None or "value" in ecb)
    inst = ownership.institutional_holders("MSFT")
    hard("institutional_holders returns dict w/ top_holders", isinstance(inst.get("top_holders"), list))
    soft(f"13F holders found ({len(inst.get('top_holders') or [])})", len(inst.get("top_holders") or []) >= 1)
    hard("finviz.key_stats returns a dict", isinstance(finviz.key_stats("MSFT"), dict))
    hard("finviz.screen returns a list", isinstance(finviz.screen({"Sector": "Technology"}, limit=5), list))
    hard("bulk.available returns dict", isinstance(bulk.available(), dict))
    # the three fragile scrapes must return the right TYPE without raising (empty ok)
    hard("stockanalysis returns dict", isinstance(estimates.stockanalysis_estimates("MSFT"), dict))
    hard("macrotrends returns list", isinstance(valinputs.macrotrends_history("MSFT", "microsoft"), list))
    hard("nitter returns dict-or-None", altdata.nitter_mentions("MSFT") is None
         or isinstance(altdata.nitter_mentions("MSFT"), dict))


if __name__ == "__main__":
    test_registry()
    test_commercial_gating()
    test_valinputs()
    test_macro()
    test_new_modules()
    test_final8()
    n = sum(_hard)
    print(f"\n{n}/{len(_hard)} hard checks passed")
    sys.exit(0 if all(_hard) else 1)
