import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppLayout from "@/components/AppLayout";
import { UPLOAD } from "@/constants/testIds";
import { toast } from "sonner";
import { UploadCloud, Loader2, FilePlus2 } from "lucide-react";

export default function Upload() {
  const navigate = useNavigate();
  const [deals, setDeals] = useState([]);
  const [dealId, setDealId] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/deals");
    setDeals(data);
    if (data.length && !dealId) setDealId(data[0].id);
  }, [dealId]);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async (file) => {
    if (!file) return;
    if (!dealId) {
      toast.error("Create or select a deal first.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Only PDF files are supported.");
      return;
    }
    setUploading(true);
    const fd = new FormData();
    fd.append("file", file);
    try {
      await api.post(`/deals/${dealId}/documents`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Upload received. Extraction queued.");
      navigate(`/deals/${dealId}`);
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

  return (
    <AppLayout>
      <div className="px-6 py-6">
        <div className="border-b border-[var(--cv-border)] pb-5">
          <div className="cv-tag">// INGEST</div>
          <h1 className="mt-2 font-heading text-3xl font-bold tracking-tight md:text-4xl">
            Drop a PDF.<span className="cv-cursor" />
          </h1>
          <p className="mt-2 max-w-2xl font-body text-sm text-[var(--cv-muted)]">
            ClearVault will index pages, extract financial tables and surface red flags. Pick the
            mandate this document belongs to first.
          </p>
        </div>

        <div className="mt-6 grid grid-cols-12 gap-4">
          <div className="col-span-12 md:col-span-4">
            <label className="block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
              Mandate
            </label>
            <select
              data-testid={UPLOAD.dealSelect}
              value={dealId}
              onChange={(e) => setDealId(e.target.value)}
              className="mt-2 w-full border border-[var(--cv-border)] bg-[var(--cv-surface)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
            >
              {deals.length === 0 && <option value="">No deals yet</option>}
              {deals.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} — {d.target_company}
                </option>
              ))}
            </select>
            <button
              onClick={() => navigate("/dashboard")}
              className="mt-3 flex w-full items-center justify-center gap-2 border border-[var(--cv-border)] px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)]"
            >
              <FilePlus2 className="h-3.5 w-3.5" /> Create new deal
            </button>

            <div className="mt-6 border border-[var(--cv-border)] bg-[var(--cv-surface)] p-4">
              <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                Pipeline
              </div>
              <ol className="mt-3 space-y-2 font-mono text-[11px] text-[var(--cv-muted)]">
                <li>1. Upload PDF (≤ 50 MB)</li>
                <li>2. Page-by-page indexing</li>
                <li>3. Multimodal extraction (Gemini 3)</li>
                <li>4. Red-flag scoring &amp; output</li>
              </ol>
            </div>
          </div>

          <div className="col-span-12 md:col-span-8">
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
              className="cv-dropzone flex cursor-pointer flex-col items-center justify-center px-8 py-24 text-center"
            >
              <UploadCloud className="h-10 w-10 text-[var(--cv-primary)]" />
              <h3 className="mt-4 font-heading text-2xl font-bold tracking-tight">
                Drop your PDF here
              </h3>
              <p className="mt-2 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                or click to browse · pdf only
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
                <div
                  data-testid={UPLOAD.processingStatus}
                  className="mt-6 flex items-center gap-2 font-mono text-xs text-[var(--cv-primary)]"
                >
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Uploading…
                </div>
              )}
              <button
                type="button"
                data-testid={UPLOAD.submit}
                onClick={(e) => {
                  e.stopPropagation();
                  fileRef.current?.click();
                }}
                className="mt-8 bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)]"
              >
                Select PDF
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
