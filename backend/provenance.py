"""Feature 3 — Highlighting & Provenance Engine (deterministic).

Source page assignment is derived from raw PDF text only, never from LLM output.
A row that cannot be matched in any chunk gets `null`, not a guess.
"""
from __future__ import annotations

import re
from typing import Optional


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
            seen.add(v)
            out.append(v)

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
        push(re.sub(r',', '', form))  # strip thousand-separators
        no_trail = re.sub(r'\.0+$', '', form)
        push(no_trail)
        push(re.sub(r',', '', no_trail))

    return out


def _parse_table_data_rows(table_md: str) -> list[list[str]]:
    """Return list of data-row cell lists (header + separator stripped)."""
    rows: list[list[str]] = []
    for line in table_md.strip().split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # skip separator lines like |---|---|
        if re.match(r"^[\|\s\-:]+$", stripped):
            continue
        cells = [c.strip() for c in stripped.split("|") if c.strip() != ""]
        if cells:
            rows.append(cells)
    # First non-separator row is the header → drop it
    return rows[1:] if len(rows) > 1 else []


def extract_table_from_answer(answer: str) -> Optional[str]:
    """Return the first complete Markdown pipe table block in the answer text, or None.
    Requires >=3 pipe rows (header + separator + >=1 data row).
    """
    if not answer:
        return None
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


def resolve_table_provenance(table_md: str, chunks: list[dict]) -> dict:
    """Match each table data row to the chunk page containing its cell values.

    Returns:
      row_pages: list[int | None]
      row_docs: list[str | None]
      highlight_terms_by_page: dict[int, list[str]]
      cited_pages: list[int]
    """
    data_rows = _parse_table_data_rows(table_md or "")

    row_pages: list[Optional[int]] = []
    row_docs: list[Optional[str]] = []
    highlight_terms_by_page: dict[int, list[str]] = {}

    for row in data_rows:
        cell_variant_sets = [_numeric_variants(cell) for cell in row if cell.strip()]
        if not cell_variant_sets:
            row_pages.append(None)
            row_docs.append(None)
            continue

        matched_page: Optional[int] = None
        matched_doc: Optional[str] = None
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
                        break  # one variant per cell is enough

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
                    bucket.append(v)
                    existing.add(v)

    return {
        "row_pages": row_pages,
        "row_docs": row_docs,
        "highlight_terms_by_page": {str(k): v for k, v in highlight_terms_by_page.items()},
        "cited_pages": sorted(highlight_terms_by_page.keys()),
    }
