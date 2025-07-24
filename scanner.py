# scanner.py
import os
import re
import json
import time
import uuid
import base64
import random
import string
from collections import deque, Counter
from urllib.parse import urljoin, urlparse

import httpx
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
import tldextract

load_dotenv()

# ======================================================================================
# CONFIG
# ======================================================================================

class Config:
    # Budgets
    SITE_BUDGET_SECS         = int(os.getenv("SITE_BUDGET_SECS", 60))
    SITE_MAX_BUDGET_SECS     = int(os.getenv("SITE_MAX_BUDGET_SECS", 90))

    # Crawl
    CRAWL_MAX_PAGES          = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH          = int(os.getenv("CRAWL_MAX_DEPTH", 2))
    MAX_ENQUEUED_LINKS       = int(os.getenv("MAX_ENQUEUED_LINKS", 200))

    # Timeouts
    BASIC_TIMEOUT_SECS       = int(os.getenv("BASIC_TIMEOUT_SECS", 10))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 30))

    # Heuristics to trigger JS rendering
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))

    # ScrapingBee
    SCRAPINGBEE_URL          = "https://app.scrapingbee.com/api/v1/"
    SB_MAX_RETRIES           = int(os.getenv("SB_MAX_RETRIES", 3))
    SB_BACKOFF_BASE          = float(os.getenv("SB_BACKOFF_BASE", 0.6))
    SB_ALLOW_PREMIUM_STEALTH = os.getenv("SB_ALLOW_PREMIUM_STEALTH", "false").lower() == "true"

    # Screenshots
    # How many distinct URLs to screenshot (max). We'll try: fold (page 1), mid (page 2/3), footer (last)
    MAX_SCREENSHOTS_TO_AI    = int(os.getenv("MAX_SCREENSHOTS_TO_AI", 3))
    SB_SCREENSHOT_WIDTH      = int(os.getenv("SB_SCREENSHOT_WIDTH", 1400))
    SB_SCREENSHOT_HEIGHT     = int(os.getenv("SB_SCREENSHOT_HEIGHT", 900))

    # LLM
    OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o")
    LLM_TEMPERATURE          = float(os.getenv("LLM_TEMPERATURE", 0.1))

    # Regex & signals
    SPA_SIGNALS = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

    # Cookie banner handling
    CONSENT_CLICK_XPATHS = [
        # buttons with common accept words (en/de/es)
        "//button[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑÄÖÜẞ','abcdefghijklmnopqrstuvwxyzáéíóúüñäöüß'), 'i agree')]",
        "//button[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑÄÖÜẞ','abcdefghijklmnopqrstuvwxyzáéíóúüñäöüß'), 'accept')]",
        "//button[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑÄÖÜẞ','abcdefghijklmnopqrstuvwxyzáéíóúüñäöüß'), 'allow')]",
        "//button[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑÄÖÜẞ','abcdefghijklmnopqrstuvwxyzáéíóúüñäöüß'), 'zulassen')]",
        "//button[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑÄÖÜẞ','abcdefghijklmnopqrstuvwxyzáéíóúüñäöüß'), 'permitir')]",
        "//button[contains(translate(normalize-space(text()),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑÄÖÜẞ','abcdefghijklmnopqrstuvwxyzáéíóúüñäöüß'), 'permitirlas')]",
    ]
    CONSENT_CLICK_CSS = [
        "#onetrust-accept-btn-handler",
        ".onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyLevelButtonAccept",
        "#cookie-accept",
        ".cookie-accept",
        ".cookies-accept",
        ".cc-allow",
        ".cky-btn-accept",
        "[data-testid='cookie-accept']",
        "button[aria-label='Accept']",
        "button[aria-label='Allow']",
    ]

    # A small, schema-safe script to kill whatever remains
    COOKIE_KILLER_SCRIPT = r"""
(function(){
  try {
    const kill = [
      "[id*='cookie']", "[class*='cookie']",
      "[id*='consent']", "[class*='consent']",
      "[id*='gdpr']",   "[class*='gdpr']",
      "[id*='privacy']","[class*='privacy']",
      "iframe[src*='consent']", "iframe[src*='cookie']"
    ];
    document.querySelectorAll(kill.join(',')).forEach(el => {
      el.style.cssText = "display:none!important;visibility:hidden!important;opacity:0!important;";
    });
    document.body.style.overflow = 'auto';
  } catch(e){}
})();
""".strip()

# ======================================================================================
# LIGHT JSON VALIDATION (no external dependency)
# ======================================================================================

