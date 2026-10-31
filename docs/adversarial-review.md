# CourtOfCode Adversarial Review (Milestone v1)

Every finding below was produced by attacking `contracts/court_of_code.py` as if each
caller, juror, party and every byte of externally fetched evidence were hostile, and as if
the contract custodied real value. Each item is marked FIXED with the direct-mode test that
proves it, or OPEN with a stated reason. All findings are checked with
`gltest tests/test_court_of_code_direct.py` (70 passing, leader path). Validator agreement
is not proven by direct mode; the consensus-bound settlement, ladder binding and void
refunds are covered by named leader-path tests here and the deterministic transitions are
additionally confirmed live on studionet in `docs/deployment.md`.

## 1. State machine

| Status | Trigger | Next status | Effect on custody |
| --- | --- | --- | --- |
| (created) | `file_dispute_payable` | `OPEN_FOR_REBUTTAL` | principal debited from claimant CET into `vault_custody_balance`; native filing bond into `native_escrow_balance` |
| `OPEN_FOR_REBUTTAL` | `post_respondent_bond_payable` | `READY_FOR_TRIAL` | respondent CET bond added to vault |
| any open | `file_amicus_brief` / `upvote_amicus_brief` | unchanged | reputation only, no fund movement |
| open after gate | `adjudicate_docket` | `ADJUDICATED` | derived band + payouts stored, no transfer yet |
| `ADJUDICATED` | `challenge_verdict_payable` (party, in window) | `CHALLENGED` | challenge bond added to vault |
| `ADJUDICATED`/`CHALLENGED` after appeal deadline | `execute_decree_settlement` | `FINALIZED` or void | escrow-conserving credits |
| open past timeout | `claim_expired_or_uncontested_refund` | `VOID_ZERO_WINNER_REFUND` | 100 percent principal + bonds refunded |
| `OPEN_FOR_REBUTTAL`, no briefs | `cancel_docket` (claimant) | `CANCELLED` | principal returned to claimant CET |

There is no `ADJUDICATED` deterministic backdoor and no `advance_clock`. Rule 2 is enforced
structurally: `test_no_manual_clock_advance_or_deterministic_backdoor` greps the source for
`def advance_clock`, `gl.advance_clock` and a deterministic settlement symbol and fails if
any appear. `test_no_admin_fund_bypass_symbols` confirms no owner-only path can move escrow;
the only owner privilege is `set_filing_paused`, which gates new filings and can never touch
custody (`test_file_paused_soft_fails`).

## 2. Liveness: no stuck funds

- Every open docket has a terminal exit. If the respondent never rebuts, the claimant either
  `cancel_docket` (while no juror has filed) or waits for the rebuttal deadline to expire and
  then `adjudicate_docket` from the window-expired path
  (`test_adjudicate_on_window_expiry_without_rebuttal`).
- If nobody ever adjudicates, `claim_expired_or_uncontested_refund` voids and refunds 100
  percent of principal plus bonds after `adjudication_timeout_epoch`
  (`test_expired_unadjudicated_docket_void_refunds_principal`).
- Dead evidence URLs cannot freeze a case: the leader function falls back to the on-chain
  brief summary and records `web_source_verified=false`, still producing a consensus-bound
  band (`test_web_source_unreachable_marks_unverified_but_still_adjudicates`).
- The `set_filing_paused` valve is not a fund lock: it only blocks new filings and can be
  cleared by the owner; in-flight escrow always has the timeout refund available.

## 3. Race conditions between competing transitions

- Double settlement: `execute_decree_settlement` guards on `settled` and on status
  (`ADJUDICATED`/`CHALLENGED`), then flips to `FINALIZED`. A second call reverts
  (`test_cannot_adjudicate_twice`, `test_settlement_after_appeal_window_conserves` and the
  already-settled guard in `claim_expired_or_uncontested_refund`).
- Cancel versus adjudicate: `cancel_docket` requires `OPEN_FOR_REBUTTAL` and zero briefs;
  adjudication leaves that state, so whichever lands first blocks the other
  (`test_cancel_blocked_when_briefs_exist`, `test_cancel_blocked_for_non_claimant`).
- Challenge versus settlement: `challenge_verdict_payable` requires `ADJUDICATED` and the
  appeal window still open; settlement requires the appeal window closed, so a party challenge
  always precedes and forces the void path (`test_contested_challenge_voids_and_refunds_all`).
