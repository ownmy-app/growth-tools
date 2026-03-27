# growth-tools

> Automated lead capture from Reddit, Discord and GitHub -- with hybrid LLM scoring and outreach drafts.

Built for dev-tool and SaaS companies that want inbound signal from developer communities
without hiring a full-time growth team.

---

## Quick start

```bash
pip install growth-tools

# Configure
cp examples/sample-icp.env .env
# Edit .env with your API keys and brand config

# One command to run anything:
growth-tools reddit          # scan subreddits for leads
growth-tools api             # start the REST API
growth-tools discord         # run the Discord bot
growth-tools scan            # scan GitHub for competitor SDK repos
```

---

## Unified CLI

Everything runs through `growth-tools <command>`:

```
$ growth-tools --help

usage: growth-tools [-h] [--version] {reddit,api,discord,scan} ...

Automated lead capture from Reddit, Discord, and GitHub with hybrid LLM scoring.

commands:
  reddit     Monitor subreddits for high-intent leads
  api        Start the REST API server (website + GitHub auditor)
  discord    Run the Discord bot (persistent)
  scan       Scan GitHub for repos importing competitor SDKs

examples:
  growth-tools reddit              Scan subreddits for leads
  growth-tools reddit --limit 50   Scan with 50 posts per subreddit
  growth-tools api                 Start REST API on port 8000
  growth-tools api --port 3000     Start REST API on custom port
  growth-tools discord             Run Discord bot
  growth-tools scan                Scan GitHub for competitor SDK repos
  growth-tools scan --sdks firebase,appwrite
```

The legacy `growth-reddit` and `growth-api` commands still work for backward compatibility.

---

## Multi-LLM support

By default growth-tools uses OpenAI. Switch to any provider with two env vars:

| Provider | `LLM_PROVIDER` | `LLM_MODEL` default | Install |
|----------|----------------|----------------------|---------|
| OpenAI | `openai` (default) | `gpt-4.1-mini` | included |
| Anthropic | `anthropic` | `claude-sonnet-4-20250514` | `pip install growth-tools[anthropic]` |
| LiteLLM (100+ providers) | `litellm` | `gpt-4.1-mini` | `pip install growth-tools[litellm]` |

```bash
# Use Anthropic Claude
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-sonnet-4-20250514
export ANTHROPIC_API_KEY=sk-ant-...
growth-tools reddit

# Use any provider via LiteLLM (Gemini, Mistral, Ollama, etc.)
export LLM_PROVIDER=litellm
export LLM_MODEL=gemini/gemini-2.0-flash
growth-tools reddit

# Install all LLM providers at once
pip install growth-tools[all-llm]
```

All LLM calls (classification, scoring, outreach drafts) route through a single `ask_llm()` function that handles provider switching, retries, and model fallbacks automatically.

---

## Environment variables

Required (see `examples/sample-icp.env`):

```bash
# LLM provider (pick one)
LLM_PROVIDER=openai              # openai | anthropic | litellm
LLM_MODEL=gpt-4.1-mini           # model name (optional, sensible defaults)
OPENAI_API_KEY=sk-proj-...       # required for openai/litellm
ANTHROPIC_API_KEY=sk-ant-...     # required for anthropic

# Reddit credentials
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...

# Brand identity (used in LLM-generated outreach)
BRAND_NAME="Your Product"
BRAND_TAGLINE="helps teams ship production-ready apps"
ICP_PAIN="move from prototype to production"
```

Optional:

```bash
SUPABASE_URL=...                  # lead storage
SUPABASE_SERVICE_ROLE_KEY=...
DISCORD_TOKEN=...                 # Discord bot
GITHUB_TOKEN=ghp_...              # GitHub API (for scan command)
SLACK_WEBHOOK_URL=...             # Slack notifications for hot leads
```

---

## What's included

| Module | What it does |
|--------|-------------|
| `systems/reddit_capture.py` | Monitors subreddits, two-stage filter (keyword then LLM), saves hot leads |
| `systems/discord_bot.py` | Discord bot with per-channel cooldown, confidence threshold gating |
| `systems/website_auditor.py` | Detects tech stack from HTML/headers (Next.js, Vite, Supabase, Vercel...) |
| `systems/github_auditor.py` | Scans repos for migration readiness + competitor SDK lead capture |
| `systems/crm_sequencer.py` | LLM-generated outreach drafts (capped at 90 words for reply rates) |
| `core/scoring.py` | Hybrid rule + LLM scoring: `0.5 * rule_score + 0.5 * llm_intent_score` |
| `core/llm.py` | Multi-provider LLM layer (OpenAI, Anthropic, LiteLLM) with fallback + retries |
| `config_loader.py` | YAML-based configuration (subreddits, keywords, thresholds, competitor SDKs) |
| `notifications.py` | Slack webhook notifications for hot leads (Block Kit format) |
| `api/main.py` | FastAPI: `POST /audit/website`, `POST /audit/github`, `GET /health` |
| `cli.py` | Unified CLI entry point for all commands |

