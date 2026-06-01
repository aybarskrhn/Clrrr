import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppLayout from "@/components/AppLayout";
import { DASHBOARD, DEAL } from "@/constants/testIds";
import { Plus, AlertOctagon, FileText, Briefcase, Flame, X } from "lucide-react";
import { toast } from "sonner";

function StatCard({ label, value, hint, testid, accent }) {
  return (
    <div
      data-testid={testid}
      className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5"
    >
      <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">
        {label}
      </div>
      <div
        className={`mt-3 font-mono text-4xl font-bold tracking-tight ${
          accent ? "text-[var(--cv-primary)]" : "text-[var(--cv-text)]"
        }`}
      >
        {value}
      </div>
      <div className="mt-1 font-mono text-[11px] text-[var(--cv-muted)]">{hint}</div>
    </div>
  );
}

function NewDealDialog({ open, onClose, onCreated }) {
  const [form, setForm] = useState({ name: "", target_company: "", sector: "Industrials", deal_size: "" });
  const [loading, setLoading] = useState(false);
  if (!open) return null;

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/deals", form);
      toast.success("Deal created.");
      onCreated(data);
      onClose();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to create deal");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <form
        onSubmit={submit}
        data-testid={DEAL.newDealDialog}
        className="w-full max-w-lg border border-[var(--cv-primary)] bg-[var(--cv-surface)] p-7"
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
              New mandate
            </div>
            <h3 className="mt-1 font-heading text-xl font-bold tracking-tight">Create a deal</h3>
          </div>
          <button type="button" onClick={onClose} className="text-[var(--cv-muted)] hover:text-[var(--cv-text)]">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Project codename
            </label>
            <input
              required
              data-testid={DEAL.newDealName}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Project Northstar"
              className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
            />
          </div>
          <div className="col-span-2">
            <label className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Target company
            </label>
            <input
              required
              data-testid={DEAL.newDealTarget}
              value={form.target_company}
              onChange={(e) => setForm({ ...form, target_company: e.target.value })}
              placeholder="Acme Industrial Corp"
              className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
            />
          </div>
          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Sector
            </label>
            <input
              data-testid={DEAL.newDealSector}
              value={form.sector}
              onChange={(e) => setForm({ ...form, sector: e.target.value })}
              className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
            />
          </div>
          <div>
            <label className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Deal size
            </label>
            <input
              data-testid={DEAL.newDealSize}
              value={form.deal_size}
              onChange={(e) => setForm({ ...form, deal_size: e.target.value })}
              placeholder="$45M"
              className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
            />
          </div>
        </div>
        <button
          type="submit"
          disabled={loading}
          data-testid={DEAL.newDealSubmit}
          className="mt-7 w-full bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-60"
        >
          {loading ? "Creating…" : "Create deal"}
        </button>
      </form>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [deals, setDeals] = useState([]);
  const [activity, setActivity] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);

  const load = async () => {
    try {
      const [s, d, a] = await Promise.all([
        api.get("/dashboard/stats"),
        api.get("/deals"),
        api.get("/activity/recent"),
      ]);
      setStats(s.data);
      setDeals(d.data);
      setActivity(a.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 5000); // poll for processing updates
    return () => clearInterval(id);
  }, []);

  return (
    <AppLayout>
      <div data-testid={DASHBOARD.root} className="px-6 py-6">
        {/* Heading */}
        <div className="flex items-end justify-between border-b border-[var(--cv-border)] pb-5">
          <div>
            <div className="cv-tag">// CONTROL ROOM</div>
            <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight md:text-4xl">
              Active mandates<span className="cv-cursor" />
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <input
              data-testid={DASHBOARD.commandPalette}
              placeholder="> search deals, docs, flags…"
              className="hidden w-72 border border-[var(--cv-border)] bg-[var(--cv-surface)] px-3 py-2 font-mono text-xs text-[var(--cv-text)] outline-none focus:border-[var(--cv-primary)] md:block"
            />
            <button
              onClick={() => setDialogOpen(true)}
              data-testid={DASHBOARD.newDealBtn}
              className="flex items-center gap-2 bg-[var(--cv-primary)] px-3 py-2 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)]"
            >
              <Plus className="h-3.5 w-3.5" /> New deal
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-4">
          <StatCard
            testid={DASHBOARD.statDealsActive}
            label="Active deals"
            value={stats?.deals_active ?? "—"}
            hint={`${stats?.deals_total ?? 0} total mandates`}
          />
          <StatCard
            testid={DASHBOARD.statDocs}
            label="Docs processed"
            value={stats?.documents_completed ?? "—"}
            hint={`${stats?.documents_total ?? 0} ingested`}
          />
          <StatCard
            testid={DASHBOARD.statRedFlags}
            label="Red flags surfaced"
            value={stats?.red_flags_total ?? "—"}
            hint="across all deals"
            accent
          />
          <StatCard
            testid={DASHBOARD.statHighSeverity}
            label="High severity"
            value={stats?.red_flags_high ?? "—"}
            hint="needs IC attention"
          />
        </div>

        {/* Lower split */}
        <div className="mt-6 grid grid-cols-12 gap-4">
          {/* Deals table */}
          <section
            data-testid={DASHBOARD.dealsTable}
            className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-8"
          >
            <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-4 py-3">
              <h2 className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Deal book
              </h2>
              <Link
                to="/deals"
                className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)] hover:underline"
              >
                view all →
              </Link>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full font-mono text-xs">
                <thead>
                  <tr className="border-b border-[var(--cv-border)] text-left text-[var(--cv-muted)]">
                    <th className="px-4 py-2.5">Project</th>
                    <th className="px-4 py-2.5">Target</th>
                    <th className="px-4 py-2.5">Sector</th>
                    <th className="px-4 py-2.5 text-right">Size</th>
                    <th className="px-4 py-2.5 text-right">Docs</th>
                    <th className="px-4 py-2.5 text-right">Flags</th>
                    <th className="px-4 py-2.5">Stage</th>
                  </tr>
                </thead>
                <tbody>
                  {deals.length === 0 && (
                    <tr>
                      <td colSpan={7} className="px-4 py-12 text-center text-[var(--cv-muted)]">
                        <div className="mb-2 flex justify-center">
                          <Briefcase className="h-8 w-8 opacity-60" />
                        </div>
                        No mandates yet. Create your first deal to start ingesting.
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
                      <td className="px-4 py-3 text-right text-[var(--cv-text)]">{d.deal_size || "—"}</td>
                      <td className="px-4 py-3 text-right text-[var(--cv-text)]">{d.documents_count}</td>
                      <td
                        className={`px-4 py-3 text-right ${
                          d.red_flags_count > 0 ? "text-[var(--cv-primary)]" : "text-[var(--cv-muted)]"
                        }`}
                      >
                        {d.red_flags_count}
                      </td>
                      <td className="px-4 py-3">
                        <span className="cv-chip cv-chip-amber">{d.stage.replace("_", " ")}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Activity */}
          <aside
            data-testid={DASHBOARD.recentActivity}
            className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-4"
          >
            <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Recent activity
            </div>
            <ul className="divide-y divide-[var(--cv-border)]/60">
              {activity.length === 0 && (
                <li className="px-4 py-8 text-center font-mono text-xs text-[var(--cv-muted)]">
                  No ingestion activity yet.
                </li>
              )}
              {activity.map((a) => (
                <li key={a.id} className="flex items-start gap-3 px-4 py-3">
                  <FileText className="mt-0.5 h-3.5 w-3.5 text-[var(--cv-primary)]" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-body text-sm text-[var(--cv-text)]">{a.filename}</div>
                    <div className="mt-1 flex items-center gap-2 font-mono text-[11px] text-[var(--cv-muted)]">
                      <StatusChip status={a.status} />
                      <span>{a.created_at?.slice(11, 19)} UTC</span>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </aside>
        </div>

        {/* Hint strip */}
        <div className="mt-6 flex items-center gap-3 border border-dashed border-[var(--cv-border)] bg-[var(--cv-surface)]/60 px-4 py-3 font-mono text-[11px] text-[var(--cv-muted)]">
          <Flame className="h-3.5 w-3.5 text-[var(--cv-primary)]" />
          Tip — drop a PDF on the <Link to="/upload" className="text-[var(--cv-primary)] hover:underline">Ingest tab</Link>{" "}
          to surface red flags in under 90 seconds.
        </div>
      </div>

      <NewDealDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={(d) => {
          setDeals((arr) => [d, ...arr]);
          navigate(`/deals/${d.id}`);
        }}
      />
    </AppLayout>
  );
}

function StatusChip({ status }) {
  if (status === "completed")
    return <span className="cv-chip cv-chip-green">✓ extracted</span>;
  if (status === "processing")
    return <span className="cv-chip cv-chip-amber">⟳ processing</span>;
  if (status === "failed")
    return <span className="cv-chip cv-chip-red"><AlertOctagon className="h-3 w-3" /> failed</span>;
  return <span className="cv-chip">{status}</span>;
}
