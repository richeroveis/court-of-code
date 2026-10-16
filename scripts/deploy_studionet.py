"""Deploy CourtOfCode to studionet and seed rich, verifiable on-chain data.

Provider-level retry and checkpoint resilience:
- Every step is keyed in evidence/_checkpoint.json. A rerun skips steps that already
  reached a FINALIZED transaction and resumes from the deployed contract address, so an
  interrupted run never re-does work or double-seeds.
- Each submission is wrapped in bounded retries with exponential backoff to survive
  transient JSON-RPC / rate-limit (-32429 / 429 / -32028) failures.
- Every write is awaited to FINALIZED and its execution result is checked, and the
  explorer-independent schema is used to prove source identity by sha256.

Run from the repository root:  python scripts/deploy_studionet.py
"""

import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

# Fail fast on hung JSON-RPC sockets so the retry loop can recover instead of
# blocking forever on a stalled studio connection.
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
from gltest.types import TransactionStatus  # noqa: E402

EVIDENCE_DIR = ROOT / "evidence"
CHECKPOINT_PATH = EVIDENCE_DIR / "_checkpoint.json"
TXLOG_PATH = EVIDENCE_DIR / "transactions.json"
CONTRACT_FILE = ROOT / "contracts" / "court_of_code.py"
CONTRACT_NAME = "CourtOfCode"

FINALIZED = TransactionStatus.FINALIZED
WAIT_INTERVAL = 4000
WAIT_RETRIES = 45

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
    markers = ["-32429", "429", "-32028", "rate", "timeout", "temporar", "connection", "reset"]
    low = err_text.lower()
    return any(m in low for m in markers)


def _safe_verify(verify):
    """Evaluate an effect-idempotency check, treating read errors as 'not yet done'."""
    if verify is None:
        return False
    try:
        return bool(verify())
    except Exception:  # noqa: BLE001 - a failed read must not crash the seed
        return False


def _transact(contract, method, args, expect_success=True, verify=None, retries=5):
    """Submit a write, await FINALIZED, verify execution result.

    Idempotency: a transient failure can occur after the transaction already landed on
    chain (the response is simply lost). Before retrying we re-check the desired effect
    via ``verify``; if it is already present we stop and return None so the caller does
    not double-apply a non-idempotent write.
    """
    last_err = None
    for attempt in range(retries):
        try:
            fn = getattr(contract, method)
            receipt = fn(args=list(args)).transact(
                wait_transaction_status=FINALIZED,
                wait_interval=WAIT_INTERVAL,
                wait_retries=WAIT_RETRIES,
            )
        except Exception as exc:  # noqa: BLE001
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
            # A revert that we did not expect, unless the effect is already present
            # (duplicate submission), in which case the earlier attempt won.
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
    except Exception:  # noqa: BLE001
        return str(receipt)[:200]


def _read(contract, method, args=None):
    last_err = None
    for attempt in range(6):
        try:
            fn = getattr(contract, method)
            return fn(args=list(args or [])).call()
        except Exception as exc:  # noqa: BLE001 - studio proxy reads are flaky
            last_err = str(exc)
            time.sleep(5 + attempt * 5)
    raise RuntimeError(f"read {method} failed after retries: {last_err}")


def _ensure_account(ckpt, key):
    """Persist generated signer keys so reruns reuse the same addresses."""
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


def _sha256_file(path):
    return _sha256_bytes(path.read_bytes())


