import os
import re
import json
import base64
import uuid
import time
from urllib.parse import urljoin, urlparse

import httpx
import requests
import tldextract
from bs4 import BeautifulSoup
from collections import deque
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# -----------------------------------------------------------------------------------
# SECTION 5: CONFIGURATION
# -----------------------------------------------------------------------------------
class Config:
    SITE_BUDGET_SECS = int(os.getenv("SITE_BUDGET_SECS", 60))
    SITE_MAX_BUDGET_SECS = int(os.getenv("SITE_MAX_BUDGET_SECS", 90))
    CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH = int(os.getenv("CRAWL_MAX_DEPTH", 2))
    BASIC_TIMEOUT_SECS = int(os.getenv("BASIC_TIMEOUT_SECS", 10))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 30))
    RENDER_MIN_LINKS = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

# Force render the homepage (recommended to ensure full DOM/screenshot)
FORCE_RENDER_HOMEPAGE = True

# -----------------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------------

def _clean_url(url: str) -> str:
    """Cleans and standardizes a URL."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]

def _reg_domain(u: str) -> str:
    """Return the registrable domain (example.com, example.co.uk)."""
    u = _clean_url(u)
    e = tldextract.extract(u)
    if not e.suffix:
        host = urlparse(u).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    return f"{e.domain}.{e.suffix}".lower()

def _is_same_domain(home: str, test: str) -> bool:
    """Checks if two URLs belong to the same registrable domain."""
    return _reg_domain(home) == _reg_domain(test)

def find_priority_page(discovered_links: list, keywords: list) -> str or None:
    """Searches a list of discovered links for the best match based on keywords."""
    for link_url, link_text in discovered_links:
        for keyword in keywords:
            if keyword in link_url.lower() or keyword in link_text.lower():
                return link_url
    return None

# -----------------------------------------------------------------------------------
# GDPR / Cookie banner handling (cookies + js_scenario)
# -----------------------------------------------------------------------------------

COMMON_CONSENT_COOKIES = {
    # OneTrust-style permissive cookie
    "onetrust": (
        "OptanonConsent=isIABGlobal=false&datestamp=2024-01-01T00:00:00.000Z"
        "&version=6.17.0&hosts=&consentId=00000000-0000-0000-0000-000000000000"
        "&interactionCount=0&landingPath=NotLandingPage&groups=1%3A1,2%3A1,3%3A1,4%3A1; "
        "OptanonAlertBoxClosed=2024-01-01T00:00:00.000Z"
    )
}

def guess_cmp_cookie(domain: str) -> str | None:
    # For now always return OneTrust fallback; extend later with heuristics.
    return COMMON_CONSENT_COOKIES["onetrust"]

JS_SCENARIO = [
    {"name": "wait", "args": {"duration": 1000}},
    {"name": "script", "args": {"code": r"""
        (function(){
          const selectors = [
            "button#onetrust-accept-btn-handler",
            "button[aria-label='Accept']",
            "button:has-text('Accept All')",
            "button:has-text('Accept all')",
            "button:has-text('I agree')",
            "button:has-text('Agree')",
            ".cookie-accept, .cookies-accept, .cc-allow, .cky-btn-accept"
          ];
          for (const sel of selectors) {
            try {
              const el = document.querySelector(sel);
              if (el) { el.click(); console.log('Clicked consent button', sel); }
            } catch(e){}
          }
        })();
    """}},
    {"name": "wait", "args": {"duration": 500}},
    {"name": "script", "args": {"code": r"""
        (function(){
          const kill = [
            "[id*=cookie]", "[class*=cookie]",
            "[id*=consent]", "[class*=consent]",
            "[id*=gdpr]", "[class*=gdpr]",
            "[id*=privacy]", "[class*=privacy]",
            "iframe[src*='consent']", "iframe[src*='cookie']"
          ];
          document.querySelectorAll(kill.join(',')).forEach(el => {
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
            el.style.setProperty('opacity', '0', 'important');
          });
          document.body.style.overflow = 'auto';
        })();
    """}}
]

def build_scrapingbee_params(url: str, render_js: bool, want_screenshot: bool) -> dict:
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    e = tldextract.extract(url)
    reg_domain = f"{e.domain}.{e.suffix}".lower()

    params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
        "wait": 3000,  # integer ms
        "js_scenario": json.dumps(JS_SCENARIO),
    }

    # Pre-seed consent cookie
    consent_cookie = guess_cmp_cookie(reg_domain)
    if consent_cookie:
        params["cookies"] = consent_cookie

    if want_screenshot:
        params.update({
            "screenshot": "true",
            "block_resources": "false",   # don't block images when screenshotting
            "window_width": 1280,
            "window_height": 1024,
            "screenshot_full_page": "false",
        })
    else:
        params["block_resources"] = "true"  # speed up HTML

    return params

# -----------------------------------------------------------------------------------
# SECTION 4: ARCHITECTURE (Fetchers, Policy, Extractor)
# -----------------------------------------------------------------------------------

class FetchResult:
    def __init__(self, url, html, status_code, from_renderer):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

_basic_client = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"},
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS
)

def basic_fetcher(url: str) -> FetchResult:
    """Performs a simple, fast HTTP GET request."""
    print(f"[BasicFetcher] Fetching {url}")
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)

def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    """Uses ScrapingBee to get HTML, rendering JS if necessary, with consent handling."""
    print(f"[ScrapingBeeHTML] Fetching {url} (render_js={render_js})")
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if not api_key:
        return FetchResult(url, "ScrapingBee API Key not set", 500, from_renderer=render_js)

    params = build_scrapingbee_params(url, render_js, want_screenshot=False)
    try:
        res = requests.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
        res.raise_for_status()
        return FetchResult(url, res.text, res.status_code, from_renderer=render_js)
    except requests.exceptions.HTTPError as he:
        body = he.response.text[:1000] if he.response is not None else ""
        print(f"[ScrapingBeeHTML] HTTP ERROR for {url}: {he.response.status_code if he.response else ''} {body}")
        return FetchResult(url, f"Failed via ScrapingBee: {body}", he.response.status_code if he.response else 500, from_renderer=render_js)
    except Exception as e:
        print(f"[ScrapingBeeHTML] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed via ScrapingBee: {e}", 500, from_renderer=render_js)

def scrapingbee_screenshot_fetcher(url: str, render_js: bool):
    """Uses ScrapingBee to get a screenshot, rendering JS if necessary, with consent handling."""
    print(f"[ScrapingBeeScreenshot] Fetching {url} (render_js={render_js})")
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if not api_key:
        return None

    params = build_scrapingbee_params(url, render_js, want_screenshot=True)
    try:
        res = requests.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
        res.raise_for_status()
        return base64.b64encode(res.content).decode("utf-8")
    except requests.exceptions.HTTPError as he:
        body = he.response.text[:1000] if he.response is not None else ""
        print(f"[ScrapingBeeScreenshot] HTTP ERROR for {url}: {he.response.status_code if he.response else ''} {body}")
        return None
    except Exception as e:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {e}")
        return None

def render_policy(result: FetchResult) -> (bool, str):
    """Decides if we need to use ScrapingBee based on improved heuristics."""
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

def social_extractor(soup, base_url):
    """Finds the best social media profile links."""
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = urljoin(base_url, best_link)
    return found_socials

# -----------------------------------------------------------------------------------
# AI Analysis Functions
# -----------------------------------------------------------------------------------

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
        Analyze the **Emotion** key. This is the primary key; without it, nothing is memorable.
        - **Your analysis must cover:** How the brand connects with audiences on an emotional level. Does it evoke warmth, trust, joy, or admiration? Does it use meaningful experiences, human stories, or mission-driven language? Is there a clear emotional reward for the user?
    """,
    "Attention": """
        Analyze the **Attention** key. This is a stimulus key.
        - **Your analysis must cover:** How the brand stands out and sustains interest. Evaluate its distinctiveness. Does it use surprising visuals or headlines? Does it create an authentic and engaging journey for the user, avoiding clichés and overuse of calls to action?
    """,
    "Story": """
        Analyze the **Story** key. This is a stimulus key.
        - **Your analysis must cover:** The clarity and power of the brand's narrative. Is there an authentic story that explains who the brand is and what it promises? Does this story build trust and pique curiosity more effectively than just facts and figures alone?
    """,
    "Involvement": """
        Analyze the **Involvement** key. This is a stimulus key.
        - **Your analysis must cover:** How the brand makes the audience feel like active participants. Does it connect to what is meaningful for them? Does it foster a sense of community or belonging? Does it make people feel included and empowered?
    """,
    "Repetition": """
        Analyze the **Repetition** key. This is a reinforcement key.
        - **Your analysis must cover:** The strategic reuse of brand elements. Are key symbols, taglines, colors, or experiences repeated consistently across touchpoints to reinforce memory and create new associations? Is this repetition thoughtful, or does it risk overexposure?
    """,
    "Consistency": """
        Analyze the **Consistency** key. This is a reinforcement key.
        - **Your analysis must cover:** The coherence of the brand across all touchpoints. Do the tone, message, and design feel aligned? Does this create a sense of familiarity, allowing the user's brain to recognize patterns and anticipate what to expect?
    """
}

