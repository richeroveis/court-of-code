import { useState } from "react";
import { ChevronDown, ChevronRight, Globe, ShieldCheck, Radio, Cpu, Scale } from "lucide-react";
import { click, hum } from "../lib/sound";

interface CaseLike {
  case_id: number;
  case_title: string;
  mandatory_spec_token: string;
  claimant_evidence_url: string;
  respondent_rebuttal_url: string;
  status: string;
  claimant_award_bps: number;
  verdict_label: string;
  judicial_opinion: string;
}

// A collapsible inspector that lays bare the exact non-deterministic pipeline the
// contract runs: the two gl.nondet.web.render source URLs, the mandatory token check,
// and the gl.eq_principle.prompt_comparative evaluation stages.
export default function PromptInspector({ c }: { c: CaseLike }) {
  const [open, setOpen] = useState(false);
  const stages = [
    { icon: Globe, title: "gl.nondet.web.render", body: "Independently fetch both evidence URLs as text (leader and every validator)." },
    { icon: ShieldCheck, title: "sanitize_evidence", body: "Strip control chars, defuse </untrusted delimiters, truncate to 5000 chars." },
    { icon: Cpu, title: "gl.nondet.exec_prompt", body: "Tribunal LLM returns claimant_award_bps, spec_token_found, opinion." },
    { icon: Radio, title: "prompt_comparative", body: "Validators re-run and must agree exactly on bps (500 ladder) and token flag." },
    { icon: Scale, title: "deterministic settlement", body: "Token cap, escrow-conserving split, verdict band, credit awards." },
  ];

  return (
    <section className="panel inspector">
      <button
        type="button"
        className="inspector-head"
        onClick={() => {
          setOpen((v) => !v);
          if (open) click();
          else hum();
        }}
      >
        <span className="inspector-title">Consensus &amp; Prompt Inspector</span>
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {open && (
        <div className="inspector-body">
          <div className="insp-row">
            <span className="insp-k">Claimant render URL</span>
            <code className="insp-url claim">{c.claimant_evidence_url}</code>
          </div>
          <div className="insp-row">
            <span className="insp-k">Respondent render URL</span>
            <code className="insp-url resp">{c.respondent_rebuttal_url || "(none submitted)"}</code>
          </div>
          <div className="insp-row">
            <span className="insp-k">Mandatory spec token</span>
            <code className="insp-token">{c.mandatory_spec_token}</code>
            <span className="insp-note">
              If not genuinely present in the claimant evidence, a majority award is capped at 5000 bps.
            </span>
          </div>

          <ol className="pipeline">
            {stages.map((st, i) => {
              const Icon = st.icon;
              return (
                <li key={st.title} className="pipe-node">
                  <span className="pipe-dot">{i + 1}</span>
                  <span className="pipe-icon">
                    <Icon size={15} />
                  </span>
                  <div>
                    <div className="pipe-title">{st.title}</div>
                    <div className="pipe-body">{st.body}</div>
                  </div>
                </li>
              );
            })}
          </ol>

          <div className="insp-result">
            <span className="insp-k">Live result</span>
            <b className={`verdict-${c.verdict_label}`}>{c.verdict_label}</b>
            <span className="muted small">
              {" "}
              {c.claimant_award_bps} bps &middot; {c.status}
            </span>
          </div>
          {c.judicial_opinion && <div className="insp-opinion">{c.judicial_opinion}</div>}
        </div>
      )}
    </section>
  );
}
