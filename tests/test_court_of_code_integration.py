"""Live integration tests against the seeded CourtOfCode deployment on studionet.

These read the consensus-finalized state through the real GenLayer RPC and assert the
accounting invariants and seeded tribunal data. They are the on-chain counterpart to
the direct-mode leader-path tests. Run with:

    gltest tests/test_court_of_code_integration.py -v -s

The deployment address is taken from evidence/_checkpoint.json written by
scripts/deploy_studionet.py.
"""

import json
import time
from pathlib import Path

import pytest

from gltest import get_contract_factory
from gltest.accounts import get_default_account

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "evidence" / "_checkpoint.json"
CONTRACT_NAME = "CourtOfCode"


def _address():
    if not CHECKPOINT.exists():
        pytest.skip("no studionet deployment checkpoint found; run deploy_studionet.py first")
    addr = json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("contract_address")
    if not addr:
        pytest.skip("checkpoint has no contract_address")
    return addr


@pytest.fixture(scope="module")
def deployed():
    factory = get_contract_factory(CONTRACT_NAME)
    owner = get_default_account()
    contract = factory.build_contract(contract_address=_address(), account=owner)
    return contract, owner


def _read(contract, method, args=None, retries=6):
    last = None
    for attempt in range(retries):
        try:
            return getattr(contract, method)(args=list(args or [])).call()
        except Exception as exc:  # noqa: BLE001 - studio proxy reads are flaky
            last = str(exc)
            time.sleep(4 + attempt * 4)
    raise AssertionError(f"read {method} failed after retries: {last}")


def test_get_all_cases_returns_seeded_cases(deployed):
    contract, _ = deployed
    cases = _read(contract, "get_all_cases")
    assert len(cases) >= 2
    ids = {c["case_id"] for c in cases}
    assert 1 in ids and 2 in ids


def test_adjudicated_case_conserves_escrow(deployed):
    contract, _ = deployed
    case1 = _read(contract, "get_case", [1])
    assert case1["status"] == "ADJUDICATED"
    assert case1["verdict_label"] == "SPLIT_REMEDY"
    assert case1["claimant_award_bps"] == 6000
    assert case1["claimant_payout"] + case1["respondent_payout"] == case1["disputed_escrow"]


def test_second_case_still_open(deployed):
    contract, _ = deployed
    case2 = _read(contract, "get_case", [2])
    assert case2["status"] == "OPEN_FOR_REBUTTAL"
    assert case2["disputed_escrow"] == 180000


def test_briefs_recorded_for_case_one(deployed):
    contract, _ = deployed
    briefs = _read(contract, "get_case_briefs", [1])
    assert len(briefs) == 2
    sides = sorted(b["side"] for b in briefs)
    assert sides == ["SUPPORT_CLAIMANT", "SUPPORT_RESPONDENT"]
    # The claimant-supporting brief was upvoted once.
    by_side = {b["side"]: b for b in briefs}
    assert by_side["SUPPORT_CLAIMANT"]["upvotes"] == 1


def test_tribunal_stats_match_seed(deployed):
    contract, _ = deployed
    stats = _read(contract, "get_tribunal_stats")
    assert stats["total_cases"] >= 2
    assert stats["adjudicated_cases"] >= 1
    assert stats["total_briefs"] >= 2
    assert stats["votes_for_claimant"] >= 1
    assert stats["votes_for_respondent"] >= 1


def test_juror_reputation_reflects_brief_and_upvote(deployed):
    contract, _ = deployed
    board = _read(contract, "get_juror_leaderboard")
    reps = {r["juror"].lower(): r["reputation"] for r in board}
    # juror1 authored a brief (+10) and received one upvote (+3) = 13
    juror1 = "0x9926c6407afb19b6349a9a68294e70b2ca3c4f29"
    assert reps.get(juror1) == 13


def test_split_awards_are_claimable(deployed):
    contract, owner = deployed
    claimant_award = _read(contract, "get_claimable_award", [owner.address])
    assert int(claimant_award) == 150000  # 60% of 250000 escrow
    respondent = "0xFF21Bc38046f8299544598C0e44C964A8E49E2C5"
    resp_award = _read(contract, "get_claimable_award", [respondent])
    assert int(resp_award) == 100000  # 40% of 250000 escrow
