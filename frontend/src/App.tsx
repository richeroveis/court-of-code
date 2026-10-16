import { useCallback, useEffect, useMemo, useState } from "react";
import confetti from "canvas-confetti";
import {
  Scale,
  Volume2,
  VolumeX,
  Gavel,
  ShieldAlert,
  Sparkles,
  Radio,
  Trophy,
  Wallet,
  RefreshCw,
} from "lucide-react";
import {
  WalletState,
  contractAddress,
  setContractAddress,
  connectBurner,
  connectMetaMask,
  rotateBurner,
  readContract,
  writeContract,
} from "./lib/genlayer";
import BackgroundFX from "./components/BackgroundFX";
import Gauge from "./components/Gauge";
import Simulator from "./components/Simulator";
import PromptInspector from "./components/PromptInspector";
import GuardLab from "./components/GuardLab";
import { isMuted, toggleMuted, click, hum, chime, errorBuzz } from "./lib/sound";

function celebrate() {
  confetti({
    particleCount: 90,
    spread: 78,
    startVelocity: 32,
    origin: { y: 0.66 },
    colors: ["#22d3ee", "#e2be60", "#34d399", "#f59e0b"],
  });
}

interface DisputeCase {
  case_id: number;
  claimant: string;
  respondent: string;
  case_title: string;
  contract_rubric: string;
  mandatory_spec_token: string;
  claimant_evidence_url: string;
  respondent_rebuttal_url: string;
  rebuttal_note: string;
  disputed_escrow: number;
  votes_for_claimant: number;
  votes_for_respondent: number;
  amicus_count: number;
  status: string;
  claimant_award_bps: number;
  claimant_payout: number;
  respondent_payout: number;
  verdict_label: string;
  judicial_opinion: string;
}

interface Brief {
  brief_id: number;
  case_id: number;
  juror: string;
  juror_handle: string;
  side: string;
  argument: string;
  upvotes: number;
}

interface Stats {
  total_cases: number;
  open_cases: number;
  adjudicated_cases: number;
  cancelled_cases: number;
  total_briefs: number;
  votes_for_claimant: number;
  votes_for_respondent: number;
  escrow_in_dispute: number;
}

interface Toast {
  kind: "ok" | "err" | "pending";
  text: string;
}

const LOGO_URL = `${import.meta.env.BASE_URL}logo.png`;

const PRESET = {
  respondent: "0x154a452b0755EE812014C1405B15D905BA06f9c7",
  case_title: "Vue dashboard migration bounty",
  contract_rubric:
    "Port the legacy jQuery dashboard to Vue 3, keep the REST contract, ship the VUE-77 test suite green",
  mandatory_spec_token: "VUE-77",
  claimant_evidence_url: "https://github.com/nimbus-labs/dashboard/pull/77",
  disputed_escrow: 120000,
};

