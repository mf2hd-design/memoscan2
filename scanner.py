#!/usr/bin/env python3
import os
import re
import uuid
import time
import base64
import json
import threading
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Iterable, Generator, Optional

import httpx
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# =====================================================================================
# GLOBAL, SHARED, IN-MEMORY CACHE (screenshots etc.)  <-- imported by app.py
# =====================================================================================
SHARED_CACHE: Dict[str, dict] = {}

# =====================================================================================
# CONFIG
# =====================================================================================

class Config:
    # Budgets
    SITE_BUDGET_SECS         = int(os.getenv("SITE_BUDGET_SECS", 60))
    SITE_MAX_BUDGET_SECS     = int(os.getenv("SITE_MAX_BUDGET_SECS", 90))

    # Crawl
    CRAWL_MAX_PAGES          = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH          = int(os.getenv("CRAWL_MAX_DEPTH", 2))

    # Timeouts
    BASIC_TIMEOUT_SECS       = int(os.getenv("BASIC_TIMEOUT_SECS", 10))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 30))

    # Heuristics
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))

    # LLM
    OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o")
    MAX_SCREENSHOTS_FOR_LLM  = int(os.getenv("MAX_SCREENSHOTS_FOR_LLM", 3))

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY")
    SB_MAX_RETRIES           = int(os.getenv("SB_MAX_RETRIES", 3))
    SB_USE_PREMIUM_ON_500    = os.getenv("SB_USE_PREMIUM_ON_500", "false").lower() == "true"
    SB_USE_STEALTH_ON_500    = os.getenv("SB_USE_STEALTH_ON_500", "false").lower() == "true"

    # Misc
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)


# =====================================================================================
# DATA TYPES
# =====================================================================================

@dataclass
class FetchResult:
    url: str
    html: str
    status_code: int
    from_renderer: bool


# =====================================================================================
# HTTP CLIENTS
# =====================================================================================

_basic_client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    },
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS
)


# =====================================================================================
# HELPERS
# =====================================================================================

def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]


def _host(u: str) -> str:
    return urlparse(u).netloc.lower()


def _is_same_domain(home: str, test: str) -> bool:
    return _host(home) == _host(test)


def _data_uri_from_bytes(raw_bytes: bytes, fmt: str = "png") -> str:
    b64 = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:image/{fmt};base64,{b64}"


def social_extractor(soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = urljoin(base_url, best_link)
    return found_socials


def render_policy(result: FetchResult) -> Tuple[bool, str]:
    if result.status_code >= 400:
        return True, "http_error"
    soup = BeautifulSoup(result.html, "lxml")
    visible_text_len = len(soup.get_text(" ", strip=True))
    if visible_text_len < Config.RENDER_MIN_TEXT_BYTES:
        return True, "small_text"
    if len(soup.find_all("a", href=True)) < Config.RENDER_MIN_LINKS:
        return True, "few_links"
    lower_html = result.html.lower()
    for signal in Config.SPA_SIGNALS:
        if signal in lower_html:
            return True, "spa_signal"
    return False, "ok"


# =====================================================================================
# FETCHERS
# =====================================================================================

def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] {url}")
    try:
        res = _basic_client.get(url)
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)


