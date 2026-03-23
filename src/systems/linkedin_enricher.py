"""
LinkedIn lead enricher.

Reads a CSV of leads (with LinkedIn and Company LinkedIn columns), fetches
profile + recent posts + company info via linkedin-api, and scores each lead
with an LLM against your ICP.

Required env vars:
    LINKEDIN_EMAIL         LinkedIn account email (use a spare account)
    LINKEDIN_PASSWORD      LinkedIn account password
    OPENAI_API_KEY         OpenAI API key
    ICP_DESCRIPTION        Who you're targeting (e.g. "Sales managers with 5+ YOE")
    ICP_PAIN               Common problems your targets face
    BRAND_NAME             Your company name
    BRAND_DESCRIPTION      One-line description of your company

Output columns added to the CSV:
    user_rating      1–10 score for the individual
    company_rating   1–10 score for their company
    top_tools        Comma-separated tool suggestions
"""

import csv
import json
import math
import os
import time
from typing import Optional

import pandas as pd
from openai import OpenAI

SYSTEM_PROMPT = """
You are a lead qualification expert. Evaluate each lead against the ICP and company below.
Qualify whether the lead is a good fit for {brand_name}.
{brand_description}

RETURN ONLY THE REQUESTED JSON OUTPUT.
"""

USER_PROMPT = """
Analyze the user's profile and company to determine if they match this ICP:

ICP: {icp_description}

Common problems they face: {icp_pain}

Rate this lead 1–10 on fit as a potential customer.

User Profile:
{user_profile}

User Posts (last 10):
{user_posts}

Company Information:
{company_information}

Return JSON only:
{{
  "user_rating": <1-10>,
  "company_rating": <1-10>,
  "top_tools": [
    {{"tool_name": "...", "description": "... and how it helps this company"}}
  ]
}}
(max 3 tools)
"""


def _make_linkedin_client():
    from linkedin_api import Linkedin
    email = os.environ["LINKEDIN_EMAIL"]
    password = os.environ["LINKEDIN_PASSWORD"]
    return Linkedin(email, password)


def get_user_profile(api, public_id: str) -> dict:
    data = api.get_profile(public_id)
    return {
        "summary": data.get("summary", ""),
        "experience": [
            {"title": e.get("title", ""), "description": e.get("description", "")}
            for e in data.get("experience", [])
        ],
        "languages": [l.get("name", "") for l in data.get("languages", [])],
        "skills": [s.get("name", "") for s in data.get("skills", [])],
    }


def get_user_posts(api, public_id: str, post_count: int = 10) -> list:
    posts = api.get_profile_posts(public_id=public_id, post_count=post_count)
    return [
        p["commentary"]["text"]["text"]
        for p in posts
        if "commentary" in p and "text" in p.get("commentary", {})
    ]


def get_company_info(api, public_id: str) -> dict:
    data = api.get_company(public_id)
    hq = data.get("headquarter", {})
    return {
        "company_name": data.get("name", ""),
        "tagline": data.get("tagline", ""),
        "description": data.get("description", ""),
        "location": f"{hq.get('city', '')}, {hq.get('country', '')}",
        "website": data.get("companyPageUrl", ""),
        "industry": (data.get("companyIndustries") or [{}])[0].get("localizedName", ""),
        "staff_count": data.get("staffCount", 0),
        "founded_year": data.get("foundedOn", {}).get("year", ""),
    }


def score_lead(openai_client: OpenAI, profile: dict, posts: list, company: dict) -> dict:
    brand_name = os.environ.get("BRAND_NAME", "our company")
    brand_description = os.environ.get("BRAND_DESCRIPTION", "")
    icp_description = os.environ.get("ICP_DESCRIPTION", "")
    icp_pain = os.environ.get("ICP_PAIN", "")

    prompt = USER_PROMPT.format(
        icp_description=icp_description,
        icp_pain=icp_pain,
        user_profile=json.dumps(profile, indent=2),
        user_posts=json.dumps(posts, indent=2),
        company_information=json.dumps(company, indent=2),
    )
    system = SYSTEM_PROMPT.format(brand_name=brand_name, brand_description=brand_description)
    resp = openai_client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0,
    )
    raw = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "")
    return json.loads(raw)


def enrich_csv(input_path: str, output_path: Optional[str] = None) -> str:
    """
    Enrich a CSV of leads with LLM-generated ratings and tool suggestions.

    The CSV must have columns:
        - 'LinkedIn Link'          e.g. https://www.linkedin.com/in/johndoe
        - 'Company LinkedIn Link'  e.g. https://www.linkedin.com/company/acme

    Returns the path to the output CSV.
    """
    output_path = output_path or input_path
    api = _make_linkedin_client()
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    df = pd.read_csv(input_path)
    data = list(df.itertuples(index=True))

    for idx, row in df.iterrows():
        top_tools_val = row.get("top_tools", "")
        # Skip already-processed rows
        if top_tools_val and not (isinstance(top_tools_val, float) and math.isnan(top_tools_val)):
            continue

        li_link = row.get("LinkedIn Link", "")
        co_link = row.get("Company LinkedIn Link", "")
        li_id = li_link.rstrip("/").split("/")[-1] if li_link else None
        co_id = co_link.rstrip("/").split("/")[-1] if co_link else None

        if not li_id or not co_id:
            continue

        try:
            # Rate-limit to avoid LinkedIn blocks
            time.sleep(120)
            profile = get_user_profile(api, li_id)
            posts = get_user_posts(api, li_id, post_count=10)
            company = get_company_info(api, co_id)
            result = score_lead(openai_client, profile, posts, company)

            df.at[idx, "user_rating"] = result.get("user_rating", "")
            df.at[idx, "company_rating"] = result.get("company_rating", "")
            tools = result.get("top_tools", [])
            df.at[idx, "top_tools"] = ", ".join(
                f"{t['tool_name']}: {t['description']}"
                for t in tools
                if isinstance(t, dict)
            )
            df.to_csv(output_path, index=False)

        except Exception as e:
            print(f"Error processing row {idx}: {e}")

    df.to_csv(output_path, index=False)
    return output_path
