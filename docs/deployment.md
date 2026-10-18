# CourtOfCode studionet deployment and evidence

This page records the live, consensus-finalized deployment of the CourtOfCode
intelligent contract. Every claim below is backed by a transaction verified through
the GenLayer RPC (see `evidence/transactions.json`). Nothing here is asserted from
CLI output alone.

This deployment resolves the steward review: it settles with real on-chain value
custody and payout, requires both parties to authorize a deterministic split, and
opens live adjudication only after a respondent rebuttal or an explicit on-chain
response deadline.

## Network and contract

| Field | Value |
| --- | --- |
| Network | studionet (GenLayer Studio, gasless) |
| Chain id | 61999 |
| RPC | https://studio.genlayer.com/api |
| Contract address | `0xAEB9AF77E30eA8B1CDcEAF2E5e2dAb5F677A7899` |
| Runner (pinned line 1) | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (GenVM v0.2.16) |
| Explorer | https://genlayer-explorer.vercel.app |

## Source identity (3-way sha256)

| Artifact | sha256 |
| --- | --- |
| Local `contracts/court_of_code.py` (LF normalized) | `ddf24bcc4af71f1d508b4816ce15535029c8f8020165926203fb428aba5bd05d` |
| Code bytes submitted in the deploy transaction | `ddf24bcc4af71f1d508b4816ce15535029c8f8020165926203fb428aba5bd05d` |
| ABI schema read from the deployed address | `169ca1d27c368d046c945b7b8b0cfc7ec208b0445a1a64e969dbfcc690f1204f` |
| ABI schema compiled from the local source | `169ca1d27c368d046c945b7b8b0cfc7ec208b0445a1a64e969dbfcc690f1204f` |

The submitted code hash equals the local file hash (line endings aside), and the
on-chain ABI schema equals the schema the studio RPC derives from the local source.
Together these prove the deployed contract was built from this exact file.

## Accounts used in the seed

| Role | Address |
| --- | --- |
| Owner / claimant signer | `0x154a452b0755EE812014C1405B15D905BA06f9c7` |
| Respondent signer | `0x7b0440cB8F20bB5939AC050Baa5A050ae5686735` |
| Juror 1 (auditcrew) | `0x73c75724d503ED5a64fCF53EA61BB7D96675a4Ef` |
| Juror 2 (stableship) | `0x25C8c41257726bbfe21083b294Bf7F914e59cd55` |

The claimant and respondent are the two distinct parties required by the mutual
settlement flow; the juror and respondent accounts are throwaway signers generated
by the seed script, and studionet is gasless so they need no funding.

## Seeded scenario, transaction by transaction

Case #1 exercises the full two-party mutual settlement backed by real custody. Case
#2 showcases an open case plus two adversarial rollbacks that must revert on chain.