def _scrapingbee_request(
    url: str,
    render_js: bool,
    screenshot: bool,
    with_js: bool,
    escalate_proxy: bool
) -> requests.Response:
    """
    Low-level ScrapingBee call with retries. Returns the Response object.
    """
    if not Config.SCRAPINGBEE_API_KEY:
        raise RuntimeError("No SCRAPINGBEE_API_KEY configured")

    base_params = {
        "api_key": Config.SCRAPINGBEE_API_KEY,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "true" if not screenshot else "false",
        "timeout": Config.SCRAPINGBEE_TIMEOUT_SECS * 1000,  # ms
    }

    # screenshot flags
    if screenshot:
        base_params["screenshot"] = "true"
        base_params["screenshot_full_page"] = "false"
        base_params["window_width"] = 1280
        base_params["window_height"] = 1024

    # remove fields ScrapingBee doesn't like for HTML (avoid 400 format/response_format)
    # we only use raw bytes for screenshot, HTML for html.

    # optional premium/stealth
    if escalate_proxy and Config.SB_USE_PREMIUM_ON_500:
        base_params["premium_proxy"] = "true"
    if escalate_proxy and Config.SB_USE_STEALTH_ON_500:
        base_params["stealth_proxy"] = "true"

    # cookie banner killer JS (in a single "script" instruction to avoid schema issues)
    js_instructions = None
    if with_js:
        js_code = r"""
        (function(){
          try {
            const textNeedles = [
              'accept','agree','allow','permitir','zulassen','consent','cookies',
              'ok','got it','dismiss','yes'
            ];
            const clickByText = (tag) => {
              const els = document.querySelectorAll(tag);
              for (const el of els) {
                const txt = (el.innerText || el.textContent || '').toLowerCase();
                for (const n of textNeedles) {
                  if (txt.includes(n)) {
                    try { el.click(); return true; } catch(e){}
                  }
                }
              }
              return false;
            };
            const cssSelectors = [
              '#onetrust-accept-btn-handler','.onetrust-accept-btn-handler',
              '#CybotCookiebotDialogBodyLevelButtonAccept','#cookie-accept',
              '.cookie-accept','.cookies-accept','.cc-allow','.cky-btn-accept',
              '[data-testid="cookie-accept"]','button[aria-label="Accept"]',
              'button[aria-label="I agree"]'
            ];
            for (const sel of cssSelectors){
              const el = document.querySelector(sel);
              if (el) { try { el.click(); } catch(e){} }
            }
            clickByText('button') || clickByText('a');

            const kill = [
              "[id*='cookie']", "[class*='cookie']",
              "[id*='consent']", "[class*='consent']",
              "[id*='gdpr']",   "[class*='gdpr']",
              "[id*='privacy']","[class*='privacy']",
              "iframe[src*='consent']", "iframe[src*='cookie']"
            ];
            document.querySelectorAll(kill.join(',')).forEach(el => {
              try {
                el.style.cssText="display:none!important;visibility:hidden!important;opacity:0!important;pointer-events:none!important;";
              } catch(e){}
            });
            document.body && (document.body.style.overflow = 'auto');
          } catch(e) {}
        })();
        """.strip()

        js_instructions = {"instructions": [{"script": {"code": js_code}}]}

    for attempt in range(Config.SB_MAX_RETRIES):
        try:
            params = dict(base_params)
            if js_instructions:
                params["js_scenario"] = json.dumps(js_instructions)  # MUST be JSON string for SB strict schema
            res = requests.get(
                "https://app.scrapingbee.com/api/v1/",
                params=params,
                timeout=Config.SCRAPINGBEE_TIMEOUT_SECS
            )
            if res.status_code >= 500 and attempt == 0 and not escalate_proxy:
                # retry with escalate if configured
                if Config.SB_USE_PREMIUM_ON_500 or Config.SB_USE_STEALTH_ON_500:
                    return _scrapingbee_request(url, render_js, screenshot, with_js, escalate_proxy=True)
            res.raise_for_status()
            return res
        except requests.exceptions.HTTPError as he:
            try:
                body = he.response.text[:500]
            except Exception:
                body = ""
            print(f"[ScrapingBee] HTTP {he.response.status_code} attempt={attempt} body={body}")
            if attempt == Config.SB_MAX_RETRIES - 1:
                raise
        except Exception as e:
            print(f"[ScrapingBee] EXC attempt={attempt} {e}")
            if attempt == Config.SB_MAX_RETRIES - 1:
                raise

    raise RuntimeError("ScrapingBee failed after retries")


