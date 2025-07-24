import os
import re
import json
import base64
import uuid
import time
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

try:
    import tldextract
except ImportError:
    tldextract = None  # fallback

load_dotenv()

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

    # Render heuristics
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # Images to pass to LLM
    MAX_SCREENSHOTS_FOR_LLM  = int(os.getenv("MAX_SCREENSHOTS_FOR_LLM", 3))

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY", "")
    # Costly, off by default; only use on last retry if allowed:
    SCRAPINGBEE_USE_PREMIUM  = os.getenv("SCRAPINGBEE_USE_PREMIUM", "false").lower() == "true"
    SCRAPINGBEE_USE_STEALTH  = os.getenv("SCRAPINGBEE_USE_STEALTH", "false").lower() == "true"

    # Screenshot options
    SCREENSHOT_FULL_PAGE     = os.getenv("SCREENSHOT_FULL_PAGE", "false").lower() == "true"

    # Regexes
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

    # LLM model
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

# =====================================================================================
# UTIL / HELPERS
# =====================================================================================

def _registrable_host(u: str) -> str:
    if not tldextract:
        host = urlparse(u).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    e = tldextract.extract(u)
    dom = f"{e.domain}.{e.suffix}".lower()
    return dom if dom != "." else urlparse(u).netloc.lower()

def _is_same_domain(home: str, test: str) -> bool:
    return _registrable_host(home) == _registrable_host(test)

def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]

def _is_valid_data_uri_img(uri: str) -> bool:
    return uri.startswith("data:image/png;base64,") or \
           uri.startswith("data:image/jpeg;base64,") or \
           uri.startswith("data:image/webp;base64,") or \
           uri.startswith("data:image/gif;base64,")

def _strip_scripts_and_styles(soup: BeautifulSoup):
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup

def _extract_visual_hints(html: str):
    fonts = set()
    colors = set()

    font_re = re.compile(r"font-family\s*:\s*([^;]+);", re.I)
    for m in font_re.finditer(html):
        v = m.group(1)
        parts = [p.strip().strip("'\"") for p in v.split(",")]
        for p in parts:
            if p.lower() not in ("sans-serif", "serif", "monospace"):
                fonts.add(p)

    hex_re = re.compile(r"#[0-9a-fA-F]{3,8}")
    for m in hex_re.finditer(html):
        colors.add(m.group(0).lower())

    var_re = re.compile(r"--[\w-]+\s*:\s*(#[0-9a-fA-F]{3,8})", re.I)
    for m in var_re.finditer(html):
        colors.add(m.group(1).lower())

    return {
        "fonts": list(sorted(fonts))[:15],
        "colors": list(sorted(colors))[:15],
    }

def _data_uri_from_bytes(b: bytes, fmt="png"):
    return f"data:image/{fmt};base64,{base64.b64encode(b).decode('utf-8')}"

# =====================================================================================
# FETCHERS
# =====================================================================================

class FetchResult:
    def __init__(self, url: str, html: str, status_code: int, from_renderer: bool):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

_basic_client = httpx.Client(
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            " AppleWebKit/537.36 (KHTML, like Gecko)"
            " Chrome/120.0.0.0 Safari/537.36"
        )
    },
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS
)

def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] {url}")
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)

# ------------------------- ScrapingBee helpers -------------------------

