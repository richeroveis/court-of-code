// Pure helpers that mirror the on-chain settlement math in
// contracts/court_of_code.py so the UI can preview exact outcomes deterministically.
// Every function here is a faithful port of the contract's deterministic block.

export const BPS_LADDER = 500;
export const BPS_MAX = 10000;
export const TOKEN_CAP = 5000;

export function clampBps(bps: number): number {
  if (!Number.isFinite(bps)) return 0;
  return Math.max(0, Math.min(BPS_MAX, Math.floor(bps)));
}

// The contract snaps the raw LLM award onto a fixed 500 bps ladder so the value that
// moves funds is a discrete label every validator must reproduce exactly.
export function quantizeBps(bps: number): number {
  const c = clampBps(bps);
  return Math.floor(c / BPS_LADDER) * BPS_LADDER;
}

// A claimant cannot win a majority award without the mandatory spec token.
export function applyTokenCap(quantized: number, specTokenFound: boolean): number {
  if (!specTokenFound && quantized > TOKEN_CAP) return TOKEN_CAP;
  return quantized;
}

export function verdictLabel(bps: number): string {
  if (bps >= 6500) return "CLAIMANT_PREVAILS";
  if (bps >= 3500) return "SPLIT_REMEDY";
  return "RESPONDENT_PREVAILS";
}

// Escrow-conserving split: claimant is floored, respondent absorbs the remainder.
export function splitPayout(escrow: number, bps: number): { claimant: number; respondent: number } {
  const e = Math.max(0, Math.floor(escrow));
  const claimant = Math.floor((e * bps) / BPS_MAX);
  const respondent = e - claimant;
  return { claimant, respondent };
}

export interface Settlement {
  rawBps: number;
  quantizedBps: number;
  cappedBps: number;
  claimantPayout: number;
  respondentPayout: number;
  verdict: string;
  conserved: boolean;
}

// Full pipeline used by the what-if simulator and the split-award gauge.
export function settle(rawBps: number, escrow: number, specTokenFound: boolean): Settlement {
  const quantized = quantizeBps(rawBps);
  const capped = applyTokenCap(quantized, specTokenFound);
  const { claimant, respondent } = splitPayout(escrow, capped);
  return {
    rawBps: clampBps(rawBps),
    quantizedBps: quantized,
    cappedBps: capped,
    claimantPayout: claimant,
    respondentPayout: respondent,
    verdict: verdictLabel(capped),
    conserved: claimant + respondent === Math.max(0, Math.floor(escrow)),
  };
}

export function shortAddr(addr: string): string {
  if (!addr) return "";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}