def main():
    print("=== CourtOfCode studionet deploy + seed ===")
    ckpt = _load_checkpoint()
    factory = get_contract_factory(CONTRACT_NAME)

    owner = get_default_account()
    print(f"Owner / default account: {owner.address}")

    # Deploy (or reconnect)
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
    r_contract = contract.connect(respondent)
    j1_contract = contract.connect(juror1)
    j2_contract = contract.connect(juror2)

    def run_step(step, method, args, signer, expect_success=True, detail="", verify=None):
        # The checkpoint is authoritative: once a step recorded a finalized tx (or a
        # detected on-chain effect) it never re-runs, even if a later read is flaky.
        if ckpt["steps"].get(step, {}).get("done"):
            print(f"  [{step}] already recorded done, skipping")
            return
        if _safe_verify(verify):
            print(f"  [{step}] effect already on-chain, skipping")
            ckpt["steps"][step] = {"done": True, "effect": "present"}
            _save_checkpoint(ckpt)
            return
        signer_contract = contract_owner if signer is owner else contract.connect(signer)
        receipt = _transact(signer_contract, method, args, expect_success=expect_success, verify=verify)
        if receipt is None:
            ckpt["steps"][step] = {"done": True, "effect": "present"}
            _save_checkpoint(ckpt)
            print(f"  [{step}] done (effect present, no fresh tx)")
            return
        _record_tx(ckpt, step, method, receipt, detail)

    def _status(cid):
        return _read(contract_owner, "get_case", [cid])["status"]

    def _counters():
        st = _read(contract_owner, "get_tribunal_stats")
        return st["total_cases"], st["votes_for_claimant"], st["votes_for_respondent"]

    def _brief_upvotes(bid):
        for b in _read(contract_owner, "get_case_briefs", [1]):
            if b["brief_id"] == bid:
                return b["upvotes"]
        return -1

    # 1. File two realistic open-source bounty dispute cases (claimant = owner).
    run_step(
        "file_case_1", "file_dispute_case",
        [respondent.address, "React Native offline cache bounty",
         "Ship an offline-first cache layer, keep the public api, must pass the PR-312 suite",
         "PR-312", "https://github.com/nimbus-labs/mobile/pull/312", 250000],
        owner, detail="case 1 open for rebuttal", verify=lambda: _counters()[0] >= 1,
    )
    run_step(
        "file_case_2", "file_dispute_case",
        [respondent.address, "Rust telemetry pipeline bounty",
         "Migrate the telemetry ingestion to rust, keep p99 latency under 40ms",
         "RUST-9", "https://github.com/nimbus-labs/telemetry/pull/9", 180000],
        owner, detail="case 2 open for rebuttal", verify=lambda: _counters()[0] >= 2,
    )

    # 2. Respondent submits a rebuttal on case 1 (transitions to READY_FOR_TRIAL).
    run_step(
        "submit_rebuttal", "submit_respondent_rebuttal",
        [1, "https://github.com/nimbus-labs/mobile/pull/318",
         "Cache layer drops writes under airplane mode; the suite is not actually green"],
        respondent, detail="case 1 -> READY_FOR_TRIAL",
        verify=lambda: _status(1) != "OPEN_FOR_REBUTTAL",
    )

    # 3. Two community jurors file amicus briefs on case 1.
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

    # 4. juror2 upvotes juror1's brief (cross-upvote, not a self-upvote).
    run_step(
        "upvote_brief", "upvote_amicus_brief",
        [1], juror2, detail="brief 1 upvoted by juror2",
        verify=lambda: _brief_upvotes(1) >= 1,
    )

    # 5. Adjudicate case 1 with a proportional split award (owner deterministic path).
    run_step(
        "adjudicate_case_1", "adjudicate_case_deterministic",
        [1, 6000, "Deliverable substantially meets spec but a known regression remains; 60/40 split"],
        owner, detail="case 1 -> ADJUDICATED 6000 bps",
        verify=lambda: _status(1) == "ADJUDICATED",
    )

    # 6. Expected rollback: withdrawing a party with no award must revert.
    run_step(
        "expected_rollback", "withdraw_award",
        [], juror1, expect_success=False,
        detail="juror1 holds no award; withdrawal reverts and applies no state change",
    )

    # Read back state and verify the escrow-conservation invariant live.
    print("--- verifying on-chain state ---")
    case1 = _read(contract_owner, "get_case", [1])
    stats = _read(contract_owner, "get_tribunal_stats")
    briefs = _read(contract_owner, "get_case_briefs", [1])
    leaderboard = _read(contract_owner, "get_juror_leaderboard")
    claimant_award = _read(contract_owner, "get_claimable_award", [owner.address])
    respondent_award = _read(contract_owner, "get_claimable_award", [respondent.address])

    conserved = case1["claimant_payout"] + case1["respondent_payout"] == case1["disputed_escrow"]
    print(f"case 1 status={case1['status']} verdict={case1['verdict_label']} "
          f"bps={case1['claimant_award_bps']} payouts={case1['claimant_payout']}/{case1['respondent_payout']} "
          f"conserved={conserved}")
    if not conserved:
        raise RuntimeError("ESCROW CONSERVATION VIOLATED on-chain")
    if case1["status"] != "ADJUDICATED":
        raise RuntimeError("case 1 not adjudicated on-chain")
    if len(briefs) != 2:
        raise RuntimeError(f"expected 2 briefs, got {len(briefs)}")

    # Rollback verification: juror1 must still have zero claimable award.
    juror1_award = _read(contract_owner, "get_claimable_award", [juror1.address])
    print(f"juror1 claimable after rollback attempt (must be 0): {juror1_award}")
    if juror1_award != 0:
        raise RuntimeError("rollback step unexpectedly moved funds")

    # 3-way sha256 identity proof.
    print("--- verifying source identity (sha256) ---")
    # The studionet client guards schema RPC to localnet; the hosted-studio client
    # (localnet chain object pointed at the studio endpoint) passes that guard while
    # still querying the live studio RPC, so schema hashes come from the network.
    from gltest.clients import get_gl_hosted_studio_client

    client = get_gl_hosted_studio_client()

    def _retry(fn):
        last = None
        for attempt in range(6):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
                time.sleep(5 + attempt * 5)
        raise RuntimeError(f"schema RPC failed: {last}")

    local_file_hash = _sha256_bytes(CONTRACT_FILE.read_bytes().replace(b"\r\n", b"\n"))
    submitted_code_hash = _sha256_bytes(factory.contract_code.encode("utf-8"))
    schema_onchain = _retry(lambda: client.get_contract_schema(address))
    schema_from_source = _retry(lambda: client.get_contract_schema_for_code(factory.contract_code))
    onchain_hash = _sha256_bytes(json.dumps(schema_onchain, sort_keys=True).encode())
    source_derived_hash = _sha256_bytes(json.dumps(schema_from_source, sort_keys=True).encode())
    print(f"H1 local file        : {local_file_hash}")
    print(f"H2 submitted code    : {submitted_code_hash}")
    print(f"H3 on-chain schema   : {onchain_hash}")
    print(f"H3b source schema    : {source_derived_hash}")
    identity = {
        "local_file_sha256": local_file_hash,
        "submitted_code_sha256": submitted_code_hash,
        "onchain_schema_sha256": onchain_hash,
        "source_derived_schema_sha256": source_derived_hash,
        "file_matches_submitted_code": local_file_hash == submitted_code_hash,
        "onchain_matches_source": onchain_hash == source_derived_hash,
    }
    if not identity["file_matches_submitted_code"]:
        raise RuntimeError("deployed code does not match local file")
    if not identity["onchain_matches_source"]:
        raise RuntimeError("on-chain schema does not match source-derived schema")

    # Persist the full evidence bundle.
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
        "tribunal_stats": stats,
        "case_1_briefs": briefs,
        "juror_leaderboard": leaderboard,
        "claimant_award": claimant_award,
        "respondent_award": respondent_award,
        "transactions": ckpt["txs"],
    }
    TXLOG_PATH.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(f"\nSUCCESS address={address}")
    print(f"Evidence written to {TXLOG_PATH}")
    return address


if __name__ == "__main__":
    main()
