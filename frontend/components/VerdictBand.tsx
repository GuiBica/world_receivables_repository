import { VERDICT_LABEL, fmtMoneyMap, type UploadRun } from "@/lib/api";

export default function VerdictBand({ run }: { run: UploadRun }) {
  const s = run.summary;
  const tone = run.verdict === "CLEAR" ? "green" : run.verdict === "POTENTIAL_DUPLICATES" ? "amber" : "red";
  const hasOverstatement = Object.keys(s.potential_overstatement_cents).length > 0;
  return (
    <section className={`verdict ${tone}`} aria-label="Verification result">
      <h2>{VERDICT_LABEL[run.verdict]}</h2>
      <p className="meta">
        {s.total_rows.toLocaleString("en-GB")} rows analysed from {run.filename}. Total amount submitted: {fmtMoneyMap(s.amount_by_currency_cents)}.
      </p>
      <div className="stats">
        <div>
          <div className="n">{s.counts.EXACT_DUPLICATE}</div>
          <div className="l">exact duplicates</div>
        </div>
        <div>
          <div className="n">{s.counts.ID_COLLISION}</div>
          <div className="l">invoice ID collisions</div>
        </div>
        <div>
          <div className="n">{s.counts.ECONOMIC_DUPLICATE}</div>
          <div className="l">possible economic duplicates</div>
        </div>
        <div>
          <div className="n">{s.counts.DATA_QUALITY}</div>
          <div className="l">data quality issue types ({s.data_quality_rows} rows)</div>
        </div>
      </div>
      {hasOverstatement && (
        <p className="overstated">
          Amount that could be counted twice: <strong>{fmtMoneyMap(s.potential_overstatement_cents)}</strong>
        </p>
      )}
    </section>
  );
}