export default function App() {
  const [wallet, setWallet] = useState<WalletState | null>(null);
  const [contract, setContract] = useState(contractAddress());
  const [cases, setCases] = useState<DisputeCase[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<DisputeCase | null>(null);
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [leaderboard, setLeaderboard] = useState<{ juror: string; reputation: number }[]>([]);
  const [claimable, setClaimable] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [busy, setBusy] = useState(false);
  const [muted, setMutedState] = useState(isMuted());

  const toggleSound = () => {
    const m = toggleMuted();
    setMutedState(m);
    if (!m) click();
  };

  const flash = (kind: Toast["kind"], text: string) => setToast({ kind, text });

  const load = useCallback(
    async (w: WalletState, cid: number | null) => {
      try {
        const all = await readContract<DisputeCase[]>(w, "get_all_cases");
        setCases(all);
        const st = await readContract<Stats>(w, "get_tribunal_stats");
        setStats(st);
        const lb = await readContract<{ juror: string; reputation: number }[]>(
          w,
          "get_juror_leaderboard",
        );
        setLeaderboard(lb);
        const cw = await readContract<number>(w, "get_claimable_award", [w.address]);
        setClaimable(Number(cw));
        const id = cid ?? (all.length ? all[all.length - 1].case_id : null);
        if (id != null) {
          setSelectedId(id);
          const one = await readContract<DisputeCase>(w, "get_case", [id]);
          setSelected(one);
          const bs = await readContract<Brief[]>(w, "get_case_briefs", [id]);
          setBriefs(bs);
        }
      } catch (e) {
        flash("err", `Read failed: ${(e as Error).message}`);
      }
    },
    [],
  );

  const connect = async (mode: "burner" | "metamask") => {
    click();
    try {
      setBusy(true);
      const w = mode === "burner" ? connectBurner() : await connectMetaMask();
      setWallet(w);
      hum();
      flash("ok", `Connected ${mode} wallet ${short(w.address)}`);
      await load(w, selectedId);
    } catch (e) {
      errorBuzz();
      flash("err", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const rotate = async () => {
    click();
    rotateBurner();
    await connect("burner");
    flash("ok", "Rotated to a fresh juror identity");
  };

  const selectCase = async (id: number) => {
    if (!wallet) return;
    click();
    setSelectedId(id);
    const one = await readContract<DisputeCase>(wallet, "get_case", [id]);
    setSelected(one);
    const bs = await readContract<Brief[]>(wallet, "get_case_briefs", [id]);
    setBriefs(bs);
    hum();
  };

  const runWrite = async (
    fn: string,
    args: unknown[],
    opts: { leaderOnly?: boolean; label: string },
  ) => {
    if (!wallet) return;
    try {
      setBusy(true);
      hum();
      flash("pending", `${opts.label}: submitting to studionet consensus...`);
      const res = await writeContract(wallet, fn, args, { leaderOnly: opts.leaderOnly });
      if (res.statusName !== "FINALIZED") {
        errorBuzz();
        flash("err", `${opts.label}: ${res.statusName} (tx ${short(res.txHash)})`);
        return;
      }
      if (!res.succeeded) {
        errorBuzz();
        flash("err", `${opts.label}: execution reverted (tx ${short(res.txHash)})`);
        return;
      }
      chime();
      celebrate();
      flash("ok", `${opts.label}: FINALIZED tx ${short(res.txHash)}`);
      await load(wallet, selectedId);
    } catch (e) {
      errorBuzz();
      flash("err", `${opts.label} failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  // One-click adversarial probe: attempt to file a self-dealing case (respondent equals
  // caller). The contract guard must revert it, and nothing is written on chain.
  const probeGuard = async () => {
    if (!wallet || busy) return;
    click();
    setBusy(true);
    flash("pending", "Security guard probe: filing self-dealing case (expect revert)...");
    try {
      const res = await writeContract(
        wallet,
        "file_dispute_case",
        [wallet.address, "guard probe", "guard rubric text", "TOK", "https://example.com/x", 5000],
        { leaderOnly: true },
      );
      if (!res.succeeded) {
        errorBuzz();
        flash("ok", `Guard held: self-dealing case reverted as expected (tx ${short(res.txHash)})`);
      } else {
        chime();
        flash("err", "Guard FAILED: self-dealing case was unexpectedly accepted");
      }
    } catch (e) {
      errorBuzz();
      flash("ok", `Guard held: probe reverted (${(e as Error).message.slice(0, 60)})`);
    } finally {
      setBusy(false);
    }
  };

  // ---- action forms ----
  const [fileForm, setFileForm] = useState({ ...PRESET });
  const [rebuttalForm, setRebuttalForm] = useState({ url: "", note: "" });
  const [briefForm, setBriefForm] = useState({
    handle: "juror",
    side: "SUPPORT_CLAIMANT",
    argument: "",
  });
  const [liveBusy, setLiveBusy] = useState(false);

  const isClaimant = selected && wallet && eq(selected.claimant, wallet.address);
  const isRespondent = selected && wallet && eq(selected.respondent, wallet.address);
  const isOpen = selected && (selected.status === "OPEN_FOR_REBUTTAL" || selected.status === "READY_FOR_TRIAL");

  const awardPct = useMemo(
    () => (selected ? (selected.claimant_award_bps / 10000) * 100 : 0),
    [selected],
  );

  return (
    <div className="app">
      <BackgroundFX />
      <header className="top">
        <img src={LOGO_URL} alt="CourtOfCode" />
        <div className="title-block">
          <h1>
            <Scale size={18} className="h1icon" /> CourtOfCode Tribunal
          </h1>
          <div className="sub">
            Decentralized bounty &amp; PR dispute court on GenLayer studionet
          </div>
        </div>
        <div className="spacer" />
        <button
          className="ghost iconbtn"
          onClick={toggleSound}
          title={muted ? "Unmute UI sound" : "Mute UI sound"}
          aria-label={muted ? "Unmute" : "Mute"}
        >
          {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
        </button>
        <div className="wallet">
          {!wallet && (
            <>
              <button className="primary" disabled={busy} onClick={() => connect("burner")}>
                <Wallet size={14} className="btnicon" /> 1-Click Instant Juror Wallet
              </button>
              <button disabled={busy} onClick={() => connect("metamask")}>
                Connect MetaMask
              </button>
            </>
          )}
          {wallet && (
            <>
              <span className="badge">{wallet.mode}</span>
              <span className="badge live">{short(wallet.address)}</span>
              <button className="ghost" disabled={busy} onClick={rotate} title="New burner identity">
                <RefreshCw size={13} className="btnicon" /> Rotate Identity
              </button>
              <button className="ghost" onClick={() => setWallet(null)}>
                Disconnect
              </button>
            </>
          )}
        </div>
      </header>

      <Simulator
        escrow={selected?.disputed_escrow ?? 250000}
        bps={selected?.claimant_award_bps ?? 6000}
        specTokenFound={(selected?.claimant_award_bps ?? 6000) > 5000}
      />

      <div className="grid">
        <div>
          <section className="panel">
            <h2>
              <Gavel size={15} className="h2icon" /> Docket
            </h2>
            {!wallet && <div className="muted">Connect a wallet to read the live tribunal.</div>}
            {wallet && (
              <div className="case-list">
                {cases.length === 0 && <div className="muted">No cases filed yet.</div>}
                {cases.map((c) => (
                  <div
                    key={c.case_id}
                    className={`case-row ${c.case_id === selectedId ? "active" : ""}`}
                    onClick={() => selectCase(c.case_id)}
                  >
                    <span>
                      <span className="id">#{c.case_id}</span> {c.case_title}
                    </span>
                    <span className={`status-chip status-${c.status}`}>{c.status}</span>
                  </div>
                ))}
              </div>
            )}
          </section>

          {selected && (
            <section className="panel" style={{ marginTop: 16 }}>
              <h2>
                Case #{selected.case_id} &middot; {selected.case_title}
              </h2>
              <div className="muted small" style={{ marginBottom: 10 }}>
                Rubric: {selected.contract_rubric}
                <br />
                Mandatory spec token: <span style={{ color: "var(--gold)" }}>{selected.mandatory_spec_token}</span>
                {" "}&middot; Escrow {selected.disputed_escrow}
              </div>

              <div className="evidence-bench">
                <div className="evidence claimant">
                  <div className="who">Claimant deliverable proof</div>
                  <div className="url">
                    <a href={selected.claimant_evidence_url} target="_blank" rel="noreferrer">
                      {selected.claimant_evidence_url}
                    </a>
                  </div>
                  <div className="note">
                    Votes for claimant: {selected.votes_for_claimant}
                  </div>
                </div>
                <div className="evidence respondent">
                  <div className="who">Respondent rebuttal</div>
                  {selected.respondent_rebuttal_url ? (
                    <div className="url">
                      <a href={selected.respondent_rebuttal_url} target="_blank" rel="noreferrer">
                        {selected.respondent_rebuttal_url}
                      </a>
                    </div>
                  ) : (
                    <div className="muted">No rebuttal submitted yet.</div>
                  )}
                  {selected.rebuttal_note && <div className="note">{selected.rebuttal_note}</div>}
                  <div className="note">
                    Votes for respondent: {selected.votes_for_respondent}
                  </div>
                </div>
              </div>

              <div className="award-bar">
                <div className="award-flex">
                  <div className="award-main">
                    <div className="award-pct">
                      Split award: {awardPct.toFixed(1)}% claimant / {(100 - awardPct).toFixed(1)}%
                      respondent &middot;{" "}
                      <span className={`status-chip status-${selected.status}`}>{selected.verdict_label}</span>
                    </div>
                    <div className="award-track">
                      <div className="award-fill" style={{ width: `${awardPct}%` }} />
                    </div>
                    <div className="award-labels">
                      <span>0 bps</span>
                      <span>{selected.claimant_award_bps} bps to claimant</span>
                      <span>10000 bps</span>
                    </div>
                  </div>
                  <div className="award-gauge">
                    <Gauge value={selected.claimant_award_bps} caption="claimant award" />
                  </div>
                </div>
                {selected.status === "ADJUDICATED" && (
                  <div className="meta-grid">
                    <div className="cell">
                      <div className="k">Claimant payout</div>
                      {selected.claimant_payout}
                    </div>
                    <div className="cell">
                      <div className="k">Respondent payout</div>
                      {selected.respondent_payout}
                    </div>
                    <div className="cell">
                      <div className="k">Conserved</div>
                      {selected.claimant_payout + selected.respondent_payout === selected.disputed_escrow
                        ? "yes"
                        : "no"}
                    </div>
                  </div>
                )}
                {selected.judicial_opinion && (
                  <div className="txlink" style={{ marginTop: 8 }}>
                    Opinion: {selected.judicial_opinion}
                  </div>
                )}
              </div>

              <PromptInspector c={selected} />

              <div className="actions">
                {isRespondent && selected.status === "OPEN_FOR_REBUTTAL" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      runWrite("submit_respondent_rebuttal", [selected.case_id, rebuttalForm.url, rebuttalForm.note], {
                        label: "Submit rebuttal",
                      })
                    }
                  >
                    Submit Rebuttal
                  </button>
                )}
                {isOpen && (
                  <button
                    disabled={busy || liveBusy}
                    onClick={async () => {
                      setLiveBusy(true);
                      await runWrite("adjudicate_case_live", [selected.case_id], {
                        leaderOnly: false,
                        label: "Live AI adjudication",
                      });
                      setLiveBusy(false);
                    }}
                  >
                    {liveBusy ? "Adjudicating (full consensus)..." : (<><Radio size={13} className="btnicon" /> Trigger Live AI Adjudication</>)}
                  </button>
                )}
                {selected.status === "ADJUDICATED" && claimable > 0 && eq(selected.claimant, wallet!.address) && (
                  <button className="gold" disabled={busy} onClick={() => runWrite("withdraw_award", [], { label: "Withdraw award" })}>
                    Withdraw {claimable}
                  </button>
                )}
                {selected.status === "ADJUDICATED" && claimable > 0 && eq(selected.respondent, wallet!.address) && (
                  <button className="gold" disabled={busy} onClick={() => runWrite("withdraw_award", [], { label: "Withdraw award" })}>
                    Withdraw {claimable}
                  </button>
                )}
                {isClaimant && selected.status === "OPEN_FOR_REBUTTAL" && selected.amicus_count === 0 && (
                  <button className="ghost" disabled={busy} onClick={() => runWrite("cancel_case", [selected.case_id], { label: "Cancel case" })}>
                    Cancel &amp; Refund
                  </button>
                )}
              </div>
            </section>
          )}

          {selected && (
            <section className="panel" style={{ marginTop: 16 }}>
              <h2><Gavel size={15} className="h2icon" /> Amicus Briefs ({briefs.length})</h2>
              {briefs.map((b) => (
                <div className="brief" key={b.brief_id}>
                  <div className="head">
                    <span>
                      @{b.juror_handle}{" "}
                      <span
                        className={
                          b.side === "SUPPORT_CLAIMANT"
                            ? "side-claimant"
                            : b.side === "SUPPORT_RESPONDENT"
                              ? "side-respondent"
                              : "side-neutral"
                        }
                      >
                        {b.side}
                      </span>
                    </span>
                    <span>
                      {b.upvotes} upvotes{" "}
                      {isOpen && wallet && !eq(b.juror, wallet.address) && (
                        <button
                          className="ghost"
                          disabled={busy}
                          onClick={() => runWrite("upvote_amicus_brief", [b.brief_id], { label: "Upvote brief" })}
                        >
                          +1
                        </button>
                      )}
                    </span>
                  </div>
                  <div className="arg">{b.argument}</div>
                </div>
              ))}

              {isOpen && wallet && (
                <div style={{ marginTop: 10 }}>
                  <div className="muted small" style={{ marginBottom: 6 }}>
                    File an amicus brief (this also casts your weighted vote)
                  </div>
                  <div className="row" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <input
                      style={{ flex: 1, minWidth: 120 }}
                      value={briefForm.handle}
                      onChange={(e) => setBriefForm({ ...briefForm, handle: e.target.value })}
                      placeholder="juror handle"
                    />
                    <select
                      value={briefForm.side}
                      onChange={(e) => setBriefForm({ ...briefForm, side: e.target.value })}
                    >
                      <option value="SUPPORT_CLAIMANT">SUPPORT_CLAIMANT</option>
                      <option value="SUPPORT_RESPONDENT">SUPPORT_RESPONDENT</option>
                      <option value="NEUTRAL_TECHNICAL">NEUTRAL_TECHNICAL</option>
                    </select>
                  </div>
                  <div className="row">
                    <textarea
                      value={briefForm.argument}
                      onChange={(e) => setBriefForm({ ...briefForm, argument: e.target.value })}
                      placeholder="technical argument (max 300 chars)"
                    />
                  </div>
                  <button
                    className="primary"
                    disabled={busy || briefForm.argument.length === 0}
                    onClick={() =>
                      runWrite("file_amicus_brief", [selected.case_id, briefForm.handle, briefForm.side, briefForm.argument], {
                        label: "File amicus brief",
                      })
                    }
                  >
                    File Brief &amp; Vote
                  </button>
                </div>
              )}
            </section>
          )}
        </div>

        <div>
          {wallet && (
            <section className="panel">
              <h2>
                <Gavel size={15} className="h2icon" /> File New Dispute Case
              </h2>
              <div className="row">
                <label>Respondent address</label>
                <input value={fileForm.respondent} onChange={(e) => setFileForm({ ...fileForm, respondent: e.target.value })} />
              </div>
              <div className="row">
                <label>Case title</label>
                <input value={fileForm.case_title} onChange={(e) => setFileForm({ ...fileForm, case_title: e.target.value })} />
              </div>
              <div className="row">
                <label>Contract rubric</label>
                <textarea value={fileForm.contract_rubric} onChange={(e) => setFileForm({ ...fileForm, contract_rubric: e.target.value })} />
              </div>
              <div className="row">
                <label>Mandatory spec token</label>
                <input value={fileForm.mandatory_spec_token} onChange={(e) => setFileForm({ ...fileForm, mandatory_spec_token: e.target.value })} />
              </div>
              <div className="row">
                <label>Claimant evidence URL</label>
                <input value={fileForm.claimant_evidence_url} onChange={(e) => setFileForm({ ...fileForm, claimant_evidence_url: e.target.value })} />
              </div>
              <div className="row">
                <label>Disputed escrow (100..10000000)</label>
                <input type="number" value={fileForm.disputed_escrow} onChange={(e) => setFileForm({ ...fileForm, disputed_escrow: Number(e.target.value) })} />
              </div>
              <div className="actions">
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() =>
                    runWrite("file_dispute_case", [
                      fileForm.respondent,
                      fileForm.case_title,
                      fileForm.contract_rubric,
                      fileForm.mandatory_spec_token,
                      fileForm.claimant_evidence_url,
                      fileForm.disputed_escrow,
                    ], { label: "File dispute case" })
                  }
                >
                  File Case
                </button>
                <button className="ghost" onClick={() => setFileForm({ ...PRESET })}>
                  <Sparkles size={13} className="btnicon" /> Quick-Fill Preset
                </button>
                <button className="danger" disabled={busy} onClick={probeGuard} title="Fire an adversarial probe that must revert">
                  <ShieldAlert size={13} className="btnicon" /> Test Guard (Revert)
                </button>
              </div>
            </section>
          )}

          <GuardLab wallet={wallet} />

          {selected && isRespondent && (
            <section className="panel" style={{ marginTop: 16 }}>
              <h2>Rebuttal Inputs</h2>
              <div className="row">
                <label>Rebuttal URL (optional)</label>
                <input value={rebuttalForm.url} onChange={(e) => setRebuttalForm({ ...rebuttalForm, url: e.target.value })} placeholder="https://..." />
              </div>
              <div className="row">
                <label>Note</label>
                <textarea value={rebuttalForm.note} onChange={(e) => setRebuttalForm({ ...rebuttalForm, note: e.target.value })} />
              </div>
            </section>
          )}

          <section className="panel" style={{ marginTop: 16 }}>
            <h2><Sparkles size={15} className="h2icon" /> Tribunal Stats</h2>
            {stats ? (
              <div className="meta-grid">
                <div className="cell"><div className="k">Cases</div>{stats.total_cases}</div>
                <div className="cell"><div className="k">Open</div>{stats.open_cases}</div>
                <div className="cell"><div className="k">Adjudicated</div>{stats.adjudicated_cases}</div>
                <div className="cell"><div className="k">Briefs</div>{stats.total_briefs}</div>
                <div className="cell"><div className="k">Votes C/R</div>{stats.votes_for_claimant}/{stats.votes_for_respondent}</div>
                <div className="cell"><div className="k">Escrow disputed</div>{stats.escrow_in_dispute}</div>
              </div>
            ) : (
              <div className="muted">Connect a wallet.</div>
            )}
          </section>

          <section className="panel" style={{ marginTop: 16 }}>
            <h2><Trophy size={15} className="h2icon" /> Juror Leaderboard</h2>
            {leaderboard.length === 0 && <div className="muted">No jurors yet.</div>}
            {leaderboard.map((r) => (
              <div className="leader-row" key={r.juror}>
                <span>{short(r.juror)}</span>
                <span style={{ color: "var(--gold)" }}>{r.reputation} rep</span>
              </div>
            ))}
          </section>

          <section className="panel" style={{ marginTop: 16 }}>
            <h2><Scale size={15} className="h2icon" /> Contract</h2>
            <div className="row">
              <input value={contract} onChange={(e) => setContract(e.target.value)} />
            </div>
            <button
              className="ghost"
              onClick={() => {
                setContractAddress(contract);
                flash("ok", "Contract address saved");
                if (wallet) load(wallet, null);
              }}
            >
              Apply address
            </button>
            <div className="txlink" style={{ marginTop: 8 }}>
              Explorer:{" "}
              <a href={`https://genlayer-explorer.vercel.app/tx/${contract}`} target="_blank" rel="noreferrer">
                {short(contract)}
              </a>
            </div>
          </section>
        </div>
      </div>

      {toast && (
        <div className={`toast ${toast.kind}`} onClick={() => setToast(null)}>
          {toast.text}
        </div>
      )}
    </div>
  );
}

function short(addr: string) {
  if (!addr) return "";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

function eq(a: string, b: string) {
  return (a || "").toLowerCase() === (b || "").toLowerCase();
}
