// Pure, deterministic mirrors of the on-chain Chancery settlement math in
// contracts/court_of_code.py so the workbench can preview an exact decree before
// any transaction is submitted. Every function is a faithful port of the contract.

export const AWARD_LADDER = [0, 2500, 5000, 7500, 10000] as const;
export const BASELINE_GRID = 500;
export const BPS_MAX = 10000;

export type VerdictBand =
  | "FULL_CLAIMANT_DECREE"
  | "MAJORITY_CLAIMANT_SPLIT"
  | "EQUITABLE_FIFTY_SPLIT"
  | "PARTIAL_CONTRIBUTION_AWARD"
  | "RESPONDENT_SUMMARY_DISMISSAL";

export function clampBps(bps: number): number {
  if (!Number.isFinite(bps)) return 0;
  return Math.max(0, Math.min(BPS_MAX, Math.floor(bps)));
}

// The fund-moving award is snapped onto the discrete 5-anchor judicial ladder so the
// value is a label every validator must reproduce exactly, never a free-form number.
export function snapToLadder(bps: number): number {
  const v = clampBps(bps);
  let best = AWARD_LADDER[0];
  let bestDist = v - best;
  for (const anchor of AWARD_LADDER) {
    const dist = Math.abs(v - anchor);
    if (dist < bestDist) {
      best = anchor;
      bestDist = dist;
    }
  }
  return best;
}

// The specification-completeness baseline is quantized onto a fixed 500-bps grid.
export function quantizeBaseline(bps: number): number {
  const v = clampBps(bps);
  return Math.floor(v / BASELINE_GRID) * BASELINE_GRID;
}

export function bandFor(awardBps: number): VerdictBand {
  if (awardBps === 10000) return "FULL_CLAIMANT_DECREE";
  if (awardBps === 7500) return "MAJORITY_CLAIMANT_SPLIT";
  if (awardBps === 5000) return "EQUITABLE_FIFTY_SPLIT";
  if (awardBps === 2500) return "PARTIAL_CONTRIBUTION_AWARD";
  return "RESPONDENT_SUMMARY_DISMISSAL";
}

export interface DerivedPayouts {
  claimantPayout: number;
  respondentRefund: number;
  slashAmount: number;
}

export function derivePayouts(principal: number, respondentBond: number, awardBps: number): DerivedPayouts {
  const p = Math.max(0, Math.floor(principal));
  const b = Math.max(0, Math.floor(respondentBond));
  const claimantPayout = Math.floor((p * awardBps) / BPS_MAX);
  const respondentRefund = p - claimantPayout;
  const slashAmount = awardBps >= 7500 ? b : 0;
  return { claimantPayout, respondentRefund, slashAmount };
}

export interface Apportionment {
  rawAward: number;
  snappedAward: number;
  quantizedBaseline: number;
  band: VerdictBand;
  claimantCredit: number;
  respondentCredit: number;
  principal: number;
  respondentBond: number;
  conserved: boolean;
}

// Full decree pipeline: award snaps to the ladder, baseline snaps to the 500 grid,
// and the un-slashed respondent bond always returns to the respondent so the escrow
// re-sums to principal + bond exactly.
export function apportion(
  rawAward: number,
  rawBaseline: number,
  principal: number,
  respondentBond: number,
): Apportionment {
  const snappedAward = snapToLadder(rawAward);
  const quantizedBaseline = quantizeBaseline(rawBaseline);
  const band = bandFor(snappedAward);
  const { claimantPayout, respondentRefund, slashAmount } = derivePayouts(
    principal,
    respondentBond,
    snappedAward,
  );
  const p = Math.max(0, Math.floor(principal));
  const b = Math.max(0, Math.floor(respondentBond));
  const claimantCredit = claimantPayout + slashAmount;
  const respondentCredit = respondentRefund + (b - slashAmount);
  return {
    rawAward: clampBps(rawAward),
    snappedAward,
    quantizedBaseline,
    band,
    claimantCredit,
    respondentCredit,
    principal: p,
    respondentBond: b,
    conserved: claimantCredit + respondentCredit === p + b,
  };
}

export function shortAddr(addr: string): string {
  if (!addr) return "";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

export function formatEpoch(epoch: number): string {
  if (!epoch) return "--";
  return new Date(epoch * 1000).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export function remaining(nowEpoch: number, deadline: number): string {
  if (!deadline) return "--";
  const diff = deadline - nowEpoch;
  if (diff <= 0) return "closed";
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