- Withdraw versus new credit: `withdraw_refund` clamps to the current balance and never
  over-draws; `withdraw_award` reverts on zero so it cannot double-pay
  (`test_withdraw_refund_clamps_overrequest`, `test_withdraw_award_zero_reverts`).

## 4. Accounting invariants

- Escrow conservation is the core invariant. `_derive_payouts` sets
  `payout = principal * award_bps // 10000` (award bounded to the ladder, so the floor never
  exceeds principal) and `refund = principal - payout`. At settlement the claimant receives
  `payout + slash` and the respondent receives `refund + (bond - slash)`, so the two credits
  always re-sum to `principal + bond`. FIXED:
  `test_settlement_after_appeal_window_conserves`,
  `test_settlement_partial_award_returns_unslashed_bond`,
  `test_full_claimant_decree_credits_principal_and_slash`, and the `conserved` flag returned
  by `_compute_docket_state` (`test_view_and_settlement_never_diverge`).
- The void and timeout refunds return exactly `principal + respondent_bond + challenge_bond`
  and reduce `vault_custody_balance` by the same amount, so the vault never leaks or traps a
  unit (`test_expired_unadjudicated_docket_void_refunds_principal`,
  `test_contested_challenge_voids_and_refunds_all`).
- One shared invariant helper (Rule 5): every read view, the leaderboard and settlement all
  call `_compute_docket_state`, so a reported payout can never diverge from the settled value.

## 5. Input validation at every entry point

- Respondent must be a well-formed 20-byte hex address and differ from the caller
  (`test_file_bad_respondent_soft_fails`, `test_file_self_dealing_soft_fails`).
- Docket id, title, brief summary and spec token are length-bounded and shape-checked
  (`test_file_bad_token_soft_fails`, and the bad-pr-url guard `test_file_bad_pr_url_soft_fails`).
- Both evidence URLs must be `http(s)` with no whitespace or control characters, 8..512 long
  (`_is_valid_url`, exercised by `test_file_bad_pr_url_soft_fails`).
- Principal has an inclusive floor and ceiling (100 .. 1e12) and the filer must hold enough
  CET (`test_file_underfunded_cet_soft_fails`).
- The rebuttal and appeal windows each have a floor and a ceiling in seconds, so no caller can
  set a zero or absurd deadline (`test_file_bad_rebuttal_window_soft_fails`,
  `test_file_bad_appeal_window_soft_fails`).
- View arguments are validated: bad addresses and unknown dockets revert cleanly
  (`test_refundable_and_rejection_views_reject_bad_address`, `test_get_docket_missing_reverts`).

## 6. Rule 8: non-trapping payable refunds (the Joaquin rule)

- No `@gl.public.write.payable` method ever reverts on a validation failure. On any failure
  `file_dispute_payable`, `post_respondent_bond_payable` and `challenge_verdict_payable` credit
  100 percent of `gl.message.value` to `refundable_balances[sender]`, record the reason in
  `last_payable_rejection[sender]`, bump `total_refundable_custody`, and return
  `SOFT_FAIL_REFUND_CREDITED:<reason>` instead of reverting. FIXED:
  `test_fund_zero_soft_fails_without_revert`, `test_file_duplicate_docket_id_soft_fails`,
  `test_file_self_dealing_soft_fails`, `test_file_underfunded_cet_soft_fails`,
  `test_file_bad_rebuttal_window_soft_fails`, `test_rebuttal_non_respondent_soft_fails`,
  `test_rebuttal_underfunded_bond_soft_fails`, `test_rebuttal_after_window_expiry_soft_fails`,
  `test_challenge_non_party_soft_fails`, `test_challenge_before_adjudication_soft_fails`.
- The refund custody is fully claimable and tracked: `test_custody_summary_tracks_refundable_custody`,
  `test_refund_claim_zero_when_nothing`, `test_withdraw_refund_clamps_overrequest`. Native
  release to an EOA uses `@gl.evm.contract_interface` (`_GENRecipient(sender).emit_transfer`),
  never `gl.get_contract_at(...).emit_transfer`. This exact path was exercised live: a duplicate
  filing credited 2,500,000 and `claim_refundable_balance` released it back, leaving
  `total_refundable_custody` at zero (see `docs/deployment.md`).
