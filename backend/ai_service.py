"""AI extraction service using Gemini 2.5 Flash via Google AI SDK."""
import json
import logging
import os
import re
from typing import Any, Dict

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"

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
    """Send PDF to Gemini 2.5 Flash and return structured extraction dict."""
    client = _get_client()

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    response = await client.aio.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(inline_data=types.Blob(data=pdf_bytes, mime_type="application/pdf")),
                    types.Part(text=(
                        "Analyze the attached PDF as an M&A due diligence document and respond "
                        "with the strict JSON schema described in your instructions. JSON only."
                    )),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
        ),
    )

    raw = response.text
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

    response = await client.aio.models.generate_content(
        model=model,
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=ROLLUP_SYSTEM_PROMPT,
        ),
    )

    raw = response.text
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
