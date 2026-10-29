"use client";
import { useEffect, useState } from "react";
import { api, fmtDate, type AuditEntry } from "@/lib/api";

const ACTION_LABEL: Record<string, string> = {
  "engagement.created": "Engagement created",
  "upload.verified": "File verified",
  "finding.status_changed": "Finding reviewed",
  "report.downloaded": "Report downloaded",
  "user.login": "Signed in",
  "user.created": "Account created",
};

function describe(a: AuditEntry): string {
  const d = a.details as Record<string, unknown>;
  switch (a.action) {
    case "engagement.created":
      return String(d.name ?? "");
    case "upload.verified":
      return `${d.filename}, ${d.rows} rows, ${String(d.verdict).replaceAll("_", " ").toLowerCase()}`;
    case "finding.status_changed":
      return `${d.title}: ${String(d.from).toLowerCase()} to ${String(d.to).toLowerCase()}${d.note ? `, "${d.note}"` : ""}`;
    default:
      return "";
  }
}

export default function AuditPanel({ engagementId, refreshKey, explain }: { engagementId: number; refreshKey: number; explain: (e: unknown) => string }) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [chain, setChain] = useState<{ ok: boolean; entries: number; first_bad_id: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let alive = true;
    Promise.all([api<AuditEntry[]>(`/engagements/${engagementId}/audit`), api<{ ok: boolean; entries: number; first_bad_id: number | null }>("/audit/verify")])
      .then(([e, c]) => {
        if (!alive) return;
        setEntries(e);
        setChain(c);
      })
      .catch((e) => alive && setError(explain(e)));
    return () => {
      alive = false;
    };
  }, [open, engagementId, refreshKey, explain]);

  return (
    <section className="section">
      <details className="audit" onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>Audit trail</summary>
        {error && <div className="error" role="alert">{error}</div>}
        {chain && (
          <p className={chain.ok ? "chain-ok" : "chain-bad"} style={{ marginBottom: 12 }}>
            {chain.ok ? `Chain intact: ${chain.entries} entries verified.` : `Chain broken at entry ${chain.first_bad_id}. History has been altered.`}
          </p>
        )}
        {entries && entries.length === 0 && <div className="empty">No activity yet.</div>}
        {entries && entries.length > 0 && (
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>Action</th>
                  <th>Detail</th>
                  <th>Entry hash</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((a) => (
                  <tr key={a.id}>
                    <td>{fmtDate(a.ts)}</td>
                    <td>{a.actor}</td>
                    <td>{ACTION_LABEL[a.action] ?? a.action}</td>
                    <td>{describe(a)}</td>
                    <td className="mono">{a.entry_hash.slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>
    </section>
  );
}