---

## Scoring tiers

| Score | Tier | Action |
|-------|------|--------|
| >= 80 | **hot** | Immediate outreach |
| 60-79 | **nurture** | Add to sequence |
| 40-59 | **educate** | Send content |
| < 40 | **ignore** | Skip |

Rule signals: `+25` high-intent builder (Lovable/Replit/Bolt/v0), `+30` high-intent pain
(deploy/migrate/security/ownership), `+20` has public repo, `+25` mentions clients.
Blended 50/50 with LLM intent score.

---

## Supabase schema

```sql
create table lead_signals (
  id           uuid primary key default gen_random_uuid(),
  source       text,          -- 'reddit' | 'discord' | 'github'
  title        text,
  body         text,
  url          text,
  author       text,
  intent_score int,
  tier         text,
  builder      text,
  pain_type    text,
  reply_draft  text,
  created_at   timestamptz default now()
);
```

---

## Setup

```bash
git clone https://github.com/nometria/growth-tools
cd growth-tools
pip install -e .

# Or with all LLM providers:
pip install -e ".[all-llm]"

cp examples/sample-icp.env .env
# Edit .env with your credentials
```

---

## YAML configuration

Create a `growth.yml` in your working directory (or set the `GROWTH_CONFIG` env var to a custom path):

```yaml
subreddits: [webdev, SaaS, startups, replit, lovable]
keywords: [migrate, moving from, switching to, deploy, self-host]

scoring:
  hot_threshold: 80
  nurture_threshold: 50

# GitHub lead capture -- SDK package names to scan for
competitor_sdks: [firebase, appwrite, amplify, convex, pocketbase]
```

Every value falls back to an env var if the YAML key is absent, and then to a built-in default:

| YAML key | Env var fallback | Default |
|---|---|---|
| `subreddits` | `GROWTH_SUBREDDITS` (comma-separated) | 7 built-in subs |
| `keywords` | `GROWTH_KEYWORDS` (comma-separated) | 12 built-in keywords |
| `scoring.hot_threshold` | `GROWTH_HOT_THRESHOLD` | 80 |
| `scoring.nurture_threshold` | `GROWTH_NURTURE_THRESHOLD` | 50 |
| `competitor_sdks` | `GROWTH_COMPETITOR_SDKS` (comma-separated) | 7 popular SDKs |

Install the optional YAML dependency: `pip install growth-tools[yaml]` (or `pip install pyyaml`).

---

## Slack notifications

Hot leads (score >= `hot_threshold`) are automatically posted to Slack when `SLACK_WEBHOOK_URL` is set.

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx
```

Each notification is a rich Block Kit message showing score, tier, builder, pain type, source, and a direct link to the lead. Notifications use only `urllib` (no extra dependencies).

You can also call the notification API directly:

```python
from growth_tools.notifications import send_slack_notification, notify_if_hot

# Send for any lead
send_slack_notification(lead_dict)

# Send only if score >= threshold
notify_if_hot(lead_dict, hot_threshold=80)
```

---

## GitHub lead capture

The GitHub auditor includes competitor SDK scanning. It searches GitHub for repos that `import` competitor SDKs and scores them as potential migration leads.

```bash
# CLI
growth-tools scan
growth-tools scan --sdks firebase,appwrite --min-score 30

# Python API
from growth_tools.systems.github_auditor import search_competitor_sdk_repos

leads = search_competitor_sdk_repos(
    competitor_sdks=["firebase", "appwrite"],
    max_results_per_sdk=30,
    min_score=20,
)
```

Repos are scored 0-100 based on stars, size, recent activity, and engagement. Configure the SDK list via `competitor_sdks` in `growth.yml` or the `GROWTH_COMPETITOR_SDKS` env var.

Requires `GITHUB_TOKEN` for authenticated code search (unauthenticated requests are rate-limited).

---

## Customise

**LLM provider** -- set `LLM_PROVIDER` and `LLM_MODEL` env vars

**Target subreddits** -- set in `growth.yml` or `GROWTH_SUBREDDITS` env var

**Lead scoring** -- edit weights in `core/scoring.py` or adjust thresholds in `growth.yml`

**Outreach tone** -- edit prompts in `core/llm.py`

**Competitor SDKs** -- set in `growth.yml` or `GROWTH_COMPETITOR_SDKS` env var

---

## Python API

```python
from growth_tools.core.llm import (
    ask_llm,
    classify_post_intent,
    generate_reply_draft,
    generate_outreach_draft,
    classify_discord_message,
    score_message,
)

# Use the unified LLM layer directly
response = ask_llm("Summarize this lead...", json_mode=True)

# Classify a post
result = classify_post_intent("Need help deploying my Lovable app", "...")

# Score arbitrary text
score = score_message("How do I migrate from Firebase to self-hosted?")
```

---

## Run tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
