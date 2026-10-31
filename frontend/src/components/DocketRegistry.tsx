import { useMemo, useState } from "react";
import type { Docket } from "../lib/types";
import { shortAddr } from "../lib/court";

interface Props {
  dockets: Docket[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

// Chancery Docket Registry: a live, filterable ledger of every PR bounty dispute.
export default function DocketRegistry({ dockets, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");

  const statuses = useMemo(() => {
    const set = new Set<string>(["ALL"]);
    for (const d of dockets) set.add(d.status);
    return Array.from(set);
  }, [dockets]);

  const rows = useMemo(() => {
    const q = query.toLowerCase();
    return dockets.filter((d) => {
      if (status !== "ALL" && d.status !== status) return false;
      if (!q) return true;
      return (
        d.docket_id.toLowerCase().includes(q) ||
        d.title.toLowerCase().includes(q) ||
        d.claimant.toLowerCase().includes(q) ||
        d.respondent.toLowerCase().includes(q)
      );
    });
  }, [dockets, query, status]);

  return (
    <section className="panel">
      <h2>Chancery Docket Registry</h2>
      <div className="registry-filter">
        <input
          placeholder="Filter by docket, title or party"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      {rows.length === 0 && <div className="muted">No dockets on the roll.</div>}
      <div className="registry">
        {rows.map((d) => (
          <button
            key={d.docket_id}
            className={`registry-row ${d.docket_id === selectedId ? "active" : ""}`}
            onClick={() => onSelect(d.docket_id)}
          >
            <span className="registry-main">
              <span className="registry-id">№ {d.docket_id}</span>
              <span className="registry-title">{d.title}</span>
              <span className="registry-parties">
                {shortAddr(d.claimant)} v {shortAddr(d.respondent)}
              </span>
            </span>
            <span className={`status-chip status-${d.status}`}>{d.status}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
