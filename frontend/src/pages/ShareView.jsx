import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
import { AlertOctagon, Loader2, FileText, ShieldCheck } from "lucide-react";

function SeverityChip({ s }) {
  const k = (s || "").toLowerCase();
  return (
    <span className={`cv-chip ${k === "high" ? "cv-chip-red" : k === "medium" ? "cv-chip-amber" : ""}`}>
      {k || "info"}
    </span>
  );
}

export default function ShareView() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let live = true;
    api
      .get(`/share/${token}`)
      .then(({ data }) => live && setData(data))
      .catch((e) => live && setErr(e?.response?.data?.detail || "Memo not found"));
    return () => {
      live = false;
    };
  }, [token]);

  if (err) {
    return (
      <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)]">
        <div className="mx-auto flex max-w-2xl flex-col items-start px-8 py-24">
          <div className="flex items-center gap-2 text-[var(--cv-danger)]">
            <AlertOctagon className="h-5 w-5" />
            <span className="font-mono text-[11px] uppercase tracking-widest">Memo unavailable</span>
          </div>
          <h1 className="mt-3 font-heading text-3xl font-bold tracking-tight">{err}</h1>
          <p className="mt-3 font-body text-sm text-[var(--cv-muted)]">
            The owner may have revoked this link or removed the underlying analysis.
          </p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--cv-bg)] font-mono text-sm text-[var(--cv-muted)]">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading shared memo…
      </div>
    );
  }

  const { deal, rollup, rollup_at, view_count } = data;
  const recColor = (r) => (r === "proceed" ? "cv-chip-green" : r === "pass" ? "cv-chip-red" : "cv-chip-amber");

  return (
    <div className="min-h-screen bg-[var(--cv-bg)] text-[var(--cv-text)]">
      <header className="border-b border-[var(--cv-border)] bg-[var(--cv-bg)]">
        <div className="mx-auto flex max-w-[1100px] items-center justify-between px-8 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-7 w-7 items-center justify-center border border-[var(--cv-primary)] bg-[var(--cv-primary)] text-black">
              <span className="font-mono text-sm font-bold">CV</span>
            </div>
            <span className="font-heading text-base font-bold tracking-tight">
              CLEAR<span className="text-[var(--cv-primary)]">VAULT</span>
            </span>
            <span className="cv-chip cv-chip-amber ml-2">SHARED · READ-ONLY</span>
          </div>
          <a
            href="/"
            className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:text-[var(--cv-primary)]"
          >
            powered by clearvault →
          </a>
        </div>
      </header>

      <main data-testid="share-view-root" className="mx-auto max-w-[1100px] px-8 py-10">
        <div className="border-b border-[var(--cv-border)] pb-5">
          <div className="cv-tag">// IC MEMO · SHARED EXTERNALLY</div>
          <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight md:text-5xl">
            {deal.name}
          </h1>
          <p className="mt-2 font-mono text-xs text-[var(--cv-muted)]">
            Target · <span className="text-[var(--cv-text)]">{deal.target_company}</span>
            {deal.sector && (
              <>
                {" · "}Sector · <span className="text-[var(--cv-text)]">{deal.sector}</span>
              </>
            )}
            {deal.deal_size && (
              <>
                {" · "}Size · <span className="text-[var(--cv-text)]">{deal.deal_size}</span>
              </>
            )}
          </p>
          <p className="mt-2 font-mono text-[11px] text-[var(--cv-muted)]">
            generated {rollup_at?.slice(0, 19).replace("T", " ")} · view #{view_count}
          </p>
        </div>

        {/* Recommendation */}
        <section className="mt-6 border border-[var(--cv-border)] bg-[var(--cv-surface)] p-6">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Recommendation
            </span>
            <span className={`cv-chip ${recColor(rollup.recommendation)}`}>
              {(rollup.recommendation || "—").replace(/_/g, " ")}
            </span>
          </div>
          <p className="mt-4 font-body text-base leading-relaxed">{rollup.executive_summary}</p>
          {rollup.recommendation_rationale && (
            <p className="mt-4 border-l-2 border-[var(--cv-primary)] bg-[var(--cv-bg)] px-4 py-3 font-mono text-sm text-[var(--cv-muted)]">
              rationale · {rollup.recommendation_rationale}
            </p>
          )}
        </section>

        {/* Consolidated financials */}
        {rollup.consolidated_financials?.length > 0 && (
          <section className="mt-4 border border-[var(--cv-border)] bg-[var(--cv-surface)]">
            <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Consolidated financials
            </div>
            <table className="w-full font-mono text-xs">
              <thead>
                <tr className="border-b border-[var(--cv-border)] text-left text-[var(--cv-muted)]">
                  <th className="px-4 py-2">Line item</th>
                  <th className="px-4 py-2 text-right">Value</th>
                  <th className="px-4 py-2">Period</th>
                  <th className="px-4 py-2">Source</th>
                </tr>
              </thead>
              <tbody>
                {rollup.consolidated_financials.map((m, i) => (
                  <tr key={i} className="border-b border-[var(--cv-border)]/60">
                    <td className="px-4 py-2 text-[var(--cv-text)]">{m.label}</td>
                    <td className="px-4 py-2 text-right text-[var(--cv-primary)]">{m.value}</td>
                    <td className="px-4 py-2 text-[var(--cv-muted)]">{m.period || "—"}</td>
                    <td className="px-4 py-2 text-[var(--cv-muted)]">{m.source || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {/* Top red flags */}
        {rollup.top_red_flags?.length > 0 && (
          <section className="mt-4 border border-[var(--cv-border)] bg-[var(--cv-surface)]">
            <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Top red flags
            </div>
            <ul className="divide-y divide-[var(--cv-border)]/60">
              {rollup.top_red_flags.map((f, i) => (
                <li key={i} className="flex items-start gap-3 px-4 py-3">
                  <SeverityChip s={f.severity} />
                  <div className="flex-1">
                    <div className="font-body text-sm">{f.title}</div>
                    {f.description && (
                      <div className="mt-0.5 font-body text-xs text-[var(--cv-muted)]">{f.description}</div>
                    )}
                  </div>
                  {f.source && (
                    <span className="font-mono text-[11px] text-[var(--cv-muted)]">
                      <FileText className="mr-1 inline h-3 w-3" />
                      {f.source}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Gaps + next steps */}
        <section className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          {rollup.diligence_gaps?.length > 0 && (
            <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5">
              <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Diligence gaps
              </div>
              <ul className="mt-3 space-y-2 font-body text-sm">
                {rollup.diligence_gaps.map((g, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1 w-1 shrink-0 bg-[var(--cv-primary)]" />
                    <span>{g}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {rollup.next_steps?.length > 0 && (
            <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5">
              <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Next steps
              </div>
              <ul className="mt-3 space-y-2 font-body text-sm">
                {rollup.next_steps.map((s, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1 w-1 shrink-0 bg-[var(--cv-primary)]" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <footer className="mt-12 flex items-center justify-between border-t border-[var(--cv-border)] pt-6">
          <span className="flex items-center gap-2 font-mono text-[11px] text-[var(--cv-muted)]">
            <ShieldCheck className="h-3 w-3 text-[var(--cv-primary)]" /> Read-only · revocable at
            any time
          </span>
          <a
            href="/signup"
            className="border border-[var(--cv-border)] px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
          >
            Open your own terminal →
          </a>
        </footer>
      </main>
    </div>
  );
}
