import datetime as _dt
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "court_of_code.py"

T0 = 1_700_000_000  # deterministic base inclusion time used across the suite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hex(addr):
    if isinstance(addr, str):
        return addr
    return "0x" + bytes(addr).hex()


def _iso(ts):
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deploy(vm, deploy, alice):
    vm.sender = alice
    vm.value = 0
    vm.warp(_iso(T0))
    return deploy(str(CONTRACT_PATH))


def _fund(vm, c, alice, amount):
    vm.sender = alice
    vm.value = amount
    return c.fund_cet_vault_payable()


def _file(vm, c, alice, bob, did="D1", principal=10000, rebuttal=3600, appeal=3600, bond=0, at=T0):
    vm.sender = alice
    vm.value = bond
    vm.warp(_iso(at))
    return c.file_dispute_payable(
        did, _hex(bob), "Vue dashboard migration bounty",
        "https://specs.example.dev/vue-77", "https://github.example.dev/acme/dash/pull/77",
        "Claimant shipped the migration; maintainer withheld the bounty", "VUE-77",
        principal, rebuttal, appeal,
    )


def _rebut(vm, c, bob, did="D1", bond=4000, at=T0 + 600):
    vm.sender = bob
    vm.value = bond
    vm.warp(_iso(at))
    return c.post_respondent_bond_payable(did, "Cache drops writes under airplane mode; suite not green")


def _mock_evidence(vm):
    vm.mock_web(r".*example\.dev.*", {"status": 200, "body": "Delivers VUE-77 migration with stable REST api"})


def _mock_award(vm, award, baseline=8000, opinion="Deliverable largely meets spec"):
    vm.mock_llm(
        r".*Chancery tribunal.*",
        json.dumps(
            {"spec_baseline_score_bps": baseline, "claimant_award_bps": award, "opinion": opinion}
        ),
    )


# ---------------------------------------------------------------------------
# A. Rule 1 / Rule 2 structural guarantees
# ---------------------------------------------------------------------------


def test_line1_is_pinned_runner_header():
    first = CONTRACT_PATH.read_text(encoding="utf-8").splitlines()[0]
    assert first == '# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }'


def test_contract_under_37500_bytes():
    assert CONTRACT_PATH.stat().st_size < 37500


def test_no_manual_clock_advance_or_deterministic_backdoor():
    src = CONTRACT_PATH.read_text(encoding="utf-8")
    assert "def advance_clock" not in src
    assert "gl.advance_clock" not in src
    assert "def _deterministic" not in src
    assert "adjudicate_case_deterministic" not in src


def test_no_admin_fund_bypass_symbols():
    src = CONTRACT_PATH.read_text(encoding="utf-8")
    for bad in ("only owner may settle", "def force_settlement", "admin_claim"):
        assert bad not in src


