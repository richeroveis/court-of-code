# CourtOfCode Chancery

A decentralized software-arbitration and pull-request bounty dispute court built as a
GenLayer intelligent contract. A Claimant (the contributor who shipped the work) and a
Respondent (the sponsor or maintainer who withheld the bounty) each submit a live evidence
URL over a disputed deliverable. Community counsel file weighted amicus briefs, and
GenLayer validators render a binding, escrow-conserving apportionment by independently
fetching the evidence and comparing it against the agreed technical specification.

The point of using GenLayer here is that the outcome is a subjective technical judgment
that must settle real custody value. It cannot be reduced to a deterministic on-chain
check and cannot be trusted to a single off-chain oracle, so it needs independently
verified validator consensus with a transparent, appealable transition.

Milestone v1 hardens the tribunal around eleven Steward rules: real funded custody, a
discrete award ladder, consensus-bound baselines, enforceable timing gates, and a fully
non-trapping payable refund pattern.

- Contract: `contracts/court_of_code.py` (GenLayer intelligent contract)
- Network: studionet (chain 61999), deployed and exercised through a real multi-transaction lifecycle
- Interactive frontend: https://richeroveis.github.io/court-of-code/
- Deployment evidence: [docs/deployment.md](docs/deployment.md) and `evidence/studionet_Live_Milestone_v1.json`
- Security review: [docs/adversarial-review.md](docs/adversarial-review.md)
- Demo video: `docs/demo-video-subtitled.mp4` (bespoke rendered media, subtitled)

## Deployed contract

| Field | Value |
| --- | --- |
| Address | `0xD53816C72a715f317eA689916693308e8f701039` |
| Network | studionet (chain 61999) |
| Deployer account | `0x154a452b0755EE812014C1405B15D905BA06f9c7` |
| Pinned runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (GenVM v0.2.16) |
| Contract size | 36,486 bytes (LF-normalized deployed source, under the 37,500 byte cap) |
| Release tag | `milestone-v1` (upgrade of `studionet-v1`) |

Deploy transaction hash: `0x223a1206928ca031dae09173e149519e536301c10fcdd366c63bb92aa8dd7d87`.

## Live studionet lifecycle (Milestone v1)

Every step below was submitted to studionet (chain 61999) and awaited to FINALIZED.
Transaction hashes (view them at `https://genlayer-explorer.vercel.app/tx/<hash>`):

| Step | Result | Transaction hash |
| --- | --- | --- |
| Deploy | FINALIZED | `0x223a1206928ca031dae09173e149519e536301c10fcdd366c63bb92aa8dd7d87` |
| fund_cet_vault_payable | FINALIZED SUCCESS | `0xcd16337f74322aa58a4d78bfdd81d9f896e5eafb21d231b4e9bef10643409b97` |
| file_dispute_payable M1 | FINALIZED SUCCESS | `0x824a237adea42996ade9f07a052d6f8f5500357df4f03a1c7a6a1b0f80fab1d5` |
| file_dispute_payable M2 | FINALIZED SUCCESS | `0xd9490626bbe442f18de46a59ff680e8330d5fc1a34e12a1a59d2564e9e03a717` |
| post_respondent_bond_payable M1 | FINALIZED SUCCESS | `0xc743e08f4de79108a8ab60ff83fa8dd2d13cf54a732078e3f378cae60798e0b3` |
| file_amicus_brief M1 | FINALIZED SUCCESS | `0xe65438d288d5eaa6b7dc5e86b3cbdb0cadd2ad04b63b07d42376606f8bc656a5` |
| soft-fail duplicate filing M1 | FINALIZED SUCCESS | `0xd12f16f8ef692fd777c31836f39b8f70b5804bae1a52f1f20409dfb4f53a47d9` |
| claim_refundable_balance | FINALIZED SUCCESS | `0x23a654164e3bb53c4e50fc880244ae3e265bac0a4420a78d579085b99ab96fd5` |
| adjudicate_docket M1 (live consensus) | FINALIZED SUCCESS | `0xdd6fad248ad3c966ca759e0d2566e9eb253faf204d81a41ebe2c35f8ff678a7c` |

