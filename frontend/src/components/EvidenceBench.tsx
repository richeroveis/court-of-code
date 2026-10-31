import { useState } from "react";
import type { Brief, Docket } from "../lib/types";
import { formatEpoch, remaining, shortAddr } from "../lib/court";

interface FilePayload {
  docket_id: string;
  respondent: string;
  title: string;
  spec_reference_url: string;
  pr_evidence_url: string;
  brief_summary: string;
  mandatory_spec_token: string;
  principal_cet: number;
  rebuttal_window: number;
  appeal_window: number;
  bond: number;
}

interface Props {
  docket: Docket | null;
  briefs: Brief[];
  nowEpoch: number;
  busy: boolean;
  isClaimant: boolean;
  isRespondent: boolean;
  isOpen: boolean;
  onFile: (p: FilePayload) => void;
  onRebut: (id: string, text: string, bond: number) => void;
  onBrief: (id: string, handle: string, side: string, arg: string) => void;
  onUpvote: (briefId: number) => void;
  onAdjudicate: (id: string) => void;
  onChallenge: (id: string, bond: number) => void;
  onSettle: (id: string) => void;
  onCancel: (id: string) => void;
}

const DEFAULT_FILE: FilePayload = {
  docket_id: "",
  respondent: "0x154a452b0755EE812014C1405B15D905BA06f9c7",
  title: "Vue dashboard migration bounty",
  spec_reference_url: "https://github.com/nimbus-labs/dashboard/issues/77",
  pr_evidence_url: "https://github.com/nimbus-labs/dashboard/pull/78",
  brief_summary: "Claimant delivered the migration; the maintainer withheld the bounty.",
  mandatory_spec_token: "VUE-77",
  principal_cet: 120000,
  rebuttal_window: 86400,
  appeal_window: 86400,
  bond: 1000000,
};

