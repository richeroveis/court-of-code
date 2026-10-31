import { useState } from "react";
import type { CustodySummary } from "../lib/types";

interface Props {
  custody: CustodySummary | null;
  refundable: number;
  lastRejection: string;
  claimableAward: number;
  connected: boolean;
  busy: boolean;
  onClaimRefund: () => void;
  onWithdrawRefund: (amount: number) => void;
  onWithdrawAward: () => void;
  onFundCet: (amount: number) => void;
}

// Soft-Fail Custody Ledger + Payable Refund & Bond Custody Drawer: live CET escrow
// accounting plus the non-trapping GEN refund the contract credits on failed payables.
export default function CustodyDrawer({
  custody,
  refundable,
  lastRejection,
  claimableAward,
  connected,
  busy,
  onClaimRefund,
  onWithdrawRefund,
  onWithdrawAward,
  onFundCet,
}: Props) {
  const [withdrawAmt, setWithdrawAmt] = useState(0);
  const [fundAmt, setFundAmt] = useState(1_000_000);

  return (
    <section className="panel custody">
      <h2>Escrow Custody &amp; Refund Ledger</h2>
      <div className="custody-grid">
        <div className="cell">
          <div className="k">CET vault custody</div>
          <div className="v brass">{custody ? custody.vault_custody_balance : 0}</div>
        </div>
        <div className="cell">
          <div className="k">CET total supply</div>
          <div className="v">{custody ? custody.total_cet_supply : 0}</div>
        </div>
        <div className="cell">
          <div className="k">Native bond escrow</div>
          <div className="v cyan">{custody ? custody.native_escrow_balance : 0}</div>
        </div>
        <div className="cell">
          <div className="k">Refundable custody</div>
          <div className="v">{custody ? custody.total_refundable_custody : 0}</div>
        </div>
      </div>

      {connected && (
        <div className="drawer">
          <div className="drawer-head">
            <span>My soft-fail refund balance</span>
            <strong className="brass">{refundable} wei</strong>
          </div>
          {lastRejection && (
            <div className="rejection">
              Last payable rejection: <code>{lastRejection}</code>
            </div>
          )}
          <div className="drawer-actions">
            <button className="gold" disabled={busy || refundable === 0} onClick={onClaimRefund}>
              Claim refundable balance
            </button>
            <div className="inline">
              <input
                type="number"
                value={withdrawAmt}
                onChange={(e) => setWithdrawAmt(Number(e.target.value))}
                placeholder="amount"
              />
              <button disabled={busy || withdrawAmt <= 0} onClick={() => onWithdrawRefund(withdrawAmt)}>
                Withdraw
              </button>
            </div>
          </div>
        </div>
      )}

      {connected && (
        <div className="drawer">
          <div className="drawer-head">
            <span>My decree awards (CET)</span>
            <strong className="cyan">{claimableAward}</strong>
          </div>
          <div className="drawer-actions">
            <button className="gold" disabled={busy || claimableAward === 0} onClick={onWithdrawAward}>
              Withdraw award to CET
            </button>
            <div className="inline">
              <input
                type="number"
                value={fundAmt}
                onChange={(e) => setFundCetValue(setFundAmt, Number(e.target.value))}
                placeholder="GEN wei"
              />
              <button disabled={busy || fundAmt <= 0} onClick={() => onFundCet(fundAmt)}>
                Fund CET vault
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

function setFundCetValue(setter: (n: number) => void, value: number) {
  setter(Number.isFinite(value) && value > 0 ? Math.floor(value) : 0);
}
