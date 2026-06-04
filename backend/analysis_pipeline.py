"""Feature 1 — Analysis Terminal (OpenRouter pipeline).

Deterministic text-keyword retrieval (GPU-free fallback for ColPali/byaldi) +
multimodal OpenRouter call + unverified-flag post-processing + provenance resolution.
"""
from __future__ import annotations

import io
import logging
import os
import re
from typing import Optional

import pandas as pd
from openai import OpenAI

from extractor import (
    extract_all_page_texts,
    extract_page_text,
    render_page_b64,
)
from provenance import (
    extract_table_from_answer,
    resolve_table_provenance,
)

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")
MAX_IMAGES_PER_CALL = int(os.environ.get("MAX_IMAGES_PER_CALL", "20"))

_QA_PROMPT = (
    "You are a senior M&A due diligence analyst answering an analyst's question against the "
    "attached pages and extracted text. Output structure:\n"
    "1. Start with `## Direct Answer` — 1-3 sentence direct response with inline citations.\n"
    "2. When the answer contains tabular data, render a Markdown pipe table.\n"
    "3. End with `## Caveats` if any qualifications apply.\n"
    "Be terse. Do not fabricate. Numbers must come from the raw text below or the page images."
)

_GROUND_TRUTH_INSTRUCTION = (
    "GROUND TRUTH: The raw text blocks above are the authoritative source. If you state a number "
    "that does not appear verbatim in those blocks, append ` ⚠️ unverified` to that cell or value. "
    "Never invent figures."
)


def _get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    return OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)