export default function EvidenceBench({
  docket,
  briefs,
  nowEpoch,
  busy,
  isClaimant,
  isRespondent,
  isOpen,
  onFile,
  onRebut,
  onBrief,
  onUpvote,
  onAdjudicate,
  onChallenge,
  onSettle,
  onCancel,
}: Props) {
  const [form, setForm] = useState<FilePayload>({ ...DEFAULT_FILE });
  const [rebuttal, setRebuttal] = useState({ text: "", bond: 4000 });
  const [brief, setBrief] = useState({ handle: "counsel", side: "SUPPORT_CLAIMANT", argument: "" });

  return (
    <div className="bench">
      <section className="panel">
        <h2>Open a Docket of Dispute</h2>
        <div className="form-grid">
          <label>
            Docket №
            <input value={form.docket_id} onChange={(e) => setForm({ ...form, docket_id: e.target.value })} placeholder="unique id" />
          </label>
          <label>
            Respondent address
            <input value={form.respondent} onChange={(e) => setForm({ ...form, respondent: e.target.value })} />
          </label>
          <label className="wide">
            Title
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </label>
          <label className="wide">
            Specification reference URL
            <input value={form.spec_reference_url} onChange={(e) => setForm({ ...form, spec_reference_url: e.target.value })} />
          </label>
          <label className="wide">
            Claimant PR evidence URL
            <input value={form.pr_evidence_url} onChange={(e) => setForm({ ...form, pr_evidence_url: e.target.value })} />
          </label>
          <label className="wide">
            On-chain brief summary
            <textarea value={form.brief_summary} onChange={(e) => setForm({ ...form, brief_summary: e.target.value })} />
          </label>
          <label>
            Mandatory spec token
            <input value={form.mandatory_spec_token} onChange={(e) => setForm({ ...form, mandatory_spec_token: e.target.value })} />
          </label>
          <label>
            Principal (CET escrow)
            <input type="number" value={form.principal_cet} onChange={(e) => setForm({ ...form, principal_cet: Number(e.target.value) })} />
          </label>
          <label>
            Rebuttal window (s)
            <input type="number" value={form.rebuttal_window} onChange={(e) => setForm({ ...form, rebuttal_window: Number(e.target.value) })} />
          </label>
          <label>
            Appeal window (s)
            <input type="number" value={form.appeal_window} onChange={(e) => setForm({ ...form, appeal_window: Number(e.target.value) })} />
          </label>
          <label>
            Native bond (wei)
            <input type="number" value={form.bond} onChange={(e) => setForm({ ...form, bond: Number(e.target.value) })} />
          </label>
        </div>
        <button
          className="primary"
          disabled={busy || !form.docket_id}
          onClick={() => onFile(form)}
        >
          File Dispute (payable)
        </button>
      </section>

      {!docket ? (
        <section className="panel">
          <h2>Bilateral Evidence &amp; Live PR Diff Bench</h2>
          <div className="muted">Select a docket from the registry to open the evidence bench.</div>
        </section>
      ) : (
        <>
          <section className="panel">
            <h2>Docket № {docket.docket_id} · {docket.title}</h2>
            <div className="meta-line">
              {shortAddr(docket.claimant)} (claimant) v {shortAddr(docket.respondent)} (respondent) ·
              token <span className="brass">{docket.mandatory_spec_token}</span> · principal {docket.principal_cet} CET
            </div>
            <div className="diff-bench">
              <div className="diff claim">
                <div className="who">Claimant pull request proof</div>
                <a href={docket.pr_evidence_url} target="_blank" rel="noreferrer">{docket.pr_evidence_url}</a>
                <div className="note">Amici siding claimant: {docket.votes_for_claimant}</div>
              </div>
              <div className="diff resp">
                <div className="who">Respondent maintainer rebuttal</div>
                {docket.respondent_rebuttal ? (
                  <div className="note">{docket.respondent_rebuttal}</div>
                ) : (
                  <div className="muted">No rebuttal posted yet.</div>
                )}
                <div className="note">Amici siding respondent: {docket.votes_for_respondent}</div>
              </div>
            </div>
            <div className="timeline">
              <Timeline label="Filed" epoch={docket.filing_epoch} />
              <Timeline label="Rebuttal closes" epoch={docket.rebuttal_deadline_epoch} now={nowEpoch} />
              <Timeline label="Appeal closes" epoch={docket.appeal_deadline_epoch} now={nowEpoch} />
              <Timeline label="Timeout refund" epoch={docket.adjudication_timeout_epoch} now={nowEpoch} />
            </div>
          </section>

          <section className="panel cosign">
            <h2>Bilateral Co-Sign Settlement</h2>
            <div className="verdict-line">
              Status <span className={`status-chip status-${docket.status}`}>{docket.status}</span> ·
              band <strong className="cyan">{docket.verdict_band}</strong> ·
              award {docket.claimant_award_bps} bps · web source {docket.web_source_verified ? "verified" : "fallback"}
            </div>
            <div className="actions">
              {isOpen && (
                <button className="primary" disabled={busy} onClick={() => onAdjudicate(docket.docket_id)}>
                  Trigger Consensus Adjudication
                </button>
              )}
              {docket.status === "ADJUDICATED" && (isClaimant || isRespondent) && nowEpoch < docket.appeal_deadline_epoch && (
                <button className="danger" disabled={busy} onClick={() => onChallenge(docket.docket_id, 2000)}>
                  Challenge Decree (2000 wei)
                </button>
              )}
              {(docket.status === "ADJUDICATED" || docket.status === "CHALLENGED") && nowEpoch >= docket.appeal_deadline_epoch && (
                <button className="gold" disabled={busy} onClick={() => onSettle(docket.docket_id)}>
                  Execute Decree Settlement
                </button>
              )}
              {isClaimant && docket.status === "OPEN_FOR_REBUTTAL" && docket.amicus_count === 0 && (
                <button className="ghost" disabled={busy} onClick={() => onCancel(docket.docket_id)}>
                  Cancel &amp; Refund
                </button>
              )}
            </div>
            {docket.judicial_opinion && <div className="opinion">Opinion: {docket.judicial_opinion}</div>}
          </section>

          {isRespondent && docket.status === "OPEN_FOR_REBUTTAL" && (
            <section className="panel">
              <h2>Respondent Rebuttal &amp; Bond</h2>
              <textarea
                value={rebuttal.text}
                onChange={(e) => setRebuttal({ ...rebuttal, text: e.target.value })}
                placeholder="maintainer rebuttal (max 500 chars)"
              />
              <div className="inline">
                <input type="number" value={rebuttal.bond} onChange={(e) => setRebuttal({ ...rebuttal, bond: Number(e.target.value) })} />
                <button disabled={busy || !rebuttal.text} onClick={() => onRebut(docket.docket_id, rebuttal.text, rebuttal.bond)}>
                  Post Rebuttal (payable)
                </button>
              </div>
            </section>
          )}

          <section className="panel">
            <h2>Amicus Curiae Briefs ({briefs.length})</h2>
            {briefs.map((b) => (
              <div className="brief" key={b.brief_id}>
                <div className="head">
                  <span>
                    @{b.juror_handle} <span className={`side side-${b.side}`}>{b.side}</span>
                  </span>
                  <span>
                    {b.upvotes}↑{" "}
                    {isOpen && (
                      <button className="ghost" disabled={busy} onClick={() => onUpvote(b.brief_id)}>
                        +1
                      </button>
                    )}
                  </span>
                </div>
                <div className="arg">{b.argument}</div>
              </div>
            ))}
            {isOpen && (
              <div className="brief-form">
                <div className="inline">
                  <input value={brief.handle} onChange={(e) => setBrief({ ...brief, handle: e.target.value })} placeholder="juror handle" />
                  <select value={brief.side} onChange={(e) => setBrief({ ...brief, side: e.target.value })}>
                    <option value="SUPPORT_CLAIMANT">SUPPORT_CLAIMANT</option>
                    <option value="SUPPORT_RESPONDENT">SUPPORT_RESPONDENT</option>
                    <option value="NEUTRAL_TECHNICAL">NEUTRAL_TECHNICAL</option>
                  </select>
                </div>
                <textarea value={brief.argument} onChange={(e) => setBrief({ ...brief, argument: e.target.value })} placeholder="technical argument (max 300 chars)" />
                <button className="primary" disabled={busy || !brief.argument} onClick={() => onBrief(docket.docket_id, brief.handle, brief.side, brief.argument)}>
                  File Brief &amp; Vote
                </button>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Timeline({ label, epoch, now }: { label: string; epoch: number; now?: number }) {
  return (
    <div className="tl-node">
      <div className="tl-label">{label}</div>
      <div className="tl-epoch">{formatEpoch(epoch)}</div>
      {now !== undefined && <div className="tl-left">{remaining(now, epoch)}</div>}
    </div>
  );
}
