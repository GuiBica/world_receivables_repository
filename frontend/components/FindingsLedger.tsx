"use client";
import { useEffect, useState } from "react";
import { KIND_LABEL, STATUS_LABEL, api, type Finding, type FindingKind, type FindingRows, type FindingStatus, type Role } from "@/lib/api";
import { StatusPill } from "./Pills";

const STATUSES = Object.keys(STATUS_LABEL) as FindingStatus[];
const KINDS = Object.keys(KIND_LABEL) as FindingKind[];

function FindingDetail({ f, canReview, explain, onUpdated }: { f: Finding; canReview: boolean; explain: (e: unknown) => string; onUpdated: (f: Finding) => void }) {
  const [rows, setRows] = useState<FindingRows | null>(null);
  const [status, setStatus] = useState<FindingStatus>(f.status);
  const [note, setNote] = useState(f.note);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    if (f.rows_count === 0) return;
    api<FindingRows>(`/findings/${f.id}/rows?limit=50`)
      .then((r) => alive && setRows(r))
      .catch((e) => alive && setError(explain(e)));
    return () => {
      alive = false;
    };
  }, [f.id, f.rows_count, explain]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      onUpdated(await api<Finding>(`/findings/${f.id}`, { method: "PATCH", json: { status, note } }));
    } catch (e) {
      setError(explain(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="detail">
      <p className="desc">{f.description}</p>
      {rows && (
        <>
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Row</th>
                  <th>Invoice ID</th>
                  <th>Debtor</th>
                  <th className="num">Amount</th>
                  <th>Currency</th>
                  <th>Issue date</th>
                  <th>Due date</th>
                </tr>
              </thead>
              <tbody>
                {rows.rows.map((r) => (
                  <tr key={r.row_number}>
                    <td>{r.row_number}</td>
                    <td>{r.raw.invoice_id || "–"}</td>
                    <td>{r.raw.debtor || "–"}</td>
                    <td className="num">{r.raw.amount || "–"}</td>
                    <td>{r.raw.currency || "–"}</td>
                    <td>{r.raw.issue_date || "–"}</td>
                    <td>{r.raw.due_date || "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 8 }}>
            Showing {rows.rows.length} of {rows.total} rows. Row N is the Nth data row of the file, which is line N+1 when opened in Excel or a text editor.
          </p>
        </>
      )}
      {error && <div className="error" role="alert">{error}</div>}
      {canReview ? (
        <div className="review">
          <div>
            <label className="field" htmlFor={`st-${f.id}`}>Review status</label>
            <select id={`st-${f.id}`} value={status} onChange={(e) => setStatus(e.target.value as FindingStatus)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{STATUS_LABEL[s]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="field" htmlFor={`nt-${f.id}`}>Note</label>
            <input id={`nt-${f.id}`} type="text" value={note} maxLength={2000} placeholder="What did you check?" onChange={(e) => setNote(e.target.value)} />
          </div>
          <button className="btn" onClick={save} disabled={saving}>{saving ? "Saving..." : "Save review"}</button>
        </div>
      ) : (
        f.updated_by && <p className="small muted" style={{ marginTop: 12 }}>Reviewed by {f.updated_by}{f.note ? `: ${f.note}` : ""}</p>
      )}
    </div>
  );
}

export default function FindingsLedger({ findings, role, explain, onUpdated }: { findings: Finding[]; role: Role; explain: (e: unknown) => string; onUpdated: (f: Finding) => void }) {
  const [kind, setKind] = useState<FindingKind | "ALL">("ALL");
  const [status, setStatus] = useState<FindingStatus | "ALL">("ALL");
  const [openId, setOpenId] = useState<number | null>(null);

  const shown = findings.filter((f) => (kind === "ALL" || f.kind === kind) && (status === "ALL" || f.status === status));
  const count = (k: FindingKind) => findings.filter((f) => f.kind === k).length;

  if (findings.length === 0) return <div className="empty">No findings. Every row passed all checks.</div>;

  return (
    <>
      <div className="filters">
        <div className="chips" role="group" aria-label="Filter by type">
          <button className="chip" aria-pressed={kind === "ALL"} onClick={() => setKind("ALL")}>All ({findings.length})</button>
          {KINDS.filter((k) => count(k) > 0).map((k) => (
            <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>{KIND_LABEL[k]} ({count(k)})</button>
          ))}
        </div>
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value as FindingStatus | "ALL")}>
          <option value="ALL">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{STATUS_LABEL[s]}</option>
          ))}
        </select>
      </div>
      {shown.length === 0 ? (
        <div className="empty">No findings match these filters.</div>
      ) : (
        <ul className="findings">
          {shown.map((f) => {
            const open = openId === f.id;
            return (
              <li key={f.id} className={`finding ${f.severity}`}>
                <button aria-expanded={open} onClick={() => setOpenId(open ? null : f.id)}>
                  <span className="title">{f.title}</span>
                  <StatusPill status={f.status} />
                  <span className="sub">
                    {KIND_LABEL[f.kind]}
                    {f.rows_count > 0 && `, ${f.rows_count} row${f.rows_count === 1 ? "" : "s"}`}
                    {`, ${f.severity.toLowerCase()} severity`}
                  </span>
                </button>
                {open && <FindingDetail f={f} canReview={role !== "client"} explain={explain} onUpdated={onUpdated} />}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
