"""AI extraction service powered by Gemini via emergentintegrations.

Gemini supports native PDF file attachments. We send the PDF to the model
with a strict JSON schema prompt and parse the response.
"""
import json
import logging
import os
import re
import uuid
from typing import Any, Dict

from emergentintegrations.llm.chat import FileContentWithMimeType, LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

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


def _strip_json(raw: str) -> str:
    """Remove markdown code fences if model added them."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def extract_pdf(file_path: str, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """Send PDF to Gemini and return structured extraction dict."""
    if not EMERGENT_LLM_KEY:
        raise RuntimeError("EMERGENT_LLM_KEY is not configured")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"extract-{uuid.uuid4()}",
        system_message=EXTRACTION_SYSTEM_PROMPT,
    ).with_model("gemini", model)

    pdf_file = FileContentWithMimeType(file_path=file_path, mime_type="application/pdf")
    user_msg = UserMessage(
        text=(
            "Analyze the attached PDF as an M&A due diligence document and respond with the strict "
            "JSON schema described in your instructions. JSON only."
        ),
        file_contents=[pdf_file],
    )

    raw = await chat.send_message(user_msg)
    logger.info("AI extraction raw length=%s", len(raw or ""))
    cleaned = _strip_json(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # try to grab the largest JSON object substring
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise
        data = json.loads(match.group(0))

    # Light normalization with sane defaults so the frontend never explodes
    data.setdefault("document_type", "other")
    data.setdefault("summary", "")
    data.setdefault("financial_metrics", [])
    data.setdefault("key_terms", [])
    data.setdefault("red_flags", [])
    data.setdefault("parties", [])
    data.setdefault("confidence", 0.8)
    return data
