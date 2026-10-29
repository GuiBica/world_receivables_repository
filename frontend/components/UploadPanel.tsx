"use client";
import { useRef, useState } from "react";
import { api, type Preview, type UploadRun } from "@/lib/api";

export default function UploadPanel({
  engagementId,
  onDone,
  explain,
}: {
  engagementId: number;
  onDone: (uploadId: number) => void;
  explain: (e: unknown) => string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [declared, setDeclared] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function choose(f: File | null) {
    setFile(f);
    setPreview(null);
    setError(null);
    if (!f) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const p = await api<Preview>(`/engagements/${engagementId}/preview`, { form: fd });
      setPreview(p);
      const m: Record<string, string> = {};
      for (const [k, v] of Object.entries(p.suggested_mapping)) m[k] = v ?? "";
      setMapping(m);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  const missing = preview ? preview.fields.filter((f) => f.required && !mapping[f.key]) : [];

  async function run() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mapping", JSON.stringify(Object.fromEntries(Object.entries(mapping).map(([k, v]) => [k, v || null]))));
      fd.append("declaration", String(declared));
      const up = await api<UploadRun>(`/engagements/${engagementId}/uploads`, { form: fd });
      setFile(null);
      setPreview(null);
      setDeclared(false);
      if (inputRef.current) inputRef.current.value = "";
      onDone(up.id);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="section" aria-labelledby="upload-h">
      <h2 id="upload-h">Submit receivables</h2>
      <p className="lede">
        Upload the full receivables ledger as CSV or Excel. We suggest which column is which, you confirm, and the checks run straight away.
      </p>

      <label className="field" htmlFor="file">
        Ledger file (.csv or .xlsx)
      </label>
      <input id="file" ref={inputRef} type="file" accept=".csv,.xlsx" onChange={(e) => choose(e.target.files?.[0] ?? null)} />

      {error && <div className="error" role="alert">{error}</div>}
      {busy && !preview && file && <p className="muted small" style={{ marginTop: 10 }}>Reading the file...</p>}

      {preview && (
        <>
          <p className="muted" style={{ marginTop: 14 }}>
            {preview.n_rows.toLocaleString("en-GB")} rows found. Check that each field points to the right column.
          </p>
          <div className="mapping">
            {preview.fields.map((f) => (
              <div key={f.key}>
                <label className="field" htmlFor={`map-${f.key}`}>
                  {f.label} {!f.required && <span className="req">(optional)</span>}
                </label>
                <select id={`map-${f.key}`} value={mapping[f.key] ?? ""} onChange={(e) => setMapping({ ...mapping, [f.key]: e.target.value })}>
                  <option value="">{f.required ? "Choose a column" : "Not in file"}</option>
                  {preview.headers.map((h) => (
                    <option key={h} value={h}>
                      {h}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  {preview.fields.filter((f) => mapping[f.key]).map((f) => (
                    <th key={f.key}>{f.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample_rows.slice(0, 3).map((r, i) => (
                  <tr key={i}>
                    {preview.fields.filter((f) => mapping[f.key]).map((f) => (
                      <td key={f.key}>{r[mapping[f.key]] || "–"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <label className="declaration">
            <input type="checkbox" checked={declared} onChange={(e) => setDeclared(e.target.checked)} />
            <span>I declare that this file contains all of the company&apos;s receivables, including those already financed or pledged elsewhere.</span>
          </label>
          {missing.length > 0 && <p className="small muted" style={{ marginBottom: 10 }}>Still to map: {missing.map((m) => m.label).join(", ")}.</p>}
          <button className="btn" disabled={busy || missing.length > 0 || !declared} onClick={run}>
            {busy ? "Running checks..." : "Run verification"}
          </button>
        </>
      )}
    </section>
  );
}
