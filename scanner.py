# scanner.py
import os
import re
import json
import time
import base64
import uuid
from collections import deque
from urllib.parse import urljoin

import httpx
import requests
import tldextract
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# -----------------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------------
class Config:
    # Crawl / time budgets
    SITE_BUDGET_SECS = int(os.getenv("SITE_BUDGET_SECS", 60))
    SITE_MAX_BUDGET_SECS = int(os.getenv("SITE_MAX_BUDGET_SECS", 90))
    CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH = int(os.getenv("CRAWL_MAX_DEPTH", 2))

    # Networking
    BASIC_TIMEOUT_SECS = int(os.getenv("BASIC_TIMEOUT_SECS", 10))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 30))
    SCRAPINGBEE_MAX_RETRIES = int(os.getenv("SCRAPINGBEE_MAX_RETRIES", 2))
    SCRAPINGBEE_BACKOFF_SECS = float(os.getenv("SCRAPINGBEE_BACKOFF_SECS", 1.5))
    # none|premium|stealth
    SCRAPINGBEE_PROXY_MODE = os.getenv("SCRAPINGBEE_PROXY_MODE", "none")

    # Heuristics
    RENDER_MIN_LINKS = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # Regex
    SOCIAL_PLATFORMS = {
        "twitter": re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+"),
    }
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)


# -----------------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------------
def _reg_domain(u: str) -> str:
    e = tldextract.extract(u)
    return f"{e.domain}.{e.suffix}".lower()

def _is_same_domain(home: str, test: str) -> bool:
    return _reg_domain(home) == _reg_domain(test)

def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]

def guess_cmp_cookie(reg_domain: str):
    # Stub for pre-consent cookie injection (return a cookie string if you have a mapping per domain)
    return None


# -----------------------------------------------------------------------------------
# FETCH CORE
# -----------------------------------------------------------------------------------
class FetchResult:
    def __init__(self, url: str, html: str, status_code: int, from_renderer: bool):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer


_basic_client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    },
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS,
)


def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] Fetching {url}")
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)


# -------- ScrapingBee js_scenario (evaluate + optional clicks) --------
def make_js_scenario() -> dict:
    cookie_selectors = [
        "#onetrust-accept-btn-handler",
        ".onetrust-accept-btn-handler",
        ".cookie-accept", ".cookies-accept", ".cc-allow", ".cky-btn-accept",
        "button[aria-label='Accept']",
        "button[aria-label='Accept all']",
        "button[name='accept']",
        "[data-testid='cookie-accept']"
    ]

    instructions = [{"wait": 1200}]
    for sel in cookie_selectors:
        instructions.append({"click": sel, "optional": True})

    instructions.append({"wait": 300})

    # Final kill pass: hide any left-over consent UI
    instructions.append({
        "evaluate": """
          (() => {
            const kill = [
              "[id*=cookie]", "[class*=cookie]",
              "[id*=consent]", "[class*=consent]",
              "[id*=gdpr]",   "[class*=gdpr]",
              "[id*=privacy]","[class*=privacy]",
              "iframe[src*='consent']",
              "iframe[src*='cookie']"
            ];
            try {
              document.querySelectorAll(kill.join(',')).forEach(el => {
                el.style.cssText = "display:none!important;visibility:hidden!important;opacity:0!important;";
              });
              document.body.style.overflow = "auto";
            } catch(e) {}
          })();
        """
    })

    instructions.append({"wait": 400})
    return {"instructions": instructions}


def build_scrapingbee_params(
    url: str,
    render_js: bool,
    want_screenshot: bool,
    include_cookies: bool = False,
    use_js_scenario: bool = True,
    wait_ms: int = 1000,
) -> dict:
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if not api_key:
        raise RuntimeError("SCRAPINGBEE_API_KEY not set")

    e = tldextract.extract(url)
    reg_domain = f"{e.domain}.{e.suffix}".lower()

    params: dict = {
        "api_key": api_key,
        "url": url,
        "render_js": render_js,
        "wait": wait_ms,
    }

    # Only add js_scenario for JS-rendered requests
    if use_js_scenario and render_js:
        params["js_scenario"] = json.dumps(make_js_scenario())

    if include_cookies:
        ck = guess_cmp_cookie(reg_domain)
        if ck:
            params["cookies"] = ck

    if want_screenshot:
        params.update({
            "screenshot": True,
            "block_resources": False,
            "window_width": 1280,
            "window_height": 1024,
            "screenshot_full_page": False,
        })
    else:
        params["block_resources"] = True

    mode = Config.SCRAPINGBEE_PROXY_MODE
    if mode == "premium":
        params["premium_proxy"] = True
    elif mode == "stealth":
        params["stealth_proxy"] = True

    return params


