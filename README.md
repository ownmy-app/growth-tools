# growth-tools

> Automated lead capture from Reddit, Discord and GitHub — with hybrid LLM scoring and outreach drafts.

Built for dev-tool and SaaS companies that want inbound signal from developer communities
without hiring a full-time growth team.

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
git clone https://github.com/YOUR_ORG/growth-tools
cd growth-tools
pip install -r requirements.txt
cp .env.example .env
# Edit .env
```

---

## Run

```bash
# Reddit monitor (one-shot)
python -m src.systems.reddit_capture

# Discord bot (persistent)
python -m src.systems.discord_bot

# Website auditor API
uvicorn src.api.main:app --port 8000

# Audit a specific website
curl -X POST http://localhost:8000/audit/website -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com"}'
```

---

## Customise

**Target subreddits** — edit `SUBREDDITS` in `systems/reddit_capture.py`

**Lead scoring** — edit weights in `core/scoring.py` (or move to YAML config)

**Outreach tone** — edit prompts in `core/llm.py`

**Keyword filter** — edit `KEYWORDS` list in `systems/reddit_capture.py`

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