def _scrapingbee_js_scenario():
    """
    We ONLY use wait + evaluate (no click steps) to avoid schema issues.
    The evaluate script:
      - tries to click common selectors
      - falls back to text-based clicking (accept/agree/allow/zulassen/permitir…)
      - hides remaining overlays
    """
    text_needles = [
        "accept", "agree", "allow", "zulassen", "permitir", "consent",
        "cookies", "ok", "got it", "dismiss", "yes"
    ]

    script = f"""
(function(){{
  try {{
    const needles = {json.dumps(text_needles)};
    const tryClickByText = (tag) => {{
      const els = document.querySelectorAll(tag);
      for (const el of els) {{
        const txt = (el.innerText || el.textContent || '').toLowerCase();
        for (const n of needles) {{
          if (txt.includes(n)) {{
            try {{ el.click(); console.log('clicked text', txt); return true; }} catch (e) {{}}
          }}
        }}
      }}
      return false;
    }};

    const selectors = [
      "#onetrust-accept-btn-handler",
      ".onetrust-accept-btn-handler",
      "#CybotCookiebotDialogBodyLevelButtonAccept",
      ".cookie-accept",
      ".cookies-accept",
      ".cc-allow",
      ".cky-btn-accept",
      "button[aria-label='Accept']",
      "button[aria-label='I agree']"
    ];

    for (const sel of selectors) {{
      try {{
        const el = document.querySelector(sel);
        if (el) {{ el.click(); console.log('clicked sel', sel); }}
      }} catch(e) {{}}
    }}

    tryClickByText('button');
    tryClickByText('a');
    tryClickByText('[role=button]');

    const kill = [
      "[id*='cookie']", "[class*='cookie']",
      "[id*='consent']", "[class*='consent']",
      "[id*='gdpr']",   "[class*='gdpr']",
      "[id*='privacy']","[class*='privacy']",
      "iframe[src*='consent']", "iframe[src*='cookie']"
    ];
    document.querySelectorAll(kill.join(',')).forEach(el => {{
      el.style.setProperty('display','none','important');
      el.style.setProperty('visibility','hidden','important');
      el.style.setProperty('opacity','0','important');
      el.removeAttribute('style'); // last resort to hide if inline style reappears
    }});
    document.body && (document.body.style.overflow='auto');
  }} catch(e) {{}}
}})();
""".strip()

    return {
        "instructions": [
            {"wait": 2000},
            {"evaluate": script},
            {"wait": 400}
        ]
    }

def _validate_js_scenario(js):
    if not isinstance(js, dict):
        return False
    if "instructions" not in js or not isinstance(js["instructions"], list):
        return False
    for ins in js["instructions"]:
        if not isinstance(ins, dict) or not ins:
            return False
        if "wait" in ins:
            if not isinstance(ins["wait"], int):
                return False
        elif "evaluate" in ins:
            if not isinstance(ins["evaluate"], str):
                return False
        else:
            return False
    return True

def _scrapingbee_common_params(url: str, render_js: bool, screenshot: bool):
    p = {
        "api_key": Config.SCRAPINGBEE_API_KEY,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "false" if screenshot else "true",
        "wait": 2000,
    }
    if screenshot:
        p["screenshot"] = "true"
        # DO NOT SEND image_format -> Bee complains "Unknown field."
        if Config.SCREENSHOT_FULL_PAGE:
            p["screenshot_full_page"] = "true"
    return p

def _maybe_add_proxies(params: dict, escalate_proxy: bool):
    if not escalate_proxy:
        return params
    if Config.SCRAPINGBEE_USE_STEALTH:
        params["stealth_proxy"] = "true"
    elif Config.SCRAPINGBEE_USE_PREMIUM:
        params["premium_proxy"] = "true"
    return params

def _scrapingbee_request(url: str, render_js: bool, screenshot: bool, with_js: bool, escalate_proxy: bool):
    api = "https://app.scrapingbee.com/api/v1/"
    js_scenario = _scrapingbee_js_scenario() if with_js else None
    if js_scenario and not _validate_js_scenario(js_scenario):
        js_scenario = None

    last_exc = None
    for attempt in range(3):
        try:
            p = _scrapingbee_common_params(url, render_js=render_js, screenshot=screenshot)

            # attempt 0: with js_scenario
            # attempt 1: without js_scenario
            # attempt 2: without js_scenario + proxy escalation (if allowed)
            if attempt == 0 and with_js and js_scenario:
                p["js_scenario"] = json.dumps(js_scenario)
            elif attempt == 2:
                p = _maybe_add_proxies(p, escalate_proxy=True)

            print(f"[ScrapingBee]{'Screenshot' if screenshot else 'HTML'} {url} attempt={attempt} render_js={render_js} with_js={('js_scenario' in p)}")
            res = requests.get(api, params=p, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)

            if res.status_code >= 400:
                body = res.text[:500]
                print(f"[ScrapingBee] HTTP {res.status_code} attempt={attempt} body={body}")
                last_exc = Exception(f"HTTP {res.status_code}")
                continue

            return res

        except Exception as e:
            print(f"[ScrapingBee] EXC attempt={attempt} {e}")
            last_exc = e
            continue

    raise last_exc or Exception("ScrapingBee failed after 3 attempts")