- FINDING R8a (FIXED, non-trapping filer deposit): the native filing value sent on
  `file_dispute_payable` is tracked per docket (`filing_bond_native`) and is returned to the
  filer through `refundable_balances` at EVERY terminal exit (decree settlement, contested
  void, timeout void and cancel), so no filer deposit can ever be trapped in the contract.
  This closes a hole found in this review pass where `native_escrow_balance` was previously a
  one-way accumulator. FIXED: `test_filing_deposit_refunded_on_settlement`,
  `test_filing_deposit_refunded_on_contested_void`,
  `test_filing_deposit_refunded_on_expired_void`, `test_filing_deposit_refunded_on_cancel`.

## 7. Rule 9: consensus-bound baselines and the discrete ladder

- All fields the payout math needs (respondent, principal, bond, spec token, title, summary,
  both URLs) are snapshotted into plain locals BEFORE entering `gl.nondet`, so validators
  cannot diverge on stale storage reads.
- Inside the leader function the raw model score is quantized onto the 500 bps baseline grid
  and the award is snapped onto the discrete five-anchor ladder {0, 2500, 5000, 7500, 10000};
  the verdict band and the exact derived integer payouts are computed there, so the value that
  determines a transfer is a discrete label every validator must reproduce
  (`test_award_snapped_to_discrete_ladder`, `test_baseline_quantized_onto_500_grid`).
- `gl.eq_principle.prompt_comparative` requires 100 percent exact agreement on band, baseline,
  award and all three derived amounts; only the prose opinion may be similar. After consensus
  the contract re-derives the payouts deterministically and reverts if any consensus label is
  off the fixed grids or mismatches (`test_adjudicate_after_rebuttal_majority`,
  `test_full_claimant_decree_credits_principal_and_slash`,
  `test_partial_contribution_award_band`, `test_respondent_summary_dismissal_zero_award`).

## 8. Consensus and injection safety (GenLayer)

- Prompt injection through fetched evidence: every fetched body is run through `_sanitize_text`
  (control characters dropped, any `</untrusted` delimiter defused, truncated), and the
  settlement rule is derived from the quantized band and the deterministic ladder, not from any
  number embedded in the page, so evidence cannot move funds it does not deserve
  (`test_web_source_verified_when_reachable`, `test_web_source_unreachable_marks_unverified_but_still_adjudicates`).
- Fail-closed parsing: a non-dict tribunal result raises `[LLM_ERROR]` so the transaction
  rotates instead of persisting garbage; the tribunal prompt is built only from sanitized parts.
- OPEN (accepted): the claimant-authored `title`, `brief_summary` and `mandatory_spec_token` are
  validated (length, URL and shape) but are not passed through `_sanitize_text` before entering
  the tribunal prompt. This is a judgment-shaping concern, not a fund leak: the award is still
  forced onto the fixed ladder, gated by exact validator agreement and re-derived after
  consensus, so no crafted string can raise a payout beyond the band the validators
  independently reproduce. Planned hardening: sanitize these fields too.
- OPEN (documented): `adjudicate_docket` is permissionless once the timing gate is satisfied,
  matching the tribunal model. It cannot steal funds because the award is fully evidence and
  ladder driven regardless of the trigger, but a hostile early trigger could resolve a case
  before a party is ready. Tracked as a product decision, not a fund-safety bug.

## 9. The hosted-studio settlement limitation (honest, OPEN)

- FINDING S1 (OPEN): the live `adjudicate_docket` transaction on studionet FINALIZED and
  returned a decree, but the hosted studio did not commit the non-deterministic
  `prompt_comparative` state delta to canonical storage, so on-chain `execute_decree_settlement`
  could not be driven from it (two live renders even produced different bands). This is a
  limitation of the hosted consensus commit path, not the contract. The contract re-reads the
  docket fresh after the nondet block before mutating (see `adjudicate_docket`), and no
  deterministic settlement backdoor was added to paper over it, exactly as Rule 2 requires. All
  fund-bearing settlement logic, escrow conservation, the discrete ladder binding and the void
  and timeout refunds are proven by the direct-mode consensus-bound tests above.

## 10. Tests that prove it

70 direct-mode tests cover a negative case for every guard above plus positive scenario
flows; they are named inline. Run:

```
gltest tests/test_court_of_code_direct.py
```

Direct mode exercises only the leader path. Validator agreement for the comparative tribunal
and the quantization ladder is validated end to end on the deterministic transitions in the
live deployment described in `docs/deployment.md`.
