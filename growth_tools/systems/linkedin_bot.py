"""
LinkedIn engagement bot.

Searches LinkedIn for posts matching configurable keywords, generates
contextually relevant comments via GPT, and posts them — skipping
irrelevant posts (hiring, certifications, non-English, etc.).

Deduplicates via MD5 hash so it never comments on the same post twice.

Required env vars:
    OPENAI_API_KEY        OpenAI API key
    BRAND_NAME            Your brand name
    BRAND_URL             Your brand URL (included in comments when relevant)
    LINKEDIN_SEARCH_URL   Full LinkedIn search URL to scrape posts from
                          (default: agentic workflow + nocode posts by founders/CEOs)

Requires:
    - Chrome running with remote debugging: google-chrome --remote-debugging-port=9222
    - chromedriver on PATH (or set CHROMEDRIVER_PATH env var)
"""

import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Optional

from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

DEFAULT_SEARCH_URL = (
    "https://www.linkedin.com/search/results/content/"
    "?authorJobTitle=%22founder%20OR%20CEO%20OR%20CTO%22"
    "&datePosted=%22past-24h%22"
    "&keywords=%22agentic%20workflow%22%20OR%20%22ai-agent%22%20OR%20%22nocode%22"
    "&origin=FACETED_SEARCH&sortBy=%22date_posted%22"
)

PROCESSED_FILE = Path(os.environ.get("PROCESSED_POSTS_FILE", "processed_posts.txt"))

COMMENT_PROMPT = """
You generate professional LinkedIn comments for {brand_name} ({brand_url}), a platform relevant to no-code, workflow automation, AI agents, and internal tools.

Rules:
1. Only comment if the post is directly about: no-code, automation, platform building, internal tools, dashboards, AI, agentic AI.
   Skip: hiring announcements, certifications, personal milestones, non-English posts, job seekers.
2. Do not address the post author by name.
3. Professional, engaging, under 50 words.
4. If mentioning {brand_url}, include the full URL.
5. Sound human, not robotic.

Post content:
{post_content}

Return JSON only:
{{"comment_text": "..."}}

Return empty string for comment_text if the post should be skipped.
"""


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _load_processed() -> set:
    if not PROCESSED_FILE.exists():
        return set()
    return set(PROCESSED_FILE.read_text().splitlines())


def _save_processed(processed: set) -> None:
    PROCESSED_FILE.write_text("\n".join(processed))


def _remove_non_bmp(text: str) -> str:
    return "".join(c for c in text if ord(c) <= 0xFFFF)


def generate_comment(openai_client: OpenAI, post_content: str) -> str:
    brand_name = os.environ.get("BRAND_NAME", "our product")
    brand_url = os.environ.get("BRAND_URL", "")
    prompt = COMMENT_PROMPT.format(
        brand_name=brand_name,
        brand_url=brand_url,
        post_content=post_content,
    )
    resp = openai_client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7,
    )
    raw = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw).get("comment_text", "")


def run_bot(
    max_posts: int = 50,
    dry_run: bool = False,
    search_url: Optional[str] = None,
) -> int:
    """
    Run the LinkedIn engagement bot.

    Args:
        max_posts:  Maximum number of posts to collect and attempt to comment on.
        dry_run:    If True, generate comments but don't actually post them.
        search_url: Override the LinkedIn search URL.

    Returns:
        Number of comments successfully posted (or would have been posted in dry-run).
    """
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    service = Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)

    try:
        url = search_url or os.environ.get("LINKEDIN_SEARCH_URL", DEFAULT_SEARCH_URL)
        driver.get(url)
        time.sleep(2)

        processed = _load_processed()
        all_posts = []

        while len(all_posts) < max_posts:
            elements = driver.find_elements(
                By.XPATH, "//ul[@role='list']//li[contains(@class, 'artdeco-card')]"
            )
            if not elements:
                break
            for el in elements:
                content = el.text.strip()
                post_hash = _md5(content[:50])
                if post_hash in processed:
                    continue
                if any(p["md5"] == post_hash for p in all_posts):
                    continue
                all_posts.append({"element": el, "md5": post_hash, "content": content})
            if len(all_posts) < max_posts:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
            else:
                break

        posted = 0
        for post_data in all_posts:
            try:
                wait = random.randint(10, 60)
                comment = _remove_non_bmp(generate_comment(openai_client, post_data["content"]))
                processed.add(post_data["md5"])

                if not comment:
                    continue

                if dry_run:
                    print(f"[DRY RUN] Would comment: {comment[:80]}...")
                    posted += 1
                    continue

                post = post_data["element"]
                btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        post.find_element(By.CSS_SELECTOR, "button[aria-label='Comment']")
                    )
                )
                btn.click()
                box = post.find_element(By.CSS_SELECTOR, "div.ql-editor[contenteditable='true']")
                box.send_keys(comment)
                time.sleep(wait)
                submit = WebDriverWait(driver, wait).until(
                    EC.element_to_be_clickable(
                        post.find_element(By.CSS_SELECTOR, "button.comments-comment-box__submit-button--cr")
                    )
                )
                submit.click()
                time.sleep(wait)
                posted += 1

            except Exception as e:
                print(f"Error on post: {e}")
                driver.execute_script("arguments[0].scrollIntoView(true);", post_data["element"])
                time.sleep(10)

        _save_processed(processed)
        return posted

    finally:
        driver.quit()
