# CourtOfCode Adversarial Review

Every finding below was produced by attacking the contract in `contracts/court_of_code.py`
as if each caller, juror, party and every byte of externally fetched evidence were
hostile. Each item is marked FIXED with the direct-mode test that proves it, or OPEN
with the reason. All tests run with `gltest tests/test_court_of_code_direct.py`
(78 passing, leader path). Validator agreement is not proven by direct mode; it is
covered separately by the live studionet run described in `docs/deployment.md`.

This revision closes the three steward requirements:

- Requirement A, real on-chain value custody and payout: the CET token ledger and the
  escrow vault move real balances, not notional credits.
- Requirement B, two-party authorization: a deterministic split only settles when the
  counterparty co-signs the exact same award.
- Requirement C, response-deadline gate: live adjudication is blocked until the
  respondent rebuts or an explicit on-chain response deadline passes.

## 1. State machine

| Status | Who may act | Transition | Effect on custody |
| --- | --- | --- | --- |
| (created) | claimant via `file_dispute_case` | -> `OPEN_FOR_REBUTTAL` | debit `disputed_escrow` from claimant `token_balances`, credit `escrow_vault_balance` |
| `OPEN_FOR_REBUTTAL` | respondent or owner: `submit_respondent_rebuttal` | -> `READY_FOR_TRIAL` | none; sets `rebuttal_submitted` |
| `OPEN_FOR_REBUTTAL` | claimant: `cancel_case` (only if `amicus_count == 0`) | -> `CANCELLED` | refund `disputed_escrow` from vault back to claimant wallet |
| `OPEN_FOR_REBUTTAL` | any account: `expire_rebuttal_window` after the deadline | -> `REBUTTAL_DEADLINE_PASSED` | none |
| `OPEN_FOR_REBUTTAL` / `READY_FOR_TRIAL` / `REBUTTAL_DEADLINE_PASSED` | a party: `propose_deterministic_split` | same status | none; records the proposal and the proposing side |
| (any of the above with a live proposal) | the counterparty: `adjudicate_case_deterministic` | -> `SETTLED_MUTUAL` | credit both `claimable_awards`; funds stay in the vault |
| `OPEN_FOR_REBUTTAL` / `READY_FOR_TRIAL` / `REBUTTAL_DEADLINE_PASSED` | `adjudicate_case_live` (gated) | -> `ADJUDICATED` | credit both `claimable_awards`; funds stay in the vault |
| `ADJUDICATED` / `SETTLED_MUTUAL` | `withdraw_award` | terminal for that award | debit vault, credit caller `token_balances` |
| anytime | any account: `advance_tribunal_clock` (1..50) | monotonic clock | none |

`SETTLED_MUTUAL` is now written by `adjudicate_case_deterministic`, so the label that was
previously reserved for future use is exercised on the leader path and on studionet.

## 2. Requirement A: real custody and payout (CET ledger)

- The contract mints `10000000` CET to the deployer in `__init__` and keeps a
  `token_balances: TreeMap[Address, u256]` plus a single `escrow_vault_balance: u256`.
  FIXED: `test_owner_minted_initial_supply`.
- `file_dispute_case` debits the claimant wallet and credits the vault, so every unit of
  disputed escrow is genuinely custodied by the contract before any award can be paid.
  If the claimant cannot cover the escrow (even after the automatic first-time onboarding
  faucet) the filing reverts. FIXED: `test_custody_locks_tokens_on_file_and_transfers_on_withdraw`,
  `test_file_auto_grants_faucet_for_first_time_filer`,
  `test_file_reverts_when_balance_cannot_cover_custody`.
- Settlement only credits `claimable_awards`; the escrow stays locked 1:1 in the vault
  until each party withdraws. `withdraw_award` debits the vault and credits the caller's
  wallet, and reverts if the vault cannot cover the award. `cancel_case` refunds the
  locked escrow from the vault straight to the claimant wallet. FIXED:
  `test_custody_locks_tokens_on_file_and_transfers_on_withdraw`, `test_withdraw_returns_and_resets`,
  `test_respondent_withdraws_their_share`, `test_cancel_refunds_claimant`.
- Custody conservation is enforced by construction: total withdrawals plus refunds can
  never exceed what was locked, because both only move units out of `escrow_vault_balance`
  and the vault only ever grows by exactly `disputed_escrow` at filing.
- Onboarding `claim_faucet_tokens` is one-time per address; `fund_account` is owner-only;
  `transfer_tokens` requires a sufficient sender balance. These are the only mints and
  they are bounded, so the vault is never under-backed. FIXED:
  `test_faucet_credits_once_and_reverts_second_claim`, `test_fund_account_owner_only`,
  `test_transfer_tokens_requires_balance`.
- Views expose custody: `get_wallet_balance` and `get_tribunal_stats`
  (`escrow_vault_balance`, `tribunal_clock`). FIXED: `test_wallet_balance_view_and_invalid_address`,
  `test_tribunal_stats_totals`.

## 3. Requirement B: two-party mutual authorization of a deterministic split

