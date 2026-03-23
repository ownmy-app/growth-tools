"""
System 5: CRM + outreach sequencer.
Every detected lead enters a pipeline: category, pain, source, suggested response, follow-up.
Supports: list by status, get next actions, update status, generate drafts.
"""
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from config.settings import get_settings
from core.db import (
    get_leads_by_status,
    get_lead_by_id,
    update_lead_status,
    save_lead,
    LeadRecord,
    is_db_available,
)
from core.llm import generate_reply_draft, generate_outreach_draft
from core.scoring import score_lead, score_tier

logger = logging.getLogger(__name__)


def get_pipeline(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch leads; if status given, filter by it."""
    if not is_db_available():
        return []
    if status:
        return get_leads_by_status(status, limit=limit)
    # All recent: fetch "new" and "nurture" etc.
    out = []
    for s in ("new", "nurture", "contacted", "replied"):
        out.extend(get_leads_by_status(s, limit=limit))
    # Dedupe by id
    seen = set()
    result = []
    for row in out:
        if row.get("id") not in seen:
            seen.add(row.get("id"))
            result.append(row)
    return result[:limit]


def get_hot_leads(limit: int = 20) -> List[Dict[str, Any]]:
    """Leads with score_tier 'hot' or high intent_score, status 'new'."""
    rows = get_leads_by_status("new", limit=limit * 2)
    hot = [r for r in rows if (r.get("score_tier") == "hot" or (r.get("intent_score") or 0) >= 80)]
    return hot[:limit]


def suggest_next_actions(lead_id: int) -> Dict[str, Any]:
    """
    For a lead, return suggested next steps: reply_draft (if not yet set), outreach_draft, CTA.
    """
    if not is_db_available():
        return {"error": "CRM not available"}
    lead = get_lead_by_id(lead_id)
    if not lead:
        return {"error": "Lead not found"}
    out = {
        "lead_id": lead_id,
        "status": lead.get("status"),
        "source": lead.get("source"),
        "source_url": lead.get("source_url"),
        "suggested_reply": lead.get("suggested_reply"),
        "outreach_draft": lead.get("outreach_draft"),
        "next_actions": [],
    }
    if not lead.get("suggested_reply") and lead.get("platform") == "reddit":
        try:
            draft = generate_reply_draft(
                lead.get("title") or "",
                lead.get("body") or "",
                lead.get("builder_detected") or "unknown",
                lead.get("pain_type") or "other",
            )
            out["suggested_reply"] = draft
            out["next_actions"].append("Post Reddit reply (draft ready); approve then send.")
        except Exception as e:
            out["next_actions"].append(f"Generate reply manually (LLM failed: {e})")
    if not lead.get("outreach_draft"):
        try:
            name = (lead.get("metadata") or {}).get("author_name") or "there"
            company = (lead.get("metadata") or {}).get("company") or "your project"
            pain = lead.get("pain_type") or "productionizing"
            draft = generate_outreach_draft(name, company, pain, lead.get("source_url") or "")
            out["outreach_draft"] = draft
            out["next_actions"].append("Send outreach (draft ready); approve then send.")
        except Exception as e:
            out["next_actions"].append(f"Generate outreach manually (LLM failed: {e})")
    if not out["next_actions"]:
        out["next_actions"].append("Reply or outreach already drafted; review and send.")
    out["next_actions"].append("Update status to 'contacted' after first touch.")
    return out


def mark_contacted(lead_id: int) -> bool:
    return update_lead_status(lead_id, "contacted")


def mark_replied(lead_id: int) -> bool:
    return update_lead_status(lead_id, "replied")


def add_lead(
    source: str,
    source_url: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    platform: str = "website",
    pain_type: Optional[str] = None,
    intent_score: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Add a lead (e.g. from website audit) to the pipeline."""
    if not is_db_available():
        return None
    lead_score = score_lead(pain_type=pain_type, intent_score_from_llm=intent_score or None)
    tier = score_tier(lead_score)
    record = LeadRecord(
        source=source,
        source_url=source_url,
        title=title,
        body=body,
        platform=platform,
        intent_score=intent_score,
        lead_score=lead_score,
        score_tier=tier,
        pain_type=pain_type,
        status="new",
        metadata=metadata or {},
    )
    try:
        return save_lead(record)
    except Exception as e:
        logger.warning("add_lead failed: %s", e)
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hot = get_hot_leads(5)
    print("Hot leads:", len(hot))
    for h in hot:
        print(h.get("id"), h.get("source"), h.get("score_tier"))
