#!/usr/bin/env python3
"""
Runner: reddit lead capture (one-shot pass over configured subreddits).

Usage:
    python run_reddit.py
    python run_reddit.py --dry-run    # classify but don't save to DB
    python run_reddit.py --subreddits replit,lovable,vibecoding
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Reddit lead capture")
    parser.add_argument("--dry-run", action="store_true", help="Don't save leads to DB")
    parser.add_argument("--subreddits", help="Comma-separated subreddit list override")
    args = parser.parse_args()

    from systems.reddit_capture import run_once, SUBREDDITS
    subs = args.subreddits.split(",") if args.subreddits else SUBREDDITS
    print(f"Scanning subreddits: {subs}")
    run_once(subreddits=subs, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