def scrapingbee_html_fetcher(url: str, render_js: bool = True) -> FetchResult:
    if not Config.SCRAPINGBEE_API_KEY:
        return FetchResult(url, "ScrapingBee API key not set", 500, from_renderer=render_js)
    try:
        res = _scrapingbee_request(url, render_js=render_js, screenshot=False, with_js=True, escalate_proxy=False)
        return FetchResult(url, res.text, res.status_code, from_renderer=render_js)
    except Exception as e:
        print(f"[ScrapingBeeHTML] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed via ScrapingBee: {e}", 500, from_renderer=render_js)

def scrapingbee_screenshot_fetcher(url: str, render_js: bool = True):
    if not Config.SCRAPINGBEE_API_KEY:
        return []
    try:
        res = _scrapingbee_request(url, render_js=render_js, screenshot=True, with_js=True, escalate_proxy=False)
        # Assume PNG in the data URI (Bee returns PNG by default)
        data_uri = _data_uri_from_bytes(res.content, fmt="png")
        return [data_uri] if _is_valid_data_uri_img(data_uri) else []
    except Exception as e:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {e}")
        return []

# =====================================================================================
# RENDER POLICY
# =====================================================================================

def render_policy(result: FetchResult) -> (bool, str):
    if result.status_code >= 400:
        return True, "http_error"

    soup = BeautifulSoup(result.html, "lxml")
    visible_text_len = len(soup.get_text(" ", strip=True))
    link_count = len(soup.find_all("a", href=True))
    if visible_text_len < Config.RENDER_MIN_TEXT_BYTES:
        return True, "small_text"
    if link_count < Config.RENDER_MIN_LINKS:
        return True, "few_links"

    lower_html = result.html.lower()
    for signal in Config.SPA_SIGNALS:
        if signal in lower_html:
            return True, "spa_signal"

    return False, "ok"

def social_extractor(soup, base_url):
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = urljoin(base_url, best_link)
    return found_socials

# =====================================================================================
# LLM PROMPTS
# =====================================================================================

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
        Analyze **Emotion** (primary key). Without emotional connection nothing is memorable.
        Cover:
        - How the brand aims to make people feel (trust, warmth, admiration, excitement…)
        - Evidence from language and imagery
        - Any mission/values that create emotional salience
    """,
    "Attention": """
        Analyze **Attention** (stimulus key).
        Cover:
        - Distinctiveness vs category codes
        - Visual/structural devices that grab and sustain attention
        - First-screen (above-the-fold) stopping power
    """,
    "Story": """
        Analyze **Story** (stimulus key).
        Cover:
        - Clarity and coherence of the brand narrative
        - Promise + proof structure (benefit + evidence)
        - Use of human stories, tension/resolution, or archetypes
    """,
    "Involvement": """
        Analyze **Involvement** (stimulus key).
        Cover:
        - Does the brand make the audience an active participant?
        - Community, co-creation, invitations to act/share
        - Personalization or meaningful utility
    """,
    "Repetition": """
        Analyze **Repetition** (reinforcement key).
        Cover:
        - Reuse of distinctive brand assets (DBAs): logo, color, type, tagline, sonic mnemonics
        - Are elements repeated thoughtfully without fatigue?
    """,
    "Consistency": """
        Analyze **Consistency** (reinforcement key).
        Cover:
        - Cohesion across touchpoints: voice, visuals, structure
        - Predictability that helps the brain build memory structures
        - Any fragmentation or mismatch between channels
    """
}

# =====================================================================================
# LLM CALLS
# =====================================================================================

def _openai_client():
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
    http_client = httpx.Client(proxies=None)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
    return client, original

def _restore_env(original):
    for key, value in original.items():
        if value is not None:
            os.environ[key] = value

def call_openai_for_synthesis(corpus, visuals_hint):
    print("[AI] Synthesizing brand overview...")
    client, original = _openai_client()
    try:
        synthesis_prompt = (
            "You are a senior brand strategist. "
            "Summarize the brand’s mission, tone, and primary offerings in one concise paragraph. "
            "You will be given the raw text scraped from the site and very lightweight visual hints (fonts/colors) if available.\n\n"
            f"VISUAL HINTS: {json.dumps(visuals_hint, ensure_ascii=False)}\n\n"
            f"TEXT CORPUS:\n---\n{corpus}\n---"
        )
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."
    finally:
        _restore_env(original)

def analyze_memorability_key(key_name, prompt_template, text_corpus, images_data_uris, visuals_hint, brand_summary):
    print(f"[AI] Analyzing key: {key_name}")
    client, original = _openai_client()
    try:
        user_content = []
        for data_uri in images_data_uris[:Config.MAX_SCREENSHOTS_FOR_LLM]:
            if _is_valid_data_uri_img(data_uri):
                user_content.append({"type": "image_url", "image_url": {"url": data_uri}})

        user_content.append({"type": "text", "text":
            f"VISUAL HINTS (fonts/colors):\n{json.dumps(visuals_hint, ensure_ascii=False)}\n\n"
            f"FULL WEBSITE & SOCIAL TEXT CORPUS:\n---\n{text_corpus}\n---\n\n"
            f"BRAND SUMMARY (context):\n---\n{brand_summary}\n---"
        })

        system_prompt = f"""