def call_openai_for_synthesis(corpus):
    """Performs the AI pre-processing step to create a brand summary."""
    print("[AI] Synthesizing brand overview...")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        synthesis_prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n---\n"
            f"{corpus}\n---"
        )
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."
    finally:
        for key, value in original_proxies.items():
            if value is not None:
                os.environ[key] = value

def analyze_memorability_key(key_name, prompt_template, text_corpus, homepage_screenshot_b64, brand_summary):
    """Analyzes a single memorability key using the full context."""
    print(f"[AI] Analyzing key: {key_name}")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

        content = [
            {"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"},
            {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"}
        ]
        if homepage_screenshot_b64:
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{homepage_screenshot_b64}"}})

        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
{prompt_template}

Your response MUST be a JSON object with the following keys:
- "score": An integer from 0 to 100.
- "analysis": A comprehensive analysis of **at least five sentences** explaining your score, based on the specific criteria provided.
- "evidence": A single, direct quote from the text or a specific visual observation from the provided homepage screenshot.
- "confidence": An integer from 1 to 5.
- "confidence_rationale": A brief explanation for your confidence score.
- "recommendation": A concise, actionable recommendation for how the brand could improve its score for this specific key.
"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return key_name, json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        error_response = {
            "score": 0,
            "analysis": "Analysis failed due to a server error.",
            "evidence": str(e),
            "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Resolve the technical error to proceed."
        }
        return key_name, error_response
    finally:
        for key, value in original_proxies.items():
            if value is not None:
                os.environ[key] = value

