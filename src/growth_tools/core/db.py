"""
Supabase/DB client with retries and connection checks.
"""
import logging
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Lazy client to avoid import errors when supabase not configured
_supabase_client: Any = None


def get_db():
    """Return Supabase client; initializes on first call. Raises if not configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    from config.settings import get_settings
    settings = get_settings()
    settings.require_supabase()
    from supabase import create_client
    _supabase_client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    return _supabase_client


def is_db_available() -> bool:
    """Check if Supabase is configured and reachable."""
    try:
        from config.settings import get_settings
        s = get_settings()
        if not s.supabase_url or not s.supabase_service_role_key:
            return False
        client = get_db()
        # Lightweight check: list with limit 1
        client.table("lead_signals").select("id").limit(1).execute()
        return True
    except Exception as e:
        logger.warning("DB check failed: %s", e)
        return False


# Pydantic-style record for type hints (optional)
class LeadRecord:
    def __init__(
        self,
        source: str,
        source_url: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        platform: str = "reddit",
        intent_score: int = 0,
        lead_score: Optional[int] = None,
        score_tier: Optional[str] = None,
        builder_detected: Optional[str] = None,
        pain_type: Optional[str] = None,
        status: str = "new",
        suggested_reply: Optional[str] = None,
        outreach_draft: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.source = source
        self.source_url = source_url
        self.title = title
        self.body = body
        self.platform = platform
        self.intent_score = intent_score
        self.lead_score = lead_score
        self.score_tier = score_tier
        self.builder_detected = builder_detected
        self.pain_type = pain_type
        self.status = status
        self.suggested_reply = suggested_reply
        self.outreach_draft = outreach_draft
        self.metadata = metadata or {}

    def to_insert(self) -> Dict[str, Any]:
        row = {
            "source": self.source,
            "source_url": self.source_url,
            "title": self.title,
            "body": (self.body or "")[:10000],
            "platform": self.platform,
            "intent_score": self.intent_score,
            "builder_detected": self.builder_detected,
            "pain_type": self.pain_type,
            "status": self.status,
            "suggested_reply": self.suggested_reply,
            "outreach_draft": self.outreach_draft,
            "metadata": self.metadata,
        }
        if self.lead_score is not None:
            row["lead_score"] = self.lead_score
        if self.score_tier:
            row["score_tier"] = self.score_tier
        return row


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)
def save_lead(lead: LeadRecord) -> Dict[str, Any]:
    """Persist lead to lead_signals table. Retries on transient failures."""
    client = get_db()
    row = lead.to_insert()
    response = client.table("lead_signals").insert(row).execute()
    if response.data and len(response.data) > 0:
        return response.data[0]
    return row


def get_leads_by_status(status: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch leads by status for sequencer."""
    try:
        client = get_db()
        r = client.table("lead_signals").select("*").eq("status", status).order("created_at", desc=True).limit(limit).execute()
        return r.data or []
    except Exception as e:
        logger.warning("get_leads_by_status failed: %s", e)
        return []


def get_lead_by_id(lead_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single lead by id."""
    try:
        client = get_db()
        r = client.table("lead_signals").select("*").eq("id", lead_id).execute()
        if r.data and len(r.data) > 0:
            return r.data[0]
    except Exception as e:
        logger.warning("get_lead_by_id failed: %s", e)
    return None


def update_lead_status(lead_id: int, status: str, extra: Optional[Dict[str, Any]] = None) -> bool:
    """Update a lead's status and optionally other fields."""
    try:
        client = get_db()
        payload = {"status": status}
        if extra:
            payload.update(extra)
        client.table("lead_signals").update(payload).eq("id", lead_id).execute()
        return True
    except Exception as e:
        logger.warning("update_lead_status failed: %s", e)
        return False
