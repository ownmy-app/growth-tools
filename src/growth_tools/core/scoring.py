"""
Lead scoring for prioritization and routing.
"""
from typing import Optional


def score_lead(
    builder: Optional[str] = None,
    pain_type: Optional[str] = None,
    has_repo: bool = False,
    mentions_clients: bool = False,
    intent_score_from_llm: Optional[int] = None,
) -> int:
    """
    Compute 0-100 lead score.
    - 80–100: immediate outreach
    - 60–79: add to nurture
    - 40–59: educational content
    - below 40: ignore
    """
    score = 0
    high_intent_builders = {"lovable", "replit", "bolt", "v0"}
    high_intent_pains = {"deploy", "migrate", "security", "ownership"}

    if builder and builder.lower() in high_intent_builders:
        score += 25
    if pain_type and pain_type.lower() in high_intent_pains:
        score += 30
    if has_repo:
        score += 20
    if mentions_clients:
        score += 25

    # Blend with LLM intent score if provided (average with rule-based)
    if intent_score_from_llm is not None:
        rule_score = min(score, 100)
        score = int(0.5 * rule_score + 0.5 * max(0, min(100, intent_score_from_llm)))

    return min(score, 100)


def score_tier(score: int) -> str:
    if score >= 80:
        return "hot"
    if score >= 60:
        return "nurture"
    if score >= 40:
        return "educate"
    return "ignore"
