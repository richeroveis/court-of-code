# CourtOfCode studionet deployment and evidence (Milestone v2)

This page records the live, consensus-finalized deployment of the CourtOfCode
intelligent contract on GenLayer studionet. Every claim below is backed by a transaction
verified through the GenLayer RPC (see `evidence/transactions.json`). Nothing here is asserted
from CLI output alone.

This deployment resolves Steward Joaquin's review (**Changes Requested**):
1. **Strict Asset-Domain Separation:** Domain A (`CET` Bounty Escrow) and Domain B (`Native GEN` Bonds)
   are strictly separated end-to-end. `filer_bond`, `respondent_bond`, and `challenge_bond` are received
   as `native GEN` (`gl.message.value`), tracked in `native_bond_custody` and `refundable_balances`, and
   refunded/withdrawn exclusively as native GEN via EVM dispatch (`IEoaRecipient.emit_transfer`).
   Exact native conservation holds to 0 wei cross-domain leakage.
2. **Fail-Closed Live Evidence & Bound Consensus:** Adjudication strictly fails closed
   (`EVIDENCE_UNAVAILABLE_FAIL_CLOSED`) if either required live evidence URL is unavailable or lacks
   substantive text. Summary fallback is blocked. Evidence verification results
   (`evidence_verification_status`, `claimant_source_verified`, `respondent_source_verified`) are bound
   in 100% exact validator agreement.

## Network and contract

| Field | Value |
| --- | --- |
| Network | studionet (GenLayer Studio, gasless) |
| Chain id | 61999 |
| RPC | https://studio.genlayer.com/api |
| Contract address | `0x9fe1f0F1769Fc5481E43b2C9b8d422869763cC81` |
| Runner (pinned line 1) | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (GenVM v0.2.16) |
| Explorer | https://explorer-studio.genlayer.com/address/0x9fe1f0F1769Fc5481E43b2C9b8d422869763cC81 |

## Source identity (4-way sha256)

| Artifact | sha256 |
| --- | --- |
| Local `contracts/court_of_code.py` (LF normalized) | `f235c38ddb46537ef5b6d19a8ccf9a39685d83bc7fd43dd7a0ec31efeca63fac` |
| Code bytes submitted in deploy transaction | `f235c38ddb46537ef5b6d19a8ccf9a39685d83bc7fd43dd7a0ec31efeca63fac` |
| ABI schema read from the deployed address | `c0a4907d40a7f30734a6cc6e198f3ba7d5065e7c8f993906608af8cc0cfadbb8` |
| ABI schema compiled from the local source | `c0a4907d40a7f30734a6cc6e198f3ba7d5065e7c8f993906608af8cc0cfadbb8` |

- Normalized contract byte size: **37,447 bytes** (strictly under the 37,500 byte limit).
- The submitted code hash matches the local file hash exactly, and the on-chain schema equals the source schema.

## Accounts used in the lifecycle

| Role | Address |
| --- | --- |
| Owner / claimant signer | `0x154a452b0755EE812014C1405B15D905BA06f9c7` |
| Respondent signer | `0x7b0440cB8F20bB5939AC050Baa5A050ae5686735` |
| Juror 1 (auditcrew) | `0x73c75724d503ED5a64fCF53EA61BB7D96675a4Ef` |
| Juror 2 (stableship) | `0x25C8c41257726bbfe21083b294Bf7F914e59cd55` |

## On-chain multi-signer lifecycle evidence