You are a senior brand strategist from Saffron Brand Consultants.
{prompt_template}

Return ONLY **valid JSON** with these keys:
- "score": integer 0-100
- "analysis": >=5 sentences, deep and specific
- "evidence": a quotation (or precise visual observation)
- "confidence": integer 1-5
- "confidence_rationale": brief reason
- "recommendation": concise, actionable next step
"""

        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return key_name, json.loads(response.choices[0].message.content)

    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        err_resp = {
            "score": 0,
            "analysis": "Analysis failed due to a server error.",
            "evidence": str(e),
            "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Resolve the technical error to proceed."
        }
        return key_name, err_resp
    finally:
        _restore_env(original)

def call_openai_for_executive_summary(all_analyses):
    print("[AI] Generating Executive Summary...")
    client, original = _openai_client()
    try:
        analyses_text = "\n\n".join([
            f"Key: {item['key']}\nScore: {item['analysis']['score']}\nAnalysis: {item['analysis']['analysis']}"
            for item in all_analyses
        ])
        prompt = f"""
You are a senior brand strategist delivering a final executive summary.
Based on the following six key analyses, provide:
1. Overall Summary (short).
2. Key Strengths (2–3 strongest keys with why).
3. Primary Weaknesses (2–3 weakest keys + impact).
4. Strategic Focus (ONE key to prioritize and why).
---
{analyses_text}
---
"""
        response = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."
    finally:
        _restore_env(original)

# =====================================================================================
# MAIN ORCHESTRATOR
# =====================================================================================

def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed = []
    text_corpus = ""
    images_for_llm = []  # data URIs (max 3)
    socials_found = False
    visuals_hint_accum = {"fonts": set(), "colors": set()}

    queue = deque([(_clean_url(url), 0)])
    seen_urls = {_clean_url(url)}

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
            should_render, reason = render_policy(basic_result)
            final_result = basic_result

            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                rendered = scrapingbee_html_fetcher(current_url, render_js=True)
                if 200 <= rendered.status_code < 400 and rendered.html.strip():
                    final_result = rendered

            # Screenshot attempt (up to MAX_SCREENSHOTS_FOR_LLM)
            if len(images_for_llm) < Config.MAX_SCREENSHOTS_FOR_LLM:
                shots = scrapingbee_screenshot_fetcher(current_url, render_js=True)
                for data_uri in shots:
                    if _is_valid_data_uri_img(data_uri):
                        images_for_llm.append(data_uri)
                        image_id = str(uuid.uuid4())
                        cache[image_id] = data_uri
                        yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}
                        if len(images_for_llm) >= Config.MAX_SCREENSHOTS_FOR_LLM:
                            break

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                _strip_scripts_and_styles(soup)
                page_text = soup.get_text(" ", strip=True)
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + page_text

                hints = _extract_visual_hints(final_result.html)
                visuals_hint_accum["fonts"].update(hints["fonts"])
                visuals_hint_accum["colors"].update(hints["colors"])

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

        visuals_hint_final = {
            "fonts": sorted(list(visuals_hint_accum["fonts"]))[:15],
            "colors": sorted(list(visuals_hint_accum["colors"]))[:15],
        }

        brand_summary = call_openai_for_synthesis(text_corpus, visuals_hint_final)

        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                key, prompt, text_corpus,
                images_for_llm, visuals_hint_final, brand_summary
            )
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
