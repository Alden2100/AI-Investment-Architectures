"""Acceptance tests for the text-similarity skill (Stage 3 of idea-sourcing v2).

Run with the project venv:
    /Users/amehta2/AI-Investment-Architectures/.venv/bin/python \
        skills-library/research/text-similarity/tests/text_similarity_test.py
"""
import os
import sys

# Import the skill's run.py (one dir up) as a module.
_HERE = os.path.dirname(os.path.realpath(__file__))
_SKILL_DIR = os.path.dirname(_HERE)
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

import run as ts  # noqa: E402


def _approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


# --- shared fixtures: enough overlap that min_df=2 keeps real vocab ----------------
SOFTWARE_A = "cloud software platform subscription saas analytics enterprise software"
SOFTWARE_B = "subscription cloud software analytics platform saas enterprise tools"
OIL = "crude petroleum drilling offshore rigs exploration upstream petroleum reserves"
OIL2 = "petroleum refining crude drilling offshore upstream reserves exploration pipeline"
MANDATE_SW = "enterprise cloud software subscription analytics platform saas businesses"


def test_identical_text_cosine_one():
    """1. identical text to itself -> cosine ~1.0."""
    # Need >=2 company docs for min_df=2 to keep tokens; duplicate the doc.
    survivors = [{"ticker": "X", "description": SOFTWARE_A},
                 {"ticker": "Y", "description": SOFTWARE_A}]
    res = ts.score_text_similarity(SOFTWARE_A, [], survivors)
    for r in res:
        assert _approx(r["sim_mandate"], 1.0, tol=1e-9), r
    print("PASS 1 identical -> cosine ~1.0")


def test_no_shared_tokens_cosine_zero():
    """2. two descriptions sharing no in-vocab tokens -> cosine 0.0."""
    # Two software docs (so software tokens survive min_df) + the oil mandate.
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},
                 {"ticker": "SW2", "description": SOFTWARE_B}]
    # Mandate uses only oil tokens, none of which are in the (software) vocab.
    res = ts.score_text_similarity("crude petroleum drilling offshore rigs", [], survivors)
    for r in res:
        assert r["sim_mandate"] == 0.0, r
    print("PASS 2 disjoint tokens -> cosine 0.0")


def test_text_score_in_unit_interval():
    """3. text_score always in [0,1] over a mixed fixture."""
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},
                 {"ticker": "SW2", "description": SOFTWARE_B},
                 {"ticker": "OIL1", "description": OIL},
                 {"ticker": "OIL2", "description": OIL2},
                 {"ticker": "EMPTY", "description": ""}]
    seeds = [{"ticker": "SEED1", "description": SOFTWARE_B}]
    res = ts.score_text_similarity(MANDATE_SW, seeds, survivors)
    for r in res:
        assert 0.0 <= r["text_score"] <= 1.0, r
        assert 0.0 <= r["sim_mandate"] <= 1.0, r
        if r["sim_seeds"] is not None:
            assert 0.0 <= r["sim_seeds"] <= 1.0, r
    print("PASS 3 text_score in [0,1]")


def test_determinism():
    """4. two runs produce identical output."""
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},
                 {"ticker": "OIL1", "description": OIL},
                 {"ticker": "OIL2", "description": OIL2}]
    seeds = [{"ticker": "SEED1", "description": SOFTWARE_B}]
    r1 = ts.score_text_similarity(MANDATE_SW, seeds, survivors)
    r2 = ts.score_text_similarity(MANDATE_SW, seeds, survivors)
    assert r1 == r2, (r1, r2)
    print("PASS 4 determinism")


def test_known_similar_outranks_dissimilar():
    """5. a known-similar company outranks a dissimilar one."""
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},   # similar to mandate
                 {"ticker": "OIL1", "description": OIL},          # dissimilar
                 {"ticker": "OIL2", "description": OIL2}]         # dissimilar (vocab support)
    seeds = [{"ticker": "SEED1", "description": SOFTWARE_B}]
    res = ts.score_text_similarity(MANDATE_SW, seeds, survivors)
    by_t = {r["ticker"]: r for r in res}
    assert by_t["SW1"]["text_score"] > by_t["OIL1"]["text_score"], res
    assert by_t["SW1"]["text_score"] > by_t["OIL2"]["text_score"], res
    print("PASS 5 similar outranks dissimilar")


def test_missing_description():
    """6. missing description -> text_score 0.0 and missing_description true."""
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},
                 {"ticker": "SW2", "description": SOFTWARE_B},
                 {"ticker": "NODESC", "description": ""},
                 {"ticker": "NONE"}]  # missing key entirely
    res = ts.score_text_similarity(MANDATE_SW, [], survivors)
    by_t = {r["ticker"]: r for r in res}
    for t in ("NODESC", "NONE"):
        assert by_t[t]["text_score"] == 0.0, by_t[t]
        assert by_t[t]["missing_description"] is True, by_t[t]
    print("PASS 6 missing description flagged")


def test_no_seeds_case():
    """7. no-seeds case -> text_score == sim_mandate and sim_seeds is null."""
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},
                 {"ticker": "OIL1", "description": OIL},
                 {"ticker": "OIL2", "description": OIL2}]
    res = ts.score_text_similarity(MANDATE_SW, [], survivors)
    for r in res:
        if r["missing_description"]:
            continue
        assert r["sim_seeds"] is None, r
        assert _approx(r["text_score"], r["sim_mandate"]), r
    print("PASS 7 no-seeds: text_score == sim_mandate, sim_seeds null")


def test_empty_mandate_raises():
    """Bonus: empty mandate_text raises a clear error (spec edge case)."""
    survivors = [{"ticker": "SW1", "description": SOFTWARE_A},
                 {"ticker": "SW2", "description": SOFTWARE_B}]
    raised = False
    try:
        ts.score_text_similarity("", [], survivors)
    except ValueError:
        raised = True
    assert raised, "empty mandate_text must raise ValueError"
    print("PASS bonus empty mandate -> ValueError")


def main():
    test_identical_text_cosine_one()
    test_no_shared_tokens_cosine_zero()
    test_text_score_in_unit_interval()
    test_determinism()
    test_known_similar_outranks_dissimilar()
    test_missing_description()
    test_no_seeds_case()
    test_empty_mandate_raises()
    print("\nALL TEXT-SIMILARITY ACCEPTANCE TESTS PASSED")


if __name__ == "__main__":
    main()
