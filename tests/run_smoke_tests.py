#!/usr/bin/env python3
"""Run every full system's smoke test end-to-end and report a summary.

Keyless: live free data + local qwen3.5:9b for the model steps.
    .venv/bin/python tests/run_smoke_tests.py
"""
import os, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
FULL = ["idea-sourcing", "filing-intelligence", "portfolio-monitoring",
        "valuation", "reporting"]


def main():
    # ensure symlinks exist before running
    subprocess.run([sys.executable, os.path.join(REPO, "link.py")],
                   capture_output=True, text=True)
    results = []
    for name in FULL:
        test = os.path.join(REPO, "systems", name, "tests", "smoke_test.py")
        t0 = time.time()
        proc = subprocess.run([sys.executable, test], capture_output=True, text=True)
        dt = time.time() - t0
        ok = proc.returncode == 0
        results.append((name, ok, dt))
        print(f"{'PASS' if ok else 'FAIL'}  {name:22s} {dt:6.1f}s")
        out = (proc.stdout + proc.stderr).strip().splitlines()
        for ln in out[-3:]:
            print(f"      {ln}")
    npass = sum(1 for _n, ok, _t in results if ok)
    print(f"\n{npass}/{len(results)} systems passed.")
    sys.exit(0 if npass == len(results) else 1)


if __name__ == "__main__":
    main()