- Unilateral / owner-only deterministic adjudication was removed. `adjudicate_case_deterministic`
  now only finalizes a split that the counterparty co-signs.
- A split must first be `propose_deterministic_split` by a party (claimant or respondent);
  the proposer's own approval flag is set and the counterparty's flag is cleared. Anyone
  who is neither party (including the owner) reverts. FIXED:
  `test_propose_rejects_non_party`, `test_propose_rejects_bps_above_max`.
- The counterparty co-signs by calling `adjudicate_case_deterministic` with the exact same
  `bps`. A proposer cannot approve their own proposal, a third party cannot co-sign, a
  missing proposal reverts, and a mismatched `bps` reverts. Only when both flags are set
  does the case settle as `SETTLED_MUTUAL`. FIXED:
  `test_deterministic_split_requires_both_claimant_and_respondent_authorization`,
  `test_deterministic_unilateral_without_proposal_reverts`,
  `test_deterministic_proposer_self_approval_reverts`,
  `test_deterministic_third_party_cannot_cosign`,
  `test_deterministic_mismatched_bps_reverts`,
  `test_deterministic_respondent_proposes_claimant_cosigns`,
  `test_deterministic_rejects_bps_above_max`, `test_cannot_adjudicate_twice`.
- Award `bps` is rejected (not clamped) above 10000 on both the proposal and the co-sign.
  FIXED: `test_propose_rejects_bps_above_max`, `test_deterministic_rejects_bps_above_max`.

## 4. Requirement C: response deadline gates live adjudication

- The contract keeps a monotonic `tribunal_clock` advanced only in bounded steps (1..50).
  Each case records `filed_at_clock` and `rebuttal_deadline_clock = filed_at_clock + 3`.
  FIXED: `test_advance_tribunal_clock_bounds`.
- `adjudicate_case_live` reverts while `rebuttal_submitted` is false and the clock has not
  reached the deadline. It succeeds the instant the respondent rebuts (even before the
  deadline) and, if the respondent is silent, once the deadline has passed. FIXED:
  `test_live_adjudication_reverts_before_rebuttal_and_before_deadline`,
  `test_live_adjudication_succeeds_immediately_after_respondent_rebuttal`,
  `test_live_adjudication_succeeds_after_onchain_rebuttal_deadline_expires`.
- `expire_rebuttal_window` moves an un-rebutted, past-deadline case to
  `REBUTTAL_DEADLINE_PASSED` and reverts early if the deadline has not passed. FIXED:
  `test_expire_rebuttal_window_before_deadline_reverts`,
  `test_expire_rebuttal_window_after_deadline_advances_status`.

## 5. Liveness: no stuck funds

- Finding L1 (OPEN_FOR_REBUTTAL griefing): a respondent who never rebuts no longer stalls
  the case. Either the on-chain response deadline expires and any account may trigger
  `expire_rebuttal_window` / `adjudicate_case_live`, or the two parties agree a
  `propose_deterministic_split` plus counterparty co-sign. FIXED: `test_owner_may_submit_rebuttal`,
  `test_cancel_refunds_claimant`, `test_live_adjudication_succeeds_after_onchain_rebuttal_deadline_expires`.
- Finding L2 (cancel blocked by early briefs): once `amicus_count > 0`, `cancel_case` is
  refused, but the deadline and the mutual split remain available, so custody still reaches
  a party. FIXED: `test_cancel_blocked_when_briefs_exist` plus the deadline and mutual tests.
- Finding L3 (dead evidence url): this was previously accepted because there was no
  on-chain exit. It is now bounded by the explicit `rebuttal_deadline_clock`; even if the
  live web render keeps failing, the two parties can settle deterministically through
  `propose_deterministic_split` + `adjudicate_case_deterministic`, which fetches nothing.
  FIXED: `test_deterministic_split_requires_both_claimant_and_respondent_authorization`
  and the deadline expiry tests.

## 6. Race conditions between competing transitions

- Finding R1 (double settlement): every settlement path guards on `ADJUDICABLE_STATUSES`
  and flips status to a terminal one (`ADJUDICATED` / `SETTLED_MUTUAL` / `CANCELLED`). A
  second settlement reverts, so custody can never be split twice. FIXED:
  `test_cannot_adjudicate_twice`, `test_live_rejects_when_not_open`,
  `test_cancel_blocked_after_rebuttal`.
- Finding R2 (cancel vs adjudicate vs expire): mutually exclusive by status; `cancel_case`
  requires `OPEN_FOR_REBUTTAL`, settlements require an adjudicable status and then leave it.
  Whichever lands first blocks the others. FIXED: `test_cancel_blocked_after_rebuttal`,
  `test_brief_rejected_after_adjudication`.
- Finding R3 (withdraw vs new credit): `withdraw_award` reads the full award, zeroes it,
  debits the vault, and reverts on zero or on an under-funded vault, so it can never
  over-draw or double-pay. FIXED: `test_withdraw_returns_and_resets`, `test_withdraw_zero_reverts`.

## 7. Accounting invariants

