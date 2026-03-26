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
| `systems/github_auditor.py` | Scans repos for migration readiness (package.json, Dockerfile analysis) |
| `systems/crm_sequencer.py` | LLM-generated outreach drafts (capped at 90 words for reply rates) |
| `core/scoring.py` | Hybrid rule + LLM scoring: `0.5 × rule_score + 0.5 × llm_intent_score` |
| `core/llm.py` | OpenAI client with fallback model + tenacity retries |
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

## Customise

**Target subreddits** — set `ICP_KEYWORDS` in `.env`

**Lead scoring** — edit weights in `core/scoring.py` (or move to YAML config)

**Outreach tone** — edit prompts in `core/llm.py`

---

## Immediate next steps
1. Make subreddits + keywords configurable via env / YAML
2. Add GitHub lead capture (scan repos that import competitor SDKs)
3. Add Slack notification on "hot" leads
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
