"""
System 4: Inbound website auditor.
User pastes app URL; detect stack from HTML/headers; generate production-readiness report.
"""
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
USER_AGENT = "GrowthToolsAuditor/1.0 (compatible; +https://github.com)"


def fetch_page(url: str) -> tuple[Optional[str], Optional[str], Optional[Dict], int]:
    """
    Fetch URL. Returns (html, final_url, headers_dict, status_code).
    """
    try:
        r = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
        r.raise_for_status()
        return r.text, r.url, dict(r.headers), r.status_code
    except requests.RequestException as e:
        logger.warning("fetch_page failed: %s", e)
        return None, None, None, getattr(e, "response", None) and getattr(e.response, "status_code", None) or 0


def detect_stack_from_html(html: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, bool]:
    """Detect likely tech stack from HTML and optional response headers."""
    headers = headers or {}
    html_lower = html.lower() if html else ""
    # Server header can reveal platform
    server = (headers.get("Server") or headers.get("x-powered-by") or "").lower()

    detected = {
        "nextjs": "__next" in html_lower or "_next/" in html_lower or "next.js" in server or "next" in html_lower[:2000],
        "vite": "/assets/" in html_lower and "modulepreload" in html_lower,
        "react": "react" in html_lower or "reactdom" in html_lower,
        "vue": "vue" in html_lower or "v-bind" in html_lower,
        "supabase": "supabase" in html_lower,
        "vercel": "vercel" in html_lower or "vercel" in server,
        "netlify": "netlify" in html_lower or "netlify" in server,
    }
    return detected


def infer_risks(detected: Dict[str, bool]) -> List[str]:
    """Suggest risks based on detected stack."""
    risks = []
    if detected.get("vite"):
        risks.append("Likely SPA (Vite): check rewrite rules and SEO/SSR if needed.")
    if detected.get("supabase"):
        risks.append("Supabase client: verify auth flow, RLS, and env key exposure in client.")
    if detected.get("react") and not detected.get("nextjs"):
        risks.append("Client-side React: consider SSR/SSG for SEO and first load.")
    if detected.get("vercel") or detected.get("netlify"):
        risks.append("Hosting on Vercel/Netlify: ensure env vars and serverless limits are documented.")
    if not risks:
        risks.append("Review security headers and CSP for production.")
    return risks


def audit_url(url: str) -> Dict[str, Any]:
    """
    Full audit: fetch URL, detect stack, return title, detected_stack, risks, next_step.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    html, final_url, headers, status = fetch_page(url)
    if html is None:
        return {
            "ok": False,
            "url": url,
            "error": "Could not fetch URL (timeout or HTTP error)",
            "status_code": status,
            "title": None,
            "detected_stack": {},
            "risks": [],
            "next_step": "Check URL and try again.",
        }

    soup = BeautifulSoup(html, "html.parser")
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()[:500]

    detected = detect_stack_from_html(html, headers)
    risks = infer_risks(detected)

    return {
        "ok": True,
        "url": final_url or url,
        "status_code": status,
        "title": title,
        "detected_stack": detected,
        "risks": risks,
        "next_step": "Connect GitHub repo for a deeper production audit and migration checklist.",
    }


if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    u = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    print(json.dumps(audit_url(u), indent=2))
