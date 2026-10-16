# CourtOfCode Adversarial Review

Every finding below was produced by attacking the contract in `contracts/court_of_code.py`
as if each caller, juror, party and every byte of externally fetched evidence were
hostile. Each item is marked FIXED with the direct-mode test that proves it, or OPEN
with the reason. All tests run with `gltest tests/test_court_of_code_direct.py`
(58 passing, leader path). Validator agreement is not proven by direct mode; it is
covered separately by the live studionet run described in `docs/deployment.md`.

## 1. State machine

| Status | Who may act | Transition | Effect on funds |
| --- | --- | --- | --- |
| (created) | claimant via `file_dispute_case` | -> `OPEN_FOR_REBUTTAL` | no ledger movement; `disputed_escrow` recorded |
| `OPEN_FOR_REBUTTAL` | respondent or owner: `submit_respondent_rebuttal` | -> `READY_FOR_TRIAL` | none |
| `OPEN_FOR_REBUTTAL` | claimant: `cancel_case` (only if `amicus_count == 0`) | -> `CANCELLED` | credit full `disputed_escrow` to claimant |
| `OPEN_FOR_REBUTTAL` / `READY_FOR_TRIAL` | any juror: `file_amicus_brief` | same status | none (reputation only) |
| `OPEN_FOR_REBUTTAL` / `READY_FOR_TRIAL` | non-author juror: `upvote_amicus_brief` | same status | none (reputation only) |
| `OPEN_FOR_REBUTTAL` / `READY_FOR_TRIAL` | `adjudicate_case_live` | -> `ADJUDICATED` | split escrow across both parties |
| `OPEN_FOR_REBUTTAL` / `READY_FOR_TRIAL` | owner or a party: `adjudicate_case_deterministic` | -> `ADJUDICATED` | split escrow across both parties |
| `ADJUDICATED` | `withdraw_award` | terminal | pull caller credit to zero |
| `CANCELLED` | `withdraw_award` | terminal | pull caller credit to zero |

`SETTLED_MUTUAL` is a valid stored label reserved for future off-chain settlements; no
method writes it today. It is not a lock-up state because mutual settlement is realized
through `adjudicate_case_deterministic`, which moves the case to `ADJUDICATED`.

## 2. Liveness: no stuck funds

- Finding L1 (OPEN_FOR_REBUTTAL griefing): a respondent who never files a rebuttal
  cannot strand the claimant. The claimant can always either `cancel_case` (while no
  juror has filed) or `adjudicate_case_live` directly from `OPEN_FOR_REBUTTAL` with an
  empty rebuttal url. FIXED: `test_owner_may_submit_rebuttal`, `test_cancel_refunds_claimant`,
  and the live path is proven callable from the open state by `test_live_claimant_prevails_conserves`.
- Finding L2 (cancel blocked by early briefs): once `amicus_count > 0`, `cancel_case` is
  refused, but `adjudicate_case_live` remains available, so funds still reach a party.
  FIXED / proven reachable: `test_cancel_blocked_when_briefs_exist` plus every live test.
- Finding L3 (dead evidence url): if a claimant url becomes unreachable after filing, every
  `adjudicate_case_live` call reverts because the web render throws inside the non-deterministic
  block, so the case cannot be resolved through the live path. The recovery is
  `adjudicate_case_deterministic`, open to the owner or either party, which splits the escrow
  without fetching evidence. FIXED / proven: `test_deterministic_full_claimant` and the party
  access tests. Accepted: there is no on-chain deadline because the exit is permissionless plus
  owner arbitration, which is the intended tribunal model for this milestone.

## 3. Race conditions between competing transitions

- Finding R1 (double settlement): `adjudicate_case_live`, `adjudicate_case_deterministic`
  and `cancel_case` all guard on status, and settlement flips status to `ADJUDICATED`/`CANCELLED`.
  A second settlement reverts. No double credit is possible. FIXED:
  `test_cannot_adjudicate_twice`, `test_live_rejects_when_not_open`,
  `test_cancel_blocked_after_rebuttal`.
- Finding R2 (cancel vs adjudicate): mutually exclusive by status; `cancel_case` requires
  `OPEN_FOR_REBUTTAL`, both adjudications require `OPEN_FOR_REBUTTAL`/`READY_FOR_TRIAL` and
  then leave that state. Whichever lands first blocks the other. FIXED:
  `test_cancel_blocked_after_rebuttal`, `test_brief_rejected_after_adjudication`.
- Finding R3 (withdraw vs new credit): `withdraw_award` reads the full balance, zeroes it,
  and reverts on zero, so it can never over-draw or double-pay. Later credits start again
  from zero. FIXED: `test_withdraw_returns_and_resets`, `test_withdraw_zero_reverts`.

## 4. Accounting invariants

- Invariant: `claimant_payout + respondent_payout == disputed_escrow` for every settlement,
  and total withdrawals never exceed total escrow of resolved cases. The split is computed
  as `claimant_payout = escrow * bps // 10000` (bps bounded to 0..10000, so the floor is
  always <= escrow) and `respondent_payout = escrow - claimant_payout`, conserving every unit.
  FIXED: `test_deterministic_full_claimant`, `test_deterministic_claimant_prevails`,
  `test_deterministic_respondent_prevails`, `test_live_claimant_prevails_conserves`,
  `test_respondent_withdraws_their_share`.
