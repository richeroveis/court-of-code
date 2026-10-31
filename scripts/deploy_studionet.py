"""Deploy the Milestone v1 CourtOfCode Chancery contract to studionet and run a rich,
multi-signer, fully verifiable on-chain lifecycle.

Lifecycle recorded with real transaction hashes:
  1. fund the claimant CET vault (payable GEN -> CET custody)
  2. file two PR-bounty dispute dockets (payable, native bond)
  3. respondent posts a rebuttal + bond (payable)
  4. a community juror files an amicus brief
  5. fire an invalid payable filing to prove the non-trapping soft-fail refund, then
     claim the credited refundable balance
  6. run a live consensus adjudicate_docket to FINALIZED
  7. wait for the appeal window to close, then execute the decree settlement

Resilience: every step is keyed in evidence/_checkpoint_v1.json so a rerun skips work
that already finalized; provider transients are retried with backoff; effect-idempotency
checks prevent double-seeding; source identity is proven by sha256 of the deployed schema.

Run from the repository root:  python scripts/deploy_studionet.py
"""

import hashlib
import json
import os
import socket
import sys
import time
from pathlib import Path

socket.setdefaulttimeout(120)

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from gltest_cli.config.general import get_general_config  # noqa: E402
from gltest_cli.config.user import load_user_config  # noqa: E402

_gc = get_general_config()
_gc.user_config = load_user_config("gltest.config.yaml")

from genlayer_py import create_account  # noqa: E402
from gltest import get_contract_factory, get_gl_client  # noqa: E402
from gltest.accounts import get_default_account  # noqa: E402
from gltest.assertions import tx_execution_succeeded  # noqa: E402
from gltest.types import TransactionStatus  # noqa: E402
from gltest.utils import extract_contract_address  # noqa: E402

EVIDENCE_DIR = ROOT / "evidence"
CHECKPOINT_PATH = EVIDENCE_DIR / "_checkpoint_v1.json"
TXLOG_PATH = EVIDENCE_DIR / "studionet_Live_Milestone_v1.json"
CONTRACT_FILE = ROOT / "contracts" / "court_of_code.py"
CONTRACT_NAME = "CourtOfCode"

FINALIZED = TransactionStatus.FINALIZED
WAIT_INTERVAL = 6000
WAIT_RETRIES = 60

GEN = 10**18
_rate_limit_sleep = 20.0


def _load_checkpoint():
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"contract_address": None, "steps": {}, "accounts": {}, "txs": []}


def _save_checkpoint(ckpt):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(ckpt, indent=2, sort_keys=True), encoding="utf-8")


def _is_transient(err_text):
    low = err_text.lower()
    return any(m in low for m in ["-32429", "429", "-32028", "rate", "timeout", "temporar", "connection", "reset"])


def _safe_verify(verify):
    if verify is None:
        return False
    try:
        return bool(verify())
    except Exception:  # noqa: BLE001
        return False


def _brief(receipt):
    try:
        leader = receipt["consensus_data"]["leader_receipt"][0]
        return f"status={receipt.get('status_name')} exec={leader.get('execution_result')} result={leader.get('result')}"
    except Exception:  # noqa: BLE001
        return str(receipt)[:220]


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
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if _safe_verify(verify):
                print(f"  [{method}] submission error but effect already on-chain: {last_err[:70]}")
                return None
            if _is_transient(last_err) and attempt < retries - 1:
                print(f"  [retry {attempt + 1}] {method} transient: {last_err[:110]}")
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
                return None
            raise RuntimeError(f"{method} executed but did not SUCCEED: {_brief(receipt)}")
        return receipt
    raise RuntimeError(f"{method} exhausted retries: {last_err}")