def scrapingbee_html_fetcher(url: str, render_js: bool = True, with_js: bool = True) -> FetchResult:
    try:
        res = _scrapingbee_request(url, render_js=render_js, screenshot=False, with_js=with_js, escalate_proxy=False)
        return FetchResult(url, res.text, res.status_code, from_renderer=True)
    except Exception as e:
        print(f"[ScrapingBeeHTML] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed via ScrapingBee: {e}", 500, from_renderer=True)


def scrapingbee_screenshot_fetcher(url: str, render_js: bool = True, with_js: bool = True) -> List[Tuple[str, bytes]]:
    """
    Returns a list of (mime, raw_bytes).
    """
    try:
        res = _scrapingbee_request(url, render_js=render_js, screenshot=True, with_js=with_js, escalate_proxy=False)
        # ScrapingBee returns the image bytes directly
        mime = "image/png"
        return [(mime, res.content)]
    except Exception as e:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {e}")
        return []


# =====================================================================================
# LLM PROMPTS
# =====================================================================================

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
Analyze the **Emotion** key. This is the primary key; without it, nothing is memorable.
Cover: the emotional connection, warmth/trust/joy/admiration, human stories, mission-driven language, emotional reward.
""",
    "Attention": """
Analyze the **Attention** key (stimulus).
Cover: distinctiveness, ability to stand out, surprising visuals/headlines, authentic journey, avoidance of cliché CTA spam.
""",
    "Story": """
Analyze the **Story** key (stimulus).
Cover: clarity and power of the narrative, authenticity, trust-building beyond facts, curiosity.
""",
    "Involvement": """
Analyze the **Involvement** key (stimulus).
Cover: sense of participation, meaning for the audience, community/belonging, inclusion and empowerment.
""",
    "Repetition": """
Analyze the **Repetition** key (reinforcement).
Cover: strategic reuse of brand elements, symbols/taglines/colors across touchpoints, thoughtful vs. overexposure.
""",
    "Consistency": """
Analyze the **Consistency** key (reinforcement).
Cover: coherence across touchpoints; tone, message and design alignment; recognisable patterns and expectations.
"""
}

def call_openai_for_synthesis(corpus: str) -> str:
    print("[AI] Synthesizing brand overview...")
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=httpx.Client(proxies=None))
        prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n---\n" + corpus + "\n---"
        )
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."


def analyze_memorability_key(
    key_name: str,
    prompt_template: str,
    text_corpus: str,
    brand_summary: str,
    images_data_uris: List[str]
):
    print(f"[AI] Analyzing key: {key_name}")
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=httpx.Client(proxies=None))

        content: List[dict] = []
        # attach up to MAX_SCREENSHOTS_FOR_LLM images
        for uri in images_data_uris[:Config.MAX_SCREENSHOTS_FOR_LLM]:
            content.append({"type": "image_url", "image_url": {"url": uri}})

        content.append({"type": "text", "text": f"FULL CORPUS:\n---\n{text_corpus}\n---"})
        content.append({"type": "text", "text": f"BRAND SUMMARY:\n---\n{brand_summary}\n---"})

        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
{prompt_template}

Your response MUST be a JSON object with the following keys:
- "score": An integer from 0 to 100.
- "analysis": A comprehensive analysis of **at least five sentences** explaining your score, based on the specific criteria provided.
- "evidence": A single, direct quote or specific visual observation.
- "confidence": An integer from 1 to 5.
- "confidence_rationale": A brief explanation.
- "recommendation": A concise, actionable recommendation to improve this key.
"""

        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return key_name, json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        return key_name, {
            "score": 0,
            "analysis": "Analysis failed due to a server error.",
            "evidence": str(e),
            "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Resolve the technical error to proceed."
        }


def call_openai_for_executive_summary(all_analyses: List[dict]) -> str:
    print("[AI] Generating Executive Summary...")
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=httpx.Client(proxies=None))

        analyses_text = "\n\n".join(
            [f"Key: {d['key']}\nScore: {d['analysis']['score']}\nAnalysis: {d['analysis']['analysis']}" for d in all_analyses]
        )
        prompt = f"""You are a senior brand strategist delivering a final executive summary. Based on the six analyses:

1) **Overall Summary** – a high-level overview of the brand's memorability performance.
2) **Key Strengths** – 2-3 strongest keys and why.
3) **Primary Weaknesses** – 2-3 weakest keys and impact.
4) **Strategic Focus** – the single most important key to improve next.

---
{analyses_text}
---
"""
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."