def _bee_request(url: str, *, render_js: bool, want_screenshot: bool,
                 include_cookies: bool, wait_ms: int, use_js_scenario: bool) -> requests.Response:
    params = build_scrapingbee_params(
        url,
        render_js=render_js,
        want_screenshot=want_screenshot,
        include_cookies=include_cookies,
        use_js_scenario=use_js_scenario,
        wait_ms=wait_ms
    )
    return requests.get(
        "https://app.scrapingbee.com/api/v1/",
        params=params,
        timeout=(10, Config.SCRAPINGBEE_TIMEOUT_SECS),
    )


def _bee_call_with_retries(url: str, *, render_js: bool, want_screenshot: bool):
    """
    Try:
      1) with js_scenario (if render_js=True)
      2) without js_scenario
    All screenshot calls will force render_js=True.
    """
    if want_screenshot and not render_js:
        render_js = True

    for attempt in range(Config.SCRAPINGBEE_MAX_RETRIES + 1):
        include_cookies = False
        wait_ms = 1000 if attempt == 0 else 3000
        use_js = (attempt == 0)  # first try: with scenario, second: without

        try:
            res = _bee_request(
                url,
                render_js=render_js,
                want_screenshot=want_screenshot,
                include_cookies=include_cookies,
                wait_ms=wait_ms,
                use_js_scenario=use_js
            )
            if res.status_code < 400:
                return res
            print(f"[ScrapingBee] HTTP {res.status_code} attempt={attempt} body={res.text[:500]}")
        except requests.exceptions.RequestException as e:
            print(f"[ScrapingBee] Exception attempt={attempt}: {e}")

        if attempt < Config.SCRAPINGBEE_MAX_RETRIES:
            time.sleep(Config.SCRAPINGBEE_BACKOFF_SECS * (attempt + 1))

    return None


def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    print(f"[ScrapingBeeHTML] Fetching {url} (render_js={render_js})")
    try:
        res = _bee_call_with_retries(url, render_js=render_js, want_screenshot=False)
        if not res:
            return FetchResult(url, "Failed via ScrapingBee after retries.", 500, from_renderer=render_js)
        return FetchResult(url, res.text, res.status_code, from_renderer=render_js)
    except Exception as e:
        print(f"[ScrapingBeeHTML] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed via ScrapingBee: {e}", 500, from_renderer=render_js)


def scrapingbee_screenshot_fetcher(url: str, render_js: bool) -> str:
    # Always render JS for screenshots
    render_js = True
    print(f"[ScrapingBeeScreenshot] Fetching {url} (render_js={render_js})")
    try:
        res = _bee_call_with_retries(url, render_js=render_js, want_screenshot=True)
        if not res or res.status_code >= 400:
            return None
        # Binary PNG → base64
        return base64.b64encode(res.content).decode("utf-8")
    except Exception as e:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {e}")
        return None


# -----------------------------------------------------------------------------------
# RENDER POLICY & EXTRACTORS
# -----------------------------------------------------------------------------------
def render_policy(result: FetchResult):
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


def social_extractor(soup: BeautifulSoup, base_url: str) -> dict:
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag["href"] for tag in soup.find_all("a", href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = urljoin(base_url, best_link)
    return found_socials


# -----------------------------------------------------------------------------------
# LLM PHASE
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


def _strip_proxies_temporarily():
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
    return proxy_keys, original


def _restore_proxies(proxy_keys, original):
    for k in proxy_keys:
        if original[k] is not None:
            os.environ[k] = original[k]


def call_openai_for_synthesis(corpus: str) -> str:
    print("[AI] Synthesizing brand overview...")
    proxy_keys, original = _strip_proxies_temporarily()
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n---\n"
            f"{corpus}\n---"
        )
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."
    finally:
        _restore_proxies(proxy_keys, original)