def test_deploy_sets_owner_and_zero_counters(direct_vm, direct_deploy, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    stats = c.get_tribunal_stats()
    assert stats["total_dockets"] == 0
    assert c.get_custody_accounting_summary()["vault_custody_balance"] == 0


# ---------------------------------------------------------------------------
# B. CET vault funding (Rule 3) + soft-fail (Rule 8)
# ---------------------------------------------------------------------------


def test_fund_credits_cet_balance_and_supply(direct_vm, direct_deploy, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    assert _fund(direct_vm, c, direct_alice, 500000) == "CET_FUNDED"
    assert c.get_cet_balance(_hex(direct_alice)) == 500000
    assert c.get_custody_accounting_summary()["total_cet_supply"] == 500000


def test_fund_zero_soft_fails_without_revert(direct_vm, direct_deploy, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    direct_vm.value = 0
    rc = c.fund_cet_vault_payable()
    assert rc.startswith("SOFT_FAIL_REFUND_CREDITED:CET_DEPOSIT_ZERO")


# ---------------------------------------------------------------------------
# C. Filing success + escrow custody (Rule 3)
# ---------------------------------------------------------------------------


def test_file_success_escrows_principal(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    assert _file(direct_vm, c, direct_alice, direct_bob, principal=10000) == "FILED:D1"
    d = c.get_docket("D1")
    assert d["status"] == "OPEN_FOR_REBUTTAL"
    assert d["principal_cet"] == 10000
    assert c.get_custody_accounting_summary()["vault_custody_balance"] == 10000
    assert c.get_cet_balance(_hex(direct_alice)) == 500000 - 10000


def test_file_deadlines_are_warp_deterministic(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000, rebuttal=3600, appeal=3600, at=T0)
    d = c.get_docket("D1")
    assert d["filing_epoch"] == T0
    assert d["rebuttal_deadline_epoch"] == T0 + 3600
    assert d["appeal_deadline_epoch"] == T0 + 7200
    assert d["adjudication_timeout_epoch"] > d["appeal_deadline_epoch"]


def test_file_records_native_bond_escrow(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000, bond=321)
    assert c.get_custody_accounting_summary()["native_escrow_balance"] == 321


# ---------------------------------------------------------------------------
# D. Filing soft-fail battery (Rule 8): never reverts, always credits value
# ---------------------------------------------------------------------------


def _expect_soft_fail(direct_vm, c, actor, value, fn, reason):
    direct_vm.sender = actor
    direct_vm.value = value
    rc = fn()
    assert rc == "SOFT_FAIL_REFUND_CREDITED:" + reason
    assert c.get_refundable_balance(_hex(actor)) == value
    assert c.get_last_payable_rejection(_hex(actor)) == reason


def test_file_duplicate_docket_id_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 999,
        lambda: c.file_dispute_payable("D1", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 3600),
        "DUPLICATE_DOCKET_ID",
    )


def test_file_self_dealing_soft_fails(direct_vm, direct_deploy, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("S", _hex(direct_alice), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 3600),
        "SELF_DEALING_DOCKET",
    )


def test_file_bad_respondent_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("S", "not-an-address", "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 3600),
        "BAD_RESPONDENT_ADDRESS",
    )


def test_file_underfunded_cet_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 1000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("BIG", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 999999, 3600, 3600),
        "UNDERFUNDED_CET",
    )


def test_file_bad_rebuttal_window_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("W", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 10, 3600),
        "BAD_REBUTTAL_WINDOW",
    )


def test_file_bad_appeal_window_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("W2", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 10),
        "BAD_APPEAL_WINDOW",
    )


def test_file_bad_token_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("TK", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "bad token", 100, 3600, 3600),
        "BAD_SPEC_TOKEN",
    )


def test_file_bad_pr_url_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("U", _hex(direct_bob), "T", "https://a.dev/s", "javascript:alert(1)", "s", "T", 100, 3600, 3600),
        "BAD_PR_URL",
    )


def test_file_paused_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    c.set_filing_paused(True)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 500,
        lambda: c.file_dispute_payable("PX", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 3600),
        "FILING_PAUSED",
    )
    c.set_filing_paused(False)
    direct_vm.value = 0
    assert _file(direct_vm, c, direct_alice, direct_bob, did="PX_OK").startswith("FILED")


# ---------------------------------------------------------------------------
# E. Respondent rebuttal (payable soft-fail + gate)
# ---------------------------------------------------------------------------


def test_rebuttal_by_respondent_moves_to_trial(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    rc = _rebut(direct_vm, c, direct_bob, bond=4000)
    assert rc == "REBUTTAL_POSTED:D1"
    d = c.get_docket("D1")
    assert d["status"] == "READY_FOR_TRIAL"
    assert d["rebuttal_submitted"] is True
    assert d["respondent_bond_cet"] == 4000


def test_rebuttal_non_respondent_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _expect_soft_fail(
        direct_vm, c, direct_charlie, 700,
        lambda: c.post_respondent_bond_payable("D1", "not the respondent"),
        "NOT_RESPONDENT",
    )


def test_rebuttal_underfunded_bond_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _expect_soft_fail(direct_vm, c, direct_bob, 0, lambda: _rebut(direct_vm, c, direct_bob, bond=0), "UNDERFUNDED_BOND")


def test_rebuttal_after_window_expiry_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, rebuttal=3600)
    direct_vm.warp(_iso(T0 + 999999))
    _expect_soft_fail(
        direct_vm, c, direct_bob, 700,
        lambda: c.post_respondent_bond_payable("D1", "late rebuttal"),
        "REBUTTAL_WINDOW_EXPIRED",
    )


# ---------------------------------------------------------------------------
# F. Amicus briefs and jury voting
# ---------------------------------------------------------------------------


def _filed_ready_docket(vm, c, alice, bob):
    _fund(vm, c, alice, 500000)
    _file(vm, c, alice, bob)


