#!/usr/bin/env python3
"""
Runner: Website + GitHub auditor FastAPI server.

Usage:
    python run_api.py
    python run_api.py --port 8080

Endpoints:
    POST /audit/website   { "url": "https://example.com" }
    POST /audit/github    { "repo": "owner/repo" }
    GET  /health
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Growth tools API server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn
    uvicorn.run("api.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