def call_openai_for_executive_summary(all_analyses):
    """Generates the final executive summary based on all individual key analyses."""
    print("[AI] Generating Executive Summary...")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

        analyses_text = "\n\n".join([
            f"Key: {data['key']}\nScore: {data['analysis']['score']}\nAnalysis: {data['analysis']['analysis']}"
            for data in all_analyses
        ])

        summary_prompt = f"""You are a senior brand strategist delivering a final executive summary. Based on the following six key analyses, please provide:
1. **Overall Summary:** A brief, high-level overview of the brand's memorability performance.
2. **Key Strengths:** Identify the 2-3 strongest keys for the brand and explain why.
3. **Primary Weaknesses:** Identify the 2-3 weakest keys and explain the impact.
4. **Strategic Focus:** State the single most important key the brand should focus on to improve its overall memorability.

Here are the individual analyses to synthesize:
---
{analyses_text}
---
"""
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."
    finally:
        for key, value in original_proxies.items():
            if value is not None:
                os.environ[key] = value

# -----------------------------------------------------------------------------------
# Main Orchestrator
# -----------------------------------------------------------------------------------
def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed = []
    text_corpus = ""
    homepage_screenshot_b64 = None
    socials_found = False

    start_url = _clean_url(url)
    queue = deque([(start_url, 0)])
    seen_urls = {start_url}

    try:
        yield {'type': 'status', 'message': f'Scan initiated. Budget: {budget}s.'}

        while queue and len(pages_analyzed) < Config.CRAWL_MAX_PAGES:
            elapsed = time.time() - start_time
            if elapsed > budget:
                yield {'type': 'status', 'message': 'Time budget exceeded. Finalizing analysis.'}
                break

            current_url, depth = queue.popleft()
            yield {'type': 'status', 'message': f'Analyzing page {len(pages_analyzed) + 1}/{Config.CRAWL_MAX_PAGES}: {current_url}'}

            basic_result = basic_fetcher(current_url)
            final_result = basic_result

            if len(pages_analyzed) == 0 and FORCE_RENDER_HOMEPAGE:
                yield {'type': 'status', 'message': 'Force-rendering homepage with ScrapingBee...'}
                final_result = scrapingbee_html_fetcher(current_url, render_js=True)
            else:
                should_render, reason = render_policy(basic_result)
                if should_render:
                    yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                    final_result = scrapingbee_html_fetcher(current_url, render_js=True)

            screenshot_b64 = scrapingbee_screenshot_fetcher(current_url, render_js=final_result.from_renderer)
            if screenshot_b64:
                print(f"[DEBUG] Screenshot b64 length for {current_url}: {len(screenshot_b64)}")
                if len(pages_analyzed) == 0:
                    homepage_screenshot_b64 = screenshot_b64
                image_id = str(uuid.uuid4())
                cache[image_id] = screenshot_b64
                yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                # Strip script/style for the text corpus
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + soup.get_text(" ", strip=True)

                # Enqueue more links
                if depth < Config.CRAWL_MAX_DEPTH:
                    for a in soup.find_all("a", href=True):
                        href = a.get("href")
                        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                            continue
                        if Config.BINARY_RE.search(href):
                            continue
                        link_url = _clean_url(urljoin(current_url, href))
                        if not _is_same_domain(url, link_url) or link_url in seen_urls:
                            continue

                        remaining_slots = Config.CRAWL_MAX_PAGES - (len(pages_analyzed) + len(queue))
                        if remaining_slots <= 0:
                            break

                        queue.append((link_url, depth + 1))
                        seen_urls.add(link_url)

            pages_analyzed.append(final_result)

            elapsed = time.time() - start_time
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
            key_name, result_json = analyze_memorability_key(key, prompt, text_corpus, homepage_screenshot_b64, brand_summary)
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj

        yield {'type': 'status', 'message': 'Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {'type': 'summary', 'text': summary_text}
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