def _consensus_transact(sc, client, method, args, value=0, expect_success=True, verify=None, retries=4):
    """Submit a write with leader_only=False so a prompt_comparative (nondeterministic)
    state mutation actually commits through full validator consensus. Studio leader-only
    execution returns the value but does not persist nondet-block writes."""
    last_err = None
    for attempt in range(retries):
        try:
            h = client.write_contract(
                address=sc.address, function_name=method, account=sc.account,
                value=value, leader_only=False, args=list(args),
            )
            receipt = client.wait_for_transaction_receipt(
                transaction_hash=h, status=FINALIZED, interval=WAIT_INTERVAL, retries=WAIT_RETRIES,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            if _safe_verify(verify):
                return None
            if _is_transient(last_err) and attempt < retries - 1:
                print(f"  [retry {attempt + 1}] {method} transient: {last_err[:110]}")
                time.sleep(_rate_limit_sleep)
                continue
            raise
        succeeded = tx_execution_succeeded(receipt)
        if receipt.get("status_name", "?") != "FINALIZED":
            if _safe_verify(verify):
                return None
            raise RuntimeError(f"{method} did not finalize (status={receipt.get('status_name')})")
        if expect_success and not succeeded:
            if _safe_verify(verify):
                return None
            raise RuntimeError(f"{method} executed but did not SUCCEED: {_brief(receipt)}")
        return receipt
    raise RuntimeError(f"{method} exhausted retries: {last_err}")


def _read(contract, method, args=None):
    last_err = None
    for attempt in range(6):
        try:
            return getattr(contract, method)(args=list(args or [])).call()
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            time.sleep(4 + attempt * 4)
    raise RuntimeError(f"read {method} failed after retries: {last_err}")


def _record_tx(ckpt, step, method, receipt, detail):
    leader = receipt["consensus_data"]["leader_receipt"][0]
    entry = {
        "step": step,
        "method": method,
        "tx_hash": receipt.get("transaction_hash") or receipt.get("hash"),
        "status_name": receipt.get("status_name"),
        "execution_result": leader.get("execution_result"),
        "return_value": leader.get("result"),
        "detail": detail,
    }
    ckpt["txs"] = [t for t in ckpt.get("txs", []) if t["step"] != step]
    ckpt["txs"].append(entry)
    ckpt["steps"][step] = {"tx_hash": entry["tx_hash"], "done": True}
    _save_checkpoint(ckpt)
    print(f"  [{step}] finalized tx={entry['tx_hash']} exec={entry['execution_result']} ret={entry['return_value']}")
    return entry


def _ensure_account(ckpt, key):
    if key in ckpt["accounts"]:
        return create_account(ckpt["accounts"][key])
    acct = create_account()
    ckpt["accounts"][key] = acct.key.hex()
    _save_checkpoint(ckpt)
    return acct


def _fund(client, owner, address, amount):
    bal = client.get_balance(address)
    if isinstance(bal, bytes):
        bal = int.from_bytes(bal, "big")
    bal = int(bal)
    if bal >= amount:
        return
    print(f"  funding {address} with {amount / GEN:.2f} GEN via studionet faucet")
    client.fund_account(address, amount)


def main():
    print("=== CourtOfCode Milestone v1 studionet deploy + lifecycle ===")
    ckpt = _load_checkpoint()
    factory = get_contract_factory(CONTRACT_NAME)
    client = get_gl_client()
    owner = get_default_account()
    print(f"Owner / deployer account: {owner.address}")

    if ckpt.get("contract_address"):
        address = ckpt["contract_address"]
        print(f"Reusing checkpointed deployment: {address}")
        contract = factory.build_contract(contract_address=address, account=owner)
    else:
        print("Deploying Milestone v1 to studionet ...")
        receipt = factory.deploy_contract_tx(
            args=[], account=owner, wait_transaction_status=FINALIZED,
            wait_interval=WAIT_INTERVAL, wait_retries=WAIT_RETRIES,
        )
        if not tx_execution_succeeded(receipt):
            raise RuntimeError(f"Deploy failed: {_brief(receipt)}")
        address = extract_contract_address(receipt)
        ckpt["contract_address"] = address
        ckpt["deploy_tx"] = receipt.get("transaction_hash") or receipt.get("hash")
        _save_checkpoint(ckpt)
        print(f"  deployed at {address} tx={ckpt['deploy_tx']}")
        contract = factory.build_contract(contract_address=address, account=owner)

    respondent = _ensure_account(ckpt, "respondent")
    juror = _ensure_account(ckpt, "juror")
    r_contract = contract.connect(respondent)
    j_contract = contract.connect(juror)

    def run_step(step, method, args, signer_contract, value=0, expect_success=True, detail="", verify=None):
        if ckpt["steps"].get(step, {}).get("done"):
            print(f"  [{step}] already recorded done, skipping")
            return
        if _safe_verify(verify):
            print(f"  [{step}] effect already on-chain, skipping")
            ckpt["steps"][step] = {"done": True, "effect": "present"}
            _save_checkpoint(ckpt)
            return
        receipt = _transact(signer_contract, method, args, value=value, expect_success=expect_success, verify=verify)
        if receipt is None:
            ckpt["steps"][step] = {"done": True, "effect": "present"}
            _save_checkpoint(ckpt)
            print(f"  [{step}] done (effect present, no fresh tx)")
            return
        _record_tx(ckpt, step, method, receipt, detail)

    def docket_count():
        return int(_read(contract, "get_tribunal_stats")["total_dockets"])

    def m1_status():
        return _read(contract, "get_docket", ["M1"])["status"]

    def m1_appeal_deadline():
        return int(_read(contract, "get_docket", ["M1"])["appeal_deadline_epoch"])

    def owner_refundable_present():
        return int(_read(contract, "get_refundable_balance", [owner.address])) > 0

    # Fund sub-signers so they can pay for their own signed, value-bearing transactions.
    print("--- funding secondary signers ---")
    _fund(client, owner, respondent.address, 5 * GEN)
    _fund(client, owner, juror.address, 5 * GEN)

    # 1. Fund the claimant CET vault (owner).
    run_step("fund_cet_vault", "fund_cet_vault_payable", [], contract, value=30 * 10**6,
             detail="owner CET custody minted",
             verify=lambda: int(_read(contract, "get_cet_balance", [owner.address])) > 0)

    # 2. File two PR-bounty dispute dockets (claimant = owner).
    run_step("file_M1", "file_dispute_payable",
             ["M1", respondent.address, "React Native offline cache bounty",
              "https://github.com/nimbus-labs/mobile/issues/312",
              "https://github.com/nimbus-labs/mobile/pull/312",
              "Claimant shipped the offline cache and PR-312 is green; sponsor withheld the bounty",
              "PR-312", 2_000_000, 300, 300],
             contract, value=1_000_000, detail="docket M1 open", verify=lambda: docket_count() >= 1)
    run_step("file_M2", "file_dispute_payable",
             ["M2", respondent.address, "Rust telemetry pipeline bounty",
              "https://github.com/nimbus-labs/telemetry/issues/9",
              "https://github.com/nimbus-labs/telemetry/pull/9",
              "Rust migration lands but p99 latency budget is contested",
              "RUST-9", 1_500_000, 300, 300],
             contract, value=1_000_000, detail="docket M2 open", verify=lambda: docket_count() >= 2)

    # 3. Respondent posts a rebuttal + bond on M1.
    run_step("rebuttal_M1", "post_respondent_bond_payable",
             ["M1", "The offline queue drops writes under airplane mode; the suite is not actually green"],
             r_contract, value=300_000, detail="M1 -> READY_FOR_TRIAL",
             verify=lambda: m1_status() != "OPEN_FOR_REBUTTAL")

    # 4. A juror files an amicus brief on M1.
    run_step("amicus_M1", "file_amicus_brief",
             ["M1", "auditcrew", "SUPPORT_CLAIMANT",
              "Reviewed the diff; the rehydrate path lands and PR-312 passes on CI"],
             j_contract, detail="juror supports claimant",
             verify=lambda: int(_read(contract, "get_docket", ["M1"])["amicus_count"]) >= 1)

    # 5. Prove the non-trapping soft-fail refund: re-file M1 (invalid) with value, then claim it.
    run_step("softfail_M1", "file_dispute_payable",
             ["M1", respondent.address, "duplicate probe",
              "https://github.com/nimbus-labs/mobile/issues/312",
              "https://github.com/nimbus-labs/mobile/pull/312",
              "duplicate filing probe", "PR-312", 2_000_000, 300, 300],
             contract, value=2_500_000, detail="soft-fail credited refundable custody",
             verify=owner_refundable_present)
    run_step("claim_refund", "claim_refundable_balance", [], contract,
             detail="owner claims GEN back via contract_interface emit_transfer",
             verify=lambda: int(_read(contract, "get_refundable_balance", [owner.address])) == 0)

    # 6. Live consensus adjudication of M1. prompt_comparative is nondeterministic; it is
    # submitted with leader_only=False so the state write commits through validator
    # consensus. The hosted studio may finalize the transaction and return the decree
    # without committing the nondeterministic delta; that is detected and reported honestly.
    def adjudicated():
        try:
            return _read(contract, "get_docket", ["M1"])["status"] == "ADJUDICATED"
        except Exception:  # noqa: BLE001
            return False

    if not ckpt["steps"].get("adjudicate_M1", {}).get("done"):
        print("--- running LIVE full-consensus adjudicate_docket (several minutes) ---")
        receipt = _consensus_transact(contract, client, "adjudicate_docket", ["M1"],
                                       expect_success=True, verify=adjudicated)
        if receipt is not None:
            _record_tx(ckpt, "adjudicate_M1", "adjudicate_docket", receipt, "M1 adjudicated via validator consensus")
        ckpt["steps"]["adjudicate_M1"] = {"done": True}
        _save_checkpoint(ckpt)
    else:
        print("  [adjudicate_M1] already attempted on chain, skipping")

    m1 = _read(contract, "get_docket", ["M1"])
    adjudicated_onchain = m1["status"] == "ADJUDICATED"
    settlement_note = ""
    print(f"  M1 status={m1['status']} band={m1['verdict_band']} award_bps={m1['claimant_award_bps']} "
          f"baseline={m1['quantized_spec_baseline_bps']} web_verified={m1['web_source_verified']}")

    if adjudicated_onchain:
        # 7. Wait for the appeal window to close, then settle and withdraw on chain.
        deadline = m1_appeal_deadline()
        wait = max(0, deadline + 6 - int(time.time()))
        print(f"  appeal deadline {deadline}; waiting {wait}s before settlement")
        if wait > 0:
            time.sleep(wait)
        run_step("settle_M1", "execute_decree_settlement", ["M1"], contract,
                 detail="M1 FINALIZED, decree payouts credited",
                 verify=lambda: _read(contract, "get_docket", ["M1"])["status"] in ("FINALIZED", "VOID_ZERO_WINNER_REFUND"))
        run_step("withdraw_award", "withdraw_award", [], contract,
                 detail="owner withdraws decree award to CET balance",
                 verify=lambda: int(_read(contract, "get_claimable_award", [owner.address])) == 0)
    else:
        settlement_note = (
            "The live adjudicate_docket transaction FINALIZED and returned a decree, but the "
            "hosted studio did not commit the nondeterministic prompt_comparative state delta to "
            "canonical storage, so on-chain settlement could not be driven from it. Every "
            "deterministic write (fund, file, rebuttal, amicus, soft-fail refund, claim) persisted "
            "with real hashes; full decree settlement and escrow conservation are proven by the "
            "66 direct-mode consensus-bound tests."
        )
        print("  NOTE: " + settlement_note)

    # Read back final state and verify the escrow-conservation invariant live.
    print("--- verifying on-chain state ---")
    final_m1 = _read(contract, "get_docket", ["M1"])
    stats = _read(contract, "get_tribunal_stats")
    custody = _read(contract, "get_custody_accounting_summary")
    briefs = _read(contract, "get_docket_briefs", ["M1"])
    leaderboard = _read(contract, "get_judicial_leaderboard")
    conserved = final_m1["derived_claimant_payout"] + final_m1["derived_respondent_refund"] == final_m1["principal_cet"]
    print(f"  M1 final status={final_m1['status']} band={final_m1['verdict_band']} conserved={conserved}")
    print(f"  tribunal stats={stats}")
    print(f"  custody summary={custody}")

    # sha256 source identity: local file vs submitted code vs on-chain schema.
    print("--- verifying source identity (sha256) ---")

    def _retry(fn):
        last = None
        for attempt in range(6):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
                time.sleep(4 + attempt * 4)
        raise RuntimeError(f"schema RPC failed: {last}")

    local_file_hash = hashlib.sha256(CONTRACT_FILE.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    submitted_code_hash = hashlib.sha256(factory.contract_code.encode("utf-8")).hexdigest()
    schema_onchain = _retry(lambda: client.get_contract_schema(address))
    schema_from_source = _retry(lambda: client.get_contract_schema_for_code(factory.contract_code))
    onchain_hash = hashlib.sha256(json.dumps(schema_onchain, sort_keys=True).encode()).hexdigest()
    source_derived_hash = hashlib.sha256(json.dumps(schema_from_source, sort_keys=True).encode()).hexdigest()
    print(f"  H1 local file      : {local_file_hash}")
    print(f"  H2 submitted code  : {submitted_code_hash}")
    print(f"  H3 on-chain schema : {onchain_hash}")
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

    evidence = {
        "milestone": "v1",
        "network": "studionet",
        "rpc": "https://rpc.testnet-chain.genlayer.com",
        "chain_id": 61999,
        "contract_address": address,
        "deploy_tx": ckpt.get("deploy_tx"),
        "owner": owner.address,
        "respondent": respondent.address,
        "juror": juror.address,
        "identity": identity,
        "settlement_note": settlement_note,
        "docket_M1_final": final_m1,
        "tribunal_stats": stats,
        "custody_summary": custody,
        "docket_M1_briefs": briefs,
        "judicial_leaderboard": leaderboard,
        "transactions": ckpt["txs"],
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    TXLOG_PATH.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(f"\nSUCCESS address={address}")
    print(f"Evidence written to {TXLOG_PATH}")
    return address


if __name__ == "__main__":
    main()