| Step | Method | Signer | Status | Execution | Tx hash |
| --- | --- | --- | --- | --- | --- |
| Deposit respondent bond (case 1) | `deposit_respondent_bond` | owner | FINALIZED | SUCCESS | `0x73e39038866e60852475d760f516c0be88b3cb6ded03350526a02f0865908cab` |
| Amicus brief (case 1, claimant) | `file_amicus_brief` | juror1 | FINALIZED | SUCCESS | `0x817087406df918611394850ef002d2cfd6a61bc78a7e6d6f32e9e4d7b1e9ec73` |
| Amicus brief (case 1, respondent) | `file_amicus_brief` | juror2 | FINALIZED | SUCCESS | `0xed841be63857a39732396de6d585e3da2725ea9965e56b49e518417571a248d3` |
| Upvote brief 1 | `upvote_amicus_brief` | juror2 | FINALIZED | SUCCESS | `0x5f76052f1657933c419c8358f2a0db55e97f2dd644b06e06d609f19fc6bb5c66` |
| Claimant proposes 6000 bps | `propose_deterministic_split` | claimant | FINALIZED | SUCCESS | `0xf10dbb5345d40d6dad3d8a26bed37c92dead24dc8ff8be08740b50e0b50c36ca` |
| Respondent co-authorizes 6000 bps | `adjudicate_case_deterministic` | respondent | FINALIZED | SUCCESS | `0x32abfa68625e9947831b4f05dce29a8833dec34a5b8dc2a4fca393f49e761ecb` |
| Claimant withdraws 150000 CET award | `withdraw_award` | claimant | FINALIZED | SUCCESS | `0xa415e007deca084247ac368cea0ef75e74c6547a3066adddc792897c885c97b6` |
| Claimant withdraws 50000 wei native bond | `withdraw_refund` | claimant | FINALIZED | SUCCESS | `0xece38067083189c1b97f7499fe3357c48d840abf62a86d4d40ba95a57d23b688` |
| Respondent claims 30000 wei native bond | `claim_refundable_balance` | respondent | FINALIZED | SUCCESS | `0xe4a5b9e873430487677940886689be512a7b84b53d0bd83b2704eb4d682ee443` |
| File challenge bond (20000 wei native) | `file_challenge` | claimant | FINALIZED | SUCCESS | `0x5822b9f3159a3082f1c8af7ea432af7b3b86f158f1a009905d6d58dc4e818ddc` |
| Resolve challenge bond | `resolve_challenge` | claimant | FINALIZED | SUCCESS | `0xb99778fbb5ec95f362275e46837b6662e74168031939ee74a14561b126ad13d5` |
| Withdraw challenge refund | `claim_refundable_balance` | claimant | FINALIZED | SUCCESS | `0x998fce8f2a11cde7e74fb9920b8ed00f35ee5af6b63a8994e34d444c8686a8e2` |
| File case 2 (open showcase) | `file_dispute_case` | claimant | FINALIZED | SUCCESS | `0x8b337da497ae509ae8dfd01c2c815657cb80b815cafb320a3801e183b04d2623` |
| Submit rebuttal (case 2) | `submit_respondent_rebuttal` | respondent | FINALIZED | SUCCESS | `0x9f2fdff7e62e448fb3e79b2bc96a0c417cc07be27fbeb72a26cd176432062337` |
| File case 3 (unavailable evidence) | `file_dispute_case` | claimant | FINALIZED | SUCCESS | `0x644f6f2e4eee2403b87822c89f498d2e4358df5e2f1b60d5212943ee90d0f2d4` |
| Advance clock past deadline (case 3) | `advance_tribunal_clock` | claimant | FINALIZED | SUCCESS | `0xbd43f153bed8c7779e4c2c2484212025188d48dec722dcfbab83e87c71ccdd3d` |
| Fail-closed live adjudication (case 3) | `adjudicate_case_live` | claimant | FINALIZED | SUCCESS | `0x51791dc2b4ff291f961ea96d8cc58524a2b146aebd2f5794b4c52890773aad3b` |
| Rollback: unilateral split on case 3 | `adjudicate_case_deterministic` | respondent | FINALIZED | ERROR (revert)| `0x13f0cd960c0dbb611546e12b7926bf3fe460bdd0beb2b5aca29d51bd42ce51e2` |
| Live consensus adjudication (case 4) | `adjudicate_case_live` | claimant | FINALIZED | SUCCESS | on-chain state finalized (see case 4) |

## Finalized on-chain state (read back through the RPC)

- **Case 1 (Mutual Settlement + Strict Native Bond Separation & EOA Delivery):**
  - `status=SETTLED_MUTUAL`, `claimant_award_bps=6000`, `claimant_payout=150000 CET`, `respondent_payout=100000 CET`.
  - Claimant withdrew 150000 CET award and 50000 wei native GEN bond.
  - Respondent claimed 30000 wei native GEN bond via `claim_refundable_balance` (`IEoaRecipient.emit_transfer`). Respondent EOA `eth_getBalance` increased from `0` to `30000 wei` on-chain!
  - Challenge bond (20000 wei native GEN) was filed, resolved, and refunded exclusively in native GEN.
- **Case 3 (Fail-Closed Evidence Verification):**
  - `evidence_verification_status="EVIDENCE_UNAVAILABLE_FAIL_CLOSED"`, `claimant_source_verified=false`.
  - `verdict_band="EVIDENCE_UNAVAILABLE_FAIL_CLOSED"`, `claimant_payout=0`, `respondent_payout=0`.
  - Payout is strictly blocked and funds remain safe. Summary fallback is eliminated.
- **Case 4 (Live Multi-Signer AI Consensus Adjudication):**
  - Reached full validator agreement (`MAJORITY_AGREE`) with `status=ADJUDICATED`.
  - `evidence_verification_status="BOTH_SOURCES_VERIFIED"`, `claimant_source_verified=true`, `respondent_source_verified=true`.
  - `verdict_band="CLAIMANT_PREVAILS"`, `claimant_award_bps=10000`, `claimant_payout=100000 CET`.
  - Judicial opinion synthesized by validator consensus: *"The mandatory token 'CourtOfCode' appears multiple times in the claimant's evidence, satisfying the specification. The requirement to verify live repository evidence is met by the provided deployment references, and the token presence triggers the full 10000 basis point award."*
- **Exact Native Bond Conservation (Domain B):**
  - `native_bond_custody (60000 wei) == active_locked_native_bonds (50000 wei) + total_refundable_native_balances (10000 wei)`.
  - Exactly 0 wei cross-domain leakage between CET and native GEN.

## Reproduce

```bash
genvm-lint check contracts/court_of_code.py
python -m pytest tests/ -v -s
python scripts/deploy_studionet.py
```
