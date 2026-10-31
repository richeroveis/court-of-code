import { useMemo, useState } from "react";
import type { Docket } from "../lib/types";
import { AWARD_LADDER, apportion } from "../lib/court";
import Gauge from "./Gauge";

interface Props {
  docket: Docket | null;
}

// Chancery Award Apportionment Calculator: a docket-specific PR bounty split preview.
// This is intentionally NOT a generic what-if toy; it models the exact discrete ladder,
// 500-bps baseline grid and escrow-conserving decree the tribunal will bind on chain.
export default function AwardMatrix({ docket }: Props) {
  const [rawAward, setRawAward] = useState(6800);
  const [rawBaseline, setRawBaseline] = useState(7300);
  const [principal, setPrincipal] = useState(10000);
  const [bond, setBond] = useState(4000);

  const result = useMemo(
    () => apportion(rawAward, rawBaseline, principal, bond),
    [rawAward, rawBaseline, principal, bond],
  );

  const loadFromDocket = () => {
    if (!docket) return;
    setRawAward(docket.claimant_award_bps);
    setRawBaseline(docket.quantized_spec_baseline_bps);
    setPrincipal(docket.principal_cet);
    setBond(docket.respondent_bond_cet);
  };

  return (
    <section className="panel matrix">
      <h2>Chancery Award Apportionment</h2>
      <button className="ghost small" disabled={!docket} onClick={loadFromDocket}>
        Seed from selected docket
      </button>
      <div className="slider-row">
        <span>Consensus award (raw bps)</span>
        <input type="range" min={0} max={10000} value={rawAward} onChange={(e) => setRawAward(Number(e.target.value))} />
        <b className="cyan">{rawAward}</b>
      </div>
      <div className="slider-row">
        <span>Spec completeness baseline</span>
        <input type="range" min={0} max={10000} value={rawBaseline} onChange={(e) => setRawBaseline(Number(e.target.value))} />
        <b>{rawBaseline}</b>
      </div>
      <div className="inline">
        <label>
          Principal CET
          <input type="number" value={principal} onChange={(e) => setPrincipal(Number(e.target.value))} />
        </label>
        <label>
          Respondent bond
          <input type="number" value={bond} onChange={(e) => setBond(Number(e.target.value))} />
        </label>
      </div>

      <div className="matrix-out">
        <Gauge value={result.snappedAward} caption="snapped to judicial ladder" accent="#38BDF8" accent2="#D4AF37" size={150} />
        <div className="matrix-read">
          <div className="k">Discrete award</div>
          <div className="v brass">{result.snappedAward} bps</div>
          <div className="k">Verdict band</div>
          <div className="v">{result.band}</div>
          <div className="k">Quantized baseline</div>
          <div className="v">{result.quantizedBaseline} bps (500 grid)</div>
          <div className="k">Claimant credit</div>
          <div className="v cyan">{result.claimantCredit}</div>
          <div className="k">Respondent credit</div>
          <div className="v cyan">{result.respondentCredit}</div>
          <div className={`conserved ${result.conserved ? "ok" : "bad"}`}>
            {result.conserved ? "escrow conserved (principal + bond)" : "conservation violated"}
          </div>
        </div>
      </div>

      <div className="ladder">
        {AWARD_LADDER.map((a) => (
          <button
            key={a}
            className={`anchor ${result.snappedAward === a ? "hit" : ""}`}
            onClick={() => setRawAward(a)}
          >
            {a}
          </button>
        ))}
      </div>
    </section>
  );
}