def analyze_memorability_key(key_name, prompt_template, text_corpus, homepage_screenshot_b64, brand_summary):
    print(f"[AI] Analyzing key: {key_name}")
    proxy_keys, original = _strip_proxies_temporarily()
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

        content = [
            {"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"},
            {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"},
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
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
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
    finally:
        _restore_proxies(proxy_keys, original)


def call_openai_for_executive_summary(all_analyses):
    print("[AI] Generating Executive Summary...")
    proxy_keys, original = _strip_proxies_temporarily()
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

        analyses_text = "\n\n".join(
            [f"Key: {d['key']}\nScore: {d['analysis']['score']}\nAnalysis: {d['analysis']['analysis']}"
             for d in all_analyses]
        )
        prompt = f"""You are a senior brand strategist delivering a final executive summary. Based on the following six key analyses, please provide:
1. **Overall Summary** – brief, high-level overview.
2. **Key Strengths** – the 2-3 strongest keys and why.
3. **Primary Weaknesses** – the 2-3 weakest keys and the impact.
4. **Strategic Focus** – the single most important key to improve.

Analyses:
---
{analyses_text}
---
"""
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."
    finally:
        _restore_proxies(proxy_keys, original)


# -----------------------------------------------------------------------------------
# MAIN ORCHESTRATOR (STREAM)
# -----------------------------------------------------------------------------------
def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed = []
    text_corpus = ""
    homepage_screenshot_b64 = None
    socials_found = False

    queue = deque([(_clean_url(url), 0)])
    seen_urls = {_clean_url(url)}

    try:
        yield {"type": "status", "message": f"Scan initiated. Budget: {budget}s."}

        while queue and len(pages_analyzed) < Config.CRAWL_MAX_PAGES:
            elapsed = time.time() - start_time
            if elapsed > budget:
                yield {"type": "status", "message": "Time budget exceeded. Finalizing analysis."}
                break

            current_url, depth = queue.popleft()
            yield {"type": "status", "message": f"Analyzing page {len(pages_analyzed)+1}/{Config.CRAWL_MAX_PAGES}: {current_url}"}

            basic_result = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_result)

            final_result = basic_result
            if should_render:
                yield {"type": "status", "message": f"Basic fetch insufficient ({reason}). Escalating to JS renderer..."}
                rendered_result = scrapingbee_html_fetcher(current_url, render_js=True)
                if 200 <= rendered_result.status_code < 400 and rendered_result.html.strip():
                    final_result = rendered_result

            screenshot_b64 = scrapingbee_screenshot_fetcher(current_url, render_js=final_result.from_renderer)
            if screenshot_b64:
                if len(pages_analyzed) == 0:
                    homepage_screenshot_b64 = screenshot_b64
                image_id = str(uuid.uuid4())
                cache[image_id] = screenshot_b64
                yield {"type": "screenshot_ready", "id": image_id, "url": current_url}

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {"type": "status", "message": f"Found social links: {list(found.values())}"}

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
                    yield {"type": "status", "message": f"High JS usage and no socials found → escalating budget to {budget}s."}

        yield {"type": "status", "message": "Crawl complete. Starting AI analysis..."}
        brand_summary = call_openai_for_synthesis(text_corpus)

        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {"type": "status", "message": f"Analyzing key: {key}..."}
            key_name, result_json = analyze_memorability_key(
                key, prompt, text_corpus, homepage_screenshot_b64, brand_summary
            )
            result_obj = {"type": "result", "key": key_name, "analysis": result_json}
            all_results.append(result_obj)
            yield result_obj

        yield {"type": "status", "message": "Generating Executive Summary..."}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {"type": "summary", "text": summary_text}
        yield {"type": "complete", "message": "Analysis finished."}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {"type": "error", "message": f"A critical error occurred: {e}"}