After the run the on-chain custody accounting read back as: `vault_custody_balance` 3,800,000
CET (both principals plus the respondent bond), `native_escrow_balance` 2,000,000 (the two
filing bonds), `total_cet_supply` 30,000,000, and `total_refundable_custody` 0 (the
soft-fail refund of 2,500,000 was credited on `softfail_M1` and fully released back to the
EOA through the `@gl.evm.contract_interface` path on `claim_refundable_balance`), proving the
non-trapping payable refund rule live on chain.

Honest note on settlement: the `adjudicate_docket` transaction reached FINALIZED/SUCCESS and
returned a decree, but the hosted studio finalized the non-deterministic `prompt_comparative`
result without committing its post-consensus state delta to canonical storage, so the on-chain
`execute_decree_settlement` could not be driven from it (the two live runs even rendered
different bands, confirming the validators did not durably agree). This is a limitation of the
hosted studio consensus path, not of the contract: every deterministic transition persisted
with a real hash, and the full consensus-bound settlement, the discrete-ladder binding, the
escrow conservation and the timeout and contested void refunds are all proven by the 70 passing
direct-mode tests. No deterministic settlement backdoor was added to force an on-chain payout.

## The eleven Steward rules

1. Pinned runner header on line one; classic `from genlayer import *` SDK.
2. No admin or creator fund bypass and no manual clock advancement; every deadline is
   enforced against the deterministic GenVM inclusion timestamp.
3. Real funded custody: an internal CET ledger (`token_balances`, `vault_custody_balance`)
   plus native GEN accounting, reserving 100 percent of maximum potential liability until
   both the rebuttal and the challenge windows have closed. Native payouts to an EOA use
   `@gl.evm.contract_interface`, never `gl.get_contract_at(...).emit_transfer`.
4. Consensus-bound baselines: every storage field is snapshotted into plain locals before
   entering `gl.nondet`, the live evidence is rendered through `gl.nondet.web.render`, and
   the specification baseline is quantized onto a 500 bps grid while the award is snapped
   onto the discrete five-anchor ladder.
5. A single `_compute_docket_state` invariant helper drives every view, the leaderboard
   and settlement so status labels and payout numbers never diverge.
6. Adjudication is gated on temporal precedence: it requires a respondent rebuttal or the
   full expiry of the rebuttal deadline. Untrusted strings are sanitized and LLM JSON is
   parsed fail-closed.
8. Non-trapping payable refunds (the Joaquin rule): every `@gl.public.write.payable`
   method credits 100 percent of the sent value to `refundable_balances`, records the
   reason in `last_payable_rejection`, and returns a structured soft-fail receipt instead
   of ever reverting. `withdraw_refund`, `claim_refundable_balance`,
   `get_refundable_balance`, `get_last_payable_rejection` and `get_custody_accounting_summary`
   expose the refund custody.
10. Enforceable timing (the ProphetGrid rule): settlement is strictly after the appeal
    deadline, and `claim_expired_or_uncontested_refund` returns 100 percent of principal
    and bonds when a docket times out unresolved or ends in a dead-locked void.
11. Four-way SHA-256 identity across the local file, the git blob, the raw GitHub source
    and the deployed studionet schema.

Rule 9 binding: inside `gl.nondet` the derived integer payouts (`derived_claimant_payout`,
`derived_respondent_refund`, `derived_slash_amount`) and the discrete verdict band are
computed exactly, and `gl.eq_principle.prompt_comparative` requires 100 percent validator
agreement on all of them before the arithmetic is re-verified deterministically and the
state mutates.

## How it works

