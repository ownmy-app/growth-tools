# growth-tools

> Automated lead capture from Reddit, Discord and GitHub — with hybrid LLM scoring and outreach drafts.

Built for dev-tool and SaaS companies that want inbound signal from developer communities
without hiring a full-time growth team.

---

## Quick start

```bash
# Clone and install
git clone https://github.com/nometria/growth-tools
cd growth-tools
pip install -e .

# Configure your environment
cp examples/sample-icp.env .env
# Edit .env with your API keys and brand config

# Run Reddit monitor (one-shot)
growth-reddit

# Run the website auditor API
growth-api
# or: uvicorn growth_tools.api.main:app --port 8000

# Run tests
pytest tests/ -v
```

Required environment variables (see `examples/sample-icp.env`):
```bash
OPENAI_API_KEY=sk-proj-...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
BRAND_NAME="Your Product"
ICP_KEYWORDS="supabase,self-host,postgres,..."
```

---

## What's included

| Module | What it does |
|--------|-------------|
| `systems/reddit_capture.py` | Monitors subreddits, two-stage filter (keyword → LLM), saves hot leads |
| `systems/discord_bot.py` | Discord bot with per-channel cooldown, confidence threshold gating |
| `systems/website_auditor.py` | Detects tech stack from HTML/headers (Next.js, Vite, Supabase, Vercel…) |
| `systems/github_auditor.py` | Scans repos for migration readiness + competitor SDK lead capture |
| `systems/crm_sequencer.py` | LLM-generated outreach drafts (capped at 90 words for reply rates) |
| `core/scoring.py` | Hybrid rule + LLM scoring: `0.5 × rule_score + 0.5 × llm_intent_score` |
| `core/llm.py` | OpenAI client with fallback model + tenacity retries |
| `config_loader.py` | YAML-based configuration (subreddits, keywords, thresholds, competitor SDKs) |
| `notifications.py` | Slack webhook notifications for hot leads (Block Kit format) |
| `api/main.py` | FastAPI: `POST /audit/website`, `POST /audit/github`, `GET /health` |

---

## Scoring tiers

| Score | Tier | Action |
|-------|------|--------|
| ≥ 80 | **hot** | Immediate outreach |
| 60–79 | **nurture** | Add to sequence |
| 40–59 | **educate** | Send content |
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
cp examples/sample-icp.env .env
# Edit .env
```

---

## Run

```bash
# Reddit monitor (one-shot)
growth-reddit

# Discord bot (persistent)
python -m growth_tools.systems.discord_bot

# Website auditor API
growth-api
# or: uvicorn growth_tools.api.main:app --port 8000

# Audit a specific website
curl -X POST http://localhost:8000/audit/website -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'
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

# GitHub lead capture — SDK package names to scan for
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

The GitHub auditor now includes competitor SDK scanning. It searches GitHub for repos that `import` competitor SDKs and scores them as potential migration leads.

```bash
# CLI: scan for repos importing competitor SDKs
python -m growth_tools.systems.github_auditor --scan
python -m growth_tools.systems.github_auditor --scan firebase,appwrite

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

**Target subreddits** — set in `growth.yml` or `GROWTH_SUBREDDITS` env var

**Lead scoring** — edit weights in `core/scoring.py` or adjust thresholds in `growth.yml`

**Outreach tone** — edit prompts in `core/llm.py`

**Competitor SDKs** — set in `growth.yml` or `GROWTH_COMPETITOR_SDKS` env var

---

## Immediate next steps
1. ~~Make subreddits + keywords configurable via env / YAML~~ Done
2. ~~Add GitHub lead capture (scan repos that import competitor SDKs)~~ Done
3. ~~Add Slack notification on "hot" leads~~ Done
4. Package as `pip install growth-tools`

---

## Commercial viability
- Open-core: open source the capture + scoring, charge for the CRM sequencer
- SaaS: $200–500/mo per team for managed lead pipeline
- Competitors: Trigify, Drippi — neither does GitHub + Reddit + LLM scoring combined

---

## Example output

Running `pytest tests/ -v`:

```
============================= test session starts ==============================
platform darwin -- Python 3.13.9, pytest-9.0.2, pluggy-1.5.0
cachedir: .pytest_cache
rootdir: /tmp/ownmy-releases/growth-tools
configfile: pyproject.toml
plugins: anyio-4.12.1, cov-7.1.0
collecting ... collected 4 items

tests/test_brand_config.py::test_brand_name_reads_from_env PASSED        [ 25%]
tests/test_brand_config.py::test_brand_tagline_reads_from_env PASSED     [ 50%]
tests/test_brand_config.py::test_icp_pain_reads_from_env PASSED          [ 75%]
tests/test_brand_config.py::test_no_hardcoded_brand_names_in_source PASSED [100%]

============================== 4 passed in 0.03s ===============================
```

See `examples/sample-leads.json` for representative scored lead output and `examples/sample-icp.env` for required environment variable configuration.
