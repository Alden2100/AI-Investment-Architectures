"""Avenoth Advisory brand palette as reportlab colors.

Loaded from the vendored ``branding/colors.json`` (single source of truth) with a
hardcoded fallback, so the PDF theme always matches the brand. 60/30/10 weighting:
navy dominant, steel support, azure accent.
"""
from __future__ import annotations

import json
import os

from reportlab.lib.colors import HexColor

_FALLBACK = {
    "navy": "#0E2841", "midnight": "#081A2E", "steel": "#2E5B8A",
    "azure": "#4E95D9", "sky": "#9FC6EC", "white": "#FFFFFF", "cloud": "#F5F7FA",
    "mist": "#E4E9F0", "slate": "#64748B", "ink": "#0E2841",
    "positive": "#2F8F6B", "negative": "#C24A3A", "caution": "#C99A3C",
}


def _load_hex() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "colors.json")
    out = dict(_FALLBACK)
    try:
        with open(path) as fh:
            data = json.load(fh)
        for group in ("core", "neutral", "semantic"):
            for name, spec in data.get(group, {}).items():
                key = name.replace("-", "_")
                if isinstance(spec, dict) and spec.get("hex"):
                    out[key] = spec["hex"]
        if "slate_gray" in out:
            out["slate"] = out["slate_gray"]
    except Exception:
        pass
    return out


_HEX = _load_hex()

# reportlab Color objects
NAVY = HexColor(_HEX["navy"])
MIDNIGHT = HexColor(_HEX["midnight"])
STEEL = HexColor(_HEX["steel"])
AZURE = HexColor(_HEX["azure"])
SKY = HexColor(_HEX["sky"])
WHITE = HexColor(_HEX["white"])
CLOUD = HexColor(_HEX["cloud"])
MIST = HexColor(_HEX["mist"])
SLATE = HexColor(_HEX["slate"])
INK = HexColor(_HEX["ink"])
POSITIVE = HexColor(_HEX["positive"])
NEGATIVE = HexColor(_HEX["negative"])
CAUTION = HexColor(_HEX["caution"])

BRAND_NAME = "Avenoth Advisory"
# reportlab built-ins that match the brand pairing cross-platform:
# Times (serif) ≈ Georgia for headers; Helvetica ≈ Arial for body.
FONT_SERIF = "Times-Roman"
FONT_SERIF_BOLD = "Times-Bold"
FONT_SANS = "Helvetica"
FONT_SANS_BOLD = "Helvetica-Bold"


def status_color(label: str):
    """Map a status/verdict word to a semantic brand color."""
    s = (label or "").lower()
    if s in ("red", "sell", "pass", "breach", "negative", "fail"):
        return NEGATIVE
    if s in ("green", "buy", "pursue", "within", "positive", "ok"):
        return POSITIVE
    if s in ("yellow", "watch", "hold", "caution", "flag"):
        return CAUTION
    return STEEL
