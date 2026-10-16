# CourtOfCode

A decentralized open-source bounty and pull-request dispute tribunal, built as a
GenLayer intelligent contract. A Claimant (the contributor who shipped the work) and a
Respondent (the sponsor or maintainer who withheld the bounty) each submit a live
evidence URL over a disputed deliverable. Community jurors file weighted amicus briefs,
and GenLayer validators render a binding proportional split award (0 to 100 percent to
the claimant versus the respondent) by independently fetching the evidence and comparing
it against the agreed technical specification.

The point of using GenLayer here is that the outcome is a subjective technical judgment
that must settle real money. It cannot be reduced to a deterministic on-chain check, and
it cannot be trusted to a single off-chain oracle, so it needs independently verified
validator consensus with a transparent, appealable transition.

- Contract: `contracts/court_of_code.py` (GenLayer intelligent contract)
- Live network: studionet (chain 61999), deployed and seeded with real dispute data
- Interactive frontend: https://richeroveis.github.io/court-of-code/
- Deployment evidence: [docs/deployment.md](docs/deployment.md)
- Security review: [docs/adversarial-review.md](docs/adversarial-review.md)
- Demo video: `docs/demo-video-subtitled.mp4` (generated, not committed on main)

## Deployed contract

| Field | Value |
| --- | --- |
| Address | `0x5049635f17E614f3BE0D3446af166DBC8E61c3eC` |
| Network | studionet (chain 61999) |
| Pinned runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (GenVM v0.2.16) |
| Contract source sha256 | `7fafd77fae0d92121a04783c5b2adb9788bd8820df3bc1133ba4982713c55d74` |
| Release tag | `studionet-v1` |
| Deployed source | tag `studionet-v1`; contract sha256 `7fafd77fae0d92121a04783c5b2adb9788bd8820df3bc1133ba4982713c55d74` |

The deployed source hash and the on-chain ABI schema are cross-checked in
[docs/deployment.md](docs/deployment.md).

## How it works

1. A claimant calls `file_dispute_case`, recording the agreed rubric, a mandatory spec
   token, the claimant evidence URL and the notional disputed escrow (100 to 10000000).
2. The respondent may `submit_respondent_rebuttal`, which moves the case to
   `READY_FOR_TRIAL`.
3. Any account may `file_amicus_brief` to join the jury with one weighted vote
   (`SUPPORT_CLAIMANT`, `SUPPORT_RESPONDENT` or `NEUTRAL_TECHNICAL`) and may
   `upvote_amicus_brief` to boost another juror's argument. Reputation accrues.
4. `adjudicate_case_live` fetches both evidence URLs through `gl.nondet.web.render`,
   sanitizes them, and runs the tribunal prompt through
   `gl.eq_principle.prompt_comparative`. The award is snapped onto a fixed 500 bps ladder
   so the fund-moving value is a discrete label every validator must reproduce exactly.
5. Settlement is fully deterministic and escrow-conserving:
   `claimant_payout = escrow * bps // 10000`, `respondent_payout = escrow - claimant_payout`.
   If the mandatory spec token is not found, a majority award is capped at 5000 bps.
6. `adjudicate_case_deterministic` lets the owner or a party record a mutually agreed
   split without an LLM. `withdraw_award` pulls a party's claimable credit. `cancel_case`
   refunds the escrow to the claimant while the case is still open and unjudged.

## Frontend

The judicial terminal UI (Vite + React + genlayer-js) offers a one-click instant juror
burner wallet with a rotate-identity control, optional MetaMask (EIP-1193) connection, a
split-screen evidence bench comparing the claimant deliverable against the respondent
rebuttal, a live split-award visualizer, and every tribunal action. Deterministic writes
use `leaderOnly: true` for speed; `adjudicate_case_live` runs on full consensus.

It also carries an interactive Payout & Consensus Simulator (drag the AI-consensus and
escrow sliders to preview the exact 500 bps quantized, spec-token-capped,
escrow-conserving settlement before submitting a transaction), a per-case Consensus &
Prompt Inspector drawer that lays bare the `gl.nondet.web.render` evidence sources, the
mandatory spec-token check and the `prompt_comparative` pipeline, one-click Test Security
Guard (expected revert) and Quick-Fill actions, a custom SVG award gauge, an ambient
animated background, a zero-dependency Web Audio sound layer with a navbar mute toggle,
and a confetti burst when a write transaction reaches FINALIZED.

```
cd frontend
npm install
npm run dev      # local dev server
npm run build    # production build to frontend/dist
```

## Testing

Direct-mode tests exercise the leader path in seconds; integration tests read the live
studionet deployment.

```
genvm-lint check contracts/court_of_code.py
gltest tests/test_court_of_code_direct.py          # 58 tests, leader path
gltest tests/test_court_of_code_integration.py -v  # 7 tests, live studionet state
```

To deploy and seed a fresh instance:

```
python scripts/deploy_studionet.py
```

## Repository layout

```
contracts/court_of_code.py        the intelligent contract
tests/                            direct + integration tests, Windows conftest shim
scripts/deploy_studionet.py       idempotent studionet deploy + seed + evidence
scripts/make_logo.py              regenerates the 512x512 logo
frontend/                         Vite + React judicial terminal UI
tools/generate_soundtrack.py      stdlib-only synthesizer for the demo soundtrack
video/                            Playwright beat recorder + ffmpeg subtitle/audio muxer
docs/                             adversarial review, deployment evidence, logo, demo video
.github/workflows/                CI (lint + direct tests) and Pages deploy
```

## Security

Fund-bearing transitions are reviewed adversarially in
[docs/adversarial-review.md](docs/adversarial-review.md). Every finding is either FIXED
with a named test or OPEN with a stated reason. Direct-mode tests cover the leader path
only; validator agreement is proven by the live studionet run in
[docs/deployment.md](docs/deployment.md).
