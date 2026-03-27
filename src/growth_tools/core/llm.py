"""
Provider-agnostic LLM layer with fallbacks, retries, and safe JSON parsing.

Supported providers (set via LLM_PROVIDER env var):
  "openai"    — OpenAI API (default)
  "anthropic" — Anthropic Claude API
  "litellm"   — LiteLLM proxy (100+ providers)

Model is read from LLM_MODEL env var; each provider has a sensible default.

Brand identity for generated reply/outreach copy is read from env var:
  BRAND_NAME      (default: "our product")
  BRAND_TAGLINE   (default: "helps teams ship production-ready apps")
  ICP_PAIN        (default: "move from prototype to production")

This makes growth-tools reusable for any dev-tool company without forking.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# ── Provider configuration ───────────────────────────────────────────────────

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai").lower().strip()

_DEFAULT_MODELS = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "litellm": "gpt-4.1-mini",
}

LLM_MODEL = os.environ.get("LLM_MODEL", _DEFAULT_MODELS.get(LLM_PROVIDER, "gpt-4.1-mini"))

# Fallback model per provider (used when primary model errors)
_FALLBACK_MODELS = {
    "openai": "gpt-3.5-turbo",
    "anthropic": "claude-3-5-haiku-20241022",
    "litellm": "gpt-3.5-turbo",
}

# Brand identity -- configure via env so this file needs zero code changes
BRAND_NAME    = os.environ.get("BRAND_NAME",    "our product")
BRAND_TAGLINE = os.environ.get("BRAND_TAGLINE", "helps teams ship production-ready apps")
ICP_PAIN      = os.environ.get("ICP_PAIN",      "move from prototype to production")


# ── Provider clients ─────────────────────────────────────────────────────────

def _get_openai_client():
    """Return (client, model) for OpenAI."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "OpenAI SDK not installed. Run: pip install growth-tools[openai]  "
            "or: pip install openai"
        )
    from growth_tools.config.settings import get_settings
    s = get_settings()
    s.require_openai()
    return OpenAI(api_key=s.openai_api_key), LLM_MODEL


def _get_anthropic_client():
    """Return (client, model) for Anthropic."""
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "Anthropic SDK not installed. Run: pip install growth-tools[anthropic]  "
            "or: pip install anthropic"
        )
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
    return anthropic.Anthropic(api_key=api_key), LLM_MODEL


def _get_litellm_module():
    """Return (litellm module, model) for LiteLLM."""
    try:
        import litellm
    except ImportError:
        raise ImportError(
            "LiteLLM not installed. Run: pip install growth-tools[litellm]  "
            "or: pip install litellm"
        )
    return litellm, LLM_MODEL


# ── Unified ask_llm ──────────────────────────────────────────────────────────

def ask_llm(
    prompt: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
    model_override: Optional[str] = None,
) -> str:
    """
    Send a prompt to the configured LLM provider and return the text response.

    Parameters
    ----------
    prompt : str
        The user message.
    system : str, optional
        An optional system message (used by OpenAI and Anthropic; prepended for LiteLLM).
    json_mode : bool
        Request JSON output (supported by OpenAI and LiteLLM; for Anthropic the prompt
        should instruct the model to return JSON).
    model_override : str, optional
        Override the model for this call (e.g. for fallback).

    Returns
    -------
    str
        The raw text content of the model's response.
    """
    provider = LLM_PROVIDER

    if provider == "openai":
        return _ask_openai(prompt, system=system, json_mode=json_mode, model_override=model_override)
    elif provider == "anthropic":
        return _ask_anthropic(prompt, system=system, json_mode=json_mode, model_override=model_override)
    elif provider == "litellm":
        return _ask_litellm(prompt, system=system, json_mode=json_mode, model_override=model_override)
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Supported: openai, anthropic, litellm"
        )


def _ask_openai(
    prompt: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
    model_override: Optional[str] = None,
) -> str:
    client, default_model = _get_openai_client()
    model = model_override or default_model
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def _ask_anthropic(
    prompt: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
    model_override: Optional[str] = None,
) -> str:
    client, default_model = _get_anthropic_client()
    model = model_override or default_model
    kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    # Anthropic doesn't have a native json_mode; we rely on the prompt instructing
    # the model to return JSON.  Adding a nudge if json_mode is requested.
    if json_mode and "json" not in prompt.lower():
        kwargs["messages"][0]["content"] = prompt + "\n\nRespond with valid JSON only."
    response = client.messages.create(**kwargs)
    # response.content is a list of content blocks
    return (response.content[0].text or "").strip()


