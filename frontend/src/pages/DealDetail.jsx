import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import api, { API } from "@/lib/api";
import AppLayout from "@/components/AppLayout";
import { DEAL, UPLOAD } from "@/constants/testIds";
import { toast } from "sonner";
import {
  UploadCloud,
  FileText,
  Loader2,
  CheckCircle2,
  AlertOctagon,
  AlertTriangle,
  Trash2,
  RefreshCw,
  Download,
  Sparkles,
  FileSearch,
  LayoutGrid,
  Share2,
  Copy,
  X,
} from "lucide-react";

function StatusChip({ status }) {
  if (status === "completed")
    return (
      <span className="cv-chip cv-chip-green">
        <CheckCircle2 className="h-3 w-3" /> extracted
      </span>
    );
  if (status === "processing")
    return (
      <span className="cv-chip cv-chip-amber">
        <Loader2 className="h-3 w-3 animate-spin" /> processing
      </span>
    );
  if (status === "uploaded")
    return <span className="cv-chip cv-chip-amber">⟳ queued</span>;
  if (status === "failed")
    return (
      <span className="cv-chip cv-chip-red">
        <AlertOctagon className="h-3 w-3" /> failed
      </span>
    );
  return <span className="cv-chip">{status}</span>;
}

function SeverityChip({ s }) {
  const k = (s || "").toLowerCase();
  return (
    <span
      className={`cv-chip ${
        k === "high" ? "cv-chip-red" : k === "medium" ? "cv-chip-amber" : ""
      }`}
    >
      {k || "info"}
    </span>
  );
}

const TABS = [
  { key: "overview", label: "Overview", icon: LayoutGrid },
  { key: "preview", label: "PDF preview", icon: FileSearch },
  { key: "rollup", label: "IC roll-up", icon: Sparkles },
];

