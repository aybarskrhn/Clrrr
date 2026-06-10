"""AI extraction service using Gemini 2.5 Flash via Google AI SDK
and Claude Sonnet 4.6 via OpenRouter for the analyst Q&A pipeline."""
import base64
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-6")

EXTRACTION_SYSTEM_PROMPT = """You are a senior M&A due diligence analyst at a boutique investment bank. \
Your job is to forensically analyze financial PDFs (balance sheets, income statements, contracts, \
LOIs, NDAs, audit reports, cap tables) and extract perfectly structured data for junior analysts.

You MUST respond with ONLY valid JSON. No markdown, no commentary, no code fences.

JSON schema you must follow exactly:
{
  "document_type": "balance_sheet | income_statement | cash_flow | contract | loi | nda | cap_table | audit_report | other",
  "summary": "2-3 sentence executive summary of this document",
  "financial_metrics": [
    {"label": "Total Revenue", "value": "$42.3M", "period": "FY2024", "notes": "YoY +12%"}
  ],
  "key_terms": [
    {"label": "Governing Law", "value": "Delaware", "notes": ""}
  ],
  "red_flags": [
    {"severity": "high | medium | low", "title": "Short concise title", "description": "What an analyst must investigate", "page": 3}
  ],
  "parties": ["Acme Corp", "Buyer Holdings LLC"],
  "confidence": 0.88
}

Rules:
- financial_metrics: include AT LEAST 4 items if the document contains financial data
- red_flags: surface unusual concentrations, off-balance liabilities, going-concern notes, related-party deals, weak covenants, missing disclosures, customer concentration, declining margins
- Be specific. Use real numbers from the document. Never fabricate.
- If the document has no financial data, leave financial_metrics empty.
- confidence is your honest 0.0-1.0 estimate of extraction quality.
"""

ROLLUP_SYSTEM_PROMPT = """You are a senior M&A managing director writing an IC (investment committee) \
roll-up memo across multiple due diligence documents for a single deal. \
You will be given the extracted JSON from each document. Synthesize them.

Respond with ONLY valid JSON. No markdown, no commentary.

Schema:
{
  "executive_summary": "3-5 sentence summary suitable for the top of an IC memo",
  "recommendation": "proceed | proceed_with_caution | pass",
  "recommendation_rationale": "1-2 sentence justification",
  "consolidated_financials": [
    {"label": "Revenue", "value": "$42.3M", "period": "FY2024", "source": "audit_report.pdf"}
  ],
  "top_red_flags": [
    {"severity": "high|medium|low", "title": "short title", "description": "1 sentence", "source": "audit_report.pdf"}
  ],
  "diligence_gaps": ["What documents or data we still need"],
  "next_steps": ["Specific analyst action items"]
}

Rules:
- top_red_flags: at most 7, ranked by severity then importance
- consolidated_financials: dedupe across documents, prefer the most recent period
- Be terse. This is for senior partners. Numbers, not adjectives.
"""


def _get_client() -> genai.Client:
    if not GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. "
            "Get a free key at https://aistudio.google.com/apikey and add it to backend/.env"
        )
    return genai.Client(api_key=GOOGLE_API_KEY)


def _strip_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _repair_json(s: str) -> str:
    """Best-effort repair for common LLM JSON glitches.

    Handles: trailing commas before } or ], single-quoted keys, NaN/Infinity,
    smart quotes, stray control chars, and unterminated strings at the tail
    (truncation due to max_tokens).
    """
    # Strip control chars except \n \t \r
    s = "".join(ch for ch in s if ch >= " " or ch in "\n\t\r")
    # Smart quotes → ASCII
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    # Trailing commas before closing brackets
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    # NaN / Infinity → null
    s = re.sub(r"\bNaN\b|\b-?Infinity\b", "null", s)
    return s


def _balance_brackets(s: str) -> str:
    """If the JSON was truncated mid-structure, append missing } and ] in correct order."""
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    if in_str:
        s += '"'
    while stack:
        s += "}" if stack.pop() == "{" else "]"
    return s


