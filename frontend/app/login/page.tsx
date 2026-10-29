"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, saveSession, type User } from "@/lib/api";

const DEMOS = [
  { label: "Bank", email: "bank@demo.com" },
  { label: "Company", email: "client@demo.com" },
  { label: "Admin", email: "admin@demo.com" },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<"client" | "bank">("client");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cfg, setCfg] = useState({ allow_registration: true, demo_accounts: false });

  useEffect(() => {
    api<{ allow_registration: boolean; demo_accounts: boolean }>("/config")
      .then((c) => {
        setCfg(c);
        if (!c.allow_registration) setMode("signin");
      })
      .catch(() => undefined); // an unreachable API is reported when the visitor tries to sign in
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "signin"
          ? await api<{ access_token: string; user: User }>("/auth/login", { json: { email, password } })
          : await api<{ access_token: string; user: User }>("/auth/register", { json: { email, password, name, role } });
      saveSession(res.access_token, res.user);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="pitch">
        <h1>Check receivables before they are financed twice</h1>
        <p>
          A company uploads its receivables ledger. The registry flags exact duplicates, reused invoice numbers and invoices that look like the same debt under a different number.
        </p>
        <p>The bank receives a verification report it can review, challenge and keep on file.</p>
        {cfg.demo_accounts && (
        <div className="demo">
          <p className="small muted">Try it with a demo account (password demo1234)</p>
          <div className="row">
            {DEMOS.map((d) => (
              <button
                key={d.email}
                type="button"
                className="btn secondary"
                onClick={() => {
                  setMode("signin");
                  setEmail(d.email);
                  setPassword("demo1234");
                  setError(null);
                }}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
        )}
      </div>

      <form onSubmit={submit}>
        <div className="switch">
          <button type="button" aria-pressed={mode === "signin"} onClick={() => setMode("signin")}>Sign in</button>
          {cfg.allow_registration && (
            <button type="button" aria-pressed={mode === "register"} onClick={() => setMode("register")}>Create account</button>
          )}
        </div>
        {mode === "register" && (
          <>
            <div>
              <label className="field" htmlFor="name">Name</label>
              <input id="name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="Company or bank name" />
            </div>
            <div>
              <label className="field" htmlFor="role">I am a</label>
              <select id="role" value={role} onChange={(e) => setRole(e.target.value as "client" | "bank")}>
                <option value="client">Company submitting receivables</option>
                <option value="bank">Bank requesting a verification</option>
              </select>
            </div>
          </>
        )}
        <div>
          <label className="field" htmlFor="email">Email</label>
          <input id="email" type="email" required autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="field" htmlFor="password">Password {mode === "register" && <span className="muted">(8 characters or more)</span>}</label>
          <input id="password" type="password" required minLength={mode === "register" ? 8 : undefined} autoComplete={mode === "signin" ? "current-password" : "new-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && <div className="error" role="alert" style={{ margin: 0 }}>{error}</div>}
        <button className="btn" type="submit" disabled={busy}>
          {busy ? "Please wait..." : mode === "signin" ? "Sign in" : "Create account"}
        </button>
      </form>
    </div>
  );
}