def validate_score_json(obj: dict):
    required = ["score", "analysis", "evidence", "confidence", "confidence_rationale", "recommendation"]
    for k in required:
        if k not in obj:
            raise ValueError(f"Missing key '{k}' in LLM JSON")
    if not isinstance(obj["score"], int) or not (0 <= obj["score"] <= 100):
        raise ValueError("Invalid 'score'")
    if not isinstance(obj["confidence"], int) or not (1 <= obj["confidence"] <= 5):
        raise ValueError("Invalid 'confidence'")
    for key in ["analysis", "evidence", "confidence_rationale", "recommendation"]:
        if not isinstance(obj[key], str) or len(obj[key].strip()) == 0:
            raise ValueError(f"Invalid '{key}'")

# ======================================================================================
# SMALL UTILITIES
# ======================================================================================

def _random_id(n=6):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

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

def human_ms(ms: int) -> str:
    return f"{ms}ms"

# ======================================================================================
# TEXT DISTILLATION & VISUAL FEATURE EXTRACTION
# ======================================================================================

def distill_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript"]):
        tag.decompose()
    txt = soup.get_text(" ", strip=True)
    txt = re.sub(r"\s+", " ", txt)
    # Chop off massive junk
    return txt[:20000]

COLOR_RE = re.compile(r"#([0-9a-fA-F]{3,8})")
FONT_RE  = re.compile(r"font-family\s*:\s*([^;]+);", re.I)

def extract_visual_hints(html: str, extra_css: list[str] | None = None):
    colors = Counter()
    fonts  = Counter()
    sources = [html] + (extra_css or [])
    for source in sources:
        for c in COLOR_RE.findall(source):
            colors[c.lower()] += 1
        for f in FONT_RE.findall(source):
            clean = re.sub(r"['\"]", "", f).split(",")[0].strip().lower()
            fonts[clean] += 1
    return {
        "top_colors": [c for c, _ in colors.most_common(5)],
        "top_fonts":  [f for f, _ in fonts.most_common(5)]
    }

# ======================================================================================
# SCRAPINGBEE CLIENT (resilient wrapper)
# ======================================================================================

def build_js_scenario(click_css: list[str], click_xpaths: list[str], kill_script: str, wait_ms: int = 1200):
    """
    ScrapingBee schema-compliant js_scenario.
    - 'optional' is supported on 'click' steps.
    - 'script' is a simple string of JS code.
    - 'wait' expects an integer (ms).
    """
    instr = []
    if wait_ms and wait_ms > 0:
        instr.append({"wait": wait_ms})

    # CSS click
    for sel in click_css:
        instr.append({"click": sel, "optional": True})
    # XPath click: ScrapingBee supports xpath clicks via {"click": {"xpath": "..."}}
    for xp in click_xpaths:
        instr.append({"click": {"xpath": xp}, "optional": True})

    if kill_script and kill_script.strip():
        instr.append({"script": kill_script})

    return {"instructions": instr}

def sb_request(
    url: str,
    render_js: bool,
    want_screenshot: bool,
    js_scenario: dict | None,
    cookies: list[dict] | None,
    timeout: int,
    max_retries: int,
    block_resources: bool = True,
    allow_premium_stealth: bool = False,
    width: int | None = None,
    height: int | None = None,
):
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if not api_key:
        raise RuntimeError("SCRAPINGBEE_API_KEY not set")

    params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "true" if block_resources else "false",
        "timeout": timeout * 1000,
    }

    if want_screenshot:
        params.update({
            "screenshot": "true",
            "format": "png",
            "response_format": "base64",
            "window_width": width or Config.SB_SCREENSHOT_WIDTH,
            "window_height": height or Config.SB_SCREENSHOT_HEIGHT,
        })

    if js_scenario:
        params["js_scenario"] = json.dumps(js_scenario)

    if cookies:
        # ScrapingBee requires a *list* of cookies with limited allowed keys
        # We ensure we only keep supported keys
        safe = []
        for c in cookies:
            safe.append({
                "name":     c.get("name"),
                "value":    c.get("value"),
                "domain":   c.get("domain"),
                "path":     c.get("path", "/"),
                "secure":   bool(c.get("secure", False)),
                "httpOnly": bool(c.get("httpOnly", False)),
                "sameSite": c.get("sameSite", "Lax"),
                # expires / maxAge optional
            })
        params["cookies"] = json.dumps(safe)

    last_exc = None
    use_cookies = bool(cookies)
    use_js = bool(js_scenario)
    local_block_resources = block_resources
    premium_proxy = False
    stealth_proxy = False

    for attempt in range(max_retries):
        try:
            effective_params = dict(params)
            if premium_proxy:
                effective_params["premium_proxy"] = "true"
            if stealth_proxy:
                effective_params["stealth_proxy"] = "true"

            r = requests.get(Config.SCRAPINGBEE_URL, params=effective_params, timeout=timeout)
            if r.status_code == 200:
                return r

            body = (r.text or "")[:600]
            print(f"[ScrapingBee] HTTP {r.status_code} attempt={attempt} body={body}")

            # 400: schema invalid → strip cookies/js once
            if r.status_code == 400:
                if use_js:
                    params.pop("js_scenario", None)
                    use_js = False
                elif use_cookies:
                    params.pop("cookies", None)
                    use_cookies = False
                else:
                    # Already stripped, let's relax block_resources
                    local_block_resources = False
                    params["block_resources"] = "false"

            # 500 or >= 500: relax further
            if r.status_code >= 500:
                if attempt == 0:
                    # Turn off block resources
                    local_block_resources = False
                    params["block_resources"] = "false"
                elif attempt == 1 and allow_premium_stealth and not premium_proxy:
                    premium_proxy = True
                elif attempt == 2 and allow_premium_stealth and not stealth_proxy:
                    stealth_proxy = True

        except Exception as e:
            last_exc = e
            print(f"[ScrapingBee] EXC attempt={attempt} {e}")

        time.sleep(Config.SB_BACKOFF_BASE * (attempt + 1))

    raise RuntimeError(f"ScrapingBee failed after {max_retries} attempts: {last_exc}")

