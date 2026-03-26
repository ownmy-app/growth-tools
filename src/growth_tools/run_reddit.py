"""CLI entry point for growth-reddit."""
import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="growth-reddit",
        description="Monitor subreddits for leads matching your ICP",
    )
    parser.add_argument("--limit", type=int, default=25, help="Posts per subreddit (default: 25)")
    parser.add_argument("--no-db", action="store_true", help="Skip saving to Supabase")
    parser.add_argument("--no-drafts", action="store_true", help="Skip outreach draft generation")
    args = parser.parse_args()

    from .systems.reddit_capture import run_once

    leads = run_once(
        limit_per_sub=args.limit,
        save_to_db=not args.no_db,
        generate_drafts=not args.no_drafts,
    )
    print(f"\nFound {len(leads)} lead(s).")


if __name__ == "__main__":
    main()
