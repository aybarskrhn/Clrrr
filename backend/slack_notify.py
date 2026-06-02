"""Slack incoming-webhook notifier for ClearVault.

Users configure their own Slack incoming webhook URL in settings; we POST a
formatted block message when an extraction completes.
"""
import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


async def notify_extraction_complete(
    webhook_url: Optional[str],
    *,
    deal_name: str,
    target_company: str,
    filename: str,
    summary: str,
    red_flags: list,
    high_count: int,
    app_url: Optional[str] = None,
    deal_id: Optional[str] = None,
) -> None:
    """Fire-and-forget Slack notification. Failures are logged, never raised."""
    if not webhook_url:
        return
    if not webhook_url.startswith("https://hooks.slack.com/"):
        logger.warning("Refusing to POST to non-Slack URL: %s", webhook_url[:40])
        return

    deal_link = f"{app_url}/deals/{deal_id}" if app_url and deal_id else None
    fields = [
        {"type": "mrkdwn", "text": f"*Deal*\n{deal_name}"},
        {"type": "mrkdwn", "text": f"*Target*\n{target_company}"},
        {"type": "mrkdwn", "text": f"*Document*\n{filename}"},
        {"type": "mrkdwn", "text": f"*Red flags*\n{len(red_flags)} ({high_count} high severity)"},
    ]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "ClearVault · extraction complete"},
        },
        {"type": "section", "fields": fields},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Summary*\n{summary[:600] or '_no summary returned_'}"},
        },
    ]

    if red_flags:
        bullets = "\n".join(
            f"• *{(f.get('severity') or 'info').upper()}* — {f.get('title','')}"
            for f in red_flags[:5]
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Top flags*\n{bullets}"}})

    if deal_link:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open deal"},
                        "url": deal_link,
                    }
                ],
            }
        )

    payload = {"text": f"ClearVault — {deal_name} · {filename}", "blocks": blocks}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(webhook_url, json=payload)
            if r.status_code >= 300:
                logger.warning("Slack webhook returned %s: %s", r.status_code, r.text[:200])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Slack notification failed: %s", exc)


def fire_and_forget(coro):
    """Schedule a coroutine without awaiting it (for use inside background tasks)."""
    try:
        asyncio.get_event_loop().create_task(coro)
    except RuntimeError:
        asyncio.run(coro)