# ======================================================================================
# FETCHERS
# ======================================================================================

class FetchResult:
    def __init__(self, url: str, html: str, status_code: int, from_renderer: bool):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

_basic_client = httpx.Client(
    headers={
        "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
    },
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS,
)

def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] {url}")
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url, "", 500, from_renderer=False)

def scrapingbee_html_fetcher(url: str, allow_premium: bool) -> FetchResult:
    print(f"[ScrapingBeeHTML] {url} (render_js=True)")
    try:
        js = build_js_scenario(
            click_css=Config.CONSENT_CLICK_CSS,
            click_xpaths=Config.CONSENT_CLICK_XPATHS,
            kill_script=Config.COOKIE_KILLER_SCRIPT,
            wait_ms=1200
        )
        r = sb_request(
            url=url,
            render_js=True,
            want_screenshot=False,
            js_scenario=js,
            cookies=None,  # Start without cookies; cookies frequently cause 400s
            timeout=Config.SCRAPINGBEE_TIMEOUT_SECS,
            max_retries=Config.SB_MAX_RETRIES,
            block_resources=True,
            allow_premium_stealth=allow_premium,
        )
        return FetchResult(url, r.text, r.status_code, from_renderer=True)
    except Exception as e:
        print(f"[ScrapingBeeHTML] ERROR for {url}: {e}")
        return FetchResult(url, "", 500, from_renderer=True)

def scrapingbee_screenshot_fetcher(url: str, render_js: bool, allow_premium: bool) -> str | None:
    print(f"[ScrapingBeeScreenshot] {url} (render_js={render_js})")
    try:
        js = build_js_scenario(
            click_css=Config.CONSENT_CLICK_CSS,
            click_xpaths=Config.CONSENT_CLICK_XPATHS,
            kill_script=Config.COOKIE_KILLER_SCRIPT,
            wait_ms=1200
        )
        r = sb_request(
            url=url,
            render_js=render_js,
            want_screenshot=True,
            js_scenario=js,
            cookies=None,
            timeout=Config.SCRAPINGBEE_TIMEOUT_SECS,
            max_retries=Config.SB_MAX_RETRIES,
            block_resources=True,
            allow_premium_stealth=allow_premium,
            width=Config.SB_SCREENSHOT_WIDTH,
            height=Config.SB_SCREENSHOT_HEIGHT,
        )
        # ScrapingBee returns base64 screenshot in text body when response_format=base64
        return r.text
    except Exception as e:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {e}")
        return None

# ======================================================================================
# RENDER POLICY
# ======================================================================================

def render_policy(result: FetchResult) -> (bool, str):
    if result.status_code >= 400:
        return True, "http_error"
    soup = BeautifulSoup(result.html, "lxml")
    visible_text_len = len(soup.get_text(" ", strip=True))
    if visible_text_len < Config.RENDER_MIN_TEXT_BYTES:
        return True, "small_text"
    if len(soup.find_all("a", href=True)) < Config.RENDER_MIN_LINKS:
        return True, "few_links"
    low = result.html.lower()
    if any(sig in low for sig in Config.SPA_SIGNALS):
        return True, "spa_signal"
    return False, "ok"

