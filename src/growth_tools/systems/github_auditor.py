"""
System 3: GitHub repo auditor.
User provides repo URL; system analyzes stack and suggests migration/production readiness.
Also scans GitHub search results for repos importing competitor SDKs (lead capture).
"""
import logging
import re
import sys
import time
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


# ─── Enhanced GitHub lead capture: competitor SDK scanning ────────────────────

def _score_repo_as_lead(repo: Dict[str, Any]) -> int:
    """
    Score a GitHub repo (from search results) as a potential lead.

    Factors:
      - stars (more = bigger team / more mature)
      - size (larger repos = more invested users)
      - recent activity (pushed in last 90 days)
      - has description (shows engagement)

    Returns 0–100.
    """
    score = 0

    stars = repo.get("stargazers_count", 0)
    if stars >= 100:
        score += 25
    elif stars >= 10:
        score += 15
    elif stars >= 1:
        score += 5

    size_kb = repo.get("size", 0)
    if size_kb >= 10_000:
        score += 20
    elif size_kb >= 1_000:
        score += 10
    elif size_kb >= 100:
        score += 5

    # Recent activity
    pushed_at = repo.get("pushed_at") or ""
    if pushed_at:
        try:
            from datetime import datetime, timezone
            pushed = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - pushed).days
            if age_days <= 30:
                score += 25
            elif age_days <= 90:
                score += 15
            elif age_days <= 180:
                score += 5
        except (ValueError, TypeError):
            pass

    if repo.get("description"):
        score += 10

    if not repo.get("fork", False):
        score += 10

    # Has open issues — active project
    if (repo.get("open_issues_count") or 0) > 0:
        score += 5

    return min(score, 100)


def search_competitor_sdk_repos(
    competitor_sdks: Optional[List[str]] = None,
    max_results_per_sdk: int = 30,
    min_score: int = 20,
) -> List[Dict[str, Any]]:
    """
    Search GitHub code for repos that import competitor SDKs.

    Uses the GitHub code search API to find files containing import statements
    for the given SDK names, then scores each repo as a potential lead.

    Parameters
    ----------
    competitor_sdks : list[str], optional
        SDK package names to search for.  Falls back to the growth config.
    max_results_per_sdk : int
        Max search results to process per SDK (GitHub caps at 100).
    min_score : int
        Minimum repo score (0–100) to include in results.

    Returns
    -------
    list[dict]
        Each dict has: owner, repo, url, stars, size_kb, pushed_at,
        description, competitor_sdk, lead_score, import_patterns_found.
    """
    if competitor_sdks is None:
        try:
            from growth_tools.config_loader import load_config
            cfg = load_config()
            competitor_sdks = cfg.competitor_sdks
        except Exception:
            competitor_sdks = [
                "firebase", "appwrite", "amplify", "supabase-js",
                "convex", "pocketbase", "nhost",
            ]

    headers = _github_headers()
    captured: List[Dict[str, Any]] = []
    seen_repos: set = set()

    for sdk in competitor_sdks:
        # Build search queries for common import patterns
        queries = [
            f"import {sdk}",
            f"from {sdk}",
            f"require('{sdk}')",
            f'require("{sdk}")',
        ]

        for query in queries:
            search_url = "https://api.github.com/search/code"
            params = {
                "q": query,
                "per_page": min(max_results_per_sdk, 100),
            }

            try:
                resp = requests.get(
                    search_url,
                    headers=headers,
                    params=params,
                    timeout=GITHUB_TIMEOUT,
                )

                # GitHub code search requires authentication and may 403
                if resp.status_code == 403:
                    logger.warning(
                        "GitHub code search 403 for SDK '%s' — "
                        "set GITHUB_TOKEN for authenticated search",
                        sdk,
                    )
                    break
                if resp.status_code == 422:
                    logger.debug("GitHub code search 422 for query '%s'", query)
                    continue
                if resp.status_code != 200:
                    logger.warning(
                        "GitHub code search returned %s for SDK '%s'",
                        resp.status_code, sdk,
                    )
                    continue

                data = resp.json()
                items = data.get("items") or []

                for item in items:
                    repo_data = item.get("repository") or {}
                    full_name = repo_data.get("full_name", "")

                    if not full_name or full_name in seen_repos:
                        continue
                    seen_repos.add(full_name)

                    # Fetch full repo info for scoring
                    owner, repo_name = full_name.split("/", 1)
                    repo_info = get_repo_info(owner, repo_name)
                    if not repo_info:
                        continue

                    lead_score = _score_repo_as_lead(repo_info)
                    if lead_score < min_score:
                        continue

                    captured.append({
                        "owner": owner,
                        "repo": repo_name,
                        "url": f"https://github.com/{full_name}",
                        "stars": repo_info.get("stargazers_count", 0),
                        "size_kb": repo_info.get("size", 0),
                        "pushed_at": repo_info.get("pushed_at"),
                        "description": (repo_info.get("description") or "")[:500],
                        "competitor_sdk": sdk,
                        "lead_score": lead_score,
                        "import_patterns_found": [query],
                        "language": repo_info.get("language"),
                        "open_issues": repo_info.get("open_issues_count", 0),
                        "is_fork": repo_info.get("fork", False),
                    })
                    logger.info(
                        "GitHub lead: %s (SDK: %s, score: %d)",
                        full_name, sdk, lead_score,
                    )

                # Rate-limit courtesy pause between queries
                time.sleep(1)

            except requests.RequestException as exc:
                logger.warning("GitHub code search failed for '%s': %s", query, exc)
                continue

    # Sort by lead score descending
    captured.sort(key=lambda r: r["lead_score"], reverse=True)
    return captured