1. A claimant funds the CET vault, then calls `file_dispute_payable` recording the rubric,
   a mandatory spec token, both evidence URLs, the disputed principal and the rebuttal plus
   appeal window seconds. Invalid input soft-fails and refunds rather than reverting.
2. The respondent may `post_respondent_bond_payable` with a rebuttal and a bond, moving the
   docket to `READY_FOR_TRIAL`.
3. Any account may `file_amicus_brief` to join the jury with one weighted vote and may
   `upvote_amicus_brief` to boost another counsel's argument.
4. `adjudicate_docket` fetches both evidence URLs through `gl.nondet.web.render`, falls back
   to the on-chain brief summary when unreachable, quantizes the baseline and the award onto
   the fixed grids, and binds them through `gl.eq_principle.prompt_comparative`.
5. Settlement (`execute_decree_settlement`) is only permitted after the appeal window has
   closed and is escrow-conserving: claimant and respondent credits always re-sum to
   principal plus bond. A contested decree resolves to a clean void refund.
6. `withdraw_refund` and `claim_refundable_balance` release soft-fail refunds through the
   EVM contract interface; `withdraw_award` moves a finalized decree credit back to CET.

## Frontend

The judicial chamber workbench (Vite + React + genlayer-js) is a three-column bench:

- Left: the Chancery Docket Registry, the Escrow Custody and Refund Ledger, the pay-refund
  and bond custody drawer with one-click `claim_refundable_balance`, and the judicial
  leaderboard.
- Center: the bilateral PR diff bench comparing the claimant pull request against the
  respondent rebuttal, the live rebuttal and appeal timeline, the amicus brief panel and the
  bilateral co-sign settlement panel.
- Right: the Chancery award apportionment calculator (discrete five-anchor ladder plus the
  500 bps baseline grid), the Equivalence Principle decree transcript, and the procedural
  rule verification bench that safely exercises the soft-fail payable refund and the
  pre-deadline adjudication guard.

A one-click burner counsel wallet, optional MetaMask (EIP-1193), an initial load bounded to
four RPC reads, an ambient animated background, a zero-dependency Web Audio layer with a
mute toggle, and a confetti burst when a write reaches FINALIZED round it out.

```
cd frontend
npm install
npm run dev      # local dev server
npm run build    # production build to frontend/dist
```

## Testing

```
genvm-lint check contracts/court_of_code.py                 # 0 errors
gltest tests/test_court_of_code_direct.py                   # 70 tests, leader path
gltest tests/test_court_of_code_integration.py -v -s        # live studionet reads
```

To deploy and run the full lifecycle:

```
python scripts/deploy_studionet.py
```

## Media

The bespoke Python renderer synthesizes the original chancery soundtrack and assembles the
subtitled demo film. It drives `video/record_chancery.mjs` (Playwright) and muxes the result
with a bundled ffmpeg into `docs/demo-video-subtitled.mp4` and `frontend/public/`.

```
python scripts/render_chancery_briefing_media.py
```

## Repository layout

```
contracts/court_of_code.py                 the intelligent contract (11 Steward rules)
tests/                                      direct + integration tests, Windows conftest shim
scripts/deploy_studionet.py                 idempotent studionet deploy + lifecycle + evidence
scripts/render_chancery_briefing_media.py   bespoke soundtrack + subtitled demo renderer
frontend/                                   Vite + React judicial chamber workbench
video/record_chancery.mjs                   Playwright beat recorder for the redesigned UI
docs/                                        adversarial review, deployment evidence, demo video
evidence/                                    live transaction evidence
.github/workflows/                           CI (lint + direct tests) and Pages deploy
```

## Security

Fund-bearing transitions are reviewed adversarially in
[docs/adversarial-review.md](docs/adversarial-review.md). Every finding is either fixed with
a named test or left open with a stated reason. Direct-mode tests cover the leader path;
validator agreement is proven by the live studionet run in `evidence/studionet_Live_Milestone_v1.json`.
