"""
Unified CLI for growth-tools.

Usage:
    growth-tools reddit   — Monitor subreddits for leads
    growth-tools api      — Start the REST API server
    growth-tools discord  — Run the Discord bot
    growth-tools scan     — Scan GitHub for competitor SDK repos
    growth-tools          — Show help
"""
import argparse
import sys


def _cmd_reddit(args):
    """Run one pass of Reddit lead capture."""
    from growth_tools.systems.reddit_capture import run_once

    leads = run_once(
        limit_per_sub=args.limit,
        save_to_db=not args.no_db,
        generate_drafts=not args.no_drafts,
    )
    print(f"\nFound {len(leads)} lead(s).")
    for lead in leads:
        tier = lead.get("tier", "?")
        score = lead.get("lead_score", 0)
        print(f"  [{tier}] score={score}  {lead.get('url', '')}")


def _cmd_api(args):
    """Start the Growth Tools REST API."""
    import uvicorn

    uvicorn.run(
        "growth_tools.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def _cmd_discord(args):
    """Run the Discord bot (persistent)."""
    from growth_tools.systems.discord_bot import run_bot

    print("Starting Discord bot... (Ctrl+C to stop)")
    run_bot()


def _cmd_scan(args):
    """Scan GitHub for repos importing competitor SDKs."""
    from growth_tools.systems.github_auditor import search_competitor_sdk_repos

    sdks = args.sdks.split(",") if args.sdks else None
    results = search_competitor_sdk_repos(
        competitor_sdks=sdks,
        max_results_per_sdk=args.max_results,
        min_score=args.min_score,
    )
    print(f"\nFound {len(results)} repos importing competitor SDKs.")
    for r in results:
        print(f"  {r['url']}  SDK={r['competitor_sdk']}  score={r['lead_score']}")


def main():
    parser = argparse.ArgumentParser(
        prog="growth-tools",
        description="Automated lead capture from Reddit, Discord, and GitHub with hybrid LLM scoring.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  growth-tools reddit              Scan subreddits for leads
  growth-tools reddit --limit 50   Scan with 50 posts per subreddit
  growth-tools api                 Start REST API on port 8000
  growth-tools api --port 3000     Start REST API on custom port
  growth-tools discord             Run Discord bot
  growth-tools scan                Scan GitHub for competitor SDK repos
  growth-tools scan --sdks firebase,appwrite

environment:
  LLM_PROVIDER    openai (default) | anthropic | litellm
  LLM_MODEL       Model name (default varies by provider)
  OPENAI_API_KEY  Required for openai provider
  ANTHROPIC_API_KEY  Required for anthropic provider
""",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s 0.3.0"
    )

    subparsers = parser.add_subparsers(dest="command", title="commands")

    # ── reddit ───────────────────────────────────────────────────────────────
    p_reddit = subparsers.add_parser(
        "reddit",
        help="Monitor subreddits for high-intent leads",
        description="Scan configured subreddits, classify posts with LLM, capture leads.",
    )
    p_reddit.add_argument(
        "--limit", type=int, default=25,
        help="Posts per subreddit (default: 25)",
    )
    p_reddit.add_argument(
        "--no-db", action="store_true",
        help="Skip saving to Supabase",
    )
    p_reddit.add_argument(
        "--no-drafts", action="store_true",
        help="Skip outreach draft generation",
    )
    p_reddit.set_defaults(func=_cmd_reddit)

    # ── api ──────────────────────────────────────────────────────────────────
    p_api = subparsers.add_parser(
        "api",
        help="Start the REST API server (website + GitHub auditor)",
        description="FastAPI server: POST /audit/website, POST /audit/github, GET /health.",
    )
    p_api.add_argument(
        "--host", default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    p_api.add_argument(
        "--port", type=int, default=8000,
        help="Port to listen on (default: 8000)",
    )
    p_api.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload for development",
    )
    p_api.set_defaults(func=_cmd_api)

    # ── discord ──────────────────────────────────────────────────────────────
    p_discord = subparsers.add_parser(
        "discord",
        help="Run the Discord bot (persistent)",
        description="Watch Discord channels for pain signals, classify with LLM, respond.",
    )
    p_discord.set_defaults(func=_cmd_discord)

    # ── scan ─────────────────────────────────────────────────────────────────
    p_scan = subparsers.add_parser(
        "scan",
        help="Scan GitHub for repos importing competitor SDKs",
        description="Search GitHub code for competitor SDK usage and score repos as leads.",
    )
    p_scan.add_argument(
        "--sdks",
        help="Comma-separated SDK names to scan (default: from config)",
    )
    p_scan.add_argument(
        "--max-results", type=int, default=30,
        help="Max results per SDK (default: 30)",
    )
    p_scan.add_argument(
        "--min-score", type=int, default=20,
        help="Minimum repo score to include (default: 20)",
    )
    p_scan.set_defaults(func=_cmd_scan)

    # ── parse & dispatch ─────────────────────────────────────────────────────
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
