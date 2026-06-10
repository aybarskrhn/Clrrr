# ClearVault — PRD

## Problem
Junior M&A analysts at boutique investment banks waste full weekends on unstructured PDF data-room
auditing. Enterprise AI tools are priced for whales; public LLMs leak confidential data.

## Solution
ClearVault — a no-code, drag-and-drop AI auditor for M&A due diligence. Drop a PDF, get structured
financials + severity-ranked red flags in <90 seconds.

## Personas
- Primary: Junior M&A analysts at boutique IBs / PE firms.
- Secondary: VP / Principal supervising the analyst.

## Implemented (1st cut, Feb 2026)
- JWT auth (signup, login, me)
- Deals CRUD with stats aggregation (docs count, red flag count)
- PDF upload with background AI extraction (Gemini 2.5 Flash via emergentintegrations)
- Structured extraction schema: financial_metrics, key_terms, red_flags, parties, confidence
- Dashboard with KPI stats, deal book table, recent activity ticker
- Bloomberg-terminal landing page (hero, features, security, pricing)
- Auth pages, Dashboard, Deals list, Deal detail w/ extraction viewer, Upload ingest page
- Blue visual identity (orange → blue theme + logo placeholder, Feb 2026)
- Analysis Terminal `/api/analyze` powered by Claude Sonnet 4.6 via OpenRouter (PDF
  inline parsing + citation extraction `[Doc <label> · p.N]`, Feb 2026)
- DealDetail state-loop fix: eliminated infinite refresh that caused PDF carousel glitch
  + broken viewer + broken delete (Feb 2026)

## Backlog (P0/P1)
- P0: Excel/CSV export of extracted financials
- P1: Multi-document deal summary roll-up
- P1: Command palette (cmd+k) wired to search across deals/docs/flags
- P1: Page-level PDF preview with annotation overlay
- P2: SAML SSO, on-prem deployment guide
- P2: Slack notifications when extraction completes