- Invariant: `claimant_payout + respondent_payout == disputed_escrow` for every settlement.
  The split is `claimant_payout = escrow * bps // 10000` (bps bounded to 0..10000, so the
  floor is always <= escrow) and `respondent_payout = escrow - claimant_payout`, conserving
  every unit. FIXED: `test_custody_locks_tokens_on_file_and_transfers_on_withdraw`,
  `test_deterministic_split_labels_boundaries`, `test_live_claimant_prevails_conserves`,
  `test_respondent_withdraws_their_share`.
- Finding A1 (vote stuffing): `has_voted_case` enforces one tally vote per juror per case,
  and `has_upvoted_brief` enforces one upvote per `(brief, account)`. FIXED:
  `test_duplicate_juror_vote_rejected`, `test_duplicate_upvote_rejected`.

## 8. Input validation at every entry point

- Address sanity: `respondent` must be a well-formed 20-byte hex address and must differ
  from the caller; `fund_account` and `transfer_tokens` validate `recipient`; the award and
  balance views validate the queried address. FIXED: `test_reject_invalid_respondent_address`,
  `test_reject_self_respondent`, `test_fund_account_owner_only`,
  `test_get_claimable_award_invalid_address_reverts`, `test_wallet_balance_view_and_invalid_address`.
- Length floors and ceilings on every string, both endpoints checked. FIXED:
  `test_reject_empty_title`, `test_reject_title_too_long`, `test_reject_rubric_too_long`,
  `test_brief_rejects_argument_too_long`, `test_rebuttal_rejects_long_note`.
- URL validation: `http(s)` scheme only, no whitespace or control characters, 8..512 length. FIXED:
  `test_reject_non_http_url`, `test_reject_url_with_space`, `test_reject_url_too_short`,
  `test_rebuttal_rejects_bad_url`.
- Escrow floor and ceiling 100..10000000 enforced inclusively, plus a per-account custody
  check. FIXED: `test_reject_escrow_below_floor`, `test_reject_escrow_above_ceiling`,
  `test_accept_escrow_floor`, `test_accept_escrow_ceiling`.
- Tribunal clock advance is bounded 1..50. FIXED: `test_advance_tribunal_clock_bounds`.

## 9. Consensus safety (GenLayer)

- Finding C1 (free-form LLM number moving funds): the raw `claimant_award_bps` is snapped
  onto a fixed 21-step ladder (multiples of 500 bps) inside the non-deterministic block, so
  the value that determines a transfer is a discrete label. The equivalence principle
  requires the quantized `claimant_award_bps` and the boolean `spec_token_found` to be
  exactly equal across validators; only the prose opinion may be similar. FIXED:
  `test_live_free_form_bps_is_quantized` (8337 -> 8000).
- Finding C2 (missing mandatory spec token): if `spec_token_found` is false, any bps above
  5000 is capped to 5000 deterministically after consensus. FIXED:
  `test_live_missing_token_caps_majority`.
- Finding C3 (prompt injection through fetched evidence): all fetched bodies are stripped
  of control characters, any `</untrusted` sequence is defused, and text is truncated to
  5000 characters. The split is derived from the quantized label and the deterministic
  spec-token cap, both applied in contract code after consensus. FIXED:
  `test_live_prompt_injection_cannot_move_funds`.
- Finding C4 (party-authored rubric, title and spec token were not sanitized): this is now
  FIXED. `adjudicate_case_live` runs `case_title`, `contract_rubric` and
  `mandatory_spec_token` through the same `_sanitize_evidence` control-char /
  delimiter-defusing sanitizer before building the tribunal prompt, so a hostile claimant
  can no longer inject a closing `</untrusted...>` tag or an over-reaching instruction
  through the fields they author at filing time. FIXED:
  `test_live_hostile_rubric_delimiters_are_sanitized` (malicious rubric/title cannot lift
  the award past the deterministic spec-token cap).
- Fail-closed on bad model output: a non-dict tribunal result raises an `[LLM_ERROR]` so the
  transaction rotates instead of persisting garbage. Note: this is a leader-path test only.
- Accepted limitation (documented, not a fund leak): once the response gate opens (a rebuttal
  was filed or the deadline expired), `adjudicate_case_live` is still triggerable by any
  account, and it races `propose_deterministic_split` + co-sign. This cannot steal funds:
  the live award is fully evidence-driven and spec-token-capped regardless of who triggers
  it, and the first settlement to reach consensus flips the case to a terminal status so the
  competing path reverts and can never double-credit (Finding R1, proven by
  `test_cannot_adjudicate_twice` and `test_live_rejects_when_not_open`). The practical cost
  is timing: a hostile trigger can resolve a case the moment the window opens. Both parties
  retain the mutual-split path before that, so custody always reaches a party.

## 10. Tests that prove it

78 direct-mode tests cover a negative case for every guard above plus positive scenario
flows, including the full custody lifecycle, the two-party split, and the response-deadline
gate. They are named inline. Run:

```
gltest tests/test_court_of_code_direct.py
```

Direct mode exercises only the leader path. Validator agreement for the comparative
tribunal and the quantization ladder is validated end to end on studionet in the seeded
deployment described in `docs/deployment.md`.
