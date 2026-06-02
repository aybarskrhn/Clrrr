import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Search, X, Briefcase, FileText, AlertTriangle, Loader2 } from "lucide-react";

const EMPTY = { deals: [], documents: [], red_flags: [] };

export default function CommandPalette({ open, onClose }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      setQ("");
      setResults(EMPTY);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const search = useCallback(async (term) => {
    if (!term || term.length < 2) {
      setResults(EMPTY);
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get(`/search`, { params: { q: term } });
      setResults(data);
    } catch (e) {
      setResults(EMPTY);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const id = setTimeout(() => search(q), 220);
    return () => clearTimeout(id);
  }, [q, search]);

  if (!open) return null;

  const go = (path) => {
    onClose();
    navigate(path);
  };

  const total = results.deals.length + results.documents.length + results.red_flags.length;

  return (
    <div
      data-testid="command-palette-overlay"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/80 p-4 pt-[12vh]"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        data-testid="command-palette"
        className="w-full max-w-2xl border border-[var(--cv-primary)] bg-[var(--cv-surface)] shadow-2xl"
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-[var(--cv-border)] px-4 py-3">
          <Search className="h-4 w-4 text-[var(--cv-primary)]" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="command-palette-input"
            placeholder="search deals, documents, red flags…"
            className="flex-1 bg-transparent font-mono text-sm text-[var(--cv-text)] outline-none placeholder:text-[var(--cv-muted)]"
          />
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--cv-muted)]" />}
          <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">
            ESC
          </span>
          <button onClick={onClose} className="text-[var(--cv-muted)] hover:text-[var(--cv-text)]">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Results */}
        <div className="max-h-[60vh] overflow-y-auto">
          {q.length < 2 && (
            <div className="px-6 py-12 text-center font-mono text-xs text-[var(--cv-muted)]">
              Type at least 2 characters to search across deals · documents · red flags.
            </div>
          )}

          {q.length >= 2 && total === 0 && !loading && (
            <div className="px-6 py-12 text-center font-mono text-xs text-[var(--cv-muted)]">
              No matches for "<span className="text-[var(--cv-text)]">{q}</span>".
            </div>
          )}

          {results.deals.length > 0 && (
            <Section title="Deals" icon={Briefcase}>
              {results.deals.map((d) => (
                <Row
                  key={d.id}
                  testid={`cp-deal-${d.id}`}
                  onClick={() => go(`/deals/${d.id}`)}
                  label={d.name}
                  hint={`${d.target_company} · ${d.sector}`}
                />
              ))}
            </Section>
          )}

          {results.documents.length > 0 && (
            <Section title="Documents" icon={FileText}>
              {results.documents.map((d) => (
                <Row
                  key={d.id}
                  testid={`cp-doc-${d.id}`}
                  onClick={() => go(`/deals/${d.deal_id}`)}
                  label={d.filename}
                  hint={`status · ${d.status}`}
                />
              ))}
            </Section>
          )}

          {results.red_flags.length > 0 && (
            <Section title="Red flags" icon={AlertTriangle} accent>
              {results.red_flags.map((f, i) => (
                <Row
                  key={i}
                  testid={`cp-flag-${i}`}
                  onClick={() => go(`/deals/${f.deal_id}`)}
                  label={f.title}
                  hint={`${f.severity} · ${f.filename}${f.page ? ` · p.${f.page}` : ""}`}
                  severity={f.severity}
                />
              ))}
            </Section>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-[var(--cv-border)] px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">
          <span>↵ open</span>
          <span>esc close</span>
          <span>
            {total > 0 ? `${total} result${total === 1 ? "" : "s"}` : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, children, accent }) {
  return (
    <div>
      <div className="flex items-center gap-2 border-b border-[var(--cv-border)]/60 bg-[var(--cv-bg)] px-4 py-1.5 font-mono text-[10px] uppercase tracking-widest text-[var(--cv-muted)]">
        <Icon className={`h-3 w-3 ${accent ? "text-[var(--cv-primary)]" : ""}`} />
        {title}
      </div>
      <ul>{children}</ul>
    </div>
  );
}

function Row({ label, hint, onClick, severity, testid }) {
  return (
    <li>
      <button
        onClick={onClick}
        data-testid={testid}
        className="flex w-full items-center justify-between gap-4 border-b border-[var(--cv-border)]/40 px-4 py-2.5 text-left hover:bg-[var(--cv-surface-hover)]"
      >
        <div className="min-w-0 flex-1">
          <div className="truncate font-body text-sm text-[var(--cv-text)]">{label}</div>
          <div className="truncate font-mono text-[11px] text-[var(--cv-muted)]">{hint}</div>
        </div>
        {severity && (
          <span
            className={`cv-chip ${
              severity === "high"
                ? "cv-chip-red"
                : severity === "medium"
                ? "cv-chip-amber"
                : ""
            }`}
          >
            {severity}
          </span>
        )}
      </button>
    </li>
  );
}
