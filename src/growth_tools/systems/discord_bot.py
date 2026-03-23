# ruff: noqa: E402
"""
System 2: Discord trigger bot.
Watch channels for pain phrases; classify with LLM; respond only when confidence > threshold.
Throttles per channel and optionally logs leads to CRM.
"""
import logging
import sys
import time
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import discord
from discord.ext import commands

from config.settings import get_settings
from core.llm import classify_discord_message
from core.db import save_lead, LeadRecord, is_db_available

logger = logging.getLogger(__name__)

# Fallback trigger words when LLM is unavailable or for fast pre-filter
TRIGGER_WORDS = [
    "deploy", "production", "aws", "migrate", "move off",
    "host", "github", "custom domain", "auth", "database",
]

# Throttle: max one bot reply per channel per N seconds
CHANNEL_COOLDOWN_SECONDS = 300
_channel_last_reply: dict[int, float] = {}

# Optional: only respond in channels that have been "opted in" (empty = all)
# Set ALLOWED_CHANNEL_IDS in env as comma-separated IDs to restrict
ALLOWED_CHANNEL_IDS: set[int] = set()


def _load_allowed_channels():
    import os
    raw = os.getenv("DISCORD_ALLOWED_CHANNEL_IDS", "").strip()
    if not raw:
        return
    for s in raw.split(","):
        s = s.strip()
        if s.isdigit():
            ALLOWED_CHANNEL_IDS.add(int(s))


def should_trigger_fast(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(w in t for w in TRIGGER_WORDS)


def throttle_channel(channel_id: int) -> bool:
    """True if we're allowed to send in this channel (not in cooldown)."""
    now = time.time()
    last = _channel_last_reply.get(channel_id, 0)
    if now - last < CHANNEL_COOLDOWN_SECONDS:
        return False
    _channel_last_reply[channel_id] = now
    return True


def channel_allowed(channel_id: int) -> bool:
    if not ALLOWED_CHANNEL_IDS:
        return True
    return channel_id in ALLOWED_CHANNEL_IDS


# Response templates
REPLY_TEMPLATE = (
    "Sounds like you're moving from prototype to production. "
    "If you want, paste your repo/app link and I can suggest a migration checklist."
)


def get_discord_intents():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    return intents


def create_bot():
    settings = get_settings()
    settings.require_discord()
    _load_allowed_channels()

    bot = commands.Bot(command_prefix="!", intents=get_discord_intents())

    @bot.event
    async def on_ready():
        logger.info("Discord bot logged in as %s", bot.user)

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if not message.content or not message.content.strip():
            return
        if not channel_allowed(message.channel.id):
            return

        text = message.content.strip()
        if len(text) > 2000:
            text = text[:2000]

        if not should_trigger_fast(text):
            await bot.process_commands(message)
            return

        if not throttle_channel(message.channel.id):
            await bot.process_commands(message)
            return

        # Classify with LLM
        try:
            classification = classify_discord_message(text)
        except Exception as e:
            logger.warning("Discord classification failed: %s", e)
            classification = {"should_respond": True, "confidence": 0.5, "pain_type": "other", "summary": ""}

        threshold = settings.discord_confidence_threshold
        if not classification.get("should_respond") or classification.get("confidence", 0) < threshold:
            await bot.process_commands(message)
            return

        try:
            await message.channel.send(REPLY_TEMPLATE)
        except discord.HTTPException as e:
            logger.warning("Discord send failed: %s", e)

        # Optionally save as lead
        if is_db_available():
            try:
                lead = LeadRecord(
                    source=str(message.channel.id),
                    source_url=message.jump_url or "",
                    title=classification.get("summary", "")[:500],
                    body=text[:5000],
                    platform="discord",
                    intent_score=int(classification.get("confidence", 0) * 100),
                    pain_type=classification.get("pain_type"),
                    status="new",
                    metadata={
                        "channel_id": message.channel.id,
                        "author_id": str(message.author.id),
                        "message_id": message.id,
                    },
                )
                save_lead(lead)
            except Exception as e:
                logger.warning("Save Discord lead failed: %s", e)

        await bot.process_commands(message)

    return bot


def run_bot():
    """Blocking run of the Discord bot."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    bot = create_bot()
    settings = get_settings()
    token = settings.discord_token
    if not token:
        raise ValueError("DISCORD_TOKEN is required")
    bot.run(token)


if __name__ == "__main__":
    run_bot()
