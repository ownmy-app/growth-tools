#!/usr/bin/env python3
"""
Runner: Discord bot (persistent — runs until interrupted).

Usage:
    python run_discord.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from systems.discord_bot import run_bot

if __name__ == "__main__":
    print("Starting Discord bot... (Ctrl+C to stop)")
    run_bot()