# =====================================================================================
# MAIN ORCHESTRATOR
# =====================================================================================

def run_full_scan_stream(url: str, cache: Dict[str, dict]) -> Generator[dict, None, None]:
    start = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed: List[FetchResult] = []
    text_corpus = ""
    images_for_llm: List[str] = []   # store data URIs only for the LLM
    socials_found = False

    queue = deque([(_clean_url(url), 0)])
    seen = {_clean_url(url)}

    try:
        yield {'type': 'status', 'message': f'Scan initiated. Budget: {budget}s.'}

        while queue and len(pages_analyzed) < Config.CRAWL_MAX_PAGES:
            elapsed = time.time() - start
            if elapsed > budget:
                yield {'type': 'status', 'message': 'Time budget exceeded. Finalizing analysis.'}
                break

            current_url, depth = queue.popleft()
            yield {'type': 'status', 'message': f'Analyzing page {len(pages_analyzed)+1}/{Config.CRAWL_MAX_PAGES}: {current_url}'}

            basic_result = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_result)
            final_result = basic_result

            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                final_result = scrapingbee_html_fetcher(current_url, render_js=True, with_js=True)
                if not (200 <= final_result.status_code < 400) or not final_result.html.strip():
                    # fallback w/out js_scenario
                    final_result = scrapingbee_html_fetcher(current_url, render_js=True, with_js=False)

            # screenshots
            shots = scrapingbee_screenshot_fetcher(current_url, render_js=True, with_js=True)
            if not shots:
                shots = scrapingbee_screenshot_fetcher(current_url, render_js=True, with_js=False)

            for mime, raw_bytes in shots:
                # store in cache as raw bytes
                image_id = str(uuid.uuid4())
                cache[image_id] = {"mime": mime, "bytes": raw_bytes}
                yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

                # create data URI only for the LLM
                if len(images_for_llm) < Config.MAX_SCREENSHOTS_FOR_LLM:
                    images_for_llm.append(_data_uri_from_bytes(raw_bytes, fmt="png"))

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                for tag in soup(["script", "style"]):
                    tag.decompose()

                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + soup.get_text(" ", strip=True)

                if depth < Config.CRAWL_MAX_DEPTH:
                    for a in soup.find_all("a", href=True):
                        href = a.get("href")
                        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                            continue
                        if Config.BINARY_RE.search(href):
                            continue
                        link_url = _clean_url(urljoin(current_url, href))
                        if not _is_same_domain(url, link_url) or link_url in seen:
                            continue

                        remaining = Config.CRAWL_MAX_PAGES - (len(pages_analyzed) + len(queue))
                        if remaining <= 0:
                            break

                        queue.append((link_url, depth + 1))
                        seen.add(link_url)

            pages_analyzed.append(final_result)

            elapsed = time.time() - start
            if not escalated and elapsed < budget:
                pages_rendered_by_bee = sum(1 for p in pages_analyzed if p.from_renderer)
                if len(pages_analyzed) >= 3 and pages_rendered_by_bee >= 2 and not socials_found:
                    budget = Config.SITE_MAX_BUDGET_SECS
                    escalated = True
                    yield {'type': 'status', 'message': f'High JS usage and no socials found → escalating budget to {budget}s.'}

        yield {'type': 'status', 'message': 'Crawl complete. Starting AI analysis...'}
        brand_summary = call_openai_for_synthesis(text_corpus)

        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                key, prompt, text_corpus, brand_summary, images_for_llm
            )
            obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(obj)
            yield obj

        yield {'type': 'status', 'message': 'Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {'type': 'summary', 'text': summary_text}
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
