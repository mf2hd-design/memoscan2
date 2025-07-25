import os
import re
import io
import time
import uuid
import json
import base64
import logging
from collections import deque, Counter
from urllib.parse import urljoin

import httpx
import requests
from bs4 import BeautifulSoup
from PIL import Image
import tldextract
from jsonschema import Draft7Validator, ValidationError

from openai import OpenAI

# -----------------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("scanner")

# -----------------------------------------------------------------------------------
# Globals (shared with app.py)
# -----------------------------------------------------------------------------------
SHARED_CACHE = {}  # id -> base64 jpeg (already compressed & padded)
# -----------------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------------
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

    # Max screenshots to FORCE and pass to LLM
    FORCE_SCREENSHOTS_FIRST_N = int(os.getenv("FORCE_SCREENSHOTS_FIRST_N", 3))

    # OpenAI
    OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TEMPERATURE       = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))
    OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY", "")

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY", "")

    # Visual extraction
    NUM_DOMINANT_COLORS      = int(os.getenv("NUM_DOM_COLORS", 6))
    JPEG_MAX_SIDE_PX         = int(os.getenv("JPEG_MAX_SIDE_PX", 1600))
    JPEG_QUALITY             = int(os.getenv("JPEG_QUALITY", 75))

    # Retry
    MAX_BEE_ATTEMPTS         = int(os.getenv("SCRAPINGBEE_MAX_ATTEMPTS", 3))

    # JSON schema retries
    SCHEMA_MAX_RETRIES       = int(os.getenv("SCHEMA_MAX_RETRIES", 2))

    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

# -----------------------------------------------------------------------------------
# JSON Schema for each key’s LLM output
# -----------------------------------------------------------------------------------
MEMO_KEY_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "analysis": {"type": "string", "minLength": 20},
        "evidence": {"type": "string", "minLength": 1},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence_rationale": {"type": "string", "minLength": 5},
        "recommendation": {"type": "string", "minLength": 5}
    },
    "required": ["score", "analysis", "evidence", "confidence", "confidence_rationale", "recommendation"],
    "additionalProperties": False
}
KEY_VALIDATOR = Draft7Validator(MEMO_KEY_SCHEMA)

# -----------------------------------------------------------------------------------
# Memorability prompts
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

# -----------------------------------------------------------------------------------
# Helpers
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

def pad_b64(s: str) -> str:
    # Fix padding issues
    missing = len(s) % 4
    if missing:
        s += "=" * (4 - missing)
    return s

def b64_to_image(b64_str: str) -> Image.Image:
    try:
        b = base64.b64decode(pad_b64(b64_str), validate=False)
        return Image.open(io.BytesIO(b))
    except Exception as e:
        raise ValueError(f"Could not decode/identify image from base64: {e}")

def image_to_jpeg_b64(img: Image.Image, max_side=1600, quality=75) -> str:
    # Resize
    w, h = img.size
    scale = min(1.0, float(max_side)/max(w, h))
    if scale < 1.0:
        img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality)
    return base64.b64encode(out.getvalue()).decode("utf-8")

def extract_hex_colors_from_html(html: str) -> Counter:
    hex_re = re.compile(r'#(?:[0-9a-fA-F]{3}){1,2}')
    return Counter(m.group(0).lower() for m in hex_re.finditer(html))

def extract_font_families_from_html(html: str) -> Counter:
    # Naive: look for 'font-family: ...;' frags
    ff_re = re.compile(r'font-family\s*:\s*([^;}{]+)', re.IGNORECASE)
    families = []
    for m in ff_re.finditer(html):
        raw = m.group(1)
        # split by comma, strip quotes
        items = [x.strip(" '\"\n\t") for x in raw.split(",")]
        families.extend([i for i in items if i])
    return Counter(families)

def extract_dominant_colors_from_image(img: Image.Image, k=6) -> list:
    # Use PIL quantize
    if img.mode != "RGB":
        img = img.convert("RGB")
    q = img.quantize(colors=k, method=Image.MEDIANCUT)
    palette = q.getpalette()
    color_counts = sorted(q.getcolors(), reverse=True)  # [(count, index), ...]
    dom_hex = []
    if palette and color_counts:
        for count, idx in color_counts[:k]:
            r = palette[idx*3 + 0]
            g = palette[idx*3 + 1]
            b = palette[idx*3 + 2]
            dom_hex.append('#%02x%02x%02x' % (r, g, b))
    return dom_hex

