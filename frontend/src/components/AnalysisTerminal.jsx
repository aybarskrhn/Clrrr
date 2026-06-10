import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Loader2,
  Send,
  AlertTriangle,
  Download,
  ImageOff,
  ShieldCheck,
} from "lucide-react";

// ----------- helpers -----------

function extractTable(answer) {
  if (!answer) return null;
  const lines = answer.split("\n");
  const table = [];
  let inTable = false;
  for (const raw of lines) {
    const s = raw.trim();
    const isPipe = s.startsWith("|") && s.endsWith("|") && (s.match(/\|/g) || []).length >= 2;
    if (isPipe) {
      inTable = true;
      table.push(s);
    } else if (inTable) {
      break;
    }
  }
  if (table.length < 3) return null;
  return table;
}

function parseTable(tableLines) {
  if (!tableLines) return { header: [], rows: [] };
  const isSep = (s) => /^[\|\s\-:]+$/.test(s.trim());
  const rows = [];
  for (const line of tableLines) {
    if (isSep(line)) continue;
    const cells = line.split("|").map((c) => c.trim()).filter((c) => c !== "");
    if (cells.length) rows.push(cells);
  }
  if (rows.length === 0) return { header: [], rows: [] };
  const header = rows[0];
  const data = rows.slice(1);
  const max = Math.max(header.length, ...data.map((r) => r.length));
  const pad = (r) => [...r, ...Array(max - r.length).fill("")];
  return { header: pad(header), rows: data.map(pad) };
}

function stripTable(answer) {
  // Render everything that's NOT the first pipe table — for the prose portion
  if (!answer) return "";
  const lines = answer.split("\n");
  const out = [];
  let removed = false;
  let inTable = false;
  for (const raw of lines) {
    const s = raw.trim();
    const isPipe = s.startsWith("|") && s.endsWith("|") && (s.match(/\|/g) || []).length >= 2;
    if (!removed) {
      if (isPipe) {
        inTable = true;
        continue;
      }
      if (inTable) {
        removed = true;
        inTable = false;
        out.push(raw);
        continue;
      }
    }
    out.push(raw);
  }
  return out.join("\n");
}