# ======================================================================================
# SOCIAL EXTRACTOR
# ======================================================================================

def social_extractor(soup: BeautifulSoup, base_url: str):
    found = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found[platform] = urljoin(base_url, best_link)
    return found

# ======================================================================================
# LLM PROMPTS
# ======================================================================================

SCORE_BANDS = """
Score calibration (apply strictly):
- 90-100: World-class. Emotionally resonant, distinct visuals & story, high involvement, repetition & consistency across channels.
- 70-89: Strong, but with gaps (e.g., diluted tone, uneven consistency, or limited involvement).
- 50-69: Average; some signals exist but fragmentary, conventional, or inconsistent.
- 30-49: Weak; generic messaging/visuals, poor narrative coherence, low engagement.
- 0-29: Critically poor; brand is invisible, incoherent, or absent.
"""

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": f"""
You are evaluating **Emotion** (the primary key).
How strongly does the brand connect emotionally (warmth, trust, ambition, admiration)? Is there a clear emotional reward?
{SCORE_BANDS}
""",
    "Attention": f"""
You are evaluating **Attention** (stimulus).
How distinctive and attention-grabbing is the brand (visuals, headlines, UX flow)? Avoid clichés and spammy CTAs.
{SCORE_BANDS}
""",
    "Story": f"""
You are evaluating **Story** (stimulus).
Is the narrative authentic, clear, and compelling? Does it explain who the brand is and its promise, beyond facts?
{SCORE_BANDS}
""",
    "Involvement": f"""
You are evaluating **Involvement** (stimulus).
Does the brand invite participation, community, and empowerment? Do users feel included?
{SCORE_BANDS}
""",
    "Repetition": f"""
You are evaluating **Repetition** (reinforcement).
Are key symbols, taglines, colors, UX patterns reused strategically (not spammily) across touchpoints?
{SCORE_BANDS}
""",
    "Consistency": f"""
You are evaluating **Consistency** (reinforcement).
Are tone, message, and design coherent across channels, building familiarity and recognizability?
{SCORE_BANDS}
"""
}

# ======================================================================================
# OPENAI HELPERS
# ======================================================================================

def _new_openai_client():
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {k: os.environ.pop(k, None) for k in proxy_keys}
    http_client = httpx.Client(proxies=None)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
    return client, original_proxies

def _restore_proxies(original_proxies):
    for k, v in original_proxies.items():
        if v is not None:
            os.environ[k] = v

def call_openai_for_synthesis(text_corpus: str, visual_hints: dict):
    print("[AI] Synthesizing brand overview...")
    client, original = _new_openai_client()
    try:
        prompt = (
            "You are a senior brand strategist. Create a concise one-paragraph summary of the brand's "
            "mission, tone and primary offerings. Use ONLY the provided cleaned corpus and visual hints.\n\n"
            f"VISUAL HINTS (deterministic extraction): {json.dumps(visual_hints, ensure_ascii=False)}\n\n"
            f"CORPUS (cleaned):\n---\n{text_corpus[:15000]}\n---"
        )
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."
    finally:
        _restore_proxies(original)

def analyze_memorability_key(key_name, prompt_template, text_corpus, visual_hints, screenshots_b64, brand_summary):
    print(f"[AI] Analyzing key: {key_name}")
    client, original = _new_openai_client()
    try:
        content = []

        # Add up to MAX_SCREENSHOTS_TO_AI screenshots
        used = 0
        for b64 in screenshots_b64:
            if used >= Config.MAX_SCREENSHOTS_TO_AI:
                break
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            used += 1

        content.append({"type": "text", "text": f"VISUAL HINTS: {json.dumps(visual_hints, ensure_ascii=False)}"})
        content.append({"type": "text", "text": f"BRAND SUMMARY:\n{brand_summary}"})
        content.append({"type": "text", "text": f"CLEAN CORPUS:\n{text_corpus[:15000]}"})

        system_prompt = f"""
You are a senior brand strategist at Saffron Brand Consultants. Return STRICT JSON only.

{prompt_template}

