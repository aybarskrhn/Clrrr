import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AppLayout from "@/components/AppLayout";
import api from "@/lib/api";
import { Briefcase, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Deals() {
  const [deals, setDeals] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/deals").then(({ data }) => setDeals(data));
  }, []);

  const deleteDeal = async (e, deal) => {
    e.stopPropagation();
    if (
      !window.confirm(
        `Permanently delete "${deal.name}"? This removes its documents, extractions and roll-up.`
      )
    )
      return;
    try {
      await api.delete(`/deals/${deal.id}`);
      setDeals((arr) => arr.filter((d) => d.id !== deal.id));
      toast.success(`Deleted ${deal.name}`);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <AppLayout>
      <div className="px-6 py-6">
        <div className="flex items-end justify-between border-b border-[var(--cv-border)] pb-5">
          <div>
            <div className="cv-tag">// DEAL BOOK</div>
            <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight md:text-4xl">
              All mandates
            </h1>
          </div>
          <Link
            to="/upload"
            className="bg-[var(--cv-primary)] px-3 py-2 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)]"
          >
            Ingest a PDF
          </Link>
        </div>

        <div className="mt-6 border border-[var(--cv-border)] bg-[var(--cv-surface)]">
          <table className="w-full font-mono text-xs">
            <thead>
              <tr className="border-b border-[var(--cv-border)] text-left text-[var(--cv-muted)]">
                <th className="px-4 py-3">Project</th>
                <th className="px-4 py-3">Target</th>
                <th className="px-4 py-3">Sector</th>
                <th className="px-4 py-3 text-right">Size</th>
                <th className="px-4 py-3 text-right">Docs</th>
                <th className="px-4 py-3 text-right">Flags</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {deals.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-16 text-center text-[var(--cv-muted)]">
                    <div className="mb-3 flex justify-center">
                      <Briefcase className="h-8 w-8 opacity-60" />
                    </div>
                    No deals yet. Head to the dashboard and create your first mandate.
                  </td>
                </tr>
              )}
              {deals.map((d) => (
                <tr
                  key={d.id}
                  onClick={() => navigate(`/deals/${d.id}`)}
                  className="cursor-pointer border-b border-[var(--cv-border)]/60 hover:bg-[var(--cv-surface-hover)]"
                >
                  <td className="px-4 py-3 text-[var(--cv-text)]">{d.name}</td>
                  <td className="px-4 py-3 text-[var(--cv-muted)]">{d.target_company}</td>
                  <td className="px-4 py-3 text-[var(--cv-muted)]">{d.sector}</td>
                  <td className="px-4 py-3 text-right">{d.deal_size || "—"}</td>
                  <td className="px-4 py-3 text-right">{d.documents_count}</td>
                  <td
                    className={`px-4 py-3 text-right ${
                      d.red_flags_count > 0 ? "text-[var(--cv-primary)]" : "text-[var(--cv-muted)]"
                    }`}
                  >
                    {d.red_flags_count}
                  </td>
                  <td className="px-4 py-3 text-[var(--cv-muted)]">{d.created_at?.slice(0, 10)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={(e) => deleteDeal(e, d)}
                      data-testid={`delete-deal-${d.id}`}
                      title="Delete deal"
                      className="inline-flex h-7 w-7 items-center justify-center border border-[var(--cv-border)] text-[var(--cv-muted)] transition-colors hover:border-[var(--cv-danger)] hover:bg-[var(--cv-danger)]/10 hover:text-[var(--cv-danger)]"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppLayout>
  );
}
