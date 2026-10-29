import { STATUS_LABEL, VERDICT_LABEL, type FindingStatus, type Verdict } from "@/lib/api";

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  const tone = verdict === "CLEAR" ? "green" : verdict === "POTENTIAL_DUPLICATES" ? "amber" : "red";
  return <span className={`pill ${tone}`}>{VERDICT_LABEL[verdict]}</span>;
}

const STATUS_TONE: Record<FindingStatus, string> = { OPEN: "amber", UNDER_REVIEW: "teal", RESOLVED: "green", FALSE_POSITIVE: "grey" };

export function StatusPill({ status }: { status: FindingStatus }) {
  return <span className={`pill ${STATUS_TONE[status]}`}>{STATUS_LABEL[status]}</span>;
}
