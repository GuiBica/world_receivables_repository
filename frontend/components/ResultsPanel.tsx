"use client";
import { useEffect, useState } from "react";
import { api, downloadFile, type Finding, type Role, type UploadRun } from "@/lib/api";
import FindingsLedger from "./FindingsLedger";
import VerdictBand from "./VerdictBand";

export default function ResultsPanel({ uploadId, role, explain, onChanged }: { uploadId: number; role: Role; explain: (e: unknown) => string; onChanged: () => void }) {
  const [data, setData] = useState<{ upload: UploadRun; findings: Finding[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    api<{ upload: UploadRun; findings: Finding[] }>(`/uploads/${uploadId}`)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(explain(e)));
    return () => {
      alive = false;
    };
  }, [uploadId, explain]);

  async function report() {
    setDownloading(true);
    setError(null);
    try {
      await downloadFile(`/uploads/${uploadId}/report.pdf`, "verification-report.pdf");
      onChanged();
    } catch (e) {
      setError(explain(e));
    } finally {
      setDownloading(false);
    }
  }

  if (error && !data) return <div className="error" role="alert">{error}</div>;
  if (!data) return <p className="muted">Loading result...</p>;

  return (
    <>
      <VerdictBand run={data.upload} />
      <div className="row" style={{ marginBottom: 18 }}>
        <button className="btn secondary" onClick={report} disabled={downloading}>{downloading ? "Preparing PDF..." : "Download PDF report"}</button>
        <p className="small muted">File SHA-256 <span className="mono">{data.upload.file_sha256.slice(0, 16)}...</span></p>
      </div>
      {error && <div className="error" role="alert">{error}</div>}
      <h3 style={{ marginBottom: 10 }}>Findings</h3>
      <FindingsLedger
        findings={data.findings}
        role={role}
        explain={explain}
        onUpdated={(f) => {
          setData((d) => (d ? { ...d, findings: d.findings.map((x) => (x.id === f.id ? f : x)) } : d));
          onChanged();
        }}
      />
    </>
  );
}