def build_cookie_js_scenario() -> dict:
    """
    ScrapingBee documented shape:
    {
      "instructions": [
        {"wait": 2000},
        {"evaluate": "javascript code"},
      ],
      "strict": false
    }
    """
    code = r"""
      (function(){
        try {
          // Clicks by text
          const needles = ['accept','agree','allow','permitir','zulassen','consent','cookies','ok','got it','dismiss','yes'];
          const tryClickByText = () => {
            const tags = ['button','a','div','span'];
            for (const t of tags) {
              const els = document.querySelectorAll(t);
              for (const el of els) {
                const txt = (el.innerText||el.textContent||'').toLowerCase();
                for (const n of needles) {
                  if (txt.includes(n)) {
                    try { el.click(); console.log('clicked cookie button by text', txt); return true; } catch(e){}
                  }
                }
              }
            }
            return false;
          };

          // CSS known selectors
          const selectors = [
            '#onetrust-accept-btn-handler',
            '.onetrust-accept-btn-handler',
            '#CybotCookiebotDialogBodyLevelButtonAccept',
            '#cookie-accept', '.cookie-accept',
            '.cookies-accept', '.cc-allow', '.cky-btn-accept',
            "button[aria-label='Accept']",
            "button[aria-label='I agree']"
          ];
          for (const sel of selectors) {
            try {
              const el = document.querySelector(sel);
              if (el) { el.click(); console.log('clicked cookie button css', sel); }
            } catch(e){}
          }

          tryClickByText();

          // Hide overlays anyway
          const kill = ["[id*='cookie']", "[class*='cookie']",
                        "[id*='consent']", "[class*='consent']",
                        "[id*='gdpr']",   "[class*='gdpr']",
                        "[id*='privacy']","[class*='privacy']",
                        "iframe[src*='consent']", "iframe[src*='cookie']"];
          document.querySelectorAll(kill.join(',')).forEach(el => {
            try {
              el.style.cssText = "display:none!important;visibility:hidden!important;opacity:0!important;z-index:-1!important;";
            } catch(e){}
          });
          document.body.style.overflow = 'auto';
        } catch(e) {}
      })();
    """.strip()

    return {
        "instructions": [
            {"wait": 2000},
            {"evaluate": code}
        ],
        "strict": False
    }

# -----------------------------------------------------------------------------------
# Fetchers
# -----------------------------------------------------------------------------------
_basic_client = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"},
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS
)

class FetchResult:
    def __init__(self, url, html, status_code, from_renderer):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

def basic_fetcher(url: str) -> FetchResult:
    logger.info("[BasicFetcher] %s", url)
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        logger.error("[BasicFetcher] ERROR %s", e)
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)

