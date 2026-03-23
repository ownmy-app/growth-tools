"""
FastAPI app: website auditor + GitHub repo auditor.
Run: uvicorn api.main:app --reload (from growth-tools dir)
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from systems.website_auditor import audit_url as website_audit
from systems.github_auditor import analyze_repo_url as github_audit
from systems.crm_sequencer import add_lead
from core.db import is_db_available

app = FastAPI(
    title="Growth Tools API",
    description="Website auditor & GitHub repo auditor for production-readiness.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AuditWebsiteRequest(BaseModel):
    url: str
    save_as_lead: bool = False


class AuditGitHubRequest(BaseModel):
    repo_url: str


@app.get("/health")
def health():
    return {"status": "ok", "db": is_db_available()}


@app.post("/audit/website")
def audit_website(req: AuditWebsiteRequest):
    """Paste app URL; returns detected stack, risks, and next step. Optionally saves as lead."""
    if not req.url or len(req.url) > 2048:
        raise HTTPException(status_code=400, detail="Invalid URL")
    result = website_audit(req.url)
    if req.save_as_lead and result.get("ok") and is_db_available():
        try:
            lead = add_lead(
                source=result.get("url", req.url),
                source_url=result.get("url", req.url),
                title=result.get("title"),
                platform="website",
                pain_type="audit",
                intent_score=50,
                metadata={"audit": result},
            )
            if lead:
                result["lead_id"] = lead.get("id")
        except Exception:
            pass
    return result


@app.post("/audit/github")
def audit_github(req: AuditGitHubRequest):
    """Provide repo URL; returns detected stack, missing items, migration suggestions."""
    if not req.repo_url or len(req.repo_url) > 2048:
        raise HTTPException(status_code=400, detail="Invalid repo URL")
    return github_audit(req.repo_url)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
