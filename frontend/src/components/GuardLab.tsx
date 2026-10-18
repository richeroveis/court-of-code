import { useState } from "react";
import { ShieldAlert, FlaskConical, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import type { WalletState } from "../lib/genlayer";
import { writeContract } from "../lib/genlayer";
import { click, errorBuzz, chime } from "../lib/sound";

const OTHER = "0xFF21Bc38046f8299544598C0e44C964A8E49E2C5";

interface Guard {
  id: string;
  label: string;
  fn: string;
  args: (self: string) => unknown[];
}

const GUARDS: Guard[] = [
  {
    id: "self",
    label: "Self-dealing claimant (respondent equals caller)",
    fn: "file_dispute_case",
    args: (self) => [self, "guard probe", "guard rubric text", "TOK", "https://example.com/x", 5000],
  },
  {
    id: "floor",
    label: "Escrow below the 100 floor",
    fn: "file_dispute_case",
    args: () => [OTHER, "guard probe", "guard rubric text", "TOK", "https://example.com/x", 50],
  },
  {
    id: "url",
    label: "Non-http evidence url",
    fn: "file_dispute_case",
    args: () => [OTHER, "guard probe", "guard rubric text", "TOK", "ftp://bad", 5000],
  },
  {
    id: "cancel",
    label: "Cancel a case you do not own",
    fn: "cancel_case",
    args: () => [1],
  },
  {
    id: "withdraw",
    label: "Withdraw with an empty balance",
    fn: "withdraw_award",
    args: () => [],
  },
  {
    id: "premature-live",
    label: "Premature live adjudication before rebuttal or response deadline (case #2)",
    fn: "adjudicate_case_live",
    args: () => [2],
  },
  {
    id: "unilateral-split",
    label: "Unilateral deterministic split without counterparty co-signature (case #2)",
    fn: "adjudicate_case_deterministic",
    args: () => [2, 5000, "attempted unilateral settlement"],
  },
];

type Result = { state: "idle" | "running" | "pass" | "fail"; note: string };

// One-click adversarial probes. Every call is designed to REVERT, proving a role or
// input guard holds; nothing is written on chain when the guard works.
export default function GuardLab({ wallet }: { wallet: WalletState | null }) {
  const [results, setResults] = useState<Record<string, Result>>({});
  const [busy, setBusy] = useState<string | null>(null);

  async function run(g: Guard) {
    if (!wallet || busy) return;
    click();
    setBusy(g.id);
    setResults((r) => ({ ...r, [g.id]: { state: "running", note: "submitting expected-revert probe..." } }));
    try {
      const res = await writeContract(wallet, g.fn, g.args(wallet.address), { leaderOnly: true });
      if (!res.succeeded) {
        setResults((r) => ({ ...r, [g.id]: { state: "pass", note: `reverted as expected (${res.txHash.slice(0, 10)}...)` } }));
        errorBuzz();
      } else {
        setResults((r) => ({ ...r, [g.id]: { state: "fail", note: "UNEXPECTED: the guard did not revert" } }));
        chime();
      }
    } catch (e) {
      setResults((r) => ({
        ...r,
        [g.id]: { state: "pass", note: `guard threw before consensus: ${(e as Error).message.slice(0, 72)}` },
      }));
      errorBuzz();
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel guard">
      <h2>
        <ShieldAlert size={15} className="h2icon" /> Test Security Guard (Expected Revert)
      </h2>
      <p className="muted small guard-intro">
        Fire an adversarial input or role probe. A correct guard reverts and writes nothing.
        {!wallet && " Connect a juror wallet to run the probes."}
      </p>
      <div className="guard-list">
        {GUARDS.map((g) => {
          const r = results[g.id] ?? { state: "idle" as const, note: "" };
          return (
            <div className="guard-row" key={g.id}>
              <button
                type="button"
                className="guard-run"
                disabled={!wallet || busy !== null}
                onClick={() => run(g)}
              >
                {busy === g.id ? <Loader2 size={14} className="spin" /> : <FlaskConical size={14} />}
                <span>Run</span>
              </button>
              <div className="guard-text">
                <div className="guard-label">{g.label}</div>
                <div className={`guard-note g-${r.state}`}>
                  {r.state === "pass" && <CheckCircle2 size={13} />}
                  {r.state === "fail" && <XCircle size={13} />}
                  {r.note || "not run"}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
