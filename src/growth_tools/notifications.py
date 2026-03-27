"""
Slack notifications for hot leads.

Posts rich Block Kit messages to a Slack webhook when a lead scores above
the configured hot_threshold.  Uses only urllib (no extra dependencies).

Configuration:
    SLACK_WEBHOOK_URL   — Slack Incoming Webhook URL (required for notifications)
"""

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _get_webhook_url() -> Optional[str]:
    """Return the Slack webhook URL from env, or None if not configured."""
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    return url if url else None


def _build_slack_blocks(lead: Dict[str, Any], webhook_url: str) -> Dict[str, Any]:
    """
    Build a Slack Block Kit payload for a hot lead notification.

    *lead* is the dict returned by reddit_capture / github_auditor capture loops,
    with at least: title, url/source_url, lead_score, tier, builder, pain_type.
    """
    title = lead.get("title") or "Untitled lead"
    url = lead.get("url") or lead.get("source_url") or ""
    score = lead.get("lead_score") or lead.get("score", 0)
    tier = lead.get("tier") or lead.get("score_tier", "unknown")
    builder = lead.get("builder") or lead.get("builder_detected", "unknown")
    pain = lead.get("pain_type") or "unknown"
    source = lead.get("subreddit") or lead.get("source") or "unknown"
    platform = lead.get("platform") or "unknown"

    # Tier emoji
    tier_emoji = {
        "hot": ":fire:",
        "nurture": ":seedling:",
        "educate": ":books:",
        "ignore": ":zzz:",
    }.get(tier, ":bell:")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{tier_emoji} Hot Lead Detected — Score {score}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Tier:*\n{tier.capitalize()}"},
                {"type": "mrkdwn", "text": f"*Score:*\n{score}/100"},
                {"type": "mrkdwn", "text": f"*Builder:*\n{builder}"},
                {"type": "mrkdwn", "text": f"*Pain:*\n{pain}"},
                {"type": "mrkdwn", "text": f"*Source:*\n{source}"},
                {"type": "mrkdwn", "text": f"*Platform:*\n{platform}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title[:300]}*",
            },
        },
    ]

    # Add link button if URL is available
    if url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Lead", "emoji": True},
                    "url": url,
                    "action_id": "view_lead",
                },
            ],
        })

    blocks.append({"type": "divider"})

    return {"blocks": blocks}


def send_slack_notification(
    lead: Dict[str, Any],
    webhook_url: Optional[str] = None,
) -> bool:
    """
    Post a rich Slack notification for a lead.

    Parameters
    ----------
    lead : dict
        Lead data dict (from capture loops).  Must include at least ``title``
        and ``lead_score``.
    webhook_url : str, optional
        Slack webhook URL.  Falls back to ``SLACK_WEBHOOK_URL`` env var.

    Returns
    -------
    bool
        True if the message was posted successfully.
    """
    webhook = webhook_url or _get_webhook_url()
    if not webhook:
        logger.debug("Slack notification skipped — no SLACK_WEBHOOK_URL configured")
        return False

    payload = _build_slack_blocks(lead, webhook)
    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            if status == 200:
                logger.info("Slack notification sent for lead: %s", lead.get("title", "")[:80])
                return True
            logger.warning("Slack webhook returned HTTP %s", status)
            return False
    except urllib.error.HTTPError as exc:
        logger.warning("Slack webhook HTTP error %s: %s", exc.code, exc.reason)
        return False
    except urllib.error.URLError as exc:
        logger.warning("Slack webhook URL error: %s", exc.reason)
        return False
    except Exception as exc:
        logger.warning("Slack notification failed: %s", exc)
        return False


def notify_if_hot(
    lead: Dict[str, Any],
    hot_threshold: int = 80,
    webhook_url: Optional[str] = None,
) -> bool:
    """
    Convenience wrapper: sends a Slack notification only if the lead score
    meets or exceeds *hot_threshold*.

    Returns True if a notification was actually sent.
    """
    score = lead.get("lead_score") or lead.get("score", 0)
    if score < hot_threshold:
        return False
    return send_slack_notification(lead, webhook_url=webhook_url)