Return a JSON object with:
- "score": integer 0-100
- "analysis": >= 5 sentences, grounded in the criteria
- "evidence": direct quote or specific visual observation
- "confidence": 1-5
- "confidence_rationale": short explanation
- "recommendation": actionable, concise
"""

        def call_once():
            resp = client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content}
                ],
                response_format={"type": "json_object"},
                temperature=Config.LLM_TEMPERATURE
            )
            return resp.choices[0].message.content

        # retry with validation
        last_err = None
        for _ in range(2):
            raw = call_once()
            try:
                data = json.loads(raw)
                validate_score_json(data)
                return key_name, data
            except Exception as e:
                last_err = e
                time.sleep(0.3)

        # fallback
        print(f"[ERROR] LLM analysis invalid JSON for key {key_name}: {last_err}")
        return key_name, {
            "score": 0,
            "analysis": "Analysis failed due to invalid JSON from the model.",
            "evidence": str(last_err),
            "confidence": 1,
            "confidence_rationale": "Invalid output",
            "recommendation": "Retry with corrected prompt."
        }
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
        _restore_proxies(original)

def call_openai_for_executive_summary(all_analyses):
    print("[AI] Generating Executive Summary...")
    client, original = _new_openai_client()
    try:
        # Build deterministic synthesis source
        lines = []
        for item in all_analyses:
            k = item["key"]
            score = item["analysis"]["score"]
            an = item["analysis"]["analysis"]
            lines.append(f"Key: {k}\nScore: {score}\nAnalysis: {an}\n")
        payload = "\n".join(lines)

        prompt = f"""
You are a senior brand strategist. Using the already-scored six keys below, write:
1) Overall summary (2–3 sentences).
2) Key strengths (2-3 strongest keys, why).
3) Primary weaknesses (2-3 weakest keys, impact).
4) The single most important key to focus on next.

Use the scores as ground truth. Be concise, not repetitive.
---
{payload}
---
"""

        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."
    finally:
        _restore_proxies(original)

# ======================================================================================
# MAIN ORCHESTRATOR
# ======================================================================================

def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed: list[FetchResult] = []
    text_corpus_all = []
    homepage_screenshot_b64 = None
    screenshots_for_ai: list[str] = []
    socials_found = False
    visual_hints_accum = {"top_colors": [], "top_fonts": []}

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
            yield {'type': 'status', 'message': f'Analyzing page {len(pages_analyzed)+1}/{Config.CRAWL_MAX_PAGES}: {current_url}'}

            # Basic fetch
            basic_result = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_result)

            final_result = basic_result
            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                final_result = scrapingbee_html_fetcher(current_url, allow_premium=Config.SB_ALLOW_PREMIUM_STEALTH)

            # Screenshots: capture only a few pages (max Config.MAX_SCREENSHOTS_TO_AI)
            if len(screenshots_for_ai) < Config.MAX_SCREENSHOTS_TO_AI:
                scr_b64 = scrapingbee_screenshot_fetcher(current_url, render_js=final_result.from_renderer,
                                                         allow_premium=Config.SB_ALLOW_PREMIUM_STEALTH)
                if scr_b64:
                    if homepage_screenshot_b64 is None:
                        homepage_screenshot_b64 = scr_b64
                    screenshots_for_ai.append(scr_b64)
                    image_id = str(uuid.uuid4())
                    cache[image_id] = scr_b64
                    yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                # Socials only on the first page by default
                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                # Distill text
                distilled = distill_html_to_text(final_result.html)
                text_corpus_all.append(f"--- Page: {current_url} ---\n{distilled}")

                # Visual hints
                v = extract_visual_hints(final_result.html)
                visual_hints_accum["top_colors"].extend(v["top_colors"])
                visual_hints_accum["top_fonts"].extend(v["top_fonts"])

                # Queue new links
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

            # Escalate budget if heavy JS and no socials
            elapsed = time.time() - start_time
            if not escalated and elapsed < budget:
                pages_rendered_by_bee = sum(1 for p in pages_analyzed if p.from_renderer)
                if len(pages_analyzed) >= 3 and pages_rendered_by_bee >= 2 and not socials_found:
                    budget = Config.SITE_MAX_BUDGET_SECS
                    escalated = True
                    yield {'type': 'status', 'message': f'High JS usage + no socials → escalating budget to {budget}s.'}

        # Prepare for AI steps
        yield {'type': 'status', 'message': 'Crawl complete. Starting AI analysis...'}

        # Collapse & deduplicate visual hints
        def top_unique(lst, k=5):
            cnt = Counter([x for x in lst if x])
            return [c for c, _ in cnt.most_common(k)]

        visual_hints_final = {
            "top_colors": top_unique(visual_hints_accum["top_colors"]),
            "top_fonts": top_unique(visual_hints_accum["top_fonts"])
        }

        text_corpus = "\n\n".join(text_corpus_all)
        brand_summary = call_openai_for_synthesis(text_corpus, visual_hints_final)

        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                key, prompt,
                text_corpus=text_corpus,
                visual_hints=visual_hints_final,
                screenshots_b64=[homepage_screenshot_b64] + [b for b in screenshots_for_ai[1:]],
                brand_summary=brand_summary
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