function dropRowReasoningSection(text) {
  return (text || "").replace(/##\s*Row Reasoning[\s\S]*$/m, "").trimEnd();
}

// Compact, Bloomberg-style markdown → JSX (headings, bold, lists, line breaks)
function renderProse(text) {
  const blocks = text.split(/\n{2,}/);
  return blocks.map((block, bi) => {
    if (/^##\s+/.test(block)) {
      const heading = block.replace(/^##\s+/, "");
      return (
        <h4 key={bi} className="mt-5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-primary)]">
          {renderInline(heading)}
        </h4>
      );
    }
    if (/^[-*]\s/m.test(block)) {
      const items = block.split(/\n/).filter((l) => /^[-*]\s/.test(l)).map((l) => l.replace(/^[-*]\s+/, ""));
      return (
        <ul key={bi} className="mt-2 list-disc space-y-1 pl-5 font-body text-sm text-[var(--cv-text)]">
          {items.map((it, i) => (
            <li key={i}>{renderInline(it)}</li>
          ))}
        </ul>
      );
    }
    return (
      <p key={bi} className="mt-2 font-body text-sm leading-relaxed text-[var(--cv-text)]">
        {renderInline(block)}
      </p>
    );
  });
}

function renderInline(text) {
  // bold **x**, mono `x`, citations [Doc X · p.N] (color-only), and the unverified warning chip
  const parts = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`|\[Doc [^\]]+\]|\[Page \d+\]|⚠️\s*unverified)/g;
  let last = 0;
  let m;
  let k = 0;
  while ((m = regex.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) {
      parts.push(
        <strong key={k++} className="text-[var(--cv-text)]">
          {tok.slice(2, -2)}
        </strong>,
      );
    } else if (tok.startsWith("`")) {
      parts.push(
        <code key={k++} className="rounded-sm bg-[var(--cv-bg)] px-1.5 py-0.5 font-mono text-[12px] text-[var(--cv-primary)]">
          {tok.slice(1, -1)}
        </code>,
      );
    } else if (tok.startsWith("[Doc") || tok.startsWith("[Page")) {
      parts.push(
        <span key={k++} className="font-mono text-[11px] text-[var(--cv-primary)]">
          {tok}
        </span>,
      );
    } else {
      parts.push(
        <span
          key={k++}
          className="ml-1 inline-flex items-center gap-1 rounded-sm border border-[var(--cv-danger)]/60 bg-[var(--cv-danger)]/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-widest text-[var(--cv-danger)]"
          data-testid="analyze-unverified-chip"
        >
          <AlertTriangle className="h-3 w-3" />
          unverified
        </span>,
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// ----------- main component -----------

export default function AnalysisTerminal({ deal, documents = [] }) {
  const completed = useMemo(() => documents.filter((d) => d.status === "completed"), [documents]);
  const [scope, setScope] = useState(new Set());
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [highlights, setHighlights] = useState({}); // {`${docId}::${page}`: {png_b64, quad_count}}
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [selectedPage, setSelectedPage] = useState(null);
  const [highlightLoading, setHighlightLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const tableRef = useRef(null);

  // default scope = all completed docs
  useEffect(() => {
    if (scope.size === 0 && completed.length > 0) {
      setScope(new Set(completed.map((d) => d.id)));
    }
  }, [completed, scope.size]);

  const docNameById = useMemo(() => {
    const m = {};
    for (const d of documents) m[d.id] = d.filename;
    return m;
  }, [documents]);

  const toggleScope = (id) => {
    setScope((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const ask = async (e) => {
    e?.preventDefault();
    if (!question.trim()) return;
    if (scope.size === 0) {
      toast.error("Select at least one document.");
      return;
    }
    setLoading(true);
    setResult(null);
    setHighlights({});
    setSelectedPage(null);
    setSelectedDocId(null);
    try {
      const { data } = await api.post("/analyze", {
        question: question.trim(),
        doc_scope: Array.from(scope),
        n_results: 2,
      });
      setResult(data);

      // Pick the first provenance/cited/chunk page (per blueprint fallback chain)
      const firstPage =
        (data.provenance_cited_pages && data.provenance_cited_pages[0]) ??
        (data.cited_pages && data.cited_pages[0]) ??
        data.first_chunk_page ??
        null;
      const firstDocId = (data.row_docs || []).find((d) => !!d) || Array.from(scope)[0] || null;
      if (firstPage) setSelectedPage(firstPage);
      if (firstDocId) setSelectedDocId(firstDocId);

      // Auto-fetch highlight for the first provenance-cited page
      const hbp = data.highlight_terms_by_page || {};
      const pageKeys = Object.keys(hbp);
      if (pageKeys.length && firstDocId) {
        const firstPageKey = String(firstPage ?? pageKeys[0]);
        if (hbp[firstPageKey]) {
          fetchHighlight(firstDocId, parseInt(firstPageKey, 10), hbp[firstPageKey]);
        }
      }
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail || err?.response?.data?.error;
      if (status === 422) {
        toast.error("No relevant pages found.");
        setResult({
          error: "No relevant pages found.",
          is_verified: false,
          cited_pages: [],
        });
      } else if (status === 502) {
        toast.error("OpenRouter call failed — check your API key + balance.");
      } else {
        toast.error(detail || "Analysis failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchHighlight = async (docId, pageNum, searchTerms) => {
    if (!docId || !pageNum) return;
    setHighlightLoading(true);
    try {
      const { data } = await api.post("/highlight-page", {
        doc_name: docId,
        page_num: pageNum,
        search_terms: searchTerms || [],
      });
      setHighlights((prev) => ({
        ...prev,
        [`${docId}::${pageNum}`]: {
          png_b64: data.page_png_b64,
          quad_count: data.quad_count,
        },
      }));
      setSelectedDocId(docId);
      setSelectedPage(pageNum);
    } catch (err) {
      toast.error("Failed to render highlighted page");
    } finally {
      setHighlightLoading(false);
    }
  };

  const onRowClick = (rowIdx) => {
    if (!result) return;
    const doc = result.row_docs?.[rowIdx];
    const page = result.row_pages?.[rowIdx];
    if (!doc || !page) {
      toast.message("Unresolved row — no provenance match in the raw text.");
      return;
    }
    const terms = (result.highlight_terms_by_page || {})[String(page)] || [];
    const cacheKey = `${doc}::${page}`;
    if (highlights[cacheKey]) {
      setSelectedDocId(doc);
      setSelectedPage(page);
      return;
    }
    fetchHighlight(doc, page, terms);
  };

  const exportCsv = async () => {
    if (!result?.answer) return;
    setExporting(true);
    try {
      const { data } = await api.post("/export-table", {
        answer: result.answer,
        row_pages: result.row_pages || [],
        row_docs: result.row_docs || [],
        row_reasoning: result.row_reasoning || [],
      });
      const blob = new Blob([data.csv_data], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(data.has_unresolved ? "CSV exported (contains unresolved rows)" : "CSV exported.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Export failed");
    } finally {
      setExporting(false);
    }
  };

  // Render computed shapes
  const tableLines = extractTable(result?.answer);
  const parsed = parseTable(tableLines);
  const proseAnswer = result?.answer
    ? dropRowReasoningSection(tableLines ? stripTable(result.answer) : result.answer)
    : "";

  // Currently-displayed highlight image — keyed off the row the user explicitly
  // selected (or the first provenance row on initial load).
  const currentDocId = selectedDocId;
  const currentKey = currentDocId && selectedPage ? `${currentDocId}::${selectedPage}` : null;
  const currentHighlight = currentKey ? highlights[currentKey] : null;

  if (completed.length === 0) {
    return (
      <div className="mt-5 border border-dashed border-[var(--cv-border)] bg-[var(--cv-surface)] px-6 py-16 text-center font-mono text-xs text-[var(--cv-muted)]">
        Upload + process at least one PDF before using the Analysis Terminal.
      </div>
    );
  }

  return (
    <section data-testid="analysis-terminal-root" className="mt-5 space-y-4">
      {/* Question composer */}
      <form
        onSubmit={ask}
        data-testid="analysis-terminal-form"
        className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5"
      >
        <div className="cv-tag">// ANALYSIS TERMINAL · OPENROUTER · CLAUDE SONNET 4.6</div>
        <h3 className="mt-2 font-heading text-xl font-bold tracking-tight">
          Ask anything about these documents.
        </h3>
        <p className="mt-1 font-mono text-[11px] text-[var(--cv-muted)]">
          Deterministic, cited, source-traceable. Numbers without raw-text backing are flagged ⚠️
          unverified.
        </p>

        <label className="mt-5 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
          Document scope
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          {completed.map((d) => {
            const active = scope.has(d.id);
            return (
              <button
                key={d.id}
                type="button"
                onClick={() => toggleScope(d.id)}
                data-testid={`analyze-scope-${d.id}`}
                className={`flex items-center gap-2 border px-3 py-1.5 font-mono text-xs ${
                  active
                    ? "border-[var(--cv-primary)] bg-[var(--cv-primary)]/10 text-[var(--cv-primary)]"
                    : "border-[var(--cv-border)] text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-text)]"
                }`}
              >
                <span className={`h-2 w-2 ${active ? "bg-[var(--cv-primary)]" : "bg-[var(--cv-border)]"}`} />
                {d.filename}
              </button>
            );
          })}
        </div>

        <label className="mt-5 block font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
          Question
        </label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") ask(e);
          }}
          placeholder="e.g. Extract the FY2024 depreciation schedule and reconcile across documents."
          data-testid="analyze-question-input"
          rows={3}
          className="mt-2 w-full resize-none border border-[var(--cv-border)] bg-[var(--cv-bg)] px-3 py-2.5 font-mono text-sm outline-none focus:border-[var(--cv-primary)]"
        />

        <div className="mt-4 flex items-center justify-between gap-3">
          <span className="font-mono text-[10px] text-[var(--cv-muted)]">
            ⌘↵ to submit · temperature 0.1 · ground-truth enforced
          </span>
          <button
            type="submit"
            disabled={loading || !question.trim() || scope.size === 0}
            data-testid="analyze-submit-btn"
            className="flex items-center gap-2 bg-[var(--cv-primary)] px-4 py-2.5 font-mono text-xs font-semibold uppercase tracking-widest text-black hover:bg-[var(--cv-primary-hover)] disabled:opacity-50"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            Run query
          </button>
        </div>
      </form>

      {/* Unverified banner (blueprint requirement) */}
      {result && result.is_verified === false && !result.error && (
        <div
          data-testid="analyze-unverified-banner"
          className="flex items-start gap-3 border border-[var(--cv-danger)]/70 bg-[var(--cv-danger)]/10 px-4 py-3"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[var(--cv-danger)]" />
          <div>
            <div className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-danger)]">
              ⚠️ SCANNED DOCUMENT DETECTED
            </div>
            <p className="mt-1 font-body text-sm text-[var(--cv-text)]">
              Cross-validation disabled. Numbers may contain AI hallucinations. Manual verification
              required.
            </p>
          </div>
        </div>
      )}

      {result?.error && (
        <div className="border border-[var(--cv-border)] bg-[var(--cv-surface)] px-4 py-3 font-mono text-xs text-[var(--cv-muted)]">
          {result.error}
        </div>
      )}

      {result?.answer && (
        <div className="grid grid-cols-12 gap-4">
          {/* Answer + table */}
          <div className="col-span-12 lg:col-span-7">
            {result.is_verified && (
              <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-[var(--cv-success)]">
                <ShieldCheck className="h-3 w-3" />
                Verified against raw PDF text
              </div>
            )}

            <article className="border border-[var(--cv-border)] bg-[var(--cv-surface)] p-5">
              {renderProse(proseAnswer)}
            </article>

            {parsed.header.length > 0 && (
              <div
                ref={tableRef}
                data-testid="analyze-result-table"
                className="mt-4 border border-[var(--cv-border)] bg-[var(--cv-surface)]"
              >
                <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-4 py-3">
                  <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                    Causality / Reasoning · click row to highlight source
                  </span>
                  <button
                    onClick={exportCsv}
                    disabled={exporting}
                    data-testid="analyze-export-csv-btn"
                    className="flex items-center gap-2 border border-[var(--cv-border)] px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)] hover:border-[var(--cv-primary)] hover:text-[var(--cv-primary)] disabled:opacity-50"
                  >
                    {exporting ? <Loader2 className="h-3 w-3 animate-spin" /> : <Download className="h-3 w-3" />}
                    Export CSV
                  </button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full font-mono text-xs">
                    <thead>
                      <tr className="border-b border-[var(--cv-border)] text-left text-[var(--cv-muted)]">
                        {parsed.header.map((h, i) => (
                          <th key={i} className="px-3 py-2 whitespace-nowrap">
                            {renderInline(h)}
                          </th>
                        ))}
                        <th className="px-3 py-2">Source</th>
                        <th className="px-3 py-2">Reasoning</th>
                      </tr>
                    </thead>
                    <tbody>
                      {parsed.rows.map((row, ri) => {
                        const page = result.row_pages?.[ri];
                        const docId = result.row_docs?.[ri];
                        const reasoning = result.row_reasoning?.[ri] || "";
                        const unresolved = !page || !docId;
                        const docLabel = docId ? docNameById[docId] || docId.slice(0, 8) : "—";
                        return (
                          <tr
                            key={ri}
                            onClick={() => onRowClick(ri)}
                            data-testid={`analyze-row-${ri}`}
                            className={`border-b border-[var(--cv-border)]/60 ${
                              unresolved ? "" : "cursor-pointer hover:bg-[var(--cv-surface-hover)]"
                            }`}
                          >
                            {row.map((cell, ci) => (
                              <td key={ci} className="px-3 py-2 text-[var(--cv-text)]">
                                {renderInline(cell)}
                              </td>
                            ))}
                            <td className="px-3 py-2">
                              {unresolved ? (
                                <span className="cv-chip cv-chip-red">unresolved</span>
                              ) : (
                                <span className="cv-chip cv-chip-amber">
                                  {docLabel} · p.{page}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-[var(--cv-muted)]">
                              {reasoning || (unresolved ? "—" : "")}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* PDF page preview with highlight overlay */}
          <aside className="col-span-12 lg:col-span-5">
            <div className="sticky top-4 border border-[var(--cv-border)] bg-[var(--cv-surface)]">
              <div className="flex items-center justify-between border-b border-[var(--cv-border)] px-4 py-3">
                <span className="font-mono text-[11px] uppercase tracking-widest text-[var(--cv-muted)]">
                  Source page
                  {selectedPage ? (
                    <span className="ml-2 text-[var(--cv-primary)]">p.{selectedPage}</span>
                  ) : null}
                </span>
                {currentHighlight && (
                  <span className="font-mono text-[10px] text-[var(--cv-muted)]">
                    {currentHighlight.quad_count} highlight{currentHighlight.quad_count === 1 ? "" : "s"}
                  </span>
                )}
              </div>
              {highlightLoading && (
                <div className="flex items-center justify-center px-6 py-20 font-mono text-xs text-[var(--cv-muted)]">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> rendering page…
                </div>
              )}
              {!highlightLoading && !currentHighlight && (
                <div className="flex flex-col items-center justify-center px-6 py-20 text-center font-mono text-xs text-[var(--cv-muted)]">
                  <ImageOff className="mb-2 h-5 w-5" />
                  Click a row to render the cited PDF page with highlights.
                </div>
              )}
              {!highlightLoading && currentHighlight?.png_b64 && (
                <img
                  src={`data:image/png;base64,${currentHighlight.png_b64}`}
                  alt={`Highlighted page ${selectedPage}`}
                  data-testid="analyze-highlight-image"
                  className="w-full"
                />
              )}
              {!highlightLoading && currentHighlight && !currentHighlight.png_b64 && (
                <div className="px-6 py-12 text-center font-mono text-xs text-[var(--cv-muted)]">
                  PDF render failed — page may not exist.
                </div>
              )}
            </div>

            {/* Citation chips */}
            {(result.provenance_cited_pages || []).length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {result.provenance_cited_pages.map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      const docId = (result.row_docs || []).find(
                        (d, i) => d && result.row_pages?.[i] === p,
                      );
                      if (!docId) return;
                      const terms = (result.highlight_terms_by_page || {})[String(p)] || [];
                      fetchHighlight(docId, p, terms);
                    }}
                    data-testid={`analyze-cite-chip-${p}`}
                    className={`cv-chip ${selectedPage === p ? "cv-chip-amber" : ""}`}
                  >
                    p.{p}
                  </button>
                ))}
              </div>
            )}
          </aside>
        </div>
      )}
    </section>
  );
}