def _parse_json(raw: str) -> dict:
    cleaned = _strip_json(raw)
    # 1) straight parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # 2) extract widest {...} envelope
    match = re.search(r"\{[\s\S]*\}", cleaned)
    candidate = match.group(0) if match else cleaned
    # 3) repair common LLM glitches
    repaired = _repair_json(candidate)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass
    # 4) balance truncated brackets/strings (typical max_tokens cutoff)
    balanced = _balance_brackets(_repair_json(candidate))
    try:
        return json.loads(balanced)
    except json.JSONDecodeError as e:
        logger.error(
            "JSON parse failed after repair attempts (len=%d, head=%r, tail=%r)",
            len(candidate), candidate[:200], candidate[-200:],
        )
        raise RuntimeError(
            f"LLM returned malformed JSON that could not be repaired: {e}. "
            "Likely a truncated response — consider raising max_tokens or splitting the PDF."
        ) from e


def _openrouter_client() -> AsyncOpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set in backend/.env. Required for Claude Sonnet pipelines."
        )
    return AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": os.environ.get("PUBLIC_APP_URL", "https://clearvault.app"),
            "X-Title": "ClearVault",
        },
    )


async def extract_pdf(file_path: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Send PDF to Claude Sonnet 4.6 via OpenRouter and return structured extraction dict."""
    client = _openrouter_client()
    used_model = model or OPENROUTER_MODEL

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()
    b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
    filename = os.path.basename(file_path)

    completion = await client.chat.completions.create(
        model=used_model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": filename,
                            "file_data": f"data:application/pdf;base64,{b64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analyze the attached PDF as an M&A due diligence document and respond "
                            "with the strict JSON schema described in your instructions. "
                            "Return ONLY raw JSON — no markdown fences, no commentary, no trailing "
                            "commas. Cap each free-text field at ~200 chars and keep arrays ≤12 items "
                            "so the response fits in 8000 output tokens."
                        ),
                    },
                ],
            },
        ],
        temperature=0.1,
        max_tokens=8000,
        extra_body={
            "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
        },
    )

    raw = completion.choices[0].message.content or ""
    logger.info("AI extraction [%s] raw length=%s", used_model, len(raw))
    data = _parse_json(raw)

    data.setdefault("document_type", "other")
    data.setdefault("summary", "")
    data.setdefault("financial_metrics", [])
    data.setdefault("key_terms", [])
    data.setdefault("red_flags", [])
    data.setdefault("parties", [])
    data.setdefault("confidence", 0.8)
    return data


async def summarize_deal(
    deal_name: str, target_company: str, sector: str, documents: list,
    model: Optional[str] = None,
) -> dict:
    """Produce a roll-up IC memo via Claude Sonnet 4.6 (OpenRouter)."""
    client = _openrouter_client()
    used_model = model or OPENROUTER_MODEL

    payload = {
        "deal_name": deal_name,
        "target_company": target_company,
        "sector": sector,
        "documents": documents,
    }
    user_text = (
        "Synthesize an IC roll-up across these extracted M&A documents. Respond JSON only.\n\n"
        + json.dumps(payload, indent=2)[:60000]
    )

    completion = await client.chat.completions.create(
        model=used_model,
        messages=[
            {"role": "system", "content": ROLLUP_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0.1,
        max_tokens=4096,
    )

    raw = completion.choices[0].message.content or ""
    logger.info("Rollup [%s] raw length=%s", used_model, len(raw))
    data = _parse_json(raw)

    data.setdefault("executive_summary", "")
    data.setdefault("recommendation", "proceed_with_caution")
    data.setdefault("recommendation_rationale", "")
    data.setdefault("consolidated_financials", [])
    data.setdefault("top_red_flags", [])
    data.setdefault("diligence_gaps", [])
    data.setdefault("next_steps", [])
    return data


# =============================================================
# Analyst Q&A — direct multi-PDF question answering with Gemini
# =============================================================

QA_SYSTEM_PROMPT = """You are a senior M&A due diligence analyst answering an analyst's
question against one or more attached PDF documents.

OUTPUT FORMAT:
1. Begin with `## Direct Answer` — a 1–3 sentence direct response with inline citations.
2. When the answer contains tabular data, render a Markdown pipe table.
3. End with `## Caveats` if any qualifications apply.
4. If a Markdown table is present, append a `## Row Reasoning` section with one numbered
   bullet per data row in the form: `1. [row label]: [one-sentence reasoning]`.

CITATION FORMAT (MANDATORY):
- Cite every factual claim using `[Doc <LABEL> · p.<N>]` where <LABEL> is exactly the
  label assigned to each PDF in the user message (e.g. `1`, `2`, ...), and <N> is the
  1-based page number in that PDF.
- Every numeric value, every named figure, and every table row MUST carry a citation.

GROUND TRUTH:
- The attached PDFs are the only source. Do NOT invent numbers. If a value is not
  visible in the attached PDFs, write `not disclosed` instead of guessing.
- Be terse. Numbers, not adjectives."""


async def answer_question_with_pdf(
    question: str,
    pdf_paths: List[str],
    context: Optional[str] = None,
    doc_labels: Optional[List[str]] = None,
    model: Optional[str] = None,
) -> str:
    """Answer `question` by sending the listed PDFs to Claude Sonnet 4.6 via OpenRouter.

    Claude is more deterministic for M&A table extraction + structured citation work
    than Gemini Flash. Returns the raw Markdown answer string with `[Doc <label> · p.N]`
    citations. Caller is responsible for parsing citations out of the returned text.
    """
    if not pdf_paths:
        raise ValueError("answer_question_with_pdf: pdf_paths is empty")
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set in backend/.env. Required for the Claude "
            "Sonnet analyst Q&A pipeline."
        )

    if doc_labels is None:
        doc_labels = [str(i + 1) for i in range(len(pdf_paths))]
    if len(doc_labels) != len(pdf_paths):
        raise ValueError("answer_question_with_pdf: doc_labels length mismatch")

    user_content: list[dict] = []
    label_lines: list[str] = []
    for label, path in zip(doc_labels, pdf_paths):
        try:
            with open(path, "rb") as f:
                pdf_bytes = f.read()
        except FileNotFoundError:
            logger.warning("answer_question_with_pdf: missing file %s", path)
            continue
        b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")
        filename = os.path.basename(path)
        # OpenAI-compatible PDF file part — OpenRouter routes this to Anthropic's
        # native document content block for Claude models.
        user_content.append({
            "type": "file",
            "file": {
                "filename": filename,
                "file_data": f"data:application/pdf;base64,{b64}",
            },
        })
        label_lines.append(f"- Doc {label} = {filename}")

    if not user_content:
        raise FileNotFoundError("answer_question_with_pdf: no readable PDFs found")

    header = (
        "DOCUMENT LABELS (use these exact labels in every citation):\n"
        + "\n".join(label_lines)
    )
    if context:
        header += f"\n\nDEAL CONTEXT:\n{context.strip()}"
    user_content.append({
        "type": "text",
        "text": f"{header}\n\nQUESTION:\n{question.strip()}",
    })

    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": os.environ.get("PUBLIC_APP_URL", "https://clearvault.app"),
            "X-Title": "ClearVault Analysis Terminal",
        },
    )

    used_model = model or OPENROUTER_MODEL
    completion = await client.chat.completions.create(
        model=used_model,
        messages=[
            {"role": "system", "content": QA_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.1,
        max_tokens=4096,
        # Anthropic-specific PDF parsing hint via OpenRouter passthrough.
        extra_body={
            "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}],
        },
    )
    answer = (completion.choices[0].message.content or "").strip()
    logger.info(
        "answer_question_with_pdf [%s]: docs=%d answer_len=%d",
        used_model,
        len(user_content) - 1,
        len(answer),
    )
    return answer
