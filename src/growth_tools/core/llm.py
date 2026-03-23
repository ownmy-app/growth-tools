"""
OpenAI client with fallbacks: retries, model fallback, and safe JSON parsing.

Brand identity for generated reply/outreach copy is read from env var:
  BRAND_NAME      (default: "our product")
  BRAND_TAGLINE   (default: "helps teams ship production-ready apps")
  ICP_PAIN        (default: "move from prototype to production")

This makes growth-tools reusable for any dev-tool company without forking.
"""
import json
import logging
import os
from typing import Any, Dict

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Fallback model if primary fails
FALLBACK_MODEL = "gpt-3.5-turbo"

# Brand identity — configure via env so this file needs zero code changes
BRAND_NAME     = os.environ.get("BRAND_NAME",    "our product")
BRAND_TAGLINE  = os.environ.get("BRAND_TAGLINE",  "helps teams ship production-ready apps")
ICP_PAIN       = os.environ.get("ICP_PAIN",       "move from prototype to production")


def _get_client():
    from openai import OpenAI
    from growth_tools.config.settings import get_settings
    s = get_settings()
    s.require_openai()
    return OpenAI(api_key=s.openai_api_key), s.openai_model


def _parse_classification(raw: str) -> Dict[str, Any]:
    """Parse LLM JSON with fallbacks."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    return {
        "relevant": False,
        "intent_score": 0,
        "builder_detected": "unknown",
        "pain_type": "other",
        "reason": "Parse failed",
    }


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)
def classify_post_intent(title: str, body: str) -> Dict[str, Any]:
    """
    Classify whether a post is a high-intent lead.
    Returns dict with: relevant, intent_score, builder_detected, pain_type, reason.

    Configure ICP_PAIN env var to describe your product's target problem.
    """
    client, model = _get_client()
    prompt = f"""
You are classifying whether a post is a high-intent lead for a product that {BRAND_TAGLINE}.
A high-intent lead is someone who needs to {ICP_PAIN}.

Return strict JSON with:
{{
  "relevant": true/false,
  "intent_score": 0-100,
  "builder_detected": "lovable|replit|bolt|v0|cursor|windsurf|unknown",
  "pain_type": "deploy|migrate|auth|db|scale|security|ownership|other",
  "reason": "short explanation"
}}

Title: {title}
Body: {body}
"""
    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content
        out = _parse_classification(raw)
        if isinstance(out.get("intent_score"), (float, str)):
            try:
                out["intent_score"] = int(float(out["intent_score"]))
            except (ValueError, TypeError):
                out["intent_score"] = 0
        out["intent_score"] = max(0, min(100, out.get("intent_score", 0)))
        return out
    except Exception as e:
        logger.warning("Primary model %s failed: %s, trying fallback", model, e)
        try:
            response = client.chat.completions.create(
                model=FALLBACK_MODEL,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content
            return _parse_classification(raw)
        except Exception as e2:
            logger.error("Fallback model also failed: %s", e2)
            return {"relevant": False, "intent_score": 0, "builder_detected": "unknown",
                    "pain_type": "other", "reason": str(e2)}


def generate_reply_draft(title: str, body: str, builder: str, pain_type: str) -> str:
    """
    Generate a helpful, non-spammy Reddit/forum reply draft.
    Mentions your brand softly at the end. Cap: 120 words.
    """
    client, model = _get_client()
    prompt = f"""
Write a helpful, non-spammy reply to this post.

Context:
- The user likely built with: {builder}
- Their pain is: {pain_type}
- We represent {BRAND_NAME}, which {BRAND_TAGLINE}

Rules:
- Be useful first — give one concrete tip
- No hype, no hard sell
- Mention {BRAND_NAME} only at the end, softly
- Keep it under 120 words

Title: {title}
Body: {body}
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("generate_reply_draft failed: %s", e)
        return (
            f"Happy to share a checklist for that exact problem. "
            f"We've helped teams in the same spot at {BRAND_NAME} — feel free to DM."
        )


def generate_outreach_draft(
    name: str,
    company: str,
    pain_summary: str,
    source_url: str,
) -> str:
    """
    Generate a short, personalized outreach note. Cap: 90 words.
    """
    client, model = _get_client()
    prompt = f"""
Write a short outreach note.

Person: {name}
Company: {company}
Pain summary: {pain_summary}
Source: {source_url}

Rules:
- Not salesy
- Acknowledge their exact problem
- Mention {BRAND_NAME} briefly ({BRAND_TAGLINE})
- End with one simple CTA
- Keep it under 90 words
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("generate_outreach_draft failed: %s", e)
        return (
            f"Hi {name}, saw your post about {pain_summary}. "
            f"We {BRAND_TAGLINE}. If you'd like a quick walkthrough, reply here. — {BRAND_NAME}"
        )


def classify_discord_message(text: str) -> Dict[str, Any]:
    """
    Classify Discord message for intent (whether to respond).
    Returns: should_respond (bool), confidence (0-1), pain_type, summary.
    """
    client, model = _get_client()
    prompt = f"""
Does this message indicate someone needs to {ICP_PAIN}?
Look for signals: deploy problems, migration questions, hosting issues, auth/db trouble.

Reply with strict JSON:
{{
  "should_respond": true/false,
  "confidence": 0.0-1.0,
  "pain_type": "deploy|migrate|auth|db|hosting|other|none",
  "summary": "one line summary"
}}

Message: {text}
"""
    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content
        out = _parse_classification(raw)
        out["should_respond"] = out.get("should_respond", False)
        c = out.get("confidence", 0)
        out["confidence"] = float(c) if isinstance(c, (int, float)) else 0.0
        out["pain_type"] = out.get("pain_type", "other")
        out["summary"] = out.get("summary", "")
        return out
    except Exception as e:
        logger.warning("classify_discord_message failed: %s", e)
        return {"should_respond": False, "confidence": 0.0, "pain_type": "other", "summary": str(e)}
