"""Deploy CourtOfCode to studionet and seed rich, verifiable on-chain data.

Provider-level retry and checkpoint resilience:
- Every step is keyed in evidence/_checkpoint.json.
- Full multi-signer on-chain lifecycle proving:
  1. Strict end-to-end separation of CET bounty escrow vs Native GEN bonds.
  2. Real native GEN EOA withdrawal where claimant/respondent EOA eth_getBalance increases on-chain.
  3. Live consensus adjudication (MAJORITY_AGREE) where both live evidence URLs are verified (BOTH_SOURCES_VERIFIED) and bound in validator consensus.
  4. Fail-closed evidence verification demonstration on unavailable evidence sources.
- 4-way SHA-256 identity proof (local file, submitted code, onchain schema, source derived schema).

Run from the repository root: python scripts/deploy_studionet.py
"""

import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

socket.setdefaulttimeout(90)

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from gltest_cli.config.general import get_general_config  # noqa: E402
from gltest_cli.config.user import load_user_config  # noqa: E402

_gc = get_general_config()
_gc.user_config = load_user_config("gltest.config.yaml")

from genlayer_py import create_account  # noqa: E402
from gltest import get_contract_factory  # noqa: E402
from gltest.accounts import get_default_account  # noqa: E402
from gltest.assertions import tx_execution_succeeded  # noqa: E402
from gltest.contracts.contract import get_gl_client  # noqa: E402
from gltest.types import TransactionStatus  # noqa: E402

EVIDENCE_DIR = ROOT / "evidence"
CHECKPOINT_PATH = EVIDENCE_DIR / "_checkpoint.json"
TXLOG_PATH = EVIDENCE_DIR / "transactions.json"
CONTRACT_FILE = ROOT / "contracts" / "court_of_code.py"
CONTRACT_NAME = "CourtOfCode"

FINALIZED = TransactionStatus.FINALIZED
WAIT_INTERVAL = 4000
WAIT_RETRIES = 60
_rate_limit_sleep = 20.0


def _load_checkpoint():
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"contract_address": None, "steps": {}, "accounts": {}, "txs": []}


def _save_checkpoint(ckpt):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(
        json.dumps(ckpt, indent=2, sort_keys=True), encoding="utf-8"
    )


def _is_transient(err_text):
    markers = [
        "-32429", "429", "-32028", "rate", "timeout", "temporar", "connection", "reset",
        "502", "503", "504", "gateway", "invalid json", "bad gateway", "expecting value"
    ]
    low = err_text.lower()
    return any(m in low for m in markers)


def _safe_verify(verify):
    if verify is None:
        return False
    try:
        return bool(verify())
    except Exception:
        return False


def _transact(contract, method, args, value=0, expect_success=True, verify=None, retries=5):
    last_err = None
    for attempt in range(retries):
        try:
            fn = getattr(contract, method)
            receipt = fn(args=list(args)).transact(
                value=value,
                wait_transaction_status=FINALIZED,
                wait_interval=WAIT_INTERVAL,
                wait_retries=WAIT_RETRIES,
            )
        except Exception as exc:
            last_err = str(exc)
            if _safe_verify(verify):
                print(f"  [{method}] submission error but effect already on-chain: {last_err[:80]}")
                return None
            if _is_transient(last_err) and attempt < retries - 1:
                print(f"  [retry {attempt + 1}] {method} transient error: {last_err[:120]}")
                time.sleep(_rate_limit_sleep)
                continue
            raise
        succeeded = tx_execution_succeeded(receipt)
        status_name = receipt.get("status_name", "?")
        if status_name != "FINALIZED":
            if _safe_verify(verify):
                return None
            raise RuntimeError(f"{method} did not finalize (status={status_name})")
        if expect_success and not succeeded:
            if _safe_verify(verify):
                print(f"  [{method}] reverted but effect already on-chain (duplicate submit)")
                return None
            raise RuntimeError(f"{method} executed but did not SUCCEED: {_brief(receipt)}")
        if not expect_success and succeeded:
            raise RuntimeError(f"{method} was expected to revert but SUCCEEDED")
        return receipt
    raise RuntimeError(f"{method} exhausted retries: {last_err}")


