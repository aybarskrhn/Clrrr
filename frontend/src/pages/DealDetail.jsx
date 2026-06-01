import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import api from "@/lib/api";
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

export default function DealDetail() {
  const { id } = useParams();
  const [deal, setDeal] = useState(null);
  const [docs, setDocs] = useState([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(null);
  const fileRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const [d, dl] = await Promise.all([
        api.get(`/deals/${id}`),
        api.get(`/deals/${id}/documents`),
      ]);
      setDeal(d.data);
      setDocs(dl.data);
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
    const f = e.dataTransfer.files?.[0];
    upload(f);
  };

  const deleteDoc = async (docId) => {
    if (!window.confirm("Delete this document and its extraction?")) return;
    await api.delete(`/documents/${docId}`);
    setDocs((arr) => arr.filter((d) => d.id !== docId));
    if (selected?.id === docId) setSelected(null);
  };

  if (!deal)
    return (
      <AppLayout>
        <div className="px-6 py-12 font-mono text-sm text-[var(--cv-muted)]">Loading deal…</div>
      </AppLayout>
    );

  const ex = selected?.extracted;

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
          <div className="flex items-center gap-2">
            <span className="cv-chip">{deal.documents_count} docs</span>
            <span className="cv-chip cv-chip-amber">{deal.red_flags_count} flags</span>
            <button
              onClick={refresh}
              className="flex items-center gap-2 border border-[var(--cv-border)] px-3 py-2 font-mono text-xs uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              <RefreshCw className="h-3.5 w-3.5" /> refresh
            </button>
          </div>
        </div>

        {/* Upload zone */}
        <section className="mt-6">
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
            className="cv-dropzone group flex cursor-pointer flex-col items-center justify-center px-6 py-12 text-center"
          >
            <UploadCloud className="h-7 w-7 text-[var(--cv-primary)]" />
            <h3 className="mt-3 font-heading text-xl font-bold tracking-tight">
              Drop a PDF, or click to select.
            </h3>
            <p className="mt-2 max-w-md font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              10-Ks · LOIs · audit reports · cap tables · contracts · up to 50MB
            </p>
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,.pdf"
              data-testid={UPLOAD.fileInput}
              className="hidden"
              onChange={(e) => upload(e.target.files?.[0])}
            />
            {uploading && (
              <div className="mt-4 flex items-center gap-2 font-mono text-xs text-[var(--cv-primary)]">
                <Loader2 className="h-3.5 w-3.5 animate-spin" /> uploading…
              </div>
            )}
          </div>
        </section>

        {/* Documents + Extracted view */}
        <section className="mt-6 grid grid-cols-12 gap-4">
          {/* Doc list */}
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

          {/* Extraction viewer */}
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
                  Gemini 3 is parsing pages, locating financial tables, and ranking red-flag
                  candidates. Usually under 90 seconds for an audit report.
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
                  <span className="font-mono text-[11px] uppercase tracking-widest">
                    Extraction failed
                  </span>
                </div>
                <h3 className="mt-2 font-heading text-xl font-bold tracking-tight">
                  {selected.filename}
                </h3>
                <pre className="mt-4 whitespace-pre-wrap font-mono text-xs text-[var(--cv-muted)]">
                  {selected.error || "Unknown error"}
                </pre>
              </div>
            )}

            {ex && selected.status === "completed" && (
              <div className="space-y-4">
                {/* Summary */}
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
                      <span className="text-[var(--cv-primary)]">
                        {Math.round((ex.confidence || 0) * 100)}%
                      </span>
                    </span>
                    <span>
                      parties · <span className="text-[var(--cv-text)]">{(ex.parties || []).join(", ") || "—"}</span>
                    </span>
                  </div>
                </div>

                {/* Financial metrics */}
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
                            <td className="px-4 py-2 text-right text-[var(--cv-primary)]">
                              {m.value}
                            </td>
                            <td className="px-4 py-2 text-[var(--cv-muted)]">{m.period || "—"}</td>
                            <td className="px-4 py-2 text-[var(--cv-muted)]">{m.notes || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Red flags */}
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
                              <div className="mt-1 font-body text-xs text-[var(--cv-muted)]">
                                {f.description}
                              </div>
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

                {/* Key terms */}
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
      </div>
    </AppLayout>
  );
}