export default function DealDetail() {
  const { id } = useParams();
  const [deal, setDeal] = useState(null);
  const [docs, setDocs] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("overview");
  const [rollup, setRollup] = useState(null);
  const [rollupAt, setRollupAt] = useState(null);
  const [rollupLoading, setRollupLoading] = useState(false);
  const fileRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [d, dl, r] = await Promise.all([
        api.get(`/deals/${id}`),
        api.get(`/deals/${id}/documents`),
        api.get(`/deals/${id}/rollup`),
      ]);
      setDeal(d.data);
      setDocs(dl.data);
      setRollup(r.data?.rollup || null);
      setRollupAt(r.data?.rollup_at || null);
      if (!selected && dl.data.length) setSelected(dl.data[0]);
      if (selected) {
        const fresh = dl.data.find((x) => x.id === selected.id);
        if (fresh) setSelected(fresh);
      }
    } catch (err) {
      console.error(err);
    }
  }, [id, selected]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3500);
    return () => clearInterval(t);
  }, [refresh]);

  const upload = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Only PDF files are supported.");
      return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await api.post(`/deals/${id}/documents`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Upload received. Extraction queued.");
      setDocs((arr) => [data, ...arr]);
      setSelected(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    upload(e.dataTransfer.files?.[0]);
  };

  const deleteDoc = async (docId) => {
    if (!window.confirm("Delete this document and its extraction?")) return;
    await api.delete(`/documents/${docId}`);
    setDocs((arr) => arr.filter((d) => d.id !== docId));
    if (selected?.id === docId) setSelected(null);
  };

  const exportCsv = async () => {
    try {
      const res = await api.get(`/deals/${id}/export.csv`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `clearvault_${deal?.name?.replace(/\s+/g, "_") || "deal"}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("CSV exported.");
    } catch (err) {
      toast.error("Export failed");
    }
  };

  const generateRollup = async () => {
    setRollupLoading(true);
    try {
      const { data } = await api.post(`/deals/${id}/rollup`);
      setRollup(data.rollup);
      setRollupAt(data.rollup_at);
      toast.success("IC roll-up generated.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Roll-up failed");
    } finally {
      setRollupLoading(false);
    }
  };

  if (!deal)
    return (
      <AppLayout>
        <div className="px-6 py-12 font-mono text-sm text-[var(--cv-muted)]">Loading deal…</div>
      </AppLayout>
    );

  const ex = selected?.extracted;
  const completedDocs = docs.filter((d) => d.status === "completed");

  return (
    <AppLayout>
      <div data-testid={DEAL.detailRoot} className="px-6 py-6">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--cv-border)] pb-5">
          <div>
            <div className="cv-tag">// MANDATE · {deal.id.slice(0, 8).toUpperCase()}</div>
            <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight md:text-4xl">
              {deal.name}
            </h1>
            <p className="mt-1 font-mono text-xs text-[var(--cv-muted)]">
              Target · <span className="text-[var(--cv-text)]">{deal.target_company}</span>
              {" · "}Sector · <span className="text-[var(--cv-text)]">{deal.sector}</span>
              {deal.deal_size && (
                <>
                  {" · "}Size · <span className="text-[var(--cv-text)]">{deal.deal_size}</span>
                </>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="cv-chip">{deal.documents_count} docs</span>
            <span className="cv-chip cv-chip-amber">{deal.red_flags_count} flags</span>
            <button
              onClick={exportCsv}
              data-testid="deal-export-csv-btn"
              disabled={completedDocs.length === 0}
              className="flex items-center gap-2 border border-[var(--cv-border)] px-3 py-2 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)] disabled:opacity-40"
            >
              <Download className="h-3.5 w-3.5" /> Export CSV
            </button>
            <button
              onClick={refresh}
              className="flex items-center gap-2 border border-[var(--cv-border)] px-3 py-2 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              <RefreshCw className="h-3.5 w-3.5" /> refresh
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="mt-5 flex items-center gap-px border-b border-[var(--cv-border)]">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              data-testid={`deal-tab-${key}`}
              className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 font-mono text-xs uppercase tracking-widest ${
                tab === key
                  ? "border-[var(--cv-primary)] text-[var(--cv-primary)]"
                  : "border-transparent text-[var(--cv-muted)] hover:text-[var(--cv-text)]"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        {/* Upload zone (always visible, compact) */}
        <section className="mt-5">
          <div
            data-testid={UPLOAD.dropzone}
            data-dragging={dragging}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className="cv-dropzone group flex cursor-pointer items-center justify-between gap-4 px-5 py-4"
          >
            <div className="flex items-center gap-4">
              <UploadCloud className="h-5 w-5 text-[var(--cv-primary)]" />
              <div>
                <div className="font-heading text-sm font-bold tracking-tight">
                  Drop a PDF, or click to add another document.
                </div>
                <div className="font-mono text-[11px] text-[var(--cv-muted)]">
                  PDF only · up to 50MB · processed in &lt;90s
                </div>
              </div>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              data-testid={UPLOAD.fileInput}
              className="hidden"
              onChange={(e) => upload(e.target.files?.[0])}
            />
            {uploading && (
              <div className="flex items-center gap-2 font-mono text-xs text-[var(--cv-primary)]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> uploading…
              </div>
            )}
          </div>
        </section>

        {/* Tab content */}
        {tab === "overview" && (
          <OverviewTab
            docs={docs}
            selected={selected}
            setSelected={setSelected}
            deleteDoc={deleteDoc}
            ex={ex}
          />
        )}

        {tab === "preview" && (
          <PreviewTab docs={docs} selected={selected} setSelected={setSelected} ex={ex} />
        )}

        {tab === "rollup" && (
          <RollupTab
            dealId={id}
            rollup={rollup}
            rollupAt={rollupAt}
            onGenerate={generateRollup}
            loading={rollupLoading}
            completedCount={completedDocs.length}
          />
        )}
      </div>
    </AppLayout>
  );
}

/* ---------- Overview tab (docs list + extraction details) ---------- */
function OverviewTab({ docs, selected, setSelected, deleteDoc, ex }) {
  return (
    <section className="mt-5 grid grid-cols-12 gap-4">
      <div
        data-testid={DEAL.documentsTable}
        className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-4"
      >
        <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
          Documents ({docs.length})
        </div>
        <ul className="max-h-[640px] overflow-y-auto">
          {docs.length === 0 && (
            <li className="px-4 py-10 text-center font-mono text-xs text-[var(--cv-muted)]">
              No documents yet.
            </li>
          )}
          {docs.map((d) => {
            const active = selected?.id === d.id;
            return (
              <li
                key={d.id}
                onClick={() => setSelected(d)}
                className={`group flex cursor-pointer items-start gap-3 border-b border-[var(--cv-border)]/60 px-4 py-3 ${
                  active ? "bg-[var(--cv-surface-hover)]" : "hover:bg-[var(--cv-surface-hover)]"
                }`}
              >
                <FileText
                  className={`mt-0.5 h-3.5 w-3.5 ${
                    active ? "text-[var(--cv-primary)]" : "text-[var(--cv-muted)]"
                  }`}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-body text-sm">{d.filename}</div>
                  <div className="mt-1 flex items-center gap-2 font-mono text-[11px] text-[var(--cv-muted)]">
                    <StatusChip status={d.status} />
                    <span>{(d.file_size / 1024).toFixed(0)} KB</span>
                  </div>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteDoc(d.id);
                  }}
                  className="opacity-0 transition-opacity group-hover:opacity-100"
                  title="Delete"
                >
                  <Trash2 className="h-3.5 w-3.5 text-[var(--cv-muted)] hover:text-[var(--cv-danger)]" />
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="col-span-12 md:col-span-8">
        {!selected && (
          <div className="border border-dashed border-[var(--cv-border)] bg-[var(--cv-surface)] px-6 py-16 text-center font-mono text-xs text-[var(--cv-muted)]">
            Select a document or drop a new PDF to view its extraction.
          </div>
        )}
        {selected && selected.status !== "completed" && selected.status !== "failed" && (
          <div
            data-testid={UPLOAD.processingStatus}
            className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-8"
          >
            <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
              <Loader2 className="h-4 w-4 animate-spin" /> Processing pipeline
            </div>
            <h3 className="mt-2 font-heading text-2xl font-bold tracking-tight">
              {selected.filename}
            </h3>
            <p className="mt-3 max-w-md font-body text-sm text-[var(--cv-muted)]">
              Gemini is parsing pages, locating financial tables, and ranking red-flag candidates.
            </p>
            <div className="mt-8 space-y-2 font-mono text-[12px] text-[var(--cv-muted)]">
              {[
                "→ upload received",
                "→ pdf decoded · pages indexed",
                "→ multimodal extraction running…",
                "→ red flag detection pending",
              ].map((line, i) => (
                <div key={line} className={i < 2 ? "text-[var(--cv-success)]" : ""}>
                  {line}
                </div>
              ))}
            </div>
          </div>
        )}

        {selected?.status === "failed" && (
          <div className="border border-[var(--cv-danger)]/60 bg-[var(--cv-surface)] p-8">
            <div className="flex items-center gap-2 text-[var(--cv-danger)]">
              <AlertOctagon className="h-4 w-4" />
              <span className="font-mono text-[11px] uppercase tracking-widest">Extraction failed</span>
            </div>
            <h3 className="mt-2 font-heading text-xl font-bold tracking-tight">{selected.filename}</h3>
            <pre className="mt-4 whitespace-pre-wrap font-mono text-xs text-[var(--cv-muted)]">
              {selected.error || "Unknown error"}
            </pre>
          </div>
        )}

        {ex && selected.status === "completed" && (
          <div className="space-y-4">
            <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5">
              <div className="flex items-center justify-between">
                <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Executive summary
                </span>
                <span className="cv-chip cv-chip-amber">
                  {(ex.document_type || "other").replace("_", " ")}
                </span>
              </div>
              <p className="mt-3 font-body text-sm leading-relaxed text-[var(--cv-text)]">
                {ex.summary || "No summary available."}
              </p>
              <div className="mt-4 flex items-center gap-4 font-mono text-[11px] text-[var(--cv-muted)]">
                <span>
                  confidence ·{" "}
                  <span className="text-[var(--cv-primary)]">{Math.round((ex.confidence || 0) * 100)}%</span>
                </span>
                <span>
                  parties ·{" "}
                  <span className="text-[var(--cv-text)]">{(ex.parties || []).join(", ") || "—"}</span>
                </span>
              </div>
            </div>

            {ex.financial_metrics?.length > 0 && (
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Financial metrics
                </div>
                <table className="w-full font-mono text-xs">
                  <thead>
                    <tr className="border-b border-[var(--cv-border)] text-left text-[var(--cv-muted)]">
                      <th className="px-4 py-2">Line item</th>
                      <th className="px-4 py-2 text-right">Value</th>
                      <th className="px-4 py-2">Period</th>
                      <th className="px-4 py-2">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ex.financial_metrics.map((m, i) => (
                      <tr key={i} className="border-b border-[var(--cv-border)]/60">
                        <td className="px-4 py-2 text-[var(--cv-text)]">{m.label}</td>
                        <td className="px-4 py-2 text-right text-[var(--cv-primary)]">{m.value}</td>
                        <td className="px-4 py-2 text-[var(--cv-muted)]">{m.period || "—"}</td>
                        <td className="px-4 py-2 text-[var(--cv-muted)]">{m.notes || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {ex.red_flags?.length > 0 && (
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-4 py-3">
                  <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                    Red flags ({ex.red_flags.length})
                  </span>
                  <AlertTriangle className="h-3.5 w-3.5 text-[var(--cv-primary)]" />
                </div>
                <ul className="divide-y divide-[var(--cv-border)]/60">
                  {ex.red_flags.map((f, i) => (
                    <li key={i} className="flex items-start gap-3 px-4 py-3">
                      <SeverityChip s={f.severity} />
                      <div className="flex-1">
                        <div className="font-body text-sm">{f.title}</div>
                        {f.description && (
                          <div className="mt-1 font-body text-xs text-[var(--cv-muted)]">{f.description}</div>
                        )}
                      </div>
                      {f.page && (
                        <span className="font-mono text-[11px] text-[var(--cv-muted)]">p.{f.page}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {ex.key_terms?.length > 0 && (
              <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
                <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Key terms
                </div>
                <table className="w-full font-mono text-xs">
                  <tbody>
                    {ex.key_terms.map((t, i) => (
                      <tr key={i} className="border-b border-[var(--cv-border)]/60">
                        <td className="px-4 py-2 text-[var(--cv-muted)]">{t.label}</td>
                        <td className="px-4 py-2 text-[var(--cv-text)]">{t.value}</td>
                        <td className="px-4 py-2 text-[var(--cv-muted)]">{t.notes || ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/* ---------- PDF preview tab ---------- */
function PreviewTab({ docs, selected, setSelected, ex }) {
  const token = typeof window !== "undefined" ? localStorage.getItem("cv_token") : null;
  const completed = docs.filter((d) => d.status === "completed");
  const [page, setPage] = useState(1);

  // pick a sensible default
  useEffect(() => {
    if (!selected && completed.length) setSelected(completed[0]);
  }, [completed, selected, setSelected]);

  useEffect(() => {
    setPage(1);
  }, [selected?.id]);

  if (completed.length === 0) {
    return (
      <div className="mt-5 border border-dashed border-[var(--cv-border)] bg-[var(--cv-surface)] px-6 py-16 text-center font-mono text-xs text-[var(--cv-muted)]">
        No completed extractions yet — once a PDF finishes processing it becomes previewable here.
      </div>
    );
  }

  const fileUrl = selected
    ? `${API}/documents/${selected.id}/file?token=${encodeURIComponent(token || "")}#page=${page}`
    : null;

  return (
    <section className="mt-5 grid grid-cols-12 gap-4">
      {/* Side panel — doc switcher + flags as jump list */}
      <aside className="col-span-12 border border-[var(--cv-border)] bg-[var(--cv-surface)] md:col-span-4">
        <div className="border-b border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
          Document
        </div>
        <select
          value={selected?.id || ""}
          onChange={(e) => {
            const d = completed.find((x) => x.id === e.target.value);
            setSelected(d);
          }}
          data-testid="preview-doc-select"
          className="m-3 w-[calc(100%-1.5rem)] border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2 font-mono text-xs text-[var(--cv-text)] outline-none focus:border-[var(--cv-primary)]"
        >
          {completed.map((d) => (
            <option key={d.id} value={d.id}>
              {d.filename}
            </option>
          ))}
        </select>

        <div className="border-t border-[var(--cv-border)] px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
          Red flags · click to jump
        </div>
        <ul className="max-h-[520px] divide-y divide-[var(--cv-border)]/60 overflow-y-auto">
          {(ex?.red_flags || []).length === 0 && (
            <li className="px-4 py-6 text-center font-mono text-xs text-[var(--cv-muted)]">
              No red flags in this document.
            </li>
          )}
          {(ex?.red_flags || []).map((f, i) => (
            <li key={i}>
              <button
                onClick={() => f.page && setPage(f.page)}
                data-testid={`preview-flag-${i}`}
                className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-[var(--cv-surface-hover)]"
              >
                <SeverityChip s={f.severity} />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-body text-sm">{f.title}</div>
                  {f.page && (
                    <div className="mt-0.5 font-mono text-[11px] text-[var(--cv-primary)]">
                      jump to page {f.page} →
                    </div>
                  )}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* Iframe */}
      <div className="col-span-12 md:col-span-8">
        <div className="flex items-center justify-between border border-b-0 border-[var(--cv-border)] bg-[var(--cv-surface)] px-4 py-2">
          <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
            {selected?.filename || "—"}
          </span>
          <div className="flex items-center gap-2 font-mono text-[11px]">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="border border-[var(--cv-border)] px-2 py-0.5 hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              ‹
            </button>
            <span className="text-[var(--cv-muted)]">
              page <span className="text-[var(--cv-text)]">{page}</span>
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              className="border border-[var(--cv-border)] px-2 py-0.5 hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              ›
            </button>
          </div>
        </div>
        <iframe
          key={fileUrl}
          title="pdf-preview"
          data-testid="pdf-preview-iframe"
          src={fileUrl || "about:blank"}
          className="h-[720px] w-full border border-[var(--cv-border)] bg-black"
        />
      </div>
    </section>
  );
}

/* ---------- IC roll-up tab ---------- */
function RollupTab({ dealId, rollup, rollupAt, onGenerate, loading, completedCount }) {
  const [share, setShare] = useState(null);
  const [shareLoading, setShareLoading] = useState(false);

  useEffect(() => {
    if (!rollup) return;
    api.get(`/deals/${dealId}/share`).then(({ data }) => setShare(data?.token ? data : null));
  }, [dealId, rollup]);

  const createShare = async () => {
    setShareLoading(true);
    try {
      const { data } = await api.post(`/deals/${dealId}/share`);
      setShare(data);
      toast.success("Share link created.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Share failed");
    } finally {
      setShareLoading(false);
    }
  };

  const revokeShare = async () => {
    if (!window.confirm("Revoke this link? Anyone holding it will lose access immediately.")) return;
    setShareLoading(true);
    try {
      await api.delete(`/deals/${dealId}/share`);
      setShare(null);
      toast.success("Share link revoked.");
    } catch (err) {
      toast.error("Revoke failed");
    } finally {
      setShareLoading(false);
    }
  };

  const shareUrl = share ? `${window.location.origin}/share/${share.token}` : null;

  const copyUrl = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      toast.success("Link copied.");
    } catch (e) {
      toast.error("Couldn't copy — select and copy manually.");
    }
  };

  const recColor = (r) => {
    if (r === "proceed") return "cv-chip-green";
    if (r === "pass") return "cv-chip-red";
    return "cv-chip-amber";
  };

  return (
    <section className="mt-5 space-y-4">
      <div className="flex items-end justify-between gap-3 border border-[var(--cv-border)] bg-[var(--cv-surface)] px-5 py-4">
        <div>
          <div className="cv-tag">// IC ROLL-UP MEMO</div>
          <h3 className="mt-1 font-heading text-xl font-bold tracking-tight">
            Synthesize across all completed documents
          </h3>
          <p className="mt-1 font-mono text-[11px] text-[var(--cv-muted)]">
            {completedCount} completed doc{completedCount === 1 ? "" : "s"}
            {rollupAt && (
              <>
                {" · "}last generated{" "}
                <span className="text-[var(--cv-text)]">{rollupAt.slice(0, 19).replace("T", " ")}</span>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {rollup && !share && (
            <button
              onClick={createShare}
              disabled={shareLoading}
              data-testid="deal-share-btn"
              className="flex items-center gap-2 border border-[var(--cv-border)] px-3 py-2.5 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)] disabled:opacity-60"
            >
              {shareLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Share2 className="h-3.5 w-3.5" />}
              Share
            </button>
          )}
          <button
            onClick={onGenerate}
            disabled={loading || completedCount === 0}
            data-testid="deal-generate-rollup-btn"
            className="flex items-center gap-2 bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-50"
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            {rollup ? "Regenerate" : "Generate roll-up"}
          </button>
        </div>
      </div>

      {/* Active share link banner */}
      {share && (
        <div
          data-testid="deal-share-banner"
          className="flex flex-wrap items-center gap-3 border border-[var(--cv-primary)]/70 bg-[var(--cv-surface)] px-4 py-3"
        >
          <Share2 className="h-3.5 w-3.5 text-[var(--cv-primary)]" />
          <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
            Public link active
          </span>
          <input
            readOnly
            value={shareUrl || ""}
            data-testid="deal-share-url"
            className="flex-1 min-w-[280px] border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-1.5 font-mono text-[11px] text-[var(--cv-text)] outline-none"
            onFocus={(e) => e.target.select()}
          />
          <button
            onClick={copyUrl}
            data-testid="deal-share-copy"
            className="flex items-center gap-1 border border-[var(--cv-border)] px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
          >
            <Copy className="h-3 w-3" /> copy
          </button>
          <button
            onClick={revokeShare}
            data-testid="deal-share-revoke"
            className="flex items-center gap-1 border border-[var(--cv-border)] px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-danger)] hover:text-[var(--cv-danger)]"
          >
            <X className="h-3 w-3" /> revoke
          </button>
          <span className="font-mono text-[10px] text-[var(--cv-muted)]">
            {share.view_count} view{share.view_count === 1 ? "" : "s"}
          </span>
        </div>
      )}

      {!rollup && !loading && (
        <div className="border border-dashed border-[var(--cv-border)] bg-[var(--cv-surface)] px-6 py-16 text-center font-mono text-xs text-[var(--cv-muted)]">
          {completedCount === 0
            ? "Upload + process at least one PDF before generating an IC roll-up."
            : "No roll-up yet. Click 'Generate roll-up' to synthesize."}
        </div>
      )}

      {rollup && (
        <div className="space-y-4">
          {/* Recommendation */}
          <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Recommendation
              </span>
              <span className={`cv-chip ${recColor(rollup.recommendation)}`}>
                {(rollup.recommendation || "—").replace(/_/g, " ")}
              </span>
            </div>
            <p className="mt-3 font-body text-sm leading-relaxed">{rollup.executive_summary}</p>
            {rollup.recommendation_rationale && (
              <p className="mt-3 border-l-2 border-[var(--cv-primary)] bg-[var(--cv-bg)] px-3 py-2 font-mono text-xs text-[var(--cv-muted)]">
                rationale · {rollup.recommendation_rationale}
              </p>
            )}
          </div>

          {/* Consolidated financials */}
          {rollup.consolidated_financials?.length > 0 && (
            <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
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
            </div>
          )}

          {/* Top red flags */}
          {rollup.top_red_flags?.length > 0 && (
            <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)]">
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
                      <span className="font-mono text-[11px] text-[var(--cv-muted)]">{f.source}</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Gaps + next steps */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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
          </div>
        </div>
      )}
    </section>
  );
}
