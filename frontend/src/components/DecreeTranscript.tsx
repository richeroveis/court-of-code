import type { Docket } from "../lib/types";
import { AWARD_LADDER } from "../lib/court";

interface Props {
  docket: Docket | null;
}

// Equivalence Principle Decree Transcript: lays bare the consensus-bound baseline on
// the 500-bps grid and the five discrete split anchors, highlighting the bound band.
export default function DecreeTranscript({ docket }: Props) {
  const bands: Record<string, string> = {
    FULL_CLAIMANT_DECREE: "10000",
    MAJORITY_CLAIMANT_SPLIT: "7500",
    EQUITABLE_FIFTY_SPLIT: "5000",
    PARTIAL_CONTRIBUTION_AWARD: "2500",
    RESPONDENT_SUMMARY_DISMISSAL: "0",
  };

  return (
    <section className="panel transcript">
      <h2>Equivalence Principle Decree Transcript</h2>
      {!docket ? (
        <div className="muted">Select a docket to read its decree record.</div>
      ) : (
        <>
          <div className="tr-head">
            <span>Consensus-bound spec baseline</span>
            <strong className="brass">{docket.quantized_spec_baseline_bps} bps</strong>
            <span className="grid-tag">500-bps grid · exact validator agreement</span>
          </div>
          <div className="anchors">
            {AWARD_LADDER.map((a) => (
              <div key={a} className={`anchor-cell ${docket.claimant_award_bps === a ? "bound" : ""}`}>
                <div className="anchor-bps">{a}</div>
                <div className="anchor-band">{bandName(a, bands)}</div>
              </div>
            ))}
          </div>
          <div className="tr-derived">
            <div className="k">Bound verdict band</div>
            <div className="v cyan">{docket.verdict_band}</div>
            <div className="k">Derived claimant payout</div>
            <div className="v">{docket.derived_claimant_payout}</div>
            <div className="k">Derived respondent refund</div>
            <div className="v">{docket.derived_respondent_refund}</div>
            <div className="k">Derived slash</div>
            <div className="v">{docket.derived_slash_amount}</div>
            <div className="k">Web evidence sources</div>
            <div className="v">{docket.web_source_verified ? "rendered live by validators" : "on-chain fallback summary"}</div>
          </div>
        </>
      )}
    </section>
  );
}

function bandName(anchor: number, bands: Record<string, string>): string {
  for (const [name, val] of Object.entries(bands)) {
    if (Number(val) === anchor) return name;
  }
  return "";
}
