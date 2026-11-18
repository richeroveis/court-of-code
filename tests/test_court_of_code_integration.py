"""Live integration tests against the seeded CourtOfCode deployment on studionet.

These read the consensus-finalized state through the real GenLayer RPC and assert the
custody, escrow-conservation and mutual-settlement invariants plus the seeded tribunal
data. They are the on-chain counterpart to the direct-mode leader-path tests. Run with:

    gltest tests/test_court_of_code_integration.py -v -s

The deployment address and the throwaway signer addresses are taken from the evidence
bundle written by scripts/deploy_studionet.py.
"""

import json
import time
from pathlib import Path

import pytest

from gltest import get_contract_factory
from gltest.accounts import get_default_account

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / "evidence" / "_checkpoint.json"
EVIDENCE = ROOT / "evidence" / "transactions.json"
CONTRACT_NAME = "CourtOfCode"


def _address():
    if not CHECKPOINT.exists():
        pytest.skip("no studionet deployment checkpoint found; run deploy_studionet.py first")
    addr = json.loads(CHECKPOINT.read_text(encoding="utf-8")).get("contract_address")
    if not addr:
        pytest.skip("checkpoint has no contract_address")
    return addr


def _evidence():
    if not EVIDENCE.exists():
        pytest.skip("no evidence bundle found; run deploy_studionet.py first")
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


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


def test_case_one_settled_by_mutual_authorization(deployed):
    contract, _ = deployed
    case1 = _read(contract, "get_case", [1])
    # Requirement B: the split only settles when the counterparty co-signs.
    assert case1["status"] == "SETTLED_MUTUAL"
    assert case1["claimant_approved_split"] is True
    assert case1["respondent_approved_split"] is True
    assert case1["verdict_label"] == "SPLIT_REMEDY"
    assert case1["claimant_award_bps"] == 6000


def test_case_one_conserves_escrow(deployed):
    contract, _ = deployed
    case1 = _read(contract, "get_case", [1])
    assert case1["disputed_escrow"] == 250000
    assert case1["claimant_payout"] == 150000
    assert case1["respondent_payout"] == 100000
    assert case1["claimant_payout"] + case1["respondent_payout"] == case1["disputed_escrow"]


def test_custody_moved_into_claimant_wallet(deployed):
    # Requirement A: the claimant withdrew 150000 CET out of the vault into their wallet.
    contract, owner = deployed
    wallet = int(_read(contract, "get_wallet_balance", [owner.address]))
    claimable = int(_read(contract, "get_claimable_award", [owner.address]))
    # Case 4 awarded 100000 CET to the claimant which remains claimable until withdrawn.
    # 10000000 mint - 250000 c1 + 150000 c1 award - 180000 c2 - 100000 c3 - 100000 c4 = 9520000.
    assert claimable in (0, 100000)
    assert wallet >= 9500000


def test_respondent_award_is_backed_by_the_vault(deployed):
    contract, _ = deployed
    ev = _evidence()
    respondent = ev["respondent"]
    resp_claimable = int(_read(contract, "get_claimable_award", [respondent]))
    stats = _read(contract, "get_tribunal_stats")
    assert resp_claimable == 100000
    # The vault still holds the respondent's unclaimed award plus the open case 2 escrow.
    assert int(stats["escrow_vault_balance"]) >= resp_claimable + 180000


def test_second_case_still_open(deployed):
    contract, _ = deployed
    case2 = _read(contract, "get_case", [2])
    assert case2["status"] in ("OPEN_FOR_REBUTTAL", "READY_FOR_TRIAL")
    assert case2["disputed_escrow"] == 180000
    assert case2["rebuttal_deadline_clock"] == case2["filed_at_clock"] + 3


def test_third_case_failed_closed(deployed):
    contract, _ = deployed
    case3 = _read(contract, "get_case", [3])
    assert case3["evidence_verification_status"] == "EVIDENCE_UNAVAILABLE_FAIL_CLOSED"
    assert case3["claimant_source_verified"] is False
    assert case3["verdict_band"] == "EVIDENCE_UNAVAILABLE_FAIL_CLOSED"
    assert case3["claimant_payout"] == 0
    assert case3["respondent_payout"] == 0


def test_fourth_case_live_adjudicated_with_both_sources_verified(deployed):
    contract, _ = deployed
    case4 = _read(contract, "get_case", [4])
    assert case4["status"] == "ADJUDICATED"
    assert case4["evidence_verification_status"] == "BOTH_SOURCES_VERIFIED"
    assert case4["claimant_source_verified"] is True
    assert case4["respondent_source_verified"] is True
    assert case4["verdict_band"] == "CLAIMANT_PREVAILS"
    assert case4["claimant_award_bps"] == 10000
    assert case4["claimant_payout"] == 100000


def test_native_bonds_exact_conservation_and_separation(deployed):
    contract, _ = deployed
    stats = _read(contract, "get_tribunal_stats")
    custody = int(stats["native_bond_custody"])
    active = int(stats["active_locked_native_bonds"])
    refundable = int(stats["total_refundable_native_balances"])
    assert custody == active + refundable
    ev = _evidence()
    assert int(ev["respondent_native_balance_final"]) >= 30000


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
    assert stats["escrow_vault_balance"] >= 280000


def test_juror_reputation_reflects_brief_and_upvote(deployed):
    contract, _ = deployed
    ev = _evidence()
    juror1 = ev["juror1"].lower()
    # Reputation is a pure function of jury activity: +10 per brief authored and +3 per
    # upvote received on those briefs. Recompute it from live brief data so the assertion
    # holds as the public demo accumulates more activity beyond the original seed.
    authored = 0
    received_upvotes = 0
    for case in _read(contract, "get_all_cases"):
        for b in _read(contract, "get_case_briefs", [case["case_id"]]):
            if b["juror"].lower() == juror1:
                authored += 1
                received_upvotes += b["upvotes"]
    expected = 10 * authored + 3 * received_upvotes
    board = _read(contract, "get_juror_leaderboard")
    reps = {r["juror"].lower(): r["reputation"] for r in board}
    assert authored >= 1 and expected > 0
    assert reps.get(juror1) == expected
