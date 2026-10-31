import { useState } from "react";
import type { Docket } from "../lib/types";

interface Props {
  docket: Docket | null;
  busy: boolean;
  runSoftFailProbe: () => Promise<string>;
  runPreDeadlineProbe: () => Promise<string>;
}

// Procedural Rule Verification Bench: safely exercise the non-trapping payable refund
// (Rule 8) and the pre-deadline adjudication protection (Rule 6/10) without risking funds.
export default function RuleBench({ docket, busy, runSoftFailProbe, runPreDeadlineProbe }: Props) {
  const [log, setLog] = useState<{ tag: string; detail: string }[]>([]);

  const push = (tag: string, detail: string) => setLog((l) => [{ tag, detail }, ...l].slice(0, 6));

  const softFail = async () => {
    const r = await runSoftFailProbe();
    push("SOFT-FAIL REFUND", r);
  };
  const preDeadline = async () => {
    const r = await runPreDeadlineProbe();
    push("PRE-DEADLINE GUARD", r);
  };

  return (
    <section className="panel rulebench">
      <h2>Procedural Rule Verification Bench</h2>
      <div className="bench-btns">
        <button className="ghost" disabled={busy} onClick={softFail}>
          Fire soft-fail payable (must refund, never revert)
        </button>
        <button className="ghost" disabled={busy || !docket} onClick={preDeadline}>
          Test pre-deadline adjudication guard
        </button>
      </div>
      <p className="hint">
        The soft-fail probe sends value to a knowingly invalid filing. The contract must credit
        100% back to your refundable balance and return a receipt instead of reverting. The
        pre-deadline probe attempts to adjudicate before the rebuttal window closes and must be
        refused.
      </p>
      {log.length === 0 ? (
        <div className="muted">No probes run yet.</div>
      ) : (
        <ul className="bench-log">
          {log.map((e, i) => (
            <li key={i}>
              <span className="tag">{e.tag}</span>
              <code>{e.detail}</code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
