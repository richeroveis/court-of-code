import { useCallback, useState } from "react";
import confetti from "canvas-confetti";
import { Scale, Volume2, VolumeX, Gavel, Wallet, RefreshCw } from "lucide-react";
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
import type { Brief, CustodySummary, Docket, LeaderRow, TribunalStats } from "./lib/types";
import BackgroundFX from "./components/BackgroundFX";
import DocketRegistry from "./components/DocketRegistry";
import CustodyDrawer from "./components/CustodyDrawer";
import EvidenceBench from "./components/EvidenceBench";
import AwardMatrix from "./components/AwardMatrix";
import DecreeTranscript from "./components/DecreeTranscript";
import RuleBench from "./components/RuleBench";
import { shortAddr } from "./lib/court";
import { isMuted, toggleMuted, click, hum, chime, errorBuzz } from "./lib/sound";

const LOGO_URL = `${import.meta.env.BASE_URL}logo.png`;

function celebrate() {
  confetti({
    particleCount: 90,
    spread: 78,
    startVelocity: 32,
    origin: { y: 0.66 },
    colors: ["#38BDF8", "#D4AF37", "#34d399", "#e2be60"],
  });
}

interface Toast {
  kind: "ok" | "err" | "pending";
  text: string;
}

export default function App() {
  const [wallet, setWallet] = useState<WalletState | null>(null);
  const [contract, setContract] = useState(contractAddress());
  const [dockets, setDockets] = useState<Docket[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [briefs, setBriefs] = useState<Brief[]>([]);
  const [stats, setStats] = useState<TribunalStats | null>(null);
  const [custody, setCustody] = useState<CustodySummary | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderRow[]>([]);
  const [refundable, setRefundable] = useState(0);
  const [lastRejection, setLastRejection] = useState("");
  const [claimableAward, setClaimableAward] = useState(0);
  const [cetBalance, setCetBalance] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const [busy, setBusy] = useState(false);
  const [muted, setMutedState] = useState(isMuted());
  const nowEpoch = Math.floor(Date.now() / 1000);

  const selected = dockets.find((d) => d.docket_id === selectedId) ?? null;

  const flash = (kind: Toast["kind"], text: string) => setToast({ kind, text });
  const toggleSound = () => {
    const m = toggleMuted();
    setMutedState(m);
    if (!m) click();
  };

  const load = useCallback(async (w: WalletState) => {
    try {
      // Initial load is bounded to four RPC reads.
      const all = await readContract<Docket[]>(w, "get_all_dockets");
      const st = await readContract<TribunalStats>(w, "get_tribunal_stats");
      const cu = await readContract<CustodySummary>(w, "get_custody_accounting_summary");
      const ref = await readContract<number>(w, "get_refundable_balance", [w.address]);
      setDockets(all);
      setStats(st);
      setCustody(cu);
      setRefundable(Number(ref));
      if (all.length && !selectedId) setSelectedId(all[all.length - 1].docket_id);
    } catch (e) {
      flash("err", `Read failed: ${(e as Error).message}`);
    }
  }, [selectedId]);

  const loadExtras = useCallback(async (w: WalletState) => {
    try {
      const lb = await readContract<LeaderRow[]>(w, "get_judicial_leaderboard");
      const rej = await readContract<string>(w, "get_last_payable_rejection", [w.address]);
      const award = await readContract<number>(w, "get_claimable_award", [w.address]);
      const cet = await readContract<number>(w, "get_cet_balance", [w.address]);
      setLeaderboard(lb);
      setLastRejection(String(rej));
      setClaimableAward(Number(award));
      setCetBalance(Number(cet));
    } catch {
      /* extras are non-fatal */
    }
  }, []);

  const connect = async (mode: "burner" | "metamask") => {
    click();
    try {
      setBusy(true);
      const w = mode === "burner" ? connectBurner() : await connectMetaMask();
      setWallet(w);
      hum();
      flash("ok", `Sworn in ${mode} counsel ${shortAddr(w.address)}`);
      await load(w);
      await loadExtras(w);
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
    const w = connectBurner();
    setWallet(w);
    await load(w);
    await loadExtras(w);
    flash("ok", "Rotated to a fresh counsel identity");
  };

  const selectDocket = async (id: string) => {
    if (!wallet) return;
    click();
    setSelectedId(id);
    try {
      const bs = await readContract<Brief[]>(wallet, "get_docket_briefs", [id]);
      setBriefs(bs);
    } catch {
      setBriefs([]);
    }
  };

  const runWrite = async (
    fn: string,
    args: unknown[],
    opts: { label: string; value?: bigint; leaderOnly?: boolean },
  ) => {
    if (!wallet) return;
    try {
      setBusy(true);
      hum();
      flash("pending", `${opts.label}: submitting to studionet consensus...`);
      const res = await writeContract(wallet, fn, args, { leaderOnly: opts.leaderOnly ?? true, value: opts.value });
      if (res.statusName !== "FINALIZED") {
        errorBuzz();
        flash("err", `${opts.label}: ${res.statusName} (tx ${shortAddr(res.txHash)})`);
        return;
      }
      if (!res.succeeded) {
        errorBuzz();
        flash("err", `${opts.label}: execution reverted (tx ${shortAddr(res.txHash)})`);
        return;
      }
      chime();
      celebrate();
      flash("ok", `${opts.label}: FINALIZED tx ${shortAddr(res.txHash)}`);
      await load(wallet);
      await loadExtras(wallet);
    } catch (e) {
      errorBuzz();
      flash("err", `${opts.label} failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const refresh = async () => {
    if (!wallet) return;
    click();
    setBusy(true);
    await load(wallet);
    await loadExtras(wallet);
    if (selectedId) {
      const bs = await readContract<Brief[]>(wallet, "get_docket_briefs", [selectedId]).catch(() => [] as Brief[]);
      setBriefs(bs as Brief[]);
    }
    setBusy(false);
    flash("ok", "Chamber refreshed");
  };

  // RuleBench probes. The soft-fail probe deliberately self-deals so the contract must
  // refund the value instead of reverting; the pre-deadline probe attempts an early trial.
  const runSoftFailProbe = useCallback(async (): Promise<string> => {
    if (!wallet) return "connect a wallet first";
    const id = "PROBE-" + Date.now().toString(36);
    const res = await writeContract(
      wallet,
      "file_dispute_payable",
      [id, wallet.address, "probe", "https://a.dev/s", "https://a.dev/p", "probe summary", "P", 100, 3600, 3600],
      { leaderOnly: true, value: 1234n },
    );
    const ref = await readContract<number>(wallet, "get_refundable_balance", [wallet.address]);
    setRefundable(Number(ref));
    return `status=${res.statusName} refundable_now=${ref}`;
  }, [wallet]);

  const runPreDeadlineProbe = useCallback(async (): Promise<string> => {
    if (!wallet || !selected) return "select an open docket first";
    if (selected.status !== "OPEN_FOR_REBUTTAL") return "docket already past the rebuttal gate";
    const res = await writeContract(wallet, "adjudicate_docket", [selected.docket_id], { leaderOnly: true });
    return res.succeeded
      ? "UNEXPECTED: adjudication was allowed before the rebuttal deadline"
      : `refused as required (execution reverted before the deadline)`;
  }, [wallet, selected]);

  const isClaimant = selected && wallet && eq(selected.claimant, wallet.address);
  const isRespondent = selected && wallet && eq(selected.respondent, wallet.address);
  const isOpen = selected && (selected.status === "OPEN_FOR_REBUTTAL" || selected.status === "READY_FOR_TRIAL");

  return (
    <div className="app">
      <BackgroundFX />
      <header className="top">
        <img src={LOGO_URL} alt="CourtOfCode" />
        <div className="title-block">
          <h1>
            <Scale size={18} className="h1icon" /> CourtOfCode Chancery
          </h1>
          <div className="sub">Decentralized software arbitration &amp; judicial chamber workbench on GenLayer studionet</div>
        </div>
        <div className="spacer" />
        <button className="ghost iconbtn" onClick={toggleSound} aria-label={muted ? "Unmute" : "Mute"}>
          {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
        </button>
        <button className="ghost iconbtn" onClick={refresh} disabled={busy || !wallet} aria-label="Refresh">
          <RefreshCw size={16} />
        </button>
        <div className="wallet">
          {!wallet ? (
            <>
              <button className="primary" disabled={busy} onClick={() => connect("burner")}>
                <Wallet size={14} className="btnicon" /> 1-Click Burner Counsel
              </button>
              <button disabled={busy} onClick={() => connect("metamask")}>
                Connect MetaMask
              </button>
            </>
          ) : (
            <>
              <span className="badge">{wallet.mode}</span>
              <span className="badge live">{shortAddr(wallet.address)}</span>
              <span className="badge cet">{cetBalance} CET</span>
              <button className="ghost" disabled={busy} onClick={rotate}>Rotate</button>
              <button className="ghost" onClick={() => setWallet(null)}>Disconnect</button>
            </>
          )}
        </div>
      </header>

      <div className="bench-grid">
        <div className="col">
          <DocketRegistry dockets={dockets} selectedId={selectedId} onSelect={selectDocket} />
          <CustodyDrawer
            custody={custody}
            refundable={refundable}
            lastRejection={lastRejection}
            claimableAward={claimableAward}
            connected={!!wallet}
            busy={busy}
            onClaimRefund={() => runWrite("claim_refundable_balance", [], { label: "Claim refund" })}
            onWithdrawRefund={(a) => runWrite("withdraw_refund", [a], { label: "Withdraw refund" })}
            onWithdrawAward={() => runWrite("withdraw_award", [], { label: "Withdraw award" })}
            onFundCet={(a) => runWrite("fund_cet_vault_payable", [], { label: "Fund CET", value: BigInt(a) })}
          />
          <section className="panel">
            <h2><Gavel size={15} className="h2icon" /> Judicial Leaderboard</h2>
            {leaderboard.length === 0 && <div className="muted">No counsel reputation yet.</div>}
            {leaderboard.map((r) => (
              <div className="leader-row" key={r.juror}>
                <span>{shortAddr(r.juror)}</span>
                <span className="brass">{r.reputation} rep</span>
              </div>
            ))}
          </section>
          <section className="panel">
            <h2><Scale size={15} className="h2icon" /> Chancery Contract</h2>
            <div className="inline">
              <input value={contract} onChange={(e) => setContract(e.target.value)} />
              <button className="ghost" onClick={() => { setContractAddress(contract); flash("ok", "Address saved"); if (wallet) load(wallet); }}>Apply</button>
            </div>
            <div className="txlink">
              Explorer:{" "}
              <a href={`https://genlayer-explorer.vercel.app/tx/${contract}`} target="_blank" rel="noreferrer">
                {shortAddr(contract)}
              </a>
            </div>
          </section>
        </div>

        <div className="col">
          {!wallet && <div className="panel"><div className="muted">Sworn in a counsel wallet to open the live chamber.</div></div>}
          <EvidenceBench
            docket={selected}
            briefs={briefs}
            nowEpoch={nowEpoch}
            busy={busy}
            isClaimant={!!isClaimant}
            isRespondent={!!isRespondent}
            isOpen={!!isOpen}
            onFile={(p) =>
              runWrite(
                "file_dispute_payable",
                [p.docket_id, p.respondent, p.title, p.spec_reference_url, p.pr_evidence_url, p.brief_summary, p.mandatory_spec_token, p.principal_cet, p.rebuttal_window, p.appeal_window],
                { label: "File dispute", value: BigInt(p.bond) },
              )
            }
            onRebut={(id, text, bond) => runWrite("post_respondent_bond_payable", [id, text], { label: "Post rebuttal", value: BigInt(bond) })}
            onBrief={(id, handle, side, arg) => runWrite("file_amicus_brief", [id, handle, side, arg], { label: "File amicus brief" })}
            onUpvote={(bid) => runWrite("upvote_amicus_brief", [bid], { label: "Upvote brief" })}
            onAdjudicate={(id) => runWrite("adjudicate_docket", [id], { label: "Consensus adjudication", leaderOnly: false })}
            onChallenge={(id, bond) => runWrite("challenge_verdict_payable", [id], { label: "Challenge decree", value: BigInt(bond) })}
            onSettle={(id) => runWrite("execute_decree_settlement", [id], { label: "Execute settlement" })}
            onCancel={(id) => runWrite("cancel_docket", [id], { label: "Cancel docket" })}
          />
        </div>

        <div className="col">
          <AwardMatrix docket={selected} />
          <DecreeTranscript docket={selected} />
          <RuleBench docket={selected} busy={busy} runSoftFailProbe={runSoftFailProbe} runPreDeadlineProbe={runPreDeadlineProbe} />
          {stats && (
            <section className="panel">
              <h2>Chancery Docket Stats</h2>
              <div className="meta-grid">
                <div className="cell"><div className="k">Dockets</div>{stats.total_dockets}</div>
                <div className="cell"><div className="k">Open</div>{stats.open_dockets}</div>
                <div className="cell"><div className="k">Adjudicated</div>{stats.adjudicated_dockets}</div>
                <div className="cell"><div className="k">Settled</div>{stats.settled_dockets}</div>
                <div className="cell"><div className="k">Void</div>{stats.void_dockets}</div>
                <div className="cell"><div className="k">Briefs</div>{stats.total_briefs}</div>
                <div className="cell"><div className="k">Votes C/R</div>{stats.votes_for_claimant}/{stats.votes_for_respondent}</div>
                <div className="cell"><div className="k">Vault custody</div>{stats.vault_custody_balance}</div>
              </div>
            </section>
          )}
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

function eq(a: string, b: string) {
  return (a || "").toLowerCase() === (b || "").toLowerCase();
}
