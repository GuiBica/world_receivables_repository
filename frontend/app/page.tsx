"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import Shell from "@/components/Shell";
import { VerdictPill } from "@/components/Pills";
import { api, fmtDate, type EngagementItem } from "@/lib/api";
import { useSession } from "@/lib/useSession";

export default function Home() {
  const router = useRouter();
  const { user, ready, explain } = useSession();
  const [items, setItems] = useState<EngagementItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api<EngagementItem[]>("/engagements"));
    } catch (e) {
      setError(explain(e));
    }
  }, [explain]);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const created = await api<EngagementItem>("/engagements", { json: { name, client_email: clientEmail } });
      router.push(`/engagements/${created.id}`);
    } catch (err) {
      setError(explain(err));
      setBusy(false);
    }
  }

  if (!ready || !user) return null;

  const lede =
    user.role === "bank"
      ? "Verification requests you have sent to client companies."
      : user.role === "client"
        ? "Verification requests from your banks. Open one to upload your receivables."
        : "All engagements on the platform.";

  return (
    <Shell user={user}>
      <div className="page-head">
        <h1>Engagements</h1>
        <p className="muted" style={{ marginTop: 6 }}>{lede}</p>
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      {user.role === "bank" && (
        <section className="section" aria-labelledby="new-h">
          <h2 id="new-h">New engagement</h2>
          <p className="lede">Name the financing you want checked and enter the email of the company that will upload its receivables. They see it as soon as they sign in with that email.</p>
          <form className="row" onSubmit={create}>
            <div className="grow">
              <label className="field" htmlFor="eng-name">Engagement name</label>
              <input id="eng-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Revolving facility, Company B" />
            </div>
            <div className="grow">
              <label className="field" htmlFor="eng-email">Company email</label>
              <input id="eng-email" type="email" required value={clientEmail} onChange={(e) => setClientEmail(e.target.value)} placeholder="finance@company.com" />
            </div>
            <button className="btn" type="submit" disabled={busy}>{busy ? "Creating..." : "Create engagement"}</button>
          </form>
        </section>
      )}

      <section className="section" aria-label="Engagement list">
        {items === null ? (
          <p className="muted">Loading...</p>
        ) : items.length === 0 ? (
          <div className="empty">
            {user.role === "bank"
              ? "No engagements yet. Create one above and ask the company to upload its receivables."
              : "Nothing here yet. When a bank creates an engagement for your email address, it appears here."}
          </div>
        ) : (
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Engagement</th>
                  <th>{user.role === "client" ? "Bank" : "Company"}</th>
                  <th>Latest result</th>
                  <th className="num">Duplicates to review</th>
                  <th>Last run</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id} className="link" onClick={() => router.push(`/engagements/${e.id}`)}>
                    <td><Link href={`/engagements/${e.id}`}>{e.name}</Link></td>
                    <td>{user.role === "client" ? e.bank?.name : user.role === "bank" ? e.client_email : `${e.bank?.name ?? ""} / ${e.client_email}`}</td>
                    <td>{e.latest_upload ? <VerdictPill verdict={e.latest_upload.verdict} /> : <span className="muted">No file yet</span>}</td>
                    <td className="num">{e.latest_upload ? e.open_duplicate_findings : ""}</td>
                    <td>{fmtDate(e.latest_upload?.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Shell>
  );
}