def run_github_lead_capture(
    competitor_sdks: Optional[List[str]] = None,
    max_results_per_sdk: int = 30,
    min_score: int = 20,
    save_to_db: bool = True,
) -> List[Dict[str, Any]]:
    """
    Full GitHub lead capture: search for competitor SDK usage, score repos,
    optionally save to CRM.

    Returns list of captured lead dicts.
    """
    from core.scoring import score_lead, score_tier
    from core.db import save_lead, LeadRecord, is_db_available

    leads = search_competitor_sdk_repos(
        competitor_sdks=competitor_sdks,
        max_results_per_sdk=max_results_per_sdk,
        min_score=min_score,
    )

    use_db = save_to_db and is_db_available()
    if save_to_db and not use_db:
        logger.warning("Supabase not configured; GitHub leads will not be saved")

    for lead in leads:
        # Blend GitHub-specific score with the standard scoring model
        blended_score = score_lead(
            has_repo=True,
            pain_type="migrate",
            intent_score_from_llm=lead["lead_score"],
        )
        lead["lead_score"] = blended_score
        lead["tier"] = score_tier(blended_score)

        if use_db:
            try:
                record = LeadRecord(
                    source=f"github/{lead['competitor_sdk']}",
                    source_url=lead["url"],
                    title=f"{lead['owner']}/{lead['repo']}",
                    body=lead.get("description", ""),
                    platform="github",
                    intent_score=lead["lead_score"],
                    lead_score=blended_score,
                    score_tier=lead["tier"],
                    builder_detected=lead["competitor_sdk"],
                    pain_type="migrate",
                    status="new",
                    metadata={
                        "stars": lead["stars"],
                        "language": lead.get("language"),
                        "pushed_at": lead.get("pushed_at"),
                        "import_patterns": lead.get("import_patterns_found", []),
                    },
                )
                save_lead(record)
            except Exception as exc:
                logger.warning("Save GitHub lead failed: %s", exc)

    return leads


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        # Run competitor SDK scan
        sdks = sys.argv[2].split(",") if len(sys.argv) > 2 else None
        results = search_competitor_sdk_repos(competitor_sdks=sdks)
        print(f"\nFound {len(results)} repos importing competitor SDKs.")
        for r in results:
            print(f"  {r['url']} | SDK: {r['competitor_sdk']} | score: {r['lead_score']}")
    else:
        url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/vercel/next.js"
        result = analyze_repo_url(url)
        print(json.dumps(result, indent=2))
