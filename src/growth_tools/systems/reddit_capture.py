# ruff: noqa: E402
"""
System 1: Reddit lead capture.
Monitor subreddits for high-intent posts, classify with LLM, persist to CRM.
"""
import logging
import sys
from pathlib import Path

# Allow running from repo root or growth-tools
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import praw
from config.settings import get_settings
from core.llm import classify_post_intent, generate_reply_draft
from core.scoring import score_lead, score_tier
from core.db import save_lead, LeadRecord, is_db_available

logger = logging.getLogger(__name__)

# Legacy hard-coded defaults (overridden by config_loader when available)
_FALLBACK_SUBREDDITS = [
    "replit",
    "lovable",
    "vibecoding",
    "nocode",
    "sideproject",
    "saas",
    "entrepreneur",
]

_FALLBACK_KEYWORDS = [
    "deploy",
    "deployment",
    "production",
    "aws",
    "migrate",
    "move off",
    "custom domain",
    "auth",
    "database",
    "github",
    "hosting",
    "scale",
]


def _load_subreddits_and_keywords():
    """Load subreddits and keywords from YAML config, falling back to defaults."""
    try:
        from growth_tools.config_loader import load_config
        cfg = load_config()
        return cfg.subreddits, cfg.keywords, cfg.hot_threshold
    except Exception as exc:
        logger.debug("Config loader unavailable (%s); using built-in defaults", exc)
        return _FALLBACK_SUBREDDITS, _FALLBACK_KEYWORDS, 80


def contains_keyword(text: str, keywords: list = None) -> bool:
    if not text:
        return False
    if keywords is None:
        _, keywords, _ = _load_subreddits_and_keywords()
    t = text.lower()
    return any(k in t for k in keywords)


def get_reddit_client():
    settings = get_settings()
    settings.require_reddit()
    return praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
    )


def run_once(limit_per_sub: int = 25, save_to_db: bool = True, generate_drafts: bool = True) -> list:
    """
    Run one pass over configured subreddits. Returns list of captured lead dicts.

    Subreddits, keywords, and scoring thresholds are loaded from YAML config
    (see config_loader.py) with env-var and built-in defaults as fallback.
    """
    settings = get_settings()
    settings.require_reddit()
    settings.require_openai()
    threshold = settings.lead_intent_threshold

    # Load configurable subreddits, keywords, and hot threshold
    subreddits, keywords, hot_threshold = _load_subreddits_and_keywords()

    reddit = get_reddit_client()
    use_db = save_to_db and is_db_available()
    if save_to_db and not use_db:
        logger.warning("Supabase not configured or unreachable; leads will not be saved")

    # Import notification helper (lazy to avoid import cycle)
    try:
        from growth_tools.notifications import notify_if_hot
        _notify = True
    except Exception:
        _notify = False

    captured = []
    for sub in subreddits:
        try:
            subreddit = reddit.subreddit(sub)
            for post in subreddit.new(limit=limit_per_sub):
                full_text = f"{post.title}\n{post.selftext or ''}"
                if not contains_keyword(full_text, keywords):
                    continue

                try:
                    result = classify_post_intent(post.title, post.selftext or "")
                except Exception as e:
                    logger.warning("Classification failed for %s: %s", post.id, e)
                    continue

                if not result.get("relevant") or result.get("intent_score", 0) < threshold:
                    continue

                intent_score = result.get("intent_score", 0)
                builder = result.get("builder_detected") or "unknown"
                pain = result.get("pain_type") or "other"

                lead_score_val = score_lead(
                    builder=builder,
                    pain_type=pain,
                    has_repo="github" in full_text.lower(),
                    mentions_clients=False,
                    intent_score_from_llm=intent_score,
                )
                tier = score_tier(lead_score_val)

                suggested_reply = None
                if generate_drafts:
                    try:
                        suggested_reply = generate_reply_draft(
                            post.title, post.selftext or "", builder, pain
                        )
                    except Exception as e:
                        logger.warning("Reply draft failed: %s", e)

                source = f"r/{sub}"
                source_url = f"https://reddit.com{post.permalink}"

                lead_record = LeadRecord(
                    source=source,
                    source_url=source_url,
                    title=post.title,
                    body=(post.selftext or "")[:5000],
                    platform="reddit",
                    intent_score=intent_score,
                    lead_score=lead_score_val,
                    score_tier=tier,
                    builder_detected=builder,
                    pain_type=pain,
                    status="new",
                    suggested_reply=suggested_reply,
                    metadata={"reddit_id": post.id, "reason": result.get("reason", "")},
                )

                if use_db:
                    try:
                        save_lead(lead_record)
                    except Exception as e:
                        logger.warning("Save lead failed: %s", e)

                lead_dict = {
                    "subreddit": sub,
                    "title": post.title,
                    "url": source_url,
                    "intent_score": intent_score,
                    "lead_score": lead_score_val,
                    "tier": tier,
                    "builder": builder,
                    "pain_type": pain,
                    "platform": "reddit",
                    "classification": result,
                }
                captured.append(lead_dict)
                logger.info("Lead captured: %s | %s", source_url, tier)

                # Slack notification for hot leads
                if _notify:
                    try:
                        notify_if_hot(lead_dict, hot_threshold=hot_threshold)
                    except Exception as e:
                        logger.debug("Slack notify failed: %s", e)

        except Exception as e:
            logger.warning("Subreddit r/%s failed: %s", sub, e)

    return captured


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    captured = run_once(save_to_db=True, generate_drafts=True)
    print(f"\nCaptured {len(captured)} leads this run.")
    for c in captured:
        print("=" * 60)
        print(f"r/{c['subreddit']} | {c['tier']} (score {c['lead_score']})")
        print(c["title"])
        print(c["url"])
        print("---")


if __name__ == "__main__":
    main()
