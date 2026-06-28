"""Phase 5 verification (deterministic, no network): instrument hygiene.

Asserts _non_common_equity flags SPACs (SIC 6770) + warrants/units/rights (suffix or
Nasdaq 5th-letter) while leaving real common stock — including the single-letter ticker
'U' (Unity) — untouched. Exit 0 == pass.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
_root = HERE
while not os.path.isdir(os.path.join(_root, "skills-library")):
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "skills-library", "_shared", "data-fetch"))

_run_py = os.path.join(_root, "skills-library", "opportunity", "universe-filter", "run.py")
spec = importlib.util.spec_from_file_location("uf_run", _run_py)
uf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uf)

fails = []
def check(name, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        fails.append(name)


def main():
    nc = uf._non_common_equity
    # Should be FLAGGED (non-common equity):
    check("SPAC common via SIC 6770 (AAC)", bool(nc("AAC", 6770)))
    check("SPAC unit AACBU (5th-letter U)", bool(nc("AACBU", 6770)))
    check("warrant ABLVW (5th-letter W)", bool(nc("ABLVW", 5960)))
    check("rights AACBR (5th-letter R)", bool(nc("AACBR", 6770)))
    check("explicit unit suffix SPAC.U", bool(nc("SPAC.U", None)))
    check("explicit warrant suffix FOO-WS", bool(nc("FOO-WS", None)))
    # Should be KEPT (real common stock):
    check("Unity 'U' (single letter) kept", nc("U", 7372) is None)
    check("NET kept", nc("NET", 7372) is None)
    check("MSFT kept", nc("MSFT", 7372) is None)
    check("4-letter ending W (SNOW) kept", nc("SNOW", 7372) is None)
    check("4-letter ending U (BIDU) kept", nc("BIDU", 7372) is None)

    if fails:
        print(f"\nHYGIENE TEST: {len(fails)} FAIL: {fails}"); raise SystemExit(1)
    print("\nHYGIENE TEST: ALL PASS (SPACs/warrants/units flagged; real common stock incl. 'U' kept)")


if __name__ == "__main__":
    main()
