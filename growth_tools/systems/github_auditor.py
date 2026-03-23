"""
System 3: GitHub repo auditor.
User provides repo URL; system analyzes stack and suggests migration/production readiness.
"""
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logger = logging.getLogger(__name__)

# Timeouts and retries
GITHUB_TIMEOUT = 25
GITHUB_HEADERS: Optional[Dict[str, str]] = None


def _github_headers() -> Dict[str, str]:
    global GITHUB_HEADERS
    if GITHUB_HEADERS is not None:
        return GITHUB_HEADERS
    import os
    token = os.getenv("GITHUB_TOKEN")
    h = {"Accept": "application/vnd.github+json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    GITHUB_HEADERS = h
    return h


def parse_repo_url(url: str) -> Optional[tuple[str, str]]:
    """Return (owner, repo) or None if invalid."""
    url = url.strip().rstrip("/")
    # https://github.com/owner/repo or github.com/owner/repo
    m = re.match(r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url, re.I)
    if m:
        return m.group(1), m.group(2)
    # owner/repo
    if "/" in url and " " not in url and len(url) < 100:
        parts = url.split("/", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return parts[0], parts[1]
    return None


def get_repo_tree(owner: str, repo: str) -> List[Dict[str, Any]]:
    """Fetch repo file tree (recursive). Raises on HTTP error."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    r = requests.get(url, headers=_github_headers(), timeout=GITHUB_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return data.get("tree") or []


def get_repo_info(owner: str, repo: str) -> Dict[str, Any]:
    """Fetch repo metadata (description, default branch, etc.)."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    r = requests.get(url, headers=_github_headers(), timeout=GITHUB_TIMEOUT)
    if r.status_code != 200:
        return {}
    return r.json()


def get_readme(owner: str, repo: str) -> Optional[str]:
    """Fetch README content if present."""
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    r = requests.get(url, headers={**_github_headers(), "Accept": "application/vnd.github.raw"}, timeout=GITHUB_TIMEOUT)
    if r.status_code != 200:
        return None
    return r.text[:8000]


def analyze_repo(owner: str, repo: str) -> Dict[str, Any]:
    """
    Analyze repo structure and return detected stack, missing items, and migration suggestions.
    """
    try:
        tree = get_repo_tree(owner, repo)
    except requests.RequestException as e:
        logger.warning("get_repo_tree failed: %s", e)
        return {
            "ok": False,
            "error": str(e),
            "detected": {},
            "missing": [],
            "suggestions": ["Could not fetch repo; check URL and token."],
        }

    paths = [item["path"] for item in tree]
    detected = {
        "nextjs": any(
            p in paths for p in ("next.config.js", "next.config.mjs", "next.config.ts")
        ),
        "vite": any(
            p in paths for p in ("vite.config.ts", "vite.config.js", "vite.config.mts")
        ),
        "react": False,
        "docker": any(p in paths for p in ("Dockerfile", "Dockerfile.dev")),
        "github_actions": any(p.startswith(".github/workflows/") for p in paths),
        "supabase": any("supabase" in p.lower() for p in paths),
        "vercel": "vercel.json" in paths or any(p.startswith(".vercel") for p in paths),
        "env_example": ".env.example" in paths or "env.example" in paths,
    }

    if "package.json" in paths:
        try:
            content = _fetch_file_content(owner, repo, "package.json")
            if content and "react" in content.lower():
                detected["react"] = True
        except Exception:
            pass
    if not detected["react"] and "react" in " ".join(paths).lower():
        detected["react"] = True

    missing = []
    if not detected["docker"]:
        missing.append("No Dockerfile found — containerization recommended for production.")
    if not detected["github_actions"]:
        missing.append("No GitHub Actions workflows — consider adding CI/CD.")
    if not detected["env_example"]:
        missing.append("No .env.example — document required env vars for deployment.")

    suggestions = []
    if detected["vite"] and not detected["docker"]:
        suggestions.append("Vite SPA: add Dockerfile and ensure server rewrite rules for SPA routing.")
    if detected["supabase"]:
        suggestions.append("Supabase: verify RLS, auth flow, and env key exposure in client.")
    if detected["nextjs"]:
        suggestions.append("Next.js: check output mode (standalone/docker) and env at build time.")

    return {
        "ok": True,
        "owner": owner,
        "repo": repo,
        "detected": detected,
        "missing": missing,
        "suggestions": suggestions or ["Review security and env handling before production."],
        "repo_info": get_repo_info(owner, repo),
    }


def _fetch_file_content(owner: str, repo: str, path: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    r = requests.get(url, headers=_github_headers(), timeout=GITHUB_TIMEOUT)
    if r.status_code != 200:
        return None
    data = r.json()
    if data.get("encoding") == "base64":
        import base64
        return base64.b64decode(data.get("content", "")).decode("utf-8", errors="ignore")
    return None


def analyze_repo_url(repo_url: str) -> Dict[str, Any]:
    """Convenience: parse URL and run analyze_repo."""
    parsed = parse_repo_url(repo_url)
    if not parsed:
        return {
            "ok": False,
            "error": "Invalid GitHub repo URL or owner/repo",
            "detected": {},
            "missing": [],
            "suggestions": [],
        }
    return analyze_repo(parsed[0], parsed[1])


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/vercel/next.js"
    result = analyze_repo_url(url)
    print(json.dumps(result, indent=2))
