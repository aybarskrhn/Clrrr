# ClearVault — Core Backend Integration Blueprint

This document is the authoritative reference for migrating ClearVault's three critical backend
features into a new frontend. It contains the pure Python logic (no Streamlit) and the JSON
API contract that the new frontend must implement against.

---

## Table of Contents

1. [Feature 1 — Analysis Terminal (OpenRouter Pipeline)](#feature-1)
2. [Feature 2 — Excel Extraction & Source-Traceability](#feature-2)
3. [Feature 3 — Highlighting & Provenance Engine](#feature-3)
4. [End-to-End Data Flow](#end-to-end-data-flow)

---

## Feature 1 — Analysis Terminal (OpenRouter Pipeline) {#feature-1}

### What it does

Accepts a natural-language due diligence question, retrieves the most relevant document pages via
**ColQwen2 visual embeddings** (ColPali / byaldi), and calls the **OpenRouter API** with a
multimodal prompt (page images + raw PDF text) to produce a deterministic, cited answer.

### Key invariants

- Temperature is fixed at `0.1` for near-deterministic output.
- At most `MAX_IMAGES_PER_CALL` (default 20) base64 images are sent; overflow chunks are
  passed as text-only to stay within token limits.
- Raw PDF text (`PyMuPDF`) is always the ground truth when present. The LLM is instructed to
  flag any value not found in the raw text with `⚠️ unverified`.
- For multi-document queries the LLM must reconcile conflicting values and emit a
  `## Row Reasoning` section after every Markdown table.

### Core code — `src/vector_store.py` · `query_document`

```python
def query_document(question: str, doc_name: str, n_results: int = 3) -> list[dict]:
    """Semantic search over visual page embeddings. Returns chunk dicts."""
    rag = _get_rag_for_doc(doc_name)  # loads ColQwen2 index from .byaldi/
    if rag is None:
        return []

    index_name = _index_name(doc_name)
    page_texts = _load_text_cache(index_name)  # pre-extracted PyMuPDF text

    if doc_name not in _pdf_path_cache:
        from src.extractor import find_pdf_path as _find_pdf
        _pdf_path_cache[doc_name] = _find_pdf(doc_name) or ""
    pdf_path: str = _pdf_path_cache[doc_name]

    results = rag.search(question, k=n_results, return_base64_results=True)

    chunks: list[dict] = []
    for r in results:
        if not r.base64:
            continue
        page_num = r.page_num
        chunks.append({
            "base64": r.base64,       # PNG of the page, base64-encoded
            "page_num": page_num,     # 1-indexed
            "score": r.score,         # ColPali similarity score
            "text": page_texts.get(page_num, ""),  # deterministic raw text
            "doc_name": doc_name,
            "pdf_path": pdf_path,
        })
    return chunks
```

### Core code — `src/llm.py` · `answer_with_citations`

```python
def answer_with_citations(
    question: str,
    chunks: list[dict],
    doc_name: str | None = None,
    doc_filter: list[str] | None = None,
) -> dict:
    """Answer a due diligence question from retrieved page images with raw-text cross-validation."""
    client = _get_client()  # OpenAI-compatible client pointed at openrouter.ai/api/v1

    # 1. Filter chunks to requested doc scope
    if doc_filter:
        chunks = [c for c in chunks if c.get("doc_name") in doc_filter]

    # 2. Cap images at MAX_IMAGES_PER_CALL, ranked by ColPali score
    _img_eligible = [i for i, c in enumerate(chunks) if c.get("base64")]
    _img_eligible.sort(key=lambda i: chunks[i].get("score", 0.0), reverse=True)
    _image_indices = set(_img_eligible[:MAX_IMAGES_PER_CALL])

    # 3. Build raw-text map (tries chunk.text first, then live PyMuPDF extraction)
    page_text_map: dict[int, str] = {}
    has_raw_text = False
    for c in chunks:
        page_num = c["page_num"]
        pre_text = c.get("text", "")
        if pre_text and pre_text.strip():
            has_raw_text = True
            page_text_map[page_num] = pre_text
            continue
        pdf_path = c.get("pdf_path") or find_pdf_path(c.get("doc_name", ""))
        if pdf_path:
            text = extract_page_text(pdf_path, page_num)
            if text and text.strip():
                has_raw_text = True
                page_text_map[page_num] = text

    # 4. Build multimodal content: one text block per chunk + image block for top-N
    content: list = []
    page_refs: list[int] = []
    doc_refs: list[str] = []
    for idx, c in enumerate(chunks):
        page_num = c["page_num"]
        c_doc = c.get("doc_name") or doc_name or "document"
        chunk_text = c.get("text") or page_text_map.get(page_num, "")
        send_image = bool(c.get("base64")) and idx in _image_indices

        heading = (
            f"[TEXT-ONLY · no image attached]\n===== Raw text from {c_doc} · Page {page_num} ====="
            if c.get("base64") and not send_image
            else f"===== Raw text from {c_doc} · Page {page_num} ====="
        )
        content.append({"type": "text", "text": f"{heading}\n{chunk_text}\n"})
        if send_image:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{c['base64']}"},
            })
            page_refs.append(page_num)
            doc_refs.append(c_doc)

    # 5. Compose prompt: analyst role + citation format + ground-truth instruction + question
    unique_docs = list(dict.fromkeys(c.get("doc_name") or doc_name or "document" for c in chunks))
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
        _QA_PROMPT                             # analyst persona + output structure rules
        + "\n\nCITATION FORMAT: " + cite_instruction
        + "\n\n" + _GROUND_TRUTH_INSTRUCTION   # raw-text ground-truth enforcement
        + f"\n\nShown pages: {', '.join(f'{d} p.{p}' for d, p in zip(doc_refs, page_refs))}."
        + f"\n\nQuestion: {question}"
    )

    # 6. Call OpenRouter
    response = client.chat.completions.create(
        model=OPENROUTER_MODEL,   # default: "anthropic/claude-sonnet-4.6"
        messages=[
            {"role": "system",
             "content": "You are a senior M&A due diligence analyst. Follow ALL instructions in the user message exactly."},
            {"role": "user", "content": [{"type": "text", "text": full_prompt}] + content},
        ],
        max_tokens=4096,
        temperature=0.1,
    )
    answer = response.choices[0].message.content or ""

    # 7. Post-process: flag unverified numbers when no raw text was available
    answer = _flag_unverified_table(answer, has_raw_text=has_raw_text)

    # 8. Parse citation pages from [Doc X · p.N] and legacy [Page N] patterns
    doc_cite_pages = [int(m) for m in re.findall(r'\[Doc [^\]·]+? · p\.(\d+)\]', answer)]
    legacy_pages   = [int(m) for m in re.findall(r'\[Page (\d+)\]', answer)]
    cited_pages = sorted(set(doc_cite_pages + legacy_pages))

    # 9. Run provenance resolution (Feature 3) against all enriched chunks
    enriched_chunks = [
        {**c, "text": c.get("text") or page_text_map.get(c["page_num"], "")}
        for c in chunks
    ]
    table_md = _extract_table_from_answer(answer)
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
        "source_chunks": chunks,
        "is_verified": has_raw_text,
    }
```

### Supporting helper — `_flag_unverified_table` (`src/llm.py`)

When `has_raw_text` is `False` (scanned PDF with no text layer), this function walks every
Markdown table in the LLM answer and appends ` ⚠️ unverified` to every data cell containing a
digit. It is a pure string transform applied **before** the result is returned to the caller.

```python
def _flag_unverified_table(answer: str, has_raw_text: bool) -> str:
    """Append ' ⚠️ unverified' to every numeric data cell when no raw ground-truth text exists."""
    if has_raw_text:
        return answer  # no-op when PDF text layer is present

    # State machine: OUTSIDE → SAW_HEADER → IN_BODY
    # Injects the ⚠️ marker into body rows only (not the header or separator line)
    ...  # full implementation in src/llm.py:107–171
```

### API Contract — Feature 1

**`POST /api/analyze`**

Request body:
```json
{
  "question": "Extract the 2023 depreciation schedule.",
  "doc_scope": ["klaviyo_s1.pdf"],
  "n_results": 2
}
```

| Field | Type | Description |
|---|---|---|
| `question` | `string` | Natural-language due diligence query |
| `doc_scope` | `string[]` | Document names to search; must match indexed `doc_name` values |
| `n_results` | `integer` | Chunks to retrieve per document (default: 2) |

Successful response (`200`):
```json
{
  "answer": "## Direct Answer\nDepreciation for 2023 was $4.2M [Doc klaviyo_s1.pdf · p.47]...\n\n| Category | 2023 | 2022 |\n|---|---|---|\n| Equipment | $4.2M | $3.8M |",
  "cited_pages": [47, 83],
  "is_verified": true,
  "row_pages": [47, 83],
  "row_docs": ["klaviyo_s1.pdf", "klaviyo_s1.pdf"],
  "row_reasoning": [
    "Equipment row sourced from audited balance sheet, p.47.",
    "Software row sourced from note 6, p.83."
  ],
  "highlight_terms_by_page": {
    "47": ["$4.2M", "Equipment"],
    "83": ["$3.8M", "Software"]
  },
  "provenance_cited_pages": [47, 83],
  "first_chunk_page": 47
}
```

| Field | Type | Notes |
|---|---|---|
| `answer` | `string` | Full LLM response, Markdown-formatted. May contain `⚠️ unverified` markers. |
| `cited_pages` | `int[]` | Pages extracted from `[Doc X · p.N]` citation patterns in the answer |
| `is_verified` | `boolean` | `false` when the PDF has no text layer (scanned-only). Frontend must display warning. |
| `row_pages` | `(int\|null)[]` | One entry per table data row — the source page number, or `null` if unresolved |
| `row_docs` | `(string\|null)[]` | Source doc name per table row, or `null` if unresolved |
| `row_reasoning` | `string[]` | LLM-generated reconciliation note per row (multi-doc) or `""` (single-doc) |
| `highlight_terms_by_page` | `{[page: string]: string[]}` | Deterministic search strings per page for the highlight engine |
| `provenance_cited_pages` | `int[]` | Sorted unique pages that have ≥1 provenance match (used for PDF auto-scroll) |
| `first_chunk_page` | `int\|null` | Fallback page if no citations were parsed |

Error response (`422`):
```json
{
  "error": "No relevant pages found.",
  "cited_pages": [],
  "is_verified": false
}
```

---

## Feature 2 — Excel Extraction & Source-Traceability {#feature-2}

### What it does

When the LLM response contains a Markdown pipe table, this feature:
1. Extracts the table from the answer string.
2. Appends three provenance columns: **Source Doc**, **Source Page**, and **Causality / Reasoning**.
3. Serialises to CSV for download.

The `Source Doc` and `Source Page` columns are populated **deterministically** by
`resolve_table_provenance` (Feature 3). The `Causality / Reasoning` column is the LLM-generated
per-row explanation from the `## Row Reasoning` section.

### Core code — `app.py` · `_markdown_table_to_csv`

```python
def _markdown_table_to_csv(
    table_md: str,
    row_pages: list[int | None] | None = None,
    row_docs: list[str | None] | None = None,
    row_reasoning: list[str] | None = None,
) -> str:
    """Convert a Markdown pipe table to CSV with three appended provenance columns.

    Column order appended after the LLM data columns:
      1. Source Doc       ← row_docs      (None → "Unresolved")
      2. Source Page      ← row_pages     (None → "Unresolved")
      3. Causality / Reasoning ← row_reasoning ("" if absent)
    """
    # 1. Parse all non-separator pipe rows into a list of cell lists
    rows = []
    for line in table_md.strip().split("\n"):
        if re.match(r"^[\|\s\-:]+$", line.strip()):
            continue
        cells = [c.strip() for c in line.split("|") if c.strip() != ""]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return ""

    # 2. Pad ragged rows to the same column count
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    # 3. Append provenance columns
    has_extras = row_docs is not None or row_pages is not None or row_reasoning is not None
    if has_extras:
        rows[0] = rows[0] + ["Source Doc", "Source Page", "Causality / Reasoning"]
        for i, row in enumerate(rows[1:], 0):
            doc_str    = str(row_docs[i])    if row_docs    and i < len(row_docs)    and row_docs[i]    is not None else "Unresolved"
            page_str   = str(row_pages[i])   if row_pages   and i < len(row_pages)   and row_pages[i]   is not None else "Unresolved"
            reason_str = (row_reasoning[i]   if row_reasoning and i < len(row_reasoning) else "") or ""
            rows[i + 1] = row + [doc_str, page_str, reason_str]

    # 4. Convert to CSV via pandas
    df = pd.DataFrame(rows[1:], columns=rows[0])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()
```

### Core code — `src/llm.py` · `_extract_row_reasoning`

This function parses the `## Row Reasoning` section that the LLM emits after every Markdown table
in multi-document mode. It extracts one reasoning string per data row.

```python
def _extract_row_reasoning(answer: str, num_rows: int) -> list[str]:
    """Parse per-row reasoning from a '## Row Reasoning' section emitted by the LLM."""
    m = re.search(r'##\s*Row Reasoning\s*\n(.*?)(?=\n##|\Z)', answer, re.DOTALL)
    if not m:
        return [""] * num_rows
    section = m.group(1)
    # Each entry must match: "1. Label: reasoning text"
    entries = re.findall(r'^\d+\.\s*.+?:\s*(.+)$', section, re.MULTILINE)
    result = list(entries[:num_rows])
    result.extend([""] * (num_rows - len(result)))
    return result
```

### Core code — `src/provenance.py` · `_extract_table_from_answer`

```python
def _extract_table_from_answer(answer: str) -> str | None:
    """Return the first complete Markdown pipe table block in the answer text, or None.
    Requires ≥3 pipe rows (header + separator + ≥1 data row).
    """
    lines = answer.split("\n")
    table_lines: list[str] = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2:
            in_table = True
            table_lines.append(stripped)
        elif in_table:
            break
    return "\n".join(table_lines) if len(table_lines) >= 3 else None
```

### API Contract — Feature 2

**`POST /api/export-table`**

Request body:
```json
{
  "answer": "## Direct Answer\n...\n| Category | 2023 | 2022 |\n|---|---|---|\n| Equipment | $4.2M | $3.8M |",
  "row_pages": [47, 83],
  "row_docs": ["klaviyo_s1.pdf", "klaviyo_s1.pdf"],
  "row_reasoning": [
    "Equipment row sourced from audited balance sheet, p.47.",
    "Software row sourced from note 6, p.83."
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `answer` | `string` | Full LLM answer (same string returned by `/api/analyze`) |
| `row_pages` | `(int\|null)[]` | From `/api/analyze` response — source page per data row |
| `row_docs` | `(string\|null)[]` | From `/api/analyze` response — source doc per data row |
| `row_reasoning` | `string[]` | From `/api/analyze` response — LLM reasoning per row |

Successful response (`200`):
```json
{
  "csv_data": "Category,2023,2022,Source Doc,Source Page,Causality / Reasoning\nEquipment,$4.2M,$3.8M,klaviyo_s1.pdf,47,Equipment row sourced from audited balance sheet p.47.\n",
  "filename": "table_p47.csv",
  "row_count": 1,
  "has_unresolved": false
}
```

| Field | Type | Notes |
|---|---|---|
| `csv_data` | `string` | UTF-8 CSV content, ready for `Content-Disposition: attachment` |
| `filename` | `string` | Suggested filename — use the first cited page number |
| `row_count` | `integer` | Number of data rows (excluding header) |
| `has_unresolved` | `boolean` | `true` if any `Source Page` is "Unresolved" — frontend should warn the user |

---

## Feature 3 — Highlighting & Provenance Engine {#feature-3}

### What it does

Given a Markdown table extracted from the LLM answer, this engine:
1. Parses each data row into individual cell values.
2. Generates **format-invariant search variants** for each cell (strips `$`, normalises
   comma-separators, handles `(negative)` ↔ `-negative` forms, etc.).
3. Scans raw PDF text chunks to find which page contains the values for each row.
4. Passes the matched variant strings to **PyMuPDF** (`fitz.search_for`) to locate exact
   bounding boxes on the page and render a highlighted PNG.

**Critical design constraint:** Source page assignment is fully deterministic — it is derived
from raw PDF text only, never from LLM output. A row that cannot be matched in any chunk gets
`null`, not a guess.

### Core code — `src/provenance.py` · `_numeric_variants`

```python
def _numeric_variants(s: str) -> list[str]:
    """Generate format-invariant search variants for a single table cell value.

    Covers: currency prefix ($€£¥), thousand-separator commas,
    parentheses-negative ↔ minus-negative, trailing decimal zeros, and casefold.
    """
    s = s.strip()
    if not s:
        return []

    seen: set[str] = set()
    out: list[str] = []

    def push(v: str) -> None:
        v = v.strip()
        if v and v not in seen:
            seen.add(v); out.append(v)

    push(s)
    push(s.casefold())

    nc = re.sub(r'^[$€£¥]\s*', '', s)
    push(nc)

    paren_m = re.match(r'^\((.+)\)$', nc)
    if paren_m:
        inner = re.sub(r'^[$€£¥]\s*', '', paren_m.group(1))
        sign_forms = [f'({inner})', f'-{inner}', inner]
    elif nc.startswith('-'):
        inner = nc[1:]
        sign_forms = [f'-{inner}', f'({inner})', inner]
    else:
        sign_forms = [nc]

    for form in sign_forms:
        push(form)
        push(re.sub(r',', '', form))                 # strip thousand-separators
        no_trail = re.sub(r'\.0+$', '', form)
        push(no_trail)
        push(re.sub(r',', '', no_trail))

    return out
```

### Core code — `src/provenance.py` · `resolve_table_provenance`

```python
def resolve_table_provenance(table_md: str, chunks: list[dict]) -> dict:
    """Match each table data row to the chunk page containing its cell values.

    Returns:
        row_pages:               list[int | None]         — source page per row (None = unresolved)
        row_docs:                list[str | None]         — source doc_name per row
        highlight_terms_by_page: dict[int, list[str]]    — matched strings per page for PyMuPDF
        cited_pages:             list[int]               — sorted pages with ≥1 match
    """
    data_rows = _parse_table_data_rows(table_md)  # skips header + separator rows

    row_pages: list[int | None] = []
    row_docs: list[str | None] = []
    highlight_terms_by_page: dict[int, list[str]] = {}

    for row in data_rows:
        cell_variant_sets = [_numeric_variants(cell) for cell in row if cell.strip()]

        if not cell_variant_sets:
            row_pages.append(None); row_docs.append(None); continue

        matched_page: int | None = None
        matched_doc: str | None = None
        matched_variants: list[str] = []

        for chunk in chunks:
            chunk_text = chunk.get("text", "")
            if not chunk_text:
                continue
            page_num = chunk.get("page_num")
            if page_num is None:
                continue

            found: list[str] = []
            for variants in cell_variant_sets:
                for v in variants:
                    if v and v in chunk_text:
                        found.append(v)
                        break  # one variant per cell is sufficient

            if found:
                matched_page = int(page_num)
                matched_doc = chunk.get("doc_name")
                matched_variants = found
                break  # first chunk match wins — deterministic

        row_pages.append(matched_page)
        row_docs.append(matched_doc)

        if matched_page is not None:
            bucket = highlight_terms_by_page.setdefault(matched_page, [])
            existing = set(bucket)
            for v in matched_variants:
                if v not in existing:
                    bucket.append(v); existing.add(v)

    return {
        "row_pages": row_pages,
        "row_docs": row_docs,
        "highlight_terms_by_page": highlight_terms_by_page,
        "cited_pages": sorted(highlight_terms_by_page.keys()),
    }
```

### Core code — `src/extractor.py` · `render_page_with_highlights`

This is the PyMuPDF ground-truth renderer. The new frontend calls this to get a highlighted PNG
for any page the provenance engine matched.

```python
def render_page_with_highlights(
    pdf_path: str, page_num: int, search_terms: list[str]
) -> tuple[bytes, int]:
    """Render a PDF page to PNG with yellow highlight annotations for matched terms.

    Uses fitz.search_for (text-layer search) per term. Terms not found are silently skipped.
    Returns (png_bytes, total_quad_count); returns (b'', 0) on any failure.
    """
    try:
        with fitz.open(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                return b"", 0
            page = doc[idx]
            total_quads = 0
            for term in search_terms:
                if not term.strip():
                    continue
                try:
                    quads = page.search_for(term)   # returns list of fitz.Quad
                    if quads:
                        page.add_highlight_annot(quads)
                        total_quads += len(quads)
                except Exception:
                    pass
            pix = page.get_pixmap(dpi=150)          # 150 DPI for crisp display
            return pix.tobytes("png"), total_quads
    except Exception:
        return b"", 0
```

### Core code — `src/extractor.py` · `render_thumbnail`

Lower-resolution (50 DPI) variant for mini-previews in a source panel or citation chip.

```python
def render_thumbnail(pdf_path: str, page_num: int, search_terms: list[str]) -> bytes:
    """Render a page at 50 DPI with highlight annotations. Returns PNG bytes or b'' on failure."""
    try:
        with fitz.open(pdf_path) as doc:
            idx = page_num - 1
            if idx < 0 or idx >= len(doc):
                return b""
            page = doc[idx]
            for term in search_terms:
                if not term.strip():
                    continue
                try:
                    quads = page.search_for(term)
                    if quads:
                        page.add_highlight_annot(quads)
                except Exception:
                    pass
            pix = page.get_pixmap(dpi=50)
            return pix.tobytes("png")
    except Exception:
        return b""
```

### API Contract — Feature 3

**`POST /api/highlight-page`** — full-resolution highlighted page

Request body:
```json
{
  "doc_name": "klaviyo_s1.pdf",
  "page_num": 47,
  "search_terms": ["$4.2M", "Equipment", "4,200"]
}
```

| Field | Type | Description |
|---|---|---|
| `doc_name` | `string` | Document name (used to resolve the PDF path on disk) |
| `page_num` | `integer` | 1-indexed page number |
| `search_terms` | `string[]` | Matched variant strings from `highlight_terms_by_page[page_num]` |

Successful response (`200`):
```json
{
  "page_png_b64": "<base64-encoded PNG at 150 DPI>",
  "quad_count": 3,
  "page_num": 47,
  "doc_name": "klaviyo_s1.pdf"
}
```

| Field | Type | Notes |
|---|---|---|
| `page_png_b64` | `string` | Base64 PNG. Use as `<img src="data:image/png;base64,{value}">` |
| `quad_count` | `integer` | Number of highlighted bounding boxes. `0` means no terms were found on the text layer (page may be image-only). |

**`POST /api/highlight-thumbnail`** — 50 DPI mini-preview

Same request shape as above. Response:
```json
{
  "thumbnail_png_b64": "<base64-encoded PNG at 50 DPI>",
  "page_num": 47
}
```

**`POST /api/page-text`** — raw PyMuPDF text for a page (used for client-side verification)

Request body:
```json
{
  "doc_name": "klaviyo_s1.pdf",
  "page_num": 47
}
```

Response:
```json
{
  "text": "Equipment depreciation schedule...\n$4,200,000\n...",
  "has_text_layer": true
}
```

---

## End-to-End Data Flow

The following diagram shows how the three features connect on a single user query.

```
Frontend                    Backend
─────────                   ───────

User types question
        │
        ▼
POST /api/analyze ──────────► query_document()         [Feature 1]
  { question,                  ColQwen2 visual search
    doc_scope,                 returns: chunks[]
    n_results }                     │
                                    ▼
                             answer_with_citations()    [Feature 1]
                               builds multimodal prompt
                               calls OpenRouter API
                               parses [Doc X · p.N]
                                    │
                                    ├──► resolve_table_provenance()  [Feature 3]
                                    │      matches table rows → pages
                                    │      produces highlight_terms_by_page
                                    │
                                    ▼
◄──────────────────────────  Response JSON
  { answer,                   (cited_pages, row_pages,
    is_verified, ...}          row_docs, row_reasoning,
                               highlight_terms_by_page )

        │
        ├── Render answer Markdown with citation nav buttons
        │
        ├── If is_verified == false → show ⚠️ SCANNED DOCUMENT warning
        │
        ├── If answer contains table:
        │       │
        │       ├── POST /api/export-table ──► _markdown_table_to_csv()  [Feature 2]
        │       │     { answer, row_pages,       appends Source Doc,
        │       │       row_docs,                Source Page,
        │       │       row_reasoning }          Causality/Reasoning
        │       │   ◄── { csv_data, filename }
        │       │
        │       └── For each page in highlight_terms_by_page:
        │               POST /api/highlight-page ──► render_page_with_highlights()  [Feature 3]
        │                 { doc_name, page_num,         PyMuPDF search_for + annot
        │                   search_terms }              returns PNG at 150 DPI
        │               ◄── { page_png_b64, quad_count }
        │
        └── Auto-scroll PDF viewer to provenance_cited_pages[0]
              (or cited_pages[0], or first_chunk_page as fallback)
```

### ⚠️ Unverified flag — frontend responsibilities

| Condition | `is_verified` | Required UI behaviour |
|---|---|---|
| PDF has a text layer | `true` | Normal display |
| Scanned PDF, no text layer | `false` | **Must** display a persistent warning banner: "⚠️ SCANNED DOCUMENT DETECTED — Cross-validation disabled. Numbers may contain AI hallucinations. Manual verification required." |
| Individual table cells contain ` ⚠️ unverified` | (either) | Render the marker inline as a warning chip; do not strip it from the CSV |

### Page navigation priority

When auto-scrolling the PDF viewer after a query, use this fallback chain:

```
1. provenance_cited_pages[0]   ← deterministic, highest confidence
2. cited_pages[0]              ← LLM-parsed citation
3. first_chunk_page            ← ColPali top-ranked chunk
```