def _ask_litellm(
    prompt: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
    model_override: Optional[str] = None,
) -> str:
    litellm, default_model = _get_litellm_module()
    model = model_override or default_model
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    kwargs: Dict[str, Any] = {"model": model, "messages": messages}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    response = litellm.completion(**kwargs)
    return (response.choices[0].message.content or "").strip()


# ── JSON parsing helpers ─────────────────────────────────────────────────────

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


def _ask_with_fallback(
    prompt: str,
    *,
    system: Optional[str] = None,
    json_mode: bool = False,
) -> str:
    """
    Try the primary model; on failure, retry with the provider's fallback model.
    """
    try:
        return ask_llm(prompt, system=system, json_mode=json_mode)
    except Exception as e:
        fallback = _FALLBACK_MODELS.get(LLM_PROVIDER)
        if fallback and fallback != LLM_MODEL:
            logger.warning(
                "Primary model %s failed (%s); trying fallback %s",
                LLM_MODEL, e, fallback,
            )
            return ask_llm(prompt, system=system, json_mode=json_mode, model_override=fallback)
        raise


# ── Public API (same signatures as before) ───────────────────────────────────

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
        raw = _ask_with_fallback(prompt, json_mode=True)
        out = _parse_classification(raw)
        if isinstance(out.get("intent_score"), (float, str)):
            try:
                out["intent_score"] = int(float(out["intent_score"]))
            except (ValueError, TypeError):
                out["intent_score"] = 0
        out["intent_score"] = max(0, min(100, out.get("intent_score", 0)))
        return out
    except Exception as e:
        logger.error("classify_post_intent failed: %s", e)
        return {"relevant": False, "intent_score": 0, "builder_detected": "unknown",
                "pain_type": "other", "reason": str(e)}


def generate_reply_draft(title: str, body: str, builder: str, pain_type: str) -> str:
    """
    Generate a helpful, non-spammy Reddit/forum reply draft.
    Mentions your brand softly at the end. Cap: 120 words.
    """
    prompt = f"""
Write a helpful, non-spammy reply to this post.

Context:
- The user likely built with: {builder}
- Their pain is: {pain_type}
- We represent {BRAND_NAME}, which {BRAND_TAGLINE}

Rules:
- Be useful first -- give one concrete tip
- No hype, no hard sell
- Mention {BRAND_NAME} only at the end, softly
- Keep it under 120 words

Title: {title}
Body: {body}
"""
    try:
        return _ask_with_fallback(prompt)
    except Exception as e:
        logger.warning("generate_reply_draft failed: %s", e)
        return (
            f"Happy to share a checklist for that exact problem. "
            f"We've helped teams in the same spot at {BRAND_NAME} -- feel free to DM."
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
        return _ask_with_fallback(prompt)
    except Exception as e:
        logger.warning("generate_outreach_draft failed: %s", e)
        return (
            f"Hi {name}, saw your post about {pain_summary}. "
            f"We {BRAND_TAGLINE}. If you'd like a quick walkthrough, reply here. -- {BRAND_NAME}"
        )


def classify_discord_message(text: str) -> Dict[str, Any]:
    """
    Classify Discord message for intent (whether to respond).
    Returns: should_respond (bool), confidence (0-1), pain_type, summary.
    """
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
        raw = _ask_with_fallback(prompt, json_mode=True)
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


def score_message(text: str) -> Dict[str, Any]:
    """
    Quick intent scoring for arbitrary text.
    Returns: intent_score (0-100), pain_type, reason.
    """
    prompt = f"""
Score this message for purchase/migration intent related to: {ICP_PAIN}.

Return strict JSON:
{{
  "intent_score": 0-100,
  "pain_type": "deploy|migrate|auth|db|scale|security|ownership|other|none",
  "reason": "short explanation"
}}

Message: {text}
"""
    try:
        raw = _ask_with_fallback(prompt, json_mode=True)
        out = _parse_classification(raw)
        if isinstance(out.get("intent_score"), (float, str)):
            try:
                out["intent_score"] = int(float(out["intent_score"]))
            except (ValueError, TypeError):
                out["intent_score"] = 0
        out["intent_score"] = max(0, min(100, out.get("intent_score", 0)))
        return out
    except Exception as e:
        logger.warning("score_message failed: %s", e)
        return {"intent_score": 0, "pain_type": "other", "reason": str(e)}
