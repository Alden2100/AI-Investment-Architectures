"""Shared sector/SIC matching — one implementation used by both the Stage-1
universe-filter skill and the Stage-0b prescreen in screener.py.

Plain sector words rarely match SIC *description* text verbatim (a mandate says
"restaurants"; EDGAR says "Retail-Eating Places"; "fintech" never appears at all). The
synonym map expands a sector word to the description tokens and SIC-code prefixes that
actually occur. A value is either a list of description substrings, or a
{"desc": [...], "sic": [<code prefixes>]} dict.
"""
from __future__ import annotations

from typing import Iterable, Optional

SECTOR_SYNONYMS = {
    # software / internet / SaaS
    "software": {"desc": ["software"], "sic": ["7372", "7370", "7371", "7389"]},
    "saas": {"desc": ["software"], "sic": ["7372", "7370", "7371", "7389"]},
    "enterprise software": {"desc": ["software"], "sic": ["7372", "7370", "7371", "7389"]},
    "internet": {"desc": ["computer programming", "information retrieval"], "sic": ["7370", "7372", "7374"]},
    "data and analytics": {"desc": ["data processing", "information retrieval"], "sic": ["7372", "7374", "7370"]},
    "digital infrastructure": {"desc": ["computer", "communications services"], "sic": ["7372", "7370", "4899", "7374"]},
    "mission-critical business services": {"desc": ["services-computer", "business services"], "sic": ["7372", "7370", "7374", "7389"]},
    # fintech / payments
    "fintech": {"desc": ["software", "data processing", "finance services"], "sic": ["7372", "7374", "6199", "6099"]},
    "financial technology": {"desc": ["software", "data processing", "finance services"], "sic": ["7372", "7374", "6199", "6099"]},
    "payments": {"desc": ["data processing", "finance services"], "sic": ["7374", "6099", "6199", "7372"]},
    # semiconductors + equipment
    "semiconductor": {"desc": ["semiconductor"], "sic": ["3674"]},
    "semiconductors": {"desc": ["semiconductor"], "sic": ["3674"]},
    "semiconductor equipment": {"desc": ["special industry machinery", "semiconductor"], "sic": ["3559", "3674", "3827"]},
    # healthcare tech + medical devices
    "healthcare technology": {"desc": ["health", "medical", "software"], "sic": ["8000", "80", "7372", "3841", "3845"]},
    "healthcare": {"desc": ["health", "medical", "pharmaceutical", "hospital"], "sic": ["80", "2834", "2836", "3841", "3845"]},
    "medical devices": {"desc": ["surgical", "medical instruments", "electromedical", "medical"], "sic": ["3841", "3845", "3826"]},
    "medical device": {"desc": ["surgical", "medical instruments", "electromedical"], "sic": ["3841", "3845", "3826"]},
    # industrials / automation
    "industrial automation": {"desc": ["industrial instruments", "industrial machinery", "process control"], "sic": ["3559", "3823", "3829", "3825"]},
    # consumer / other (kept from the original filter map)
    "restaurant": {"desc": ["eating", "drinking places"], "sic": ["5812", "5810", "5813", "5814"]},
    "restaurants": {"desc": ["eating", "drinking places"], "sic": ["5812", "5810", "5813", "5814"]},
    "fast food": {"desc": ["eating"], "sic": ["5812", "5810"]},
    "casual dining": {"desc": ["eating"], "sic": ["5812", "5810"]},
    "dining": {"desc": ["eating", "drinking places"], "sic": ["5812", "5810", "5813"]},
    "biotech": ["biological", "life sciences", "physical & biological research"],
    "biotechnology": ["biological", "life sciences", "physical & biological research"],
    "reit": ["real estate investment trust"],
    "reits": ["real estate investment trust"],
    "defense": {"desc": ["guided missile", "ordnance", "ammunition"], "sic": ["348", "3760", "3761", "3795", "3812"]},
    "thrift": ["savings institution"],
    "savings": ["savings institution"],
    "auto": ["motor vehicle"],
    "automotive": ["motor vehicle"],
    # avoid-list helpers (so exclusions map to real SIC vocabulary too)
    "airline": {"desc": ["air transportation"], "sic": ["4512", "4513", "4522"]},
    "airlines": {"desc": ["air transportation"], "sic": ["4512", "4513", "4522"]},
    "tobacco": {"desc": ["tobacco", "cigarette"], "sic": ["2100", "2111"]},
    "casino": {"desc": ["gambling", "amusement", "services-miscellaneous amusement"], "sic": ["7990", "7011"]},
    "casinos": {"desc": ["gambling", "amusement"], "sic": ["7990"]},
    "commodity": {"desc": ["mining", "crude petroleum", "metal", "gold", "coal"], "sic": ["10", "12", "13", "14", "1040"]},
    "commodity producers": {"desc": ["mining", "crude petroleum", "metal mining", "gold", "coal"], "sic": ["10", "12", "13", "14"]},
    "traditional retailers": {"desc": ["retail-"], "sic": ["52", "53", "54", "56", "57", "59"]},
    "retail": {"desc": ["retail-"], "sic": ["52", "53", "54", "56", "57", "59"]},
    "oil": {"desc": ["crude petroleum", "petroleum refining", "oil & gas"], "sic": ["13", "2911"]},
    "telecom": ["telephone", "telegraph", "communications services"],
}


def word_matches(word: str, sic, desc: str) -> bool:
    """True if a sector WORD matches a row, expanding synonyms to description tokens
    and SIC-code prefixes; falls back to a raw substring of the description."""
    word = (word or "").lower().strip()
    if not word:
        return False
    d = (desc or "").lower()
    sic_str = str(sic) if sic is not None else ""
    syn = SECTOR_SYNONYMS.get(word)
    if isinstance(syn, dict):
        if any(s in d for s in syn.get("desc", [])):
            return True
        if any(sic_str.startswith(p) for p in syn.get("sic", [])):
            return True
    elif isinstance(syn, list):
        if any(s in d for s in syn):
            return True
    return word in d  # raw fallback


def sic_token_match(value, sic, sic_desc) -> bool:
    """For sic in/not_in membership tests. A value element matches a row when it equals
    the int SIC code, OR (a word) matches via synonym expansion / raw description text."""
    sic_i = None
    try:
        sic_i = int(sic) if sic is not None else None
    except (TypeError, ValueError):
        sic_i = None
    elems = value if isinstance(value, (list, tuple)) else [value]
    for elem in elems:
        try:
            ev = float(elem)
            if sic_i is not None and int(ev) == sic_i:
                return True
            continue
        except (TypeError, ValueError):
            pass
        if word_matches(str(elem), sic, sic_desc):
            return True
    return False


def matches_any(words: Iterable[str], sic, desc: str) -> Optional[str]:
    """Return the first sector word that matches the row, or None."""
    for w in words or []:
        if word_matches(w, sic, desc):
            return w
    return None