- Finding A1 (vote stuffing): `has_voted_case` enforces one tally vote per juror per case,
  and `has_upvoted_brief` enforces one upvote per `(brief, account)`. FIXED:
  `test_duplicate_juror_vote_rejected`, `test_duplicate_upvote_rejected`.

## 5. Input validation at every entry point

- Address sanity: `respondent` must be a well-formed 20-byte hex address and must differ
  from the caller. FIXED: `test_reject_invalid_respondent_address`, `test_reject_self_respondent`.
- Length floors and ceilings on every string, both endpoints checked. FIXED:
  `test_reject_empty_title`, `test_reject_title_too_long`, `test_reject_rubric_too_long`,
  `test_reject_argument_too_long`, `test_rebuttal_rejects_long_note`.
- URL validation: `http(s)` scheme only, no whitespace or control characters, 8..512 length,
  applied to both the claimant url and any non-empty rebuttal url. FIXED:
  `test_reject_non_http_url`, `test_reject_url_with_space`, `test_reject_url_too_short`,
  `test_rebuttal_rejects_bad_url`.
- Escrow floor and ceiling 100..10000000 enforced inclusively. FIXED:
  `test_reject_escrow_below_floor`, `test_reject_escrow_above_ceiling`,
  `test_accept_escrow_boundaries`.
- `adjudicate_case_deterministic` rejects (does not clamp) `claimant_award_bps > 10000`. FIXED:
  `test_deterministic_rejects_bps_above_max`.
- Access control on the deterministic path is limited to owner or a named party. FIXED:
  `test_deterministic_non_party_rejected`.

## 6. Consensus safety (GenLayer)

- Finding C1 (free-form LLM number moving funds): the raw `claimant_award_bps` from the
  tribunal is snapped onto a fixed 21-step ladder (multiples of 500 bps) inside the
  non-deterministic block, so the value that determines a transfer is a discrete label.
  The equivalence principle requires the quantized `claimant_award_bps` and the boolean
  `spec_token_found` to be exactly equal across validators; only the prose opinion may be
  similar. FIXED: `test_live_free_form_bps_is_quantized` (8337 -> 8000).
- Finding C2 (missing mandatory spec token): a claimant cannot win a majority award without
  the agreed anchor token; if `spec_token_found` is false, any bps above 5000 is capped to
  5000 deterministically after consensus. FIXED: `test_live_missing_token_caps_majority`.
- Finding C3 (prompt injection through fetched evidence): all fetched bodies are stripped
  of control characters, any `</untrusted` sequence is defused so evidence cannot close the
  delimiter early, and text is truncated to 5000 characters. The instruction to the model is
  that evidence is data, not commands. Most importantly, instructions inside the evidence
  cannot change the settlement rule: the split is derived from the quantized label and the
  deterministic spec-token cap, both applied in contract code after consensus, not from any
  number embedded in the page. FIXED / proven: `test_live_prompt_injection_cannot_move_funds`.
- Finding C4 (party-authored rubric and title are not sanitized): `case_title` and
  `contract_rubric` are supplied by the claimant at filing time and are inserted into the
  tribunal prompt as the agreed specification, but unlike fetched evidence they are NOT run
  through `_sanitize_evidence`. A hostile claimant could embed delimiter-like text or an
  over-reaching instruction in the rubric to try to sway the model toward a larger self
  award. This is an OPEN, accepted limitation for this milestone, not a fund leak: the
  contract custodies no real value (escrow and awards are a notional u256 ledger), the rubric
  and title are length capped at 1000 and 100, the award is still forced onto the 500 bps
  ladder and gated by the deterministic spec-token cap, the respondent rebuttal is fetched and
  sanitized into the same prompt, and every validator re-runs the identical prompt so no single
  party controls the outcome unilaterally. Planned hardening for a future milestone: run title
  and rubric through the same delimiter-defusing and control-char sanitizer, and require a
  respondent rubric acknowledgement before a case becomes adjudicable.
- Fail-closed on bad model output: a non-dict tribunal result raises an `[LLM_ERROR]` so the
  transaction rotates instead of persisting garbage. Note: this is a leader-path test only.
- OPEN (documented, accepted): `adjudicate_case_live` is permissionless (any account may
  trigger it once a case is open), matching the spec's "callable when status is open". This
  cannot be exploited to steal funds because the award is fully evidence-driven and
  spec-token-gated regardless of who triggers it, but a hostile trigger could resolve a case
  before the claimant is ready to publish more evidence. Mitigation for a future milestone:
  require an explicit party opt-in flag. Tracked as a product decision, not a fund-safety bug.

## 7. Tests that prove it

58 direct-mode tests cover a negative case for every guard above plus positive scenario
flows. They are named inline. Run:

```
gltest tests/test_court_of_code_direct.py
```

Direct mode exercises only the leader path. Validator agreement for the comparative
tribunal and the quantization ladder is validated end to end on studionet in the seeded
deployment described in `docs/deployment.md`.