| Step | Method | Signer | Status | Execution | Tx hash |
| --- | --- | --- | --- | --- | --- |
| File case 1 (lock 250000 CET) | `file_dispute_case` | claimant | FINALIZED | SUCCESS | `0x45d3f3a593633ef5a5810898ff663020d4fbf702a6015a4ea91b880f70a065c4` |
| Respondent rebuttal (case 1) | `submit_respondent_rebuttal` | respondent | FINALIZED | SUCCESS | `0x89c87c9a771d89d0ec54f614a25d05b70773bd0f21e5f25c4d3a56e9a27f8e71` |
| Amicus brief (case 1, claimant) | `file_amicus_brief` | juror1 | FINALIZED | SUCCESS | `0x61dd521e830dc3e8c433aa3d47a61f2d588f3fec6f64376e122a2c31cb5f6a7d` |
| Amicus brief (case 1, respondent) | `file_amicus_brief` | juror2 | FINALIZED | SUCCESS | `0x877b64af617369378eb4f020cc6c377426b3b2b59fe26187e5059f1d38fd36be` |
| Upvote brief 1 | `upvote_amicus_brief` | juror2 | FINALIZED | SUCCESS | `0x2353cabf8cb53967bf69146c8956537699249e5171f77df2febf866fe463e9a0` |
| Claimant proposes 6000 bps | `propose_deterministic_split` | claimant | FINALIZED | SUCCESS | `0x4b20ea1ce4bd8d6a0029340fda14d8341d93eae89c948d1a1b4a781688990a2f` |
| Respondent co-authorizes 6000 bps | `adjudicate_case_deterministic` | respondent | FINALIZED | SUCCESS | `0x38a9e83a696e6a48c6aab88b6d4a0dd9f2ac9df987478cd3caa4aff8639efb04` |
| Claimant withdraws 150000 CET | `withdraw_award` | claimant | FINALIZED | SUCCESS | `0xd4941f2f2226ea3050a7c6ed2242ce7cde149c1ea49a44394b63a056e9c4e782` |
| File case 2 (lock 180000 CET) | `file_dispute_case` | claimant | FINALIZED | SUCCESS | `0xf5620e77722cc5e045b74ab7b0fe3e99ceed388c05123a16a3e52628e5c6a897` |
| Amicus brief (case 2) | `file_amicus_brief` | juror1 | FINALIZED | SUCCESS | `0xdd54818b7c84cc1e576ac50f6a57347bd6c11895d7b5848890d1b25f2cdba498` |
| Upvote case 2 brief | `upvote_amicus_brief` | juror2 | FINALIZED | SUCCESS | verified by state (see note) |
| Rollback: unilateral split (case 2) | `adjudicate_case_deterministic` | respondent | FINALIZED | ERROR (revert) | `0xacf36471f5bfbc8a1d09fe2b69af0ff3244f2f29b6eb2ae7617376c211a14466` |
| Rollback: premature live (case 2) | `adjudicate_case_live` | claimant | FINALIZED | ERROR (revert) | `0x1cf1c8c3d644aab0ece24ecaf8f5199d3e2590b92cdf309c139b335576cc06c1` |

Note on "verified by state": the case 2 upvote landed on chain and its effect is
asserted directly from the finalized contract state below (the case 2 brief authored
by juror1 shows a nonzero upvote count); the checkpoint's effect-idempotency guard
skipped re-submitting it rather than double-applying it.

## Finalized on-chain state (read back through the RPC)

- Case 1: `status=SETTLED_MUTUAL`, `verdict_label=SPLIT_REMEDY`, `claimant_award_bps=6000`,
  `claimant_payout=150000`, `respondent_payout=100000`, `disputed_escrow=250000`.
  Both `claimant_approved_split` and `respondent_approved_split` are `true`. Invariant
  `claimant_payout + respondent_payout == disputed_escrow` holds.
- Case 2: `status=OPEN_FOR_REBUTTAL`, `disputed_escrow=180000`, `rebuttal_submitted=false`,
  `rebuttal_deadline_clock = filed_at_clock + 3`.
- Claimant wallet custody: the initial 10000000 CET mint, minus the 250000 case 1 lock,
  plus the 150000 withdrawn award, minus the 180000 case 2 lock equals 9720000 CET held
  by the claimant; `get_claimable_award(claimant) == 0`.
- Tribunal stats: `total_cases=2`, `open_cases=1`, `adjudicated_cases=1` (settled),
  `total_briefs=3`, `votes_for_claimant=2`, `votes_for_respondent=1`,
  `escrow_in_dispute=180000`, `escrow_vault_balance=280000`, `tribunal_clock=0`.
- The `escrow_vault_balance` of 280000 is exactly the respondent's unclaimed 100000 CET
  award plus the 180000 CET case 2 escrow, confirming the vault backs every outstanding
  claim 1:1.
- Rollback checks: the unilateral split reverted because no proposal existed on case 2,
  and the premature live adjudication reverted because case 2 was still inside its
  rebuttal window; both left no state change (case 2 is still open, juror1 claimable is 0).

## Reproduce

```
python scripts/deploy_studionet.py
gltest tests/test_court_of_code_integration.py -v -s
```

The deploy script is idempotent: it records progress in `evidence/_checkpoint.json`
and, on a rerun, skips any step whose effect is already finalized on chain.
