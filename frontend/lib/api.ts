export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "client" | "bank" | "admin";
export type User = { id: number; email: string; name: string; role: Role };
export type Verdict = "CLEAR" | "POTENTIAL_DUPLICATES" | "DUPLICATES_FOUND";
export type FindingStatus = "OPEN" | "UNDER_REVIEW" | "RESOLVED" | "FALSE_POSITIVE";
export type FindingKind = "EXACT_DUPLICATE" | "ID_COLLISION" | "ECONOMIC_DUPLICATE" | "DATA_QUALITY";

export type Summary = {
  total_rows: number;
  rows_flagged: number;
  data_quality_rows: number;
  counts: Record<FindingKind, number>;
  amount_by_currency_cents: Record<string, number>;
  potential_overstatement_cents: Record<string, number>;
  verdict: Verdict;
};

export type UploadRun = {
  id: number;
  engagement_id: number;
  filename: string;
  file_sha256: string;
  n_rows: number;
  verdict: Verdict;
  summary: Summary;
  declaration_accepted: boolean;
  created_at: string;
};

export type Finding = {
  id: number;
  kind: FindingKind;
  code: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  title: string;
  description: string;
  rows_count: number;
  rows_preview: number[];
  status: FindingStatus;
  note: string;
  updated_by: string | null;
  updated_at: string | null;
};

export type EngagementItem = {
  id: number;
  name: string;
  client_email: string;
  bank: { id: number; name: string; email: string } | null;
  created_at: string;
  latest_upload: { id: number; filename: string; verdict: Verdict; created_at: string } | null;
  open_duplicate_findings: number;
};
export type EngagementDetail = EngagementItem & { uploads: UploadRun[] };

export type Preview = {
  headers: string[];
  suggested_mapping: Record<string, string | null>;
  sample_rows: Record<string, string>[];
  n_rows: number;
  fields: { key: string; label: string; required: boolean }[];
};

export type FindingRows = {
  total: number;
  rows: { row_number: number; raw: Record<string, string>; amount_cents: number | null; currency: string | null; fingerprint: string | null }[];
};

export type AuditEntry = {
  id: number; ts: string; actor: string; action: string; entity: string; entity_id: string;
  details: Record<string, unknown>; entry_hash: string; prev_hash: string;
};

// ---- session (kept in localStorage: fine for a prototype)
const TOKEN_KEY = "rr_token";
const USER_KEY = "rr_user";

export function getToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}
export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}
export function saveSession(token: string, user: User) {
  window.localStorage.setItem(TOKEN_KEY, token);
  window.localStorage.setItem(USER_KEY, JSON.stringify(user));
}
export function clearSession() {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(USER_KEY);
}

// ---- requests
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, message);
  }
  return res;
}

export async function api<T>(path: string, opts: { method?: string; json?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  const res = await request(path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body });
  return (await res.json()) as T;
}

export async function downloadFile(path: string, fallbackName: string) {
  const res = await request(path, { method: "GET" });
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ---- formatting
export function fmtCents(cents: number): string {
  return (cents / 100).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
export function fmtMoneyMap(m: Record<string, number>): string {
  const parts = Object.entries(m).map(([ccy, c]) => `${fmtCents(c)} ${ccy}`);
  return parts.length ? parts.join(", ") : "none";
}
export function fmtDate(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "";
}
export const KIND_LABEL: Record<FindingKind, string> = {
  EXACT_DUPLICATE: "Exact duplicate",
  ID_COLLISION: "ID collision",
  ECONOMIC_DUPLICATE: "Possible economic duplicate",
  DATA_QUALITY: "Data quality",
};
export const STATUS_LABEL: Record<FindingStatus, string> = {
  OPEN: "Open",
  UNDER_REVIEW: "Under review",
  RESOLVED: "Resolved",
  FALSE_POSITIVE: "False positive",
};
export const VERDICT_LABEL: Record<Verdict, string> = {
  CLEAR: "No duplicates found",
  POTENTIAL_DUPLICATES: "Potential duplicates to review",
  DUPLICATES_FOUND: "Duplicates found",
};
export const ROLE_LABEL: Record<Role, string> = { client: "Company", bank: "Bank", admin: "Admin" };
