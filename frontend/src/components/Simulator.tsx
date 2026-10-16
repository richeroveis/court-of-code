import { useEffect, useState } from "react";
import { SlidersHorizontal, Sparkles } from "lucide-react";
import { settle } from "../lib/court";
import { hum, click } from "../lib/sound";
import Gauge from "./Gauge";

interface SimulatorProps {
  escrow?: number;
  bps?: number;
  specTokenFound?: boolean;
}

// Interactive what-if sandbox: visitors drag sliders and watch the exact contract
// settlement math (500 bps quantization, spec-token cap, escrow-conserving split and
// verdict band) update live, before ever submitting a transaction.
export default function Simulator({ escrow = 250000, bps = 6000, specTokenFound = true }: SimulatorProps) {
  const [rawBps, setRawBps] = useState(bps);
  const [esc, setEsc] = useState(escrow);
  const [found, setFound] = useState(specTokenFound);
  const [sweep, setSweep] = useState(0);

  const s = settle(rawBps, esc, found);
  const claimPct = esc > 0 ? (s.claimantPayout / esc) * 100 : 0;

  // A slow shimmer sweep so the widget feels alive even when idle.
  useEffect(() => {
    const id = window.setInterval(() => setSweep((v) => (v + 1) % 100), 60);
    return () => window.clearInterval(id);
  }, []);

  return (
    <section className="panel sim">
      <h2>
        <SlidersHorizontal size={15} className="h2icon" /> Payout &amp; Consensus Simulator
      </h2>
      <div className="sim-body">
        <div className="sim-controls">
          <label className="sim-field">
            <span>
              AI consensus award <b>{rawBps}</b> bps
            </span>
            <input
              type="range"
              min={0}
              max={10000}
              step={100}
              value={rawBps}
              onChange={(e) => {
                setRawBps(Number(e.target.value));
                hum();
              }}
            />
          </label>
          <label className="sim-field">
            <span>
              Disputed escrow <b>{esc.toLocaleString()}</b>
            </span>
            <input
              type="range"
              min={100}
              max={10000000}
              step={100}
              value={esc}
              onChange={(e) => {
                setEsc(Number(e.target.value));
                hum();
              }}
            />
          </label>
          <div className="sim-toggle">
            <span>Mandatory spec token present in evidence?</span>
            <button
              type="button"
              className={`chip ${found ? "chip-on" : "chip-off"}`}
              onClick={() => {
                setFound((v) => !v);
                click();
              }}
            >
              {found ? "FOUND" : "MISSING"}
            </button>
          </div>
          <div className="sim-readout">
            <div>
              <span className="k">Quantized (500 ladder)</span> <b>{s.quantizedBps}</b> bps
            </div>
            <div>
              <span className="k">After token cap</span> <b>{s.cappedBps}</b> bps
            </div>
            <div>
              <span className="k">Verdict band</span>{" "}
              <b className={`verdict-${s.verdict}`}>{s.verdict}</b>
            </div>
          </div>
        </div>

        <div className="sim-viz">
          <Gauge value={s.cappedBps} caption="claimant share" />
          <div className="sim-split">
            <div className="sim-split-track">
              <div className="sim-split-claim" style={{ width: `${claimPct}%` }} />
              <div className="sim-split-sheen" style={{ left: `${sweep}%` }} />
            </div>
            <div className="sim-split-labels">
              <span className="claim">Claimant {s.claimantPayout.toLocaleString()}</span>
              <span className="resp">Respondent {s.respondentPayout.toLocaleString()}</span>
            </div>
            <div className="sim-conserved">
              <Sparkles size={13} /> escrow conserved:{" "}
              <b className={s.conserved ? "good" : "bad"}>{s.conserved ? "yes" : "no"}</b>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