def test_brief_support_claimant_counts_vote(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    bid = c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "The diff ships it")
    assert bid == 1
    d = c.get_docket("D1")
    assert d["votes_for_claimant"] == 1
    assert d["amicus_count"] == 1


def test_brief_support_respondent_counts_vote(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    c.file_amicus_brief("D1", "charlie", "SUPPORT_RESPONDENT", "Missing tests")
    assert c.get_docket("D1")["votes_for_respondent"] == 1


def test_neutral_brief_counts_amicus_only(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    c.file_amicus_brief("D1", "charlie", "NEUTRAL_TECHNICAL", "Partial credit either way")
    d = c.get_docket("D1")
    assert d["amicus_count"] == 1 and d["votes_for_claimant"] == 0 and d["votes_for_respondent"] == 0


def test_duplicate_juror_vote_reverts(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "a")
    with direct_vm.expect_revert("already voted"):
        c.file_amicus_brief("D1", "charlie2", "SUPPORT_RESPONDENT", "b")


def test_brief_invalid_side_reverts(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("invalid side"):
        c.file_amicus_brief("D1", "charlie", "SUPPORT_ANYONE", "x")


def test_brief_argument_too_long_reverts(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    with direct_vm.expect_revert("argument"):
        c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "x" * 301)


def test_brief_awards_juror_reputation(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "ship it")
    board = c.get_judicial_leaderboard()
    assert board[0]["reputation"] == 10


def test_upvote_increments_and_pays_author(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    bid = c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "good")
    direct_vm.sender = direct_bob
    assert c.upvote_amicus_brief(bid) == 1
    board = c.get_judicial_leaderboard()
    assert any(r["reputation"] == 13 for r in board)


def test_self_upvote_reverts(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    bid = c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "good")
    with direct_vm.expect_revert("no self-upvote"):
        c.upvote_amicus_brief(bid)


def test_duplicate_upvote_reverts(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    bid = c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "good")
    direct_vm.sender = direct_bob
    c.upvote_amicus_brief(bid)
    with direct_vm.expect_revert("already upvoted"):
        c.upvote_amicus_brief(bid)


# ---------------------------------------------------------------------------
# G. Adjudication (Rules 4, 6, 9): consensus-bound baselines + discrete ladder
# ---------------------------------------------------------------------------


def test_adjudicate_before_rebuttal_and_window_open_reverts(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, rebuttal=3600)
    direct_vm.warp(_iso(T0 + 600))
    with direct_vm.expect_revert("rebuttal window still open"):
        c.adjudicate_docket("D1")


def test_adjudicate_after_rebuttal_majority(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=4000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 7500, baseline=8000)
    band = c.adjudicate_docket("D1")
    assert band == "MAJORITY_CLAIMANT_SPLIT"
    d = c.get_docket("D1")
    assert d["status"] == "ADJUDICATED"
    assert d["claimant_award_bps"] == 7500
    assert d["derived_claimant_payout"] == 7500
    assert d["derived_respondent_refund"] == 2500
    assert d["derived_slash_amount"] == 4000


def test_adjudicate_on_window_expiry_without_rebuttal(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000, rebuttal=3600)
    direct_vm.warp(_iso(T0 + 3601))
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 5000, baseline=5000)
    assert c.adjudicate_docket("D1") == "EQUITABLE_FIFTY_SPLIT"
    assert c.get_docket("D1")["status"] == "ADJUDICATED"


def test_award_snapped_to_discrete_ladder(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=1000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 8337, baseline=6000)  # off the ladder
    c.adjudicate_docket("D1")
    d = c.get_docket("D1")
    assert d["claimant_award_bps"] in (0, 2500, 5000, 7500, 10000)
    assert d["claimant_award_bps"] == 7500


def test_baseline_quantized_onto_500_grid(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=1000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 5000, baseline=7777)
    c.adjudicate_docket("D1")
    base = c.get_docket("D1")["quantized_spec_baseline_bps"]
    assert base % 500 == 0
    assert base == 7500


def test_full_claimant_decree_credits_principal_and_slash(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=9999)
    _rebut(direct_vm, c, direct_bob, bond=2000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 10000, baseline=10000)
    assert c.adjudicate_docket("D1") == "FULL_CLAIMANT_DECREE"
    d = c.get_docket("D1")
    assert d["derived_claimant_payout"] == 9999
    assert d["derived_respondent_refund"] == 0
    assert d["derived_slash_amount"] == 2000


def test_respondent_summary_dismissal_zero_award(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=4000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 0, baseline=1000)
    assert c.adjudicate_docket("D1") == "RESPONDENT_SUMMARY_DISMISSAL"
    d = c.get_docket("D1")
    assert d["derived_claimant_payout"] == 0
    assert d["derived_respondent_refund"] == 10000
    assert d["derived_slash_amount"] == 0


def test_partial_contribution_award_band(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=4000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 2500, baseline=4000)
    assert c.adjudicate_docket("D1") == "PARTIAL_CONTRIBUTION_AWARD"


def test_web_source_unreachable_marks_unverified_but_still_adjudicates(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=1000)
    # no web mock registered: render raises, contract falls back to on-chain summary
    _mock_award(direct_vm, 5000, baseline=5000)
    assert c.adjudicate_docket("D1") == "EQUITABLE_FIFTY_SPLIT"
    assert c.get_docket("D1")["web_source_verified"] is False


def test_web_source_verified_when_reachable(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    _rebut(direct_vm, c, direct_bob, bond=1000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 5000, baseline=5000)
    c.adjudicate_docket("D1")
    assert c.get_docket("D1")["web_source_verified"] is True


def test_cannot_adjudicate_twice(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _rebut(direct_vm, c, direct_bob, bond=1000)
    _mock_evidence(direct_vm)
    _mock_award(direct_vm, 5000, baseline=5000)
    c.adjudicate_docket("D1")
    with direct_vm.expect_revert("not adjudicable"):
        c.adjudicate_docket("D1")


# ---------------------------------------------------------------------------
# H. Settlement timing + conservation (Rule 10)
# ---------------------------------------------------------------------------


def _adjudicated_ready(vm, c, alice, bob, award=7500, bond=4000):
    _fund(vm, c, alice, 500000)
    _file(vm, c, alice, bob, principal=10000)
    _rebut(vm, c, bob, bond=bond)
    _mock_evidence(vm)
    _mock_award(vm, award, baseline=8000)
    c.adjudicate_docket("D1")


def test_settlement_before_appeal_window_reverts(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob)
    direct_vm.warp(_iso(T0 + 600))  # still inside appeal window
    with direct_vm.expect_revert("appeal window still open"):
        c.execute_decree_settlement("D1")


def test_settlement_after_appeal_window_conserves(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob, award=7500, bond=4000)
    direct_vm.warp(_iso(T0 + 7201))
    assert c.execute_decree_settlement("D1") == "SETTLED:MAJORITY_CLAIMANT_SPLIT"
    claimant_credit = c.get_claimable_award(_hex(direct_alice))
    respondent_credit = c.get_claimable_award(_hex(direct_bob))
    # payout 7500 + slash 4000 to claimant; refund 2500 to respondent (bond slashed)
    assert claimant_credit == 7500 + 4000
    assert respondent_credit == 2500
    assert claimant_credit + respondent_credit == 10000 + 4000  # principal + bond conserved
    assert c.get_docket("D1")["status"] == "FINALIZED"


def test_settlement_partial_award_returns_unslashed_bond(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob, award=5000, bond=4000)
    direct_vm.warp(_iso(T0 + 7201))
    c.execute_decree_settlement("D1")
    # award < 7500 so bond not slashed; respondent gets refund + full bond back
    assert c.get_claimable_award(_hex(direct_alice)) == 5000
    assert c.get_claimable_award(_hex(direct_bob)) == 5000 + 4000


def test_withdraw_award_credits_cet(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob, award=7500, bond=4000)
    direct_vm.warp(_iso(T0 + 7201))
    c.execute_decree_settlement("D1")
    direct_vm.sender = direct_alice
    cet_before = c.get_cet_balance(_hex(direct_alice))
    amount = c.withdraw_award()
    assert amount == 11500
    assert c.get_cet_balance(_hex(direct_alice)) == cet_before + 11500


def test_withdraw_award_zero_reverts(direct_vm, direct_deploy, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_charlie)
    with direct_vm.expect_revert("no award"):
        c.withdraw_award()


# ---------------------------------------------------------------------------
# H2. Filing bond is never trapped (Rule 10 non-trapping deposit return)
# ---------------------------------------------------------------------------


def _filed_with_deposit(vm, c, alice, bob, deposit=3000, award=7500, bond=4000):
    _fund(vm, c, alice, 500000)
    _file(vm, c, alice, bob, principal=10000, bond=deposit)
    _rebut(vm, c, bob, bond=bond)
    _mock_evidence(vm)
    _mock_award(vm, award, baseline=8000)
    c.adjudicate_docket("D1")


def test_filing_deposit_refunded_on_settlement(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_with_deposit(direct_vm, c, direct_alice, direct_bob, deposit=3000)
    assert c.get_custody_accounting_summary()["native_escrow_balance"] == 3000
    direct_vm.warp(_iso(T0 + 7201))
    c.execute_decree_settlement("D1")
    assert c.get_refundable_balance(_hex(direct_alice)) == 3000
    assert c.get_custody_accounting_summary()["native_escrow_balance"] == 0
    assert c.get_custody_accounting_summary()["total_refundable_custody"] == 3000


def test_filing_deposit_refunded_on_contested_void(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_with_deposit(direct_vm, c, direct_alice, direct_bob, deposit=2500)
    direct_vm.sender = direct_alice
    direct_vm.value = 2000
    direct_vm.warp(_iso(T0 + 600))
    c.challenge_verdict_payable("D1")
    direct_vm.warp(_iso(T0 + 7201))
    assert c.execute_decree_settlement("D1").startswith("VOID:")
    assert c.get_refundable_balance(_hex(direct_alice)) == 2500
    assert c.get_custody_accounting_summary()["native_escrow_balance"] == 0


def test_filing_deposit_refunded_on_expired_void(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000, bond=1800)
    direct_vm.warp(_iso(T0 + 3600 + 3600 + 7776001))
    assert c.claim_expired_or_uncontested_refund("D1").startswith("VOID:")
    assert c.get_refundable_balance(_hex(direct_alice)) == 1800
    assert c.get_custody_accounting_summary()["native_escrow_balance"] == 0


def test_filing_deposit_refunded_on_cancel(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000, bond=1200)
    direct_vm.sender = direct_alice
    direct_vm.value = 0
    direct_vm.warp(_iso(T0 + 60))
    assert c.cancel_docket("D1") == "CANCELLED:D1"
    assert c.get_refundable_balance(_hex(direct_alice)) == 1200
    assert c.get_custody_accounting_summary()["native_escrow_balance"] == 0


# ---------------------------------------------------------------------------
# I. Challenge / appeal + contested void (Rule 10)
# ---------------------------------------------------------------------------


def test_challenge_by_party_sets_challenged(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob, award=7500, bond=4000)
    direct_vm.value = 2000
    direct_vm.warp(_iso(T0 + 600))
    rc = c.challenge_verdict_payable("D1")
    assert rc == "CHALLENGED:D1"
    assert c.get_docket("D1")["status"] == "CHALLENGED"


def test_challenge_non_party_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob)
    direct_vm.warp(_iso(T0 + 600))
    _expect_soft_fail(direct_vm, c, direct_charlie, 2000, lambda: c.challenge_verdict_payable("D1"), "NOT_A_PARTY")


def test_challenge_before_adjudication_soft_fails(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _expect_soft_fail(direct_vm, c, direct_alice, 2000, lambda: c.challenge_verdict_payable("D1"), "NOT_APPEALABLE")


def test_contested_challenge_voids_and_refunds_all(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob, award=7500, bond=4000)
    direct_vm.value = 2000
    direct_vm.warp(_iso(T0 + 600))
    c.challenge_verdict_payable("D1")
    direct_vm.warp(_iso(T0 + 7201))
    rc = c.execute_decree_settlement("D1")
    assert rc.startswith("VOID:CONTESTED_VOID_REFUND")
    # 100% principal back to claimant, bonds to respondent
    assert c.get_claimable_award(_hex(direct_alice)) == 10000
    assert c.get_claimable_award(_hex(direct_bob)) == 4000 + 2000
    assert c.get_docket("D1")["status"] == "VOID_ZERO_WINNER_REFUND"


# ---------------------------------------------------------------------------
# J. Timeout / uncontested refund (Rule 10)
# ---------------------------------------------------------------------------


def test_expired_unadjudicated_docket_void_refunds_principal(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000, rebuttal=3600, appeal=3600)
    timeout = c.get_docket("D1")["adjudication_timeout_epoch"]
    direct_vm.warp(_iso(timeout + 1))
    rc = c.claim_expired_or_uncontested_refund("D1")
    assert rc.startswith("VOID")
    assert c.get_claimable_award(_hex(direct_alice)) == 10000
    assert c.get_docket("D1")["status"] == "VOID_ZERO_WINNER_REFUND"


def test_claim_expired_before_timeout_reverts(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    direct_vm.warp(_iso(T0 + 100))
    with direct_vm.expect_revert("adjudication timeout not reached"):
        c.claim_expired_or_uncontested_refund("D1")


def test_claim_expired_after_settlement_reverts(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob)
    direct_vm.warp(_iso(T0 + 7201))
    c.execute_decree_settlement("D1")
    with direct_vm.expect_revert("already settled"):
        c.claim_expired_or_uncontested_refund("D1")


def test_cancel_docket_refunds_claimant(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    direct_vm.sender = direct_alice
    assert c.cancel_docket("D1") == "CANCELLED:D1"
    assert c.get_docket("D1")["status"] == "CANCELLED"
    assert c.get_cet_balance(_hex(direct_alice)) == 500000  # principal returned


def test_cancel_blocked_when_briefs_exist(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _filed_ready_docket(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_charlie
    c.file_amicus_brief("D1", "charlie", "SUPPORT_CLAIMANT", "x")
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("jurors have filed"):
        c.cancel_docket("D1")


def test_cancel_blocked_for_non_claimant(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only claimant"):
        c.cancel_docket("D1")


# ---------------------------------------------------------------------------
# K. Rule 5 coherence + views + refund custody
# ---------------------------------------------------------------------------


def test_view_and_settlement_never_diverge(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _adjudicated_ready(direct_vm, c, direct_alice, direct_bob, award=7500, bond=4000)
    pre = c.get_docket("D1")
    direct_vm.warp(_iso(T0 + 7201))
    c.execute_decree_settlement("D1")
    post = c.get_docket("D1")
    # the same invariant helper drives both the view and settlement
    assert pre["derived_claimant_payout"] == post["derived_claimant_payout"] == 7500
    assert pre["verdict_band"] == "MAJORITY_CLAIMANT_SPLIT"


def test_get_all_dockets_and_stats(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob, principal=10000)
    direct_vm.value = 0
    _file(direct_vm, c, direct_alice, direct_bob, did="D2", principal=5000)
    assert len(c.get_all_dockets()) == 2
    stats = c.get_tribunal_stats()
    assert stats["total_dockets"] == 2
    assert stats["open_dockets"] == 2
    assert stats["vault_custody_balance"] == 15000


def test_custody_summary_tracks_refundable_custody(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 1234,
        lambda: c.file_dispute_payable("D1", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 3600),
        "DUPLICATE_DOCKET_ID",
    )
    assert c.get_custody_accounting_summary()["total_refundable_custody"] == 1234


def test_refund_claim_zero_when_nothing(direct_vm, direct_deploy, direct_charlie):
    c = _deploy(direct_vm, direct_deploy, direct_charlie)
    direct_vm.sender = direct_charlie
    assert c.claim_refundable_balance() == 0
    assert c.withdraw_refund(500) == "WITHDRAW_NO_REFUND_AVAILABLE"


def test_withdraw_refund_clamps_overrequest(direct_vm, direct_deploy, direct_alice, direct_bob):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    _fund(direct_vm, c, direct_alice, 500000)
    _file(direct_vm, c, direct_alice, direct_bob)
    _expect_soft_fail(
        direct_vm, c, direct_alice, 800,
        lambda: c.file_dispute_payable("D1", _hex(direct_bob), "T", "https://a.dev/s", "https://a.dev/p", "s", "T", 100, 3600, 3600),
        "DUPLICATE_DOCKET_ID",
    )
    direct_vm.sender = direct_alice
    out = c.withdraw_refund(10_000)  # clamp to 800
    assert out == "WITHDRAW_REFUNDED:800"
    assert c.get_refundable_balance(_hex(direct_alice)) == 0


def test_refundable_and_rejection_views_reject_bad_address(direct_vm, direct_deploy, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    with direct_vm.expect_revert("invalid address"):
        c.get_refundable_balance("nope")
    with direct_vm.expect_revert("invalid address"):
        c.get_last_payable_rejection("nope")


def test_get_docket_missing_reverts(direct_vm, direct_deploy, direct_alice):
    c = _deploy(direct_vm, direct_deploy, direct_alice)
    with direct_vm.expect_revert("docket not found"):
        c.get_docket("NOPE")
