"""AI extraction service — OpenRouter (extract/rollup) + Gemini 2.5 Flash (analysis)."""
import base64
import json
import logging
import os
import re
from typing import Any, Dict

from google import genai
from google.genai import types
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-6")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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


def _get_client() -> AsyncOpenAI:
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to backend/.env"
        )
    return AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )


def _get_gemini_client() -> genai.Client:
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set. Add it to backend/.env")
    return genai.Client(api_key=GOOGLE_API_KEY)


ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior M&A due diligence analyst. "
    "Answer the analyst's question using ONLY the attached PDF document(s). "
    "For every factual claim, cite the source with [Doc {filename} · p.{page}]. "
    "If the answer is not in the documents, say so explicitly and list which "
    "pages you checked. NEVER fabricate values or page numbers. If the question "
    "references a specific page, describe what is actually on that page."
)


async def answer_question_with_pdf(
    question: str,
    doc_file_paths: list[str],
    deal_context: dict | None = None,
) -> dict:
    """Send PDFs + question to Gemini 2.5 Flash and get a cited answer."""
    client = _get_gemini_client()

    parts = []
    for path in doc_file_paths:
        with open(path, "rb") as f:
            parts.append(types.Part(
                inline_data=types.Blob(
                    data=f.read(),
                    mime_type="application/pdf",
                )
            ))
    parts.append(types.Part(text=(
        f"Question: {question}\n\n"
        "Answer using ONLY the attached PDFs. Cite every factual claim "
        "with [Doc {filename} · p.{page}]. If not found, state so and "
        "list which pages you searched. Never fabricate."
    )))

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            system_instruction=ANALYSIS_SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )
    return {
        "answer": response.text or "",
        "model": GEMINI_MODEL,
        "docs_attached": [os.path.basename(p) for p in doc_file_paths],
    }


def _strip_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _parse_json(raw: str) -> dict:
    cleaned = _strip_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        return json.loads(match.group(0))


async def extract_pdf(file_path: str, model: str = MODEL) -> Dict[str, Any]:
    """Send PDF to Claude via OpenRouter and return structured extraction dict."""
    client = _get_client()

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analyze the attached PDF as an M&A due diligence document and respond "
                            "with the strict JSON schema described in your instructions. JSON only."
                        ),
                    },
                ],
            },
        ],
    )

    raw = response.choices[0].message.content
    logger.info("AI extraction raw length=%s", len(raw or ""))
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
    deal_name: str, target_company: str, sector: str, documents: list, model: str = MODEL
) -> dict:
    """Produce a roll-up IC memo across multiple extracted documents."""
    client = _get_client()

    payload = {
        "deal_name": deal_name,
        "target_company": target_company,
        "sector": sector,
        "documents": documents,
    }
    text = (
        "Synthesize an IC roll-up across these extracted M&A documents. Respond JSON only.\n\n"
        + json.dumps(payload, indent=2)[:60000]
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ROLLUP_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    )

    raw = response.choices[0].message.content
    logger.info("Rollup raw length=%s", len(raw or ""))
    data = _parse_json(raw)

    data.setdefault("executive_summary", "")
    data.setdefault("recommendation", "proceed_with_caution")
    data.setdefault("recommendation_rationale", "")
    data.setdefault("consolidated_financials", [])
    data.setdefault("top_red_flags", [])
    data.setdefault("diligence_gaps", [])
    data.setdefault("next_steps", [])
    return data
