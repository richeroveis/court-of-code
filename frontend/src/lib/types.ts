// Shared on-chain data shapes returned by the CourtOfCode Chancery contract views.
// Kept in one place so every workbench panel reads the same field names.

export interface Docket {
  docket_id: string;
  claimant: string;
  respondent: string;
  title: string;
  pr_evidence_url: string;
  spec_reference_url: string;
  brief_summary: string;
  mandatory_spec_token: string;
  principal_cet: number;
  respondent_bond_cet: number;
  challenge_bond_cet: number;
  filing_epoch: number;
  rebuttal_deadline_epoch: number;
  appeal_deadline_epoch: number;
  adjudication_timeout_epoch: number;
  respondent_rebuttal: string;
  rebuttal_submitted: boolean;
  status: string;
  verdict_band: string;
  quantized_spec_baseline_bps: number;
  claimant_award_bps: number;
  derived_claimant_payout: number;
  derived_respondent_refund: number;
  derived_slash_amount: number;
  web_source_verified: boolean;
  appeal_challenged: boolean;
  settled: boolean;
  judicial_opinion: string;
  amicus_count: number;
  votes_for_claimant: number;
  votes_for_respondent: number;
}

export interface Brief {
  brief_id: number;
  docket_id: string;
  juror: string;
  juror_handle: string;
  side: string;
  argument: string;
  upvotes: number;
}

export interface TribunalStats {
  total_dockets: number;
  open_dockets: number;
  adjudicated_dockets: number;
  settled_dockets: number;
  void_dockets: number;
  total_briefs: number;
  votes_for_claimant: number;
  votes_for_respondent: number;
  vault_custody_balance: number;
  total_refundable_custody: number;
}

export interface CustodySummary {
  vault_custody_balance: number;
  total_cet_supply: number;
  native_escrow_balance: number;
  total_refundable_custody: number;
  docket_count: number;
}

export interface LeaderRow {
  juror: string;
  reputation: number;
}