def scrapingbee_html_fetcher(url: str, render_js: bool, try_js=True) -> FetchResult:
    """
    We stick to doc-supported params:
    - url
    - api_key
    - render_js
    - wait
    - block_resources
    - js_scenario (with 'instructions' + 'evaluate' + 'wait' + 'strict')
    We fallback if 400 blaming js_scenario or 'instructions'.
    """
    api_key = Config.SCRAPINGBEE_API_KEY
    if not api_key:
        return FetchResult(url, "ScrapingBee API Key not set", 500, from_renderer=render_js)

    js_scenario = build_cookie_js_scenario()
    params_base = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
        "wait": 2000,
        "block_resources": "true"
    }

    attempts = Config.MAX_BEE_ATTEMPTS
    for attempt in range(attempts):
        with_js = try_js and attempt == 0
        params = dict(params_base)
        if with_js:
            # ScrapingBee can accept JSON string or object; errors indicated object was sometimes mis-parsed.
            # We'll pass as JSON string (safer) — but guard for 400 and retry without it.
            params["js_scenario"] = json.dumps(js_scenario)

        logger.info("[ScrapingBee]HTML %s attempt=%d render_js=%s with_js=%s",
                    url, attempt, render_js, with_js)
        try:
            res = requests.get("https://app.scrapingbee.com/api/v1/",
                               params=params,
                               timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
            if res.status_code == 200:
                return FetchResult(url, res.text, res.status_code, from_renderer=render_js)
            else:
                logger.error("[ScrapingBee] HTTP %d attempt=%d body=%s",
                             res.status_code, attempt, res.text[:300])
                # If it's a 400 and complains about js_scenario, try again without js.
                if res.status_code == 400 and with_js:
                    # Next attempt, disable JS scenario
                    try_js = False
                continue
        except Exception as e:
            logger.error("[ScrapingBee] EXC attempt=%d %s", attempt, e)
            continue

    return FetchResult(url, "ScrapingBee failed after attempts", 500, from_renderer=render_js)

def scrapingbee_screenshot_fetcher(url: str, render_js: bool, force_js=True) -> str or None:
    """
    Returns a JPEG base64 image (already compressed), placed into SHARED_CACHE by caller.
    Follows the same doc-compliant strategy as html_fetcher.
    """
    api_key = Config.SCRAPINGBEE_API_KEY
    if not api_key:
        return None

    js_scenario = build_cookie_js_scenario()
    params_base = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
        "wait": 2000,
        "block_resources": "false",
        "screenshot": "true",
        "screenshot_full_page": "false",
        "stealth_proxy": "false",
        "premium_proxy": "false",
        "strict": "false"
    }

    attempts = Config.MAX_BEE_ATTEMPTS
    for attempt in range(attempts):
        with_js = force_js and attempt == 0
        params = dict(params_base)
        if with_js:
            params["js_scenario"] = json.dumps(js_scenario)

        logger.info("[ScrapingBee]Screenshot %s attempt=%d render_js=%s with_js=%s",
                    url, attempt, render_js, with_js)
        try:
            res = requests.get("https://app.scrapingbee.com/api/v1/",
                               params=params,
                               timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
            if res.status_code == 200:
                # ScrapingBee returns raw PNG bytes (not base64) for screenshot.
                # Convert to JPEG b64 so OpenAI always accepts.
                try:
                    png_bytes = res.content
                    img = Image.open(io.BytesIO(png_bytes))
                    b64_jpeg = image_to_jpeg_b64(img, Config.JPEG_MAX_SIDE_PX, Config.JPEG_QUALITY)
                    return b64_jpeg
                except Exception as img_e:
                    logger.error("[IMG] Convert failed: %s", img_e)
                    return None
            else:
                body = res.text[:300]
                logger.error("[ScrapingBee] HTTP %d attempt=%d body=%s", res.status_code, attempt, body)
                if res.status_code == 400 and with_js:
                    force_js = False
                continue
        except Exception as e:
            logger.error("[ScrapingBee] EXC attempt=%d %s", attempt, e)
            continue

    logger.error("[ScrapingBeeScreenshot] ERROR for %s: HTTP failure", url)
    return None

# -----------------------------------------------------------------------------------
# Render Policy
# -----------------------------------------------------------------------------------
def render_policy(result: FetchResult) -> (bool, str):
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
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = urljoin(base_url, best_link)
    return found_socials

# -----------------------------------------------------------------------------------
# OpenAI helpers + schema validation
# -----------------------------------------------------------------------------------
def call_openai(client: OpenAI, **kwargs):
    return client.chat.completions.create(**kwargs)

def validate_or_fix_json(key_name: str, raw_text: str, validator: Draft7Validator, client: OpenAI, prompt_again: str, retries: int = 2):
    """
    Try to parse & validate, retry up to 'retries' times if it fails.
    """
    attempt = 0
    last_err = None
    while attempt <= retries:
        try:
            data = json.loads(raw_text)
            errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
            if errors:
                messages = "; ".join([f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors])
                raise ValidationError(messages)
            return data
        except Exception as e:
            last_err = e
            attempt += 1
            logger.warning("[Schema] %s invalid JSON for key '%s' attempt=%d err=%s", type(e).__name__, key_name, attempt, e)

            if attempt > retries:
                break

            # Re-ask the model to produce valid JSON strictly per schema
            sys_msg = (
                "Return ONLY a valid JSON object matching this JSON-Schema (no markdown, no code-fences):\n"
                + json.dumps(MEMO_KEY_SCHEMA, indent=2)
            )
            user_msg = (
                "Your previous output was invalid. Please reformat your last answer into a JSON object that is strictly valid per the schema above."
            )
            resp = call_openai(client,
                               model=Config.OPENAI_MODEL,
                               temperature=0.0,
                               messages=[
                                   {"role": "system", "content": sys_msg},
                                   {"role": "user", "content": user_msg}
                               ])
            raw_text = resp.choices[0].message.content

    # As a last resort, return a minimal fallback
    logger.error("[Schema] Giving up validating key '%s': %s", key_name, last_err)
    return {
        "score": 0,
        "analysis": "Model failed to produce a valid JSON response.",
        "evidence": "",
        "confidence": 1,
        "confidence_rationale": "Schema validation failed.",
        "recommendation": "Retry the analysis later."
    }

def call_openai_for_synthesis(client: OpenAI, corpus: str):
    logger.info("[AI] Synthesizing brand overview...")
    synthesis_prompt = (
        "Analyze the following text from a company's website and social media. "
        "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
        "This summary will be used as context for further analysis.\n\n---\n" + corpus + "\n---"
    )
    try:
        resp = call_openai(client,
                           model=Config.OPENAI_MODEL,
                           temperature=Config.OPENAI_TEMPERATURE,
                           messages=[{"role": "user", "content": synthesis_prompt}])
        return resp.choices[0].message.content
    except Exception as e:
        logger.error("[ERROR] AI synthesis failed: %s", e)
        return "Could not generate brand summary due to an error."

def analyze_memorability_key(client: OpenAI,
                             key_name: str,
                             prompt_template: str,
                             text_corpus: str,
                             brand_summary: str,
                             compressed_jpegs_b64: list,
                             visual_hints: dict):
    logger.info("[AI] Analyzing key: %s", key_name)

    # Build content payload: we include up to first N image URLs (data-uri) + text (visual hints).
    content_list = []

    # (1) Attach screenshots
    for b64 in compressed_jpegs_b64:
        content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

    # (2) Add visual hints
    if visual_hints:
        visual_hint_txt = json.dumps(visual_hints, indent=2)
        content_list.append({"type": "text", "text": f"VISUAL HINTS (colors/fonts):\n{visual_hint_txt}"})

    # (3) Corpus and summary text
    content_list.append({"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"})
    content_list.append({"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"})

    system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
    {prompt_template}

    Your response MUST be a valid JSON object with the following keys and constraints (strictly):
    {json.dumps(MEMO_KEY_SCHEMA, indent=2)}
    """

    try:
        response = call_openai(client,
                               model=Config.OPENAI_MODEL,
                               temperature=0.3,
                               messages=[
                                   {"role": "system", "content": system_prompt},
                                   {"role": "user", "content": content_list},
                               ])
        raw = response.choices[0].message.content
        # Validate/repair
        valid = validate_or_fix_json(key_name, raw, KEY_VALIDATOR, client, system_prompt, Config.SCHEMA_MAX_RETRIES)
        return key_name, valid
    except Exception as e:
        logger.error("[ERROR] LLM analysis failed for key '%s': %s", key_name, e)
        err = {
            "score": 0, "analysis": "Analysis failed due to a server error.",
            "evidence": str(e), "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Resolve the technical error to proceed."
        }
        return key_name, err

def call_openai_for_executive_summary(client: OpenAI, all_analyses):
    logger.info("[AI] Generating Executive Summary...")
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
    try:
        resp = call_openai(client,
                           model=Config.OPENAI_MODEL,
                           temperature=0.3,
                           messages=[{"role": "user", "content": summary_prompt}])
        return resp.choices[0].message.content
    except Exception as e:
        logger.error("[ERROR] AI summary failed: %s", e)
        return "Could not generate the executive summary due to an error."

# -----------------------------------------------------------------------------------
# Main Stream Orchestrator
# -----------------------------------------------------------------------------------
def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed = []
    text_corpus = ""
    socials_found = False

    # Visual artifacts
    forced_screens_b64 = []  # first N pages, always store here
    total_screens_sent_to_llm = 0

    queue = deque([(_clean_url(url), 0)])
    seen_urls = {_clean_url(url)}

    client = OpenAI(api_key=Config.OPENAI_API_KEY, http_client=httpx.Client(proxies=None))

    try:
        yield {'type': 'status', 'message': f'Scan initiated. Budget: {budget}s.'}

        while queue and len(pages_analyzed) < Config.CRAWL_MAX_PAGES:
            elapsed = time.time() - start_time
            if elapsed > budget:
                yield {'type': 'status', 'message': 'Time budget exceeded. Finalizing analysis.'}
                break

            current_url, depth = queue.popleft()
            yield {'type': 'status', 'message': f'Analyzing page {len(pages_analyzed) + 1}/{Config.CRAWL_MAX_PAGES}: {current_url}'}

            # 1) Basic fetch
            basic_result = basic_fetcher(current_url)

            # 2) Decide to render
            should_render, reason = render_policy(basic_result)

            final_result = basic_result
            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                final_result = scrapingbee_html_fetcher(current_url, render_js=True, try_js=True)

            # 3) Force screenshots for first N pages
            need_force = len(pages_analyzed) < Config.FORCE_SCREENSHOTS_FIRST_N
            if need_force:
                # Force screenshot
                b64_jpeg = scrapingbee_screenshot_fetcher(current_url, render_js=True, force_js=True)
                if not b64_jpeg:
                    # fallback non-JS
                    b64_jpeg = scrapingbee_screenshot_fetcher(current_url, render_js=False, force_js=False)
                if b64_jpeg:
                    forced_screens_b64.append(b64_jpeg)
                    image_id = str(uuid.uuid4())
                    cache[image_id] = b64_jpeg  # already jpeg
                    yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            # 4) Parse
            html = final_result.html or ""
            if html:
                soup = BeautifulSoup(html, "lxml")
                logger.info("[DEBUG] Links found on %s: %d (rendered=%s)",
                            current_url, len(soup.find_all('a', href=True)), final_result.from_renderer)

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                # Strip script/style
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + soup.get_text(" ", strip=True)

                # Expand queue
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

        # -----------------------------------------------------------------------------------
        # VISUAL FEATURE EXTRACTION
        # -----------------------------------------------------------------------------------
        visual_hints = {}
        try:
            # 1) Use HTML corpus to extract colors & font families
            color_counts = extract_hex_colors_from_html(text_corpus)
            font_counts  = extract_font_families_from_html(text_corpus)

            visual_hints["top_html_hex_colors"] = [c for c, _ in color_counts.most_common(12)]
            visual_hints["top_html_fonts"]      = [f for f, _ in font_counts.most_common(12)]

            # 2) From screenshots, get dominant colors
            dominant_sets = []
            for b64 in forced_screens_b64:
                try:
                    img = b64_to_image(b64)
                    dom_hex = extract_dominant_colors_from_image(img, k=Config.NUM_DOMINANT_COLORS)
                    dominant_sets.append(dom_hex)
                except Exception as e:
                    logger.warning("[VIS] dominant color failed: %s", e)
            # Flatten & count
            flat = [c for lst in dominant_sets for c in lst]
            visual_hints["dominant_screenshot_colors"] = [c for c, _ in Counter(flat).most_common(12)]
        except Exception as e:
            logger.warning("[VIS] Visual feature extraction failed: %s", e)
            visual_hints = {}

        # -----------------------------------------------------------------------------------
        # AI ANALYSIS
        # -----------------------------------------------------------------------------------
        yield {'type': 'status', 'message': f'Crawl complete. Starting AI analysis...'}
        brand_summary = call_openai_for_synthesis(client, text_corpus)

        all_results = []
        # Log how many screenshots we'll pass
        total_screens_sent_to_llm = len(forced_screens_b64)
        logger.info("[LLM] Passing %d screenshot(s) to the model.", total_screens_sent_to_llm)
        yield {'type': 'status', 'message': f'Passing {total_screens_sent_to_llm} screenshots to the model.'}

        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                client,
                key,
                prompt,
                text_corpus,
                brand_summary,
                forced_screens_b64,
                visual_hints
            )
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj

        yield {'type': 'status', 'message': 'Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(client, all_results)
        yield {'type': 'summary', 'text': summary_text}
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        logger.exception("[CRITICAL ERROR] The main stream failed: %s", e)
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