# ---------- Deterministic text-keyword retrieval (CPU-only ColPali replacement) ----------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "what",
    "is", "are", "was", "were", "be", "been", "by", "as", "at", "this", "that",
    "from", "how", "much", "many", "do", "does", "did", "show", "me", "tell",
}


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens >= 2 chars, stopwords stripped."""
    return [t for t in re.findall(r"[A-Za-z0-9$%.\-]+", (text or "").lower()) if len(t) >= 2 and t not in _STOPWORDS]


def _score_page(page_text: str, query_tokens: list[str]) -> float:
    """Simple TF-style overlap score — count of query tokens present in the page."""
    if not page_text or not query_tokens:
        return 0.0
    page_lower = page_text.lower()
    score = 0.0
    for t in query_tokens:
        c = page_lower.count(t)
        if c:
            score += 1.0 + min(c, 5) * 0.2  # diminishing return per repeat
    return score


def retrieve_chunks(
    question: str,
    documents: list[dict],
    n_results: int = 3,
) -> list[dict]:
    """Score every page of every document by token overlap; return top-N enriched chunks.

    `documents` is a list of `{"doc_name": str, "pdf_path": str}` (one per scoped doc).
    Returns chunk dicts with: doc_name, pdf_path, page_num, text, score, base64.
    """
    q_tokens = _tokenize(question)
    if not q_tokens:
        return []

    scored: list[tuple[float, str, str, int, str]] = []  # (score, doc_name, pdf_path, page_num, text)
    for d in documents:
        doc_name = d.get("doc_name") or ""
        pdf_path = d.get("pdf_path") or ""
        if not pdf_path:
            continue
        pages = extract_all_page_texts(pdf_path)
        for page_num, text in pages.items():
            sc = _score_page(text, q_tokens)
            if sc > 0:
                scored.append((sc, doc_name, pdf_path, page_num, text))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, n_results) * max(1, len(documents))]

    chunks: list[dict] = []
    for sc, doc_name, pdf_path, page_num, text in top[: max(1, n_results * max(1, len(documents)))]:
        b64 = render_page_b64(pdf_path, page_num, dpi=110)
        chunks.append(
            {
                "doc_name": doc_name,
                "pdf_path": pdf_path,
                "page_num": page_num,
                "score": float(sc),
                "text": text,
                "base64": b64,
            }
        )
    return chunks


# ---------- Post-processing ----------

def _flag_unverified_table(answer: str, has_raw_text: bool) -> str:
    """Append ' ⚠️ unverified' to every numeric data cell when no raw ground-truth text exists."""
    if has_raw_text or not answer:
        return answer

    out_lines: list[str] = []
    state = "OUTSIDE"  # OUTSIDE | SAW_HEADER | IN_BODY
    for raw_line in answer.split("\n"):
        line = raw_line
        stripped = line.strip()
        is_pipe_row = stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2
        is_separator = is_pipe_row and re.match(r"^[\|\s\-:]+$", stripped) is not None

        if not is_pipe_row:
            state = "OUTSIDE"
            out_lines.append(line)
            continue

        if state == "OUTSIDE":
            state = "SAW_HEADER"
            out_lines.append(line)
            continue

        if state == "SAW_HEADER":
            # The line after the header should be the separator
            if is_separator:
                state = "IN_BODY"
                out_lines.append(line)
                continue
            # No separator found — treat current as body
            state = "IN_BODY"

        if state == "IN_BODY":
            if is_separator:
                out_lines.append(line)
                continue
            cells = stripped.strip("|").split("|")
            new_cells: list[str] = []
            for cell in cells:
                cell_text = cell.strip()
                if cell_text and re.search(r"\d", cell_text) and "⚠️ unverified" not in cell_text:
                    cell_text = f"{cell_text} ⚠️ unverified"
                new_cells.append(f" {cell_text} ")
            out_lines.append("|" + "|".join(new_cells) + "|")
            continue

        out_lines.append(line)

    return "\n".join(out_lines)


def _extract_row_reasoning(answer: str, num_rows: int) -> list[str]:
    """Parse per-row reasoning from a '## Row Reasoning' section emitted by the LLM."""
    if not answer or num_rows <= 0:
        return []
    m = re.search(r"##\s*Row Reasoning\s*\n(.*?)(?=\n##|\Z)", answer, re.DOTALL)
    if not m:
        return [""] * num_rows
    section = m.group(1)
    entries = re.findall(r"^\d+\.\s*.+?:\s*(.+)$", section, re.MULTILINE)
    result = list(entries[:num_rows])
    result.extend([""] * max(0, num_rows - len(result)))
    return result


# ---------- Main pipeline ----------

def answer_with_citations(
    question: str,
    chunks: list[dict],
    doc_filter: Optional[list[str]] = None,
) -> dict:
    """Run the OpenRouter pipeline against retrieved chunks. Returns the full payload per blueprint."""
    if doc_filter:
        chunks = [c for c in chunks if c.get("doc_name") in doc_filter]

    if not chunks:
        return {
            "answer": "",
            "cited_pages": [],
            "row_pages": [],
            "row_docs": [],
            "row_reasoning": [],
            "highlight_terms_by_page": {},
            "provenance_cited_pages": [],
            "first_chunk_page": None,
            "source_chunks": [],
            "is_verified": False,
            "error": "No relevant pages found.",
        }

    # Cap images at MAX_IMAGES_PER_CALL, ranked by retrieval score
    _img_eligible = [i for i, c in enumerate(chunks) if c.get("base64")]
    _img_eligible.sort(key=lambda i: chunks[i].get("score", 0.0), reverse=True)
    _image_indices = set(_img_eligible[:MAX_IMAGES_PER_CALL])

    # Build raw-text map (tries chunk.text first, then live PyMuPDF extraction)
    page_text_map: dict[tuple[str, int], str] = {}
    has_raw_text = False
    for c in chunks:
        page_num = c["page_num"]
        c_doc = c.get("doc_name", "")
        pre_text = c.get("text", "")
        key = (c_doc, page_num)
        if pre_text and pre_text.strip():
            has_raw_text = True
            page_text_map[key] = pre_text
            continue
        pdf_path = c.get("pdf_path")
        if pdf_path:
            text = extract_page_text(pdf_path, page_num)
            if text and text.strip():
                has_raw_text = True
                page_text_map[key] = text
                c["text"] = text  # cache back

    # Build multimodal content
    content: list[dict] = []
    page_refs: list[int] = []
    doc_refs: list[str] = []
    for idx, c in enumerate(chunks):
        page_num = c["page_num"]
        c_doc = c.get("doc_name") or "document"
        chunk_text = c.get("text") or page_text_map.get((c_doc, page_num), "")
        send_image = bool(c.get("base64")) and idx in _image_indices

        heading = (
            f"[TEXT-ONLY · no image attached]\n===== Raw text from {c_doc} · Page {page_num} ====="
            if c.get("base64") and not send_image
            else f"===== Raw text from {c_doc} · Page {page_num} ====="
        )
        content.append({"type": "text", "text": f"{heading}\n{chunk_text}\n"})
        if send_image:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{c['base64']}"},
                }
            )
        page_refs.append(page_num)
        doc_refs.append(c_doc)

    # Compose prompt
    unique_docs = list(dict.fromkeys(c.get("doc_name") or "document" for c in chunks))
    is_multi_doc = len(unique_docs) > 1

    if is_multi_doc:
        doc_names_str = ", ".join(unique_docs)
        cite_instruction = (
            f"Cite every factual claim using [Doc {{doc_name}} · p.{{page_num}}] where "
            f"doc_name is exactly one of: {doc_names_str}.\n"
            "When the SAME metric appears across multiple documents, RECONCILE explicitly.\n"
            "After any Markdown table output:\n## Row Reasoning\n1. [row label]: [reasoning]\n"
            "(one numbered entry per data row)"
        )
    else:
        single_doc = unique_docs[0] if unique_docs else "document"
        cite_instruction = f"Cite every factual claim using [Doc {single_doc} · p.{{page_num}}]."

    full_prompt = (
        _QA_PROMPT
        + "\n\nCITATION FORMAT: " + cite_instruction
        + "\n\n" + _GROUND_TRUTH_INSTRUCTION
        + f"\n\nShown pages: {', '.join(f'{d} p.{p}' for d, p in zip(doc_refs, page_refs))}."
        + f"\n\nQuestion: {question}"
    )

    # Call OpenRouter
    client = _get_client()
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a senior M&A due diligence analyst. Follow ALL instructions in the user message exactly.",
            },
            {"role": "user", "content": [{"type": "text", "text": full_prompt}] + content},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    answer = response.choices[0].message.content or ""

    # Post-process: flag unverified numbers when no raw text was available
    answer = _flag_unverified_table(answer, has_raw_text=has_raw_text)

    # Parse citation pages from [Doc X · p.N] and legacy [Page N]
    doc_cite_pages = [int(m) for m in re.findall(r"\[Doc [^\]·]+? · p\.(\d+)\]", answer)]
    legacy_pages = [int(m) for m in re.findall(r"\[Page (\d+)\]", answer)]
    cited_pages = sorted(set(doc_cite_pages + legacy_pages))

    # Run provenance resolution
    enriched_chunks = [
        {**c, "text": c.get("text") or page_text_map.get((c.get("doc_name", ""), c["page_num"]), "")}
        for c in chunks
    ]
    table_md = extract_table_from_answer(answer)
    prov = (
        resolve_table_provenance(table_md, enriched_chunks)
        if table_md
        else {"row_pages": [], "row_docs": [], "highlight_terms_by_page": {}, "cited_pages": []}
    )

    num_rows = len(prov.get("row_pages", []))
    row_reasoning = _extract_row_reasoning(answer, num_rows)

    return {
        "answer": answer,
        "cited_pages": cited_pages,
        "row_pages": prov["row_pages"],
        "row_docs": prov.get("row_docs", [None] * num_rows),
        "row_reasoning": row_reasoning,
        "highlight_terms_by_page": prov["highlight_terms_by_page"],
        "provenance_cited_pages": prov["cited_pages"],
        "first_chunk_page": page_refs[0] if page_refs else None,
        "is_verified": has_raw_text,
    }


# ---------- Feature 2 — CSV export ----------

def markdown_table_to_csv(
    table_md: str,
    row_pages: Optional[list] = None,
    row_docs: Optional[list] = None,
    row_reasoning: Optional[list] = None,
) -> str:
    """Convert a Markdown pipe table to CSV with three appended provenance columns.

    Column order appended after the LLM data columns:
      1. Source Doc       <- row_docs (None -> "Unresolved")
      2. Source Page      <- row_pages (None -> "Unresolved")
      3. Causality / Reasoning <- row_reasoning ("" if absent)
    """
    rows: list[list[str]] = []
    for line in (table_md or "").strip().split("\n"):
        if re.match(r"^[\|\s\-:]+$", line.strip()):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip() != ""]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return ""

    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    has_extras = row_docs is not None or row_pages is not None or row_reasoning is not None
    if has_extras:
        rows[0] = rows[0] + ["Source Doc", "Source Page", "Causality / Reasoning"]
        for i, row in enumerate(rows[1:], 0):
            doc_str = (
                str(row_docs[i]) if row_docs and i < len(row_docs) and row_docs[i] is not None else "Unresolved"
            )
            page_str = (
                str(row_pages[i])
                if row_pages and i < len(row_pages) and row_pages[i] is not None
                else "Unresolved"
            )
            reason_str = (row_reasoning[i] if row_reasoning and i < len(row_reasoning) else "") or ""
            rows[i + 1] = row + [doc_str, page_str, reason_str]

    df = pd.DataFrame(rows[1:], columns=rows[0])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()
