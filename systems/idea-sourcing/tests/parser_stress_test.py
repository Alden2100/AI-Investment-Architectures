"""Stress the Stage-0 mandate-parser classification across tricky mandates (model).

Core rule under test: DIRECTIONAL language (preferably/ideally/strong/high-quality/
lean toward) is NEVER hard_constraint; binary mandate-explicit clauses (must/only/
above $X/exclude) SHOULD yield at least one hard_constraint. Prints each parse and
asserts the directional rule strictly (the linchpin); the binary expectation is a soft
warning (model phrasing varies).
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import _bootstrap  # noqa: F401,E402
from stages import stage0_mandate as s0  # noqa: E402

DIRECTIONAL = ("preferably", "ideally", "strong", "high-quality", "high quality",
               "lean toward", "compounder")

CASES = [
    ("must have market cap above $5 billion and be US-listed; no financials",
     {"expect_hard": True}),
    ("ideally founder-led businesses with strong returns on capital and a wide moat",
     {"expect_hard": False}),  # all directional/qualitative
    ("deep-value industrials trading below 10x earnings, preferably with low debt",
     {"expect_hard": True}),
    ("high-quality compounders we can hold for a decade",
     {"expect_hard": False}),
    ("large-cap US healthcare, exclude China and exclude tobacco",
     {"expect_hard": True}),
]

FAILS, WARNS = [], []


def main():
    for text, exp in CASES:
        print(f"\nMANDATE: {text}")
        m = s0.run(text)
        if m.get("_needs_model"):
            print("  (needs model rung — skipped)")
            WARNS.append("needs_model")
            continue
        crits = m.get("criteria", [])
        for c in crits:
            print(f"  {c['id']} [{c['type']:15}] {c['text'][:55]}")
        # STRICT: no directional-language criterion may be hard_constraint
        for c in crits:
            low = (c["text"] or "").lower()
            if c["type"] == "hard_constraint" and any(d in low for d in DIRECTIONAL):
                FAILS.append(f"directional tagged hard: {c['text']!r}")
        # SOFT expectation: binary mandates should yield >=1 hard
        has_hard = any(c["type"] == "hard_constraint" for c in crits)
        if exp["expect_hard"] and not has_hard:
            WARNS.append(f"expected a hard_constraint but got none: {text!r}")
        if not exp["expect_hard"] and has_hard:
            # acceptable only if it's a concrete binary (geography/cap), else warn
            WARNS.append(f"unexpected hard in a directional mandate: {text!r}")

    print("\n" + "=" * 60)
    for w in WARNS:
        print("WARN:", w)
    if FAILS:
        for f in FAILS:
            print("FAIL:", f)
        raise SystemExit(1)
    print("PARSER STRESS: directional-never-hard rule HELD on all parsed mandates")


if __name__ == "__main__":
    main()
