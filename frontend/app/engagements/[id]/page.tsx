"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import AuditPanel from "@/components/AuditPanel";
import ResultsPanel from "@/components/ResultsPanel";
import Shell from "@/components/Shell";
import UploadPanel from "@/components/UploadPanel";
import { api, fmtDate, type EngagementDetail } from "@/lib/api";
import { useSession } from "@/lib/useSession";

export default function EngagementPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { user, ready, explain } = useSession();
  const [eng, setEng] = useState<EngagementDetail | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(
    async (select?: number) => {
      try {
        const e = await api<EngagementDetail>(`/engagements/${id}`);
        setEng(e);
        setRunId((prev) => select ?? prev ?? e.uploads[0]?.id ?? null);
        setTick((t) => t + 1);
      } catch (err) {
        setError(explain(err));
      }
    },
    [id, explain],
  );

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!ready || !user) return null;

  const canUpload = user.role === "client" || user.role === "admin";

  return (
    <Shell user={user}>
      <div className="page-head">
        <Link href="/" className="crumb">All engagements</Link>
        <h1>{eng?.name ?? "Engagement"}</h1>
        {eng && (
          <p className="muted" style={{ marginTop: 6 }}>
            Requested by {eng.bank?.name}, for {eng.client_email}. Created {fmtDate(eng.created_at)}.
          </p>
        )}
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      {eng && canUpload && <UploadPanel engagementId={id} explain={explain} onDone={(uid) => load(uid)} />}

      {eng && (
        <section className="section" aria-labelledby="res-h">
          <h2 id="res-h">Verification result</h2>
          {eng.uploads.length === 0 ? (
            <div className="empty" style={{ marginTop: 14 }}>
              {user.role === "bank"
                ? "The company has not uploaded a file yet. The result appears here as soon as they do."
                : "No file submitted yet. Upload your ledger above to see the result."}
            </div>
          ) : (
            <>
              {eng.uploads.length > 1 && (
                <div style={{ maxWidth: 420, margin: "10px 0 16px" }}>
                  <label className="field" htmlFor="run">Verification run</label>
                  <select id="run" value={runId ?? ""} onChange={(e) => setRunId(Number(e.target.value))}>
                    {eng.uploads.map((u) => (
                      <option key={u.id} value={u.id}>{fmtDate(u.created_at)}, {u.filename}</option>
                    ))}
                  </select>
                </div>
              )}
              {runId !== null && (
                <ResultsPanel key={runId} uploadId={runId} role={user.role} explain={explain} onChanged={() => setTick((t) => t + 1)} />
              )}
            </>
          )}
        </section>
      )}

      {eng && <AuditPanel engagementId={id} refreshKey={tick} explain={explain} />}
    </Shell>
  );
}