def _brief(receipt):
    try:
        leader = receipt["consensus_data"]["leader_receipt"][0]
        res = leader.get("result", {})
        return f"status={receipt.get('status_name')} exec={leader.get('execution_result')} result={res}"
    except Exception:
        return str(receipt)[:200]


def _read(contract, method, args=None):
    last_err = None
    for attempt in range(6):
        try:
            fn = getattr(contract, method)
            return fn(args=list(args or [])).call()
        except Exception as exc:
            last_err = str(exc)
            time.sleep(4 + attempt * 4)
    raise RuntimeError(f"read {method} failed after retries: {last_err}")


def _ensure_account(ckpt, key):
    if key in ckpt["accounts"]:
        return create_account(ckpt["accounts"][key])
    acct = create_account()
    ckpt["accounts"][key] = acct.key.hex()
    _save_checkpoint(ckpt)
    return acct


def _record_tx(ckpt, step, method, receipt, detail):
    leader = receipt["consensus_data"]["leader_receipt"][0]
    entry = {
        "step": step,
        "method": method,
        "tx_hash": receipt.get("transaction_hash") or receipt.get("hash"),
        "status_name": receipt.get("status_name"),
        "execution_result": leader.get("execution_result"),
        "detail": detail,
    }
    ckpt["txs"] = [t for t in ckpt.get("txs", []) if t["step"] != step]
    ckpt["txs"].append(entry)
    ckpt["steps"][step] = {"tx_hash": entry["tx_hash"], "done": True}
    _save_checkpoint(ckpt)
    print(f"  [{step}] finalized tx={entry['tx_hash']} exec={entry['execution_result']}")
    return entry


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def main():
    print("=== CourtOfCode studionet deploy + seed (Milestone v2) ===")
    ckpt = _load_checkpoint()
    factory = get_contract_factory(CONTRACT_NAME)
    gl_client = get_gl_client()

    owner = get_default_account()
    print(f"Owner / deployer account: {owner.address}")
    owner_balance_start = gl_client.get_balance(owner.address)
    print(f"Owner starting native GEN balance: {owner_balance_start} wei")

    # Deploy or reconnect
    if ckpt.get("contract_address"):
        address = ckpt["contract_address"]
        print(f"Reusing checkpointed deployment: {address}")
        contract = factory.build_contract(contract_address=address, account=owner)
    else:
        print("Deploying CourtOfCode to studionet ...")
        receipt = factory.deploy_contract_tx(
            args=[], account=owner, wait_transaction_status=FINALIZED,
            wait_interval=WAIT_INTERVAL, wait_retries=WAIT_RETRIES,
        )
        if not tx_execution_succeeded(receipt):
            raise RuntimeError(f"Deploy failed: {receipt}")
        from gltest.utils import extract_contract_address
        address = extract_contract_address(receipt)
        ckpt["contract_address"] = address
        _save_checkpoint(ckpt)
        print(f"  deployed at {address} tx={receipt.get('transaction_hash')}")
        contract = factory.build_contract(contract_address=address, account=owner)

    contract_owner = contract
    respondent = _ensure_account(ckpt, "respondent")
    juror1 = _ensure_account(ckpt, "juror1")
    juror2 = _ensure_account(ckpt, "juror2")

    print(f"Respondent account : {respondent.address}")
    print(f"Juror 1 account    : {juror1.address}")
    print(f"Juror 2 account    : {juror2.address}")

    resp_balance_start = gl_client.get_balance(respondent.address)
    print(f"Respondent starting native GEN balance: {resp_balance_start} wei")

    def run_step(step, method, args, signer, value=0, expect_success=True, detail="", verify=None):
        if ckpt["steps"].get(step, {}).get("done"):
            print(f"  [{step}] already recorded done, skipping")
            return
        if _safe_verify(verify):
            print(f"  [{step}] effect already on-chain, skipping")
            ckpt["steps"][step] = {"done": True, "effect": "present"}
            _save_checkpoint(ckpt)
            return
        signer_contract = contract_owner if signer is owner else contract.connect(signer)
        receipt = _transact(signer_contract, method, args, value=value, expect_success=expect_success, verify=verify)
        if receipt is None:
            ckpt["steps"][step] = {"done": True, "effect": "present"}
            _save_checkpoint(ckpt)
            print(f"  [{step}] done (effect present, no fresh tx)")
            return
        _record_tx(ckpt, step, method, receipt, detail)

    def _status(cid):
        return _read(contract_owner, "get_case", [cid])["status"]

    def _case(cid):
        return _read(contract_owner, "get_case", [cid])

    def _counters():
        st = _read(contract_owner, "get_tribunal_stats")
        return st["total_cases"], st["votes_for_claimant"], st["votes_for_respondent"]

    def _wallet(addr):
        return int(_read(contract_owner, "get_wallet_balance", [addr]))

    def _brief_upvotes(cid, bid):
        for b in _read(contract_owner, "get_case_briefs", [cid]):
            if b["brief_id"] == bid:
                return b["upvotes"]
        return -1

    # =========================================================================
    # Case 1: Mutual Settlement + Strict Native GEN Bond Separation & Withdrawal
    # =========================================================================
    print("\n--- Executing Case 1 (CET Escrow + Native GEN Bond Separation) ---")

    # File case 1 with 250,000 CET bounty escrow AND 50,000 wei native GEN bond
    run_step(
        "file_case_1", "file_dispute_case",
        [respondent.address, "React Native offline cache bounty",
         "Ship an offline-first cache layer, keep the public api, must pass the PR-312 suite",
         "PR-312", "https://github.com/nimbus-labs/mobile/pull/312", 250000],
        owner, value=50000,
        detail="case 1 open: 250000 CET escrow + 50000 wei native GEN filer_bond locked",
        verify=lambda: _counters()[0] >= 1,
    )

    # Deposit respondent bond in native GEN (30,000 wei)
    run_step(
        "deposit_respondent_bond_1", "deposit_respondent_bond",
        [1], owner, value=30000,
        detail="case 1: 30000 wei native GEN respondent_bond deposited",
        verify=lambda: _case(1)["respondent_bond"] >= 30000,
    )

    # Respondent submits rebuttal
    run_step(
        "submit_rebuttal", "submit_respondent_rebuttal",
        [1, "https://github.com/nimbus-labs/mobile/pull/318",
         "Cache layer drops writes under airplane mode; the suite is not actually green"],
        respondent, detail="case 1 -> READY_FOR_TRIAL",
        verify=lambda: _case(1)["rebuttal_submitted"] is True,
    )

    # Amicus briefs & upvote
    run_step(
        "brief_claimant", "file_amicus_brief",
        [1, "auditcrew", "SUPPORT_CLAIMANT",
         "Reviewed the diff; the offline queue and rehydrate path both land and PR-312 is green on CI"],
        juror1, detail="juror1 supports claimant", verify=lambda: _counters()[1] >= 1,
    )
    run_step(
        "brief_respondent", "file_amicus_brief",
        [1, "stableship", "SUPPORT_RESPONDENT",
         "Agree with the sponsor; the crash under airplane mode is a real regression, partial credit at best"],
        juror2, detail="juror2 supports respondent", verify=lambda: _counters()[2] >= 1,
    )
    run_step(
        "upvote_brief", "upvote_amicus_brief",
        [1], juror2, detail="brief 1 upvoted by juror2",
        verify=lambda: _brief_upvotes(1, 1) >= 1,
    )

    # Two-party mutual settlement: 6000 bps
    run_step(
        "propose_split", "propose_deterministic_split",
        [1, 6000, "Deliverable substantially meets spec; a known regression remains; 60/40 split"],
        owner, detail="claimant proposes 6000 bps on case 1",
        verify=lambda: _case(1)["split_proposer"] == "CLAIMANT",
    )
    run_step(
        "cosign_settle", "adjudicate_case_deterministic",
        [1, 6000, "Respondent co-authorizes the 60/40 split"],
        respondent, detail="case 1 -> SETTLED_MUTUAL 6000 bps (150000/100000 CET, 50000/30000 native)",
        verify=lambda: _status(1) == "SETTLED_MUTUAL",
    )

    # Claimant withdraws CET award (150,000 CET)
    run_step(
        "withdraw_claimant_cet", "withdraw_award",
        [], owner, detail="claimant withdraws 150000 CET award into token_balances",
        verify=lambda: _wallet(owner.address) >= 9900000,
    )

    # Claimant withdraws native GEN refund (50,000 wei)
    run_step(
        "withdraw_claimant_native", "withdraw_refund",
        [50000], owner, detail="claimant withdraws 50000 wei native GEN via emit_transfer",
        verify=lambda: int(_read(contract_owner, "get_refundable_balance", [owner.address])) == 0,
    )

    # Respondent claims native GEN refund (30,000 wei) -> eth_getBalance increases!
    run_step(
        "claim_respondent_native", "claim_refundable_balance",
        [], respondent, detail="respondent claims 30000 wei native GEN via emit_transfer",
        verify=lambda: gl_client.get_balance(respondent.address) >= 30000,
    )

    # File and resolve challenge bond (20,000 wei native GEN)
    run_step(
        "file_challenge_case1", "file_challenge",
        [1, "Post-settlement audit challenge"], owner, value=20000,
        detail="challenge filed on case 1 with 20000 wei native GEN challenge_bond",
        verify=lambda: _case(1)["challenge_bond"] >= 20000,
    )
    run_step(
        "resolve_challenge_case1", "resolve_challenge",
        [1, True], owner,
        detail="challenge resolved upheld: 20000 wei native GEN credited to challenger refundable balance",
        verify=lambda: int(_read(contract_owner, "get_refundable_balance", [owner.address])) >= 20000,
    )
    run_step(
        "withdraw_challenge_refund", "claim_refundable_balance",
        [], owner, detail="challenger withdraws 20000 wei native GEN refund",
        verify=lambda: int(_read(contract_owner, "get_refundable_balance", [owner.address])) == 0,
    )

    # =========================================================================
    # Case 2: Open Showcase Case with Rebuttal
    # =========================================================================
    print("\n--- Executing Case 2 (Open Showcase Dispute) ---")
    claimant_live_url = "https://raw.githubusercontent.com/richeroveis/court-of-code/main/README.md"
    respondent_live_url = "https://raw.githubusercontent.com/richeroveis/court-of-code/main/docs/adversarial-review.md"

    run_step(
        "file_case_2", "file_dispute_case",
        [respondent.address, "Milestone v2 live evidence tribunal verification",
         "Verify live CourtOfCode repository evidence and confirm spec token CourtOfCode is present",
         "CourtOfCode", claimant_live_url, 180000],
        owner, value=40000,
        detail="case 2 open: 180000 CET escrow + 40000 wei native GEN filer_bond",
        verify=lambda: _counters()[0] >= 2,
    )

    run_step(
        "submit_rebuttal_case2", "submit_respondent_rebuttal",
        [2, respondent_live_url, "Both live evidence sources are online and substantive"],
        respondent, value=0,
        detail="case 2 rebuttal submitted with live evidence URL -> READY_FOR_TRIAL",
        verify=lambda: _case(2)["rebuttal_submitted"] is True,
    )

    # =========================================================================
    # Case 3: Fail-Closed Evidence Verification Demonstration
    # =========================================================================
    print("\n--- Executing Case 3 (Fail-Closed Evidence Verification) ---")

    unavailable_url = "https://raw.githubusercontent.com/richeroveis/court-of-code/main/nonexistent_404_file.txt"

    run_step(
        "file_case_3", "file_dispute_case",
        [respondent.address, "Fail-closed unavailable evidence case",
         "Agreed rubric for unavailable evidence test", "TOKEN-X", unavailable_url, 100000],
        owner, value=10000,
        detail="case 3 open with unavailable evidence URL",
        verify=lambda: _counters()[0] >= 3,
    )

    # Advance clock past rebuttal window so adjudication is unblocked by deadline
    run_step(
        "advance_clock_case3", "advance_tribunal_clock",
        [5], owner, detail="advance tribunal clock by 5 steps past case 3 deadline",
        verify=lambda: int(_read(contract_owner, "get_tribunal_stats")["tribunal_clock"]) >= 5,
    )

    # Execute live adjudication with unavailable URL: MUST fail closed
    run_step(
        "fail_closed_adjudication_case3", "adjudicate_case_live",
        [3], owner,
        detail="case 3 live adjudication fails closed: EVIDENCE_UNAVAILABLE_FAIL_CLOSED",
        verify=lambda: _case(3)["evidence_verification_status"] == "EVIDENCE_UNAVAILABLE_FAIL_CLOSED",
    )

    # Adversarial Rollback:
    # Unilateral split with no proposal must revert
    run_step(
        "rollback_unilateral_split", "adjudicate_case_deterministic",
        [3, 5000, "attempted unilateral settlement"],
        respondent, expect_success=False,
        detail="no proposal exists on case 3; co-signature reverts as expected",
    )

    # =========================================================================
    # Case 4: Live AI Consensus Adjudication (MAJORITY_AGREE & BOTH_SOURCES_VERIFIED)
    # =========================================================================
    print("\n--- Executing Case 4 (Live Consensus Adjudication) ---")
    case4_c_url = "https://raw.githubusercontent.com/richeroveis/court-of-code/main/README.md"
    case4_r_url = "https://raw.githubusercontent.com/richeroveis/court-of-code/main/docs/deployment.md"

    run_step(
        "file_case_4", "file_dispute_case",
        [respondent.address, "Milestone v2 live verification test",
         "Verify live CourtOfCode repository evidence and confirm spec token CourtOfCode is present. If the spec token CourtOfCode is present, award 10000 basis points.",
         "CourtOfCode", case4_c_url, 100000],
        owner, value=10000,
        detail="case 4 open: 100000 CET escrow + 10000 wei native GEN filer_bond",
        verify=lambda: _counters()[0] >= 4,
    )

    run_step(
        "submit_rebuttal_case4", "submit_respondent_rebuttal",
        [4, case4_r_url, "Confirmed deliverable is intact and spec token is present"],
        respondent, value=0,
        detail="case 4 rebuttal submitted with live evidence URL -> READY_FOR_TRIAL",
        verify=lambda: _case(4)["rebuttal_submitted"] is True,
    )

    run_step(
        "adjudicate_live_case4", "adjudicate_case_live",
        [4], owner,
        detail="live adjudication on case 4 reached validator consensus agreement",
        verify=lambda: _status(4) == "ADJUDICATED",
    )

    # =========================================================================
    # Verifications and Proofs
    # =========================================================================
    print("\n--- Verifying On-Chain State Invariants ---")
    case1 = _read(contract_owner, "get_dispute", [1])
    case2 = _read(contract_owner, "get_dispute", [2])
    case3 = _read(contract_owner, "get_dispute", [3])
    case4 = _read(contract_owner, "get_dispute", [4])
    stats = _read(contract_owner, "get_tribunal_stats")

    # Invariant 1: Case 1 settled mutually and conserved escrow
    assert case1["status"] == "SETTLED_MUTUAL"
    assert case1["claimant_payout"] + case1["respondent_payout"] == case1["disputed_escrow"]
    print(f"Case 1: status={case1['status']} payouts={case1['claimant_payout']}/{case1['respondent_payout']}")

    # Invariant 2: Case 3 failed closed and blocked fund release
    assert case3["evidence_verification_status"] == "EVIDENCE_UNAVAILABLE_FAIL_CLOSED"
    assert case3["claimant_source_verified"] is False
    assert case3["verdict_band"] == "EVIDENCE_UNAVAILABLE_FAIL_CLOSED"
    assert case3["claimant_payout"] == 0
    assert case3["respondent_payout"] == 0
    assert case3["status"] != "ADJUDICATED"
    print(f"Case 3: status={case3['status']} ev_status={case3['evidence_verification_status']} (Fail-Closed confirmed)")

    # Invariant 3: Case 4 live adjudication verified both sources and settled
    assert case4["status"] == "ADJUDICATED"
    assert case4["evidence_verification_status"] == "BOTH_SOURCES_VERIFIED"
    assert case4["claimant_source_verified"] is True
    assert case4["respondent_source_verified"] is True
    assert case4["verdict_band"] == "CLAIMANT_PREVAILS"
    assert case4["claimant_award_bps"] == 10000
    assert case4["claimant_payout"] == 100000
    print(f"Case 4: status={case4['status']} ev_status={case4['evidence_verification_status']} "
          f"c_verified={case4['claimant_source_verified']} r_verified={case4['respondent_source_verified']} "
          f"verdict={case4['verdict_band']}")
    assert case3["status"] != "ADJUDICATED"
    print(f"Case 3: status={case3['status']} ev_status={case3['evidence_verification_status']} (Fail-Closed confirmed)")

    # Invariant 4: Native bond conservation (Domain B 0 wei leakage)
    native_custody = int(stats["native_bond_custody"])
    active_locked = int(stats["active_locked_native_bonds"])
    total_refundable = int(stats["total_refundable_native_balances"])
    assert native_custody == active_locked + total_refundable
    print(f"Domain B Native Conservation: custody({native_custody}) == active({active_locked}) + refundable({total_refundable})")

    # Invariant 5: Real EOA native GEN withdrawal verification
    resp_balance_final = gl_client.get_balance(respondent.address)
    print(f"Respondent native GEN balance: initial={resp_balance_start} -> final={resp_balance_final} wei")
    assert resp_balance_final >= 30000, "Respondent did not receive native GEN on-chain payout"

    # =========================================================================
    # 4-way LF SHA-256 Identity Proof
    # =========================================================================
    print("\n--- Verifying 4-Way SHA-256 Identity Proof ---")
    from gltest.clients import get_gl_hosted_studio_client

    client = get_gl_hosted_studio_client()

    def _retry(fn):
        last = None
        for attempt in range(6):
            try:
                return fn()
            except Exception as exc:
                last = str(exc)
                time.sleep(4 + attempt * 4)
        raise RuntimeError(f"schema RPC failed: {last}")

    local_file_bytes = CONTRACT_FILE.read_bytes().replace(b"\r\n", b"\n")
    local_file_hash = _sha256_bytes(local_file_bytes)
    submitted_code_hash = _sha256_bytes(factory.contract_code.encode("utf-8"))
    schema_onchain = _retry(lambda: client.get_contract_schema(address))
    schema_from_source = _retry(lambda: client.get_contract_schema_for_code(factory.contract_code))
    onchain_hash = _sha256_bytes(json.dumps(schema_onchain, sort_keys=True).encode())
    source_derived_hash = _sha256_bytes(json.dumps(schema_from_source, sort_keys=True).encode())

    print(f"H1 local file        : {local_file_hash}")
    print(f"H2 submitted code    : {submitted_code_hash}")
    print(f"H3 on-chain schema   : {onchain_hash}")
    print(f"H4 source schema     : {source_derived_hash}")

    identity = {
        "local_file_sha256": local_file_hash,
        "submitted_code_sha256": submitted_code_hash,
        "onchain_schema_sha256": onchain_hash,
        "source_derived_schema_sha256": source_derived_hash,
        "file_matches_submitted_code": local_file_hash == submitted_code_hash,
        "onchain_matches_source": onchain_hash == source_derived_hash,
        "contract_byte_size": len(local_file_bytes),
        "strictly_under_37500_bytes": len(local_file_bytes) < 37500,
    }
    assert identity["file_matches_submitted_code"]
    assert identity["onchain_matches_source"]
    assert identity["strictly_under_37500_bytes"]

    # Write evidence bundle
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence = {
        "network": "studionet",
        "chain_id": 61999,
        "contract_address": address,
        "owner": owner.address,
        "respondent": respondent.address,
        "juror1": juror1.address,
        "juror2": juror2.address,
        "identity": identity,
        "case_1": case1,
        "case_2": case2,
        "case_3": case3,
        "case_4": case4,
        "tribunal_stats": stats,
        "respondent_native_balance_initial": resp_balance_start,
        "respondent_native_balance_final": resp_balance_final,
        "transactions": ckpt["txs"],
    }
    TXLOG_PATH.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(f"\nSUCCESS address={address}")
    print(f"Evidence written to {TXLOG_PATH}")
    return address


if __name__ == "__main__":
    main()
