import os
import re
import io
import json
import uuid
import time
import base64
import math
import traceback
from collections import deque
from typing import Dict, Any, List, Tuple, Optional

import requests
import httpx
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

try:
    from PIL import Image
except Exception:
    Image = None  # We'll gracefully degrade if Pillow is missing

try:
    import tldextract
except Exception:
    tldextract = None

try:
    from jsonschema import validate, Draft7Validator
    from jsonschema.exceptions import ValidationError
except Exception:
    validate = None
    Draft7Validator = None
    ValidationError = Exception

from openai import OpenAI

# -----------------------------------------------------------------------------------
# GLOBAL SHARED CACHE (screenshots & misc)
# -----------------------------------------------------------------------------------
SHARED_CACHE: Dict[str, Any] = {}  # {"id": {"bytes": b"...", "mime": "image/jpeg"}}

# -----------------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------------
class Config:
    # Budgets
    SITE_BUDGET_SECS         = int(os.getenv("SITE_BUDGET_SECS", 120))
    SITE_MAX_BUDGET_SECS     = int(os.getenv("SITE_MAX_BUDGET_SECS", 150))

    # Crawl
    CRAWL_MAX_PAGES          = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH          = int(os.getenv("CRAWL_MAX_DEPTH", 2))

    # Timeouts
    BASIC_TIMEOUT_SECS       = int(os.getenv("BASIC_TIMEOUT_SECS", 20))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 60))

    # Render policy
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # Social
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }

    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY", "").strip()
    SB_MAX_RETRIES           = 3
    SB_WAIT_MS               = int(os.getenv("SCRAPINGBEE_WAIT_MS", "2000"))  # simple wait
    SB_USE_PREMIUM_ON_500    = os.getenv("SB_USE_PREMIUM_ON_500", "false").lower() == "true"

    # Screenshots / visuals
    MAX_SCREENSHOTS_FOR_LLM  = 3
    SS_JPEG_QUALITY          = int(os.getenv("SS_JPEG_QUALITY", 45))
    SS_TARGET_WIDTH          = int(os.getenv("SS_TARGET_WIDTH", 1024))

    # OpenAI
    OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_TEMPERATURE       = float(os.getenv("OPENAI_TEMPERATURE", 0.3))

# -----------------------------------------------------------------------------------
# JSON SCHEMA for Memorability Key
# -----------------------------------------------------------------------------------
MEMO_KEY_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "analysis": {"type": "string", "minLength": 20},
        "evidence": {"type": "string", "minLength": 1},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence_rationale": {"type": "string", "minLength": 3},
        "recommendation": {"type": "string", "minLength": 3}
    },
    "required": ["score", "analysis", "evidence", "confidence", "confidence_rationale", "recommendation"],
    "additionalProperties": True
}

# -----------------------------------------------------------------------------------
# PROMPTS
# -----------------------------------------------------------------------------------
MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
Primary key. Without it, nothing is memorable.
Cover: how the brand connects emotionally (warmth, trust, joy, admiration, ambition, tension).
Point to copy, imagery, stories, or UX moments that carry affect.
""",
    "Attention": """
Stimulus key.
Cover: distinctiveness & sustained interest. Visual design (logo, typography, color), motion, headline craft,
and whether cookie walls or generic stock photos dilute attention.
""",
    "Story": """
Stimulus key.
Cover: clarity and power of the brand’s narrative. Does it have a clear promise, POV, and arc?
Is it carried consistently through sections/subpages/social posts?
""",
    "Involvement": """
Stimulus key.
Cover: how the brand invites users to participate (tools, calculators, communities, UGC, social engagement, CTAs that feel valuable).
""",
    "Repetition": """
Reinforcement key.
Cover: the reuse of assets (tagline, logo lockup, color, patterns, motion language, verbal tone) across all touchpoints.
Is it reinforcing, or repetitive without meaning?
""",
    "Consistency": """
Reinforcement key.
Cover: coherence of tone, design system, and messaging across site sections & social channels.
Are product pages, blog, corporate/about pages aligned?
"""
}

KEYS_ORDER = ["Emotion", "Attention", "Story", "Involvement", "Repetition", "Consistency"]

EXEC_SUMMARY_PROMPT = """
You are a senior brand strategist delivering a final executive summary. Based on the six keys below:

1) **Overall Summary** — high-level performance.
2) **Key Strengths** — pick 2–3 strongest keys and why.
3) **Primary Weaknesses** — pick 2–3 weakest keys & their impact.
4) **One Strategic Focus** — the single most important key to improve overall memorability.
5) **Visual Recommendations** — 3–5 highly actionable, concrete design/brand improvements (reference logo, typography, colors, pattern systems, photography style).
6) **Messaging Recommendations** — 3–5 highly actionable, concrete copy/tone/story improvements.

Return plain text (not JSON).
"""

# -----------------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------------
def _registrable_domain(u: str) -> str:
    if tldextract:
        e = tldextract.extract(u)
        return f"{e.domain}.{e.suffix}".lower()
    # fallback
    host = urlparse(u).netloc.lower()
    return host[4:] if host.startswith("www.") else host

def _is_same_domain(home: str, test: str) -> bool:
    return _registrable_domain(home) == _registrable_domain(test)

def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]

def safe_b64(data: bytes) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    # Just return standard padded base64
    return b64

def pad_b64(b64: str) -> str:
    b64 = b64.strip().replace("\n", "")
    missing = len(b64) % 4
    if missing:
        b64 += "=" * (4 - missing)
    return b64

def log_exc_prefix(prefix: str):
    print(prefix)
    traceback.print_exc()

# -----------------------------------------------------------------------------------
# FETCHERS
# -----------------------------------------------------------------------------------
class FetchResult:
    def __init__(self, url: str, html: str, status_code: int, from_renderer: bool):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

_basic_client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

def build_js_killer_script() -> str:
    """
    Returns a single JavaScript snippet that:
    - clicks likely consent buttons by text/click
    - hides remaining overlays
    ScrapingBee wants "script":"<code>" not nested JSON objects for custom JS.
    """
    return r"""
(function(){
  try {
    const textNeedles = [
      'accept','agree','allow','permitir','zulassen','consent',
      'cookies','ok','got it','dismiss','yes'
    ];

    const clickByText = (tag) => {
      const els = document.querySelectorAll(tag);
      for (const el of els) {
        const txt = (el.innerText || el.textContent || '').toLowerCase();
        for (const n of textNeedles) {
          if (txt.includes(n)) {
            try { el.click(); console.log('Clicked text button', txt); return true; } catch(e){}
          }
        }
      }
      return false;
    };

    const cssSelectors = [
      '#onetrust-accept-btn-handler', '.onetrust-accept-btn-handler',
      '#CybotCookiebotDialogBodyLevelButtonAccept',
      '#cookie-accept', '.cookie-accept', '.cookies-accept', '.cc-allow', '.cky-btn-accept',
      "[data-testid='cookie-accept']", "button[aria-label='Accept']",
      "button[aria-label='I agree']", "button[aria-label='Allow']"
    ];

    let clicked = false;
    for (const sel of cssSelectors) {
      const btn = document.querySelector(sel);
      if (btn) { try { btn.click(); clicked = True; } catch(e){} }
    }
    if(!clicked) {
      clickByText('button') || clickByText('a') || clickByText('div[role=button]');
    }

    const kill = [
      "[id*='cookie']", "[class*='cookie']",
      "[id*='consent']", "[class*='consent']",
      "[id*='gdpr']",   "[class*='gdpr']",
      "[id*='privacy']","[class*='privacy']",
      "iframe[src*='consent']", "iframe[src*='cookie']"
    ];

    document.querySelectorAll(kill.join(',')).forEach(el=>{
      try{
        el.style.cssText = "display:none!important;visibility:hidden!important;opacity:0!important;";
      } catch(e){}
    });

    document.body && (document.body.style.overflow = 'auto');
  } catch(e) {}
})();
""".strip()

def build_scrapingbee_params(url: str,
                             render_js: bool,
                             with_js: bool,
                             screenshot: bool = False,
                             full_page: bool = False,
                             premium: bool = False) -> Dict[str, Any]:
    """
    Build ScrapingBee params with the minimum valid fields. Avoid fields that caused
    400 ("Unknown field") in your logs.
    """
    params: Dict[str, Any] = {
        "api_key": Config.SCRAPINGBEE_API_KEY,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "false",      # keep 'false' to avoid 'Not a valid boolean.' (must be string)
        "wait": str(Config.SB_WAIT_MS),  # simple ms wait as string
    }

    if screenshot:
        params["screenshot"] = "true"
        if full_page:
            params["screenshot_full_page"] = "true"

    # Premium/stealth only if needed
    if premium:
        params["premium_proxy"] = "true"

    if with_js:
        # ScrapingBee expects {"instructions": [{...}, ...]} OR "script": "..."
        # Easiest safe approach: single 'script'
        params["js_scenario"] = {
            "instructions": [
                {"wait": Config.SB_WAIT_MS},
                {"script": build_js_killer_script()},
                {"wait": 500}
            ]
        }

    return params

def scrapingbee_request(url: str,
                        render_js: bool,
                        screenshot: bool,
                        full_page: bool,
                        with_js: bool,
                        want_html: bool,
                        try_premium_on_500: bool = True) -> Tuple[Optional[requests.Response], Optional[str]]:
    """
    Generic wrapper for ScrapingBee with retry & downgrade logic.
    Returns (response_or_None, error_text_or_None)
    """
    if not Config.SCRAPINGBEE_API_KEY:
        return None, "ScrapingBee API Key not set"

    last_error = None
    for attempt in range(Config.SB_MAX_RETRIES):
        use_premium = False
        if attempt > 0 and last_error and "Server responded with 500" in last_error and Config.SB_USE_PREMIUM_ON_500 and try_premium_on_500:
            use_premium = True

        params = build_scrapingbee_params(
            url=url,
            render_js=render_js,
            with_js=(with_js and attempt == 0),  # first attempt has js, then fallback
            screenshot=screenshot,
            full_page=full_page,
            premium=use_premium
        )

        label = "HTML" if want_html else "Screenshot"
        print(f"[ScrapingBee]{label} {url} attempt={attempt} render_js={render_js} with_js={with_js and attempt==0}")
        try:
            res = requests.get("https://app.scrapingbee.com/api/v1/",
                               params=params,
                               timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
            if 200 <= res.status_code < 300:
                return res, None
            else:
                body = res.text[:1000]
                print(f"[ScrapingBee] HTTP {res.status_code} attempt={attempt} body={body}")
                last_error = body
        except Exception as e:
            body = str(e)
            print(f"[ScrapingBee] EXC attempt={attempt} {e}")
            last_error = body

    return None, last_error

def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    res, err = scrapingbee_request(
        url=url, render_js=render_js, screenshot=False, full_page=False,
        with_js=True, want_html=True
    )
    if res is None:
        return FetchResult(url, f"ScrapingBee failed after {Config.SB_MAX_RETRIES} attempts: {err}", 500, from_renderer=render_js)
    return FetchResult(url, res.text, res.status_code, from_renderer=render_js)

def scrapingbee_screenshot_fetcher(url: str,
                                   render_js: bool,
                                   full_page: bool = False) -> Optional[Dict[str, Any]]:
    """
    Returns {"bytes": raw_bytes, "mime": "image/jpeg"} or None
    """
    res, err = scrapingbee_request(
        url=url, render_js=render_js, screenshot=True, full_page=full_page,
        with_js=True, want_html=False
    )
    if res is None:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {err}")
        return None

    # ScrapingBee returns raw image bytes by default when screenshot=True
    content = res.content
    if not content:
        return None

    # Convert to JPEG and downsize
    try:
        if Image is None:
            # No Pillow, just store as-is (assume PNG)
            return {"bytes": content, "mime": "image/png"}

        img = Image.open(io.BytesIO(content)).convert("RGB")
        w, h = img.size
        if w > Config.SS_TARGET_WIDTH:
            ratio = Config.SS_TARGET_WIDTH / float(w)
            img = img.resize((Config.SS_TARGET_WIDTH, int(h * ratio)), Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=Config.SS_JPEG_QUALITY, optimize=True)
        return {"bytes": out.getvalue(), "mime": "image/jpeg"}

    except Exception:
        log_exc_prefix("[ScrapingBeeScreenshot] Failed to compress/convert screenshot")
        # fall back to original
        return {"bytes": content, "mime": "image/png"}

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
    for s in Config.SPA_SIGNALS:
        if s in lower_html:
            return True, "spa_signal"
    return False, "ok"

def social_extractor(soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
    found = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best = min(links, key=len)
            found[platform] = urljoin(base_url, best)
    return found

# -----------------------------------------------------------------------------------
# VISUAL FEATURE EXTRACTION
# -----------------------------------------------------------------------------------
def extract_visual_features(images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Very light-weight: top colors + mean brightness. Requires Pillow.
    """
    if Image is None or not images:
        return {}

    def top_colors(img: Image.Image, k: int = 5) -> List[Tuple[int, int, int]]:
        # quantize to palette to get approximate dominant colors
        small = img.resize((128, 128))
        paletted = small.convert("P", palette=Image.ADAPTIVE, colors=k)
        palette = paletted.getpalette()
        color_counts = paletted.getcolors()
        if not color_counts:
            return []
        # sort by frequency
        color_counts.sort(reverse=True)
        cols = []
        for count, color_index in color_counts[:k]:
            r = palette[color_index * 3 + 0]
            g = palette[color_index * 3 + 1]
            b = palette[color_index * 3 + 2]
            cols.append((r, g, b))
        return cols

    def mean_brightness(img: Image.Image) -> float:
        gray = img.convert("L")
        hist = gray.histogram()
        total_pixels = sum(hist)
        if total_pixels == 0:
            return 0.0
        s = sum(i * v for i, v in enumerate(hist))
        return s / total_pixels

    feats = {
        "screenshots": []
    }

    for i, item in enumerate(images):
        try:
            im = Image.open(io.BytesIO(item["bytes"])).convert("RGB")
            colors = top_colors(im, 5)
            bright = mean_brightness(im)
            feats["screenshots"].append({
                "idx": i,
                "top_colors_rgb": colors,
                "mean_brightness": round(bright, 2),
            })
        except Exception:
            log_exc_prefix("[Visual] could not extract for screenshot")
            continue

    # Flatten a union of top colors to pass as human-readable hex list
    all_cols = []
    for s in feats["screenshots"]:
        all_cols.extend(s.get("top_colors_rgb", []))
    hexes = list({ "#{:02x}{:02x}{:02x}".format(r,g,b) for (r,g,b) in all_cols })
    feats["dominant_hex_palette"] = hexes[:10]

    return feats

# -----------------------------------------------------------------------------------
# OPENAI HELPERS
# -----------------------------------------------------------------------------------
def _openai_client_without_proxies() -> OpenAI:
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
    # We'll restore inside the finally block in the caller
    http_client = httpx.Client(proxies=None, timeout=60.0)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
    return client, original

def _restore_proxies(original: Dict[str, Optional[str]]):
    for k, v in original.items():
        if v is not None:
            os.environ[k] = v

def call_openai_for_synthesis(text: str) -> str:
    print("[AI] Synthesizing brand overview...")
    client, original = _openai_client_without_proxies()
    try:
        synthesis_prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n---\n"
            f"{text}\n---"
        )
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role":"user","content":synthesis_prompt}],
            temperature=0.2
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."
    finally:
        _restore_proxies(original)

def validate_or_default(key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if validate is None:
        return payload
    try:
        validate(payload, MEMO_KEY_SCHEMA)
        return payload
    except ValidationError as ve:
        print(f"[Validator] Key='{key}' payload invalid, using fallback. Error: {ve}")
        return {
            "score": payload.get("score", 0),
            "analysis": payload.get("analysis", "Analysis failed JSON validation."),
            "evidence": payload.get("evidence", "N/A"),
            "confidence": payload.get("confidence", 1),
            "confidence_rationale": payload.get("confidence_rationale", "Validation failed."),
            "recommendation": payload.get("recommendation", "Re-run with correct JSON schema.")
        }

def analyze_memorability_key(
    key_name: str,
    prompt_template: str,
    text_corpus: str,
    brand_summary: str,
    visual_features: Dict[str, Any],
    image_b64s: List[str]
) -> Tuple[str, Dict[str, Any]]:

    print(f"[AI] Analyzing key: {key_name}")
    client, original = _openai_client_without_proxies()
    try:
        # Build message
        system_prompt = f"""
You are a senior brand strategist from Saffron Brand Consultants.
You will evaluate the brand on the **{key_name}** key of memorability.

Return STRICT JSON with keys:
- score (0-100)
- analysis (>=5 sentences)
- evidence
- confidence (1-5)
- confidence_rationale
- recommendation (1-3 very actionable steps)

Use EVERY source provided (text, visuals & extracted features), but be concise.
""".strip()

        visuals_text = json.dumps(visual_features, indent=2) if visual_features else "{}"

        user_blocks: List[Dict[str, Any]] = []

        # Attach images (if any)
        for b in image_b64s:
            user_blocks.append({"type":"image_url","image_url":{"url": f"data:image/jpeg;base64,{b}"}})

        user_blocks.append({"type":"text","text": f"BRAND SUMMARY:\n{brand_summary}"})
        user_blocks.append({"type":"text","text": f"FULL TEXT CORPUS:\n{text_corpus}"})
        user_blocks.append({"type":"text","text": f"VISUAL FEATURES (colors/brightness):\n{visuals_text}"})
        user_blocks.append({"type":"text","text": f"KEY SPECIFIC PROMPT:\n{prompt_template}"})

        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_blocks},
            ],
            temperature=Config.OPENAI_TEMPERATURE,
            response_format={"type": "json_object"}
        )

        payload = resp.choices[0].message.content
        data = json.loads(payload)
        data = validate_or_default(key_name, data)
        return key_name, data

    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        fallback = {
            "score": 0,
            "analysis": "Analysis failed due to a system error.",
            "evidence": str(e),
            "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Fix the technical error and retry."
        }
        return key_name, fallback
    finally:
        _restore_proxies(original)

def call_openai_for_executive_summary(all_analyses: List[Dict[str, Any]]) -> str:
    print("[AI] Generating Executive Summary...")
    client, original = _openai_client_without_proxies()
    try:
        analyses_text = "\n\n".join([
            f"Key: {d['key']}\nScore: {d['analysis']['score']}\nAnalysis: {d['analysis']['analysis']}"
            for d in all_analyses
        ])
        msg = f"{EXEC_SUMMARY_PROMPT}\n\n---\n{analyses_text}\n---"
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role":"user","content": msg}],
            temperature=0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."
    finally:
        _restore_proxies(original)

# -----------------------------------------------------------------------------------
# MAIN ORCHESTRATOR
# -----------------------------------------------------------------------------------
def run_full_scan_stream(url: str, cache: Dict[str, Any]):

    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed: List[FetchResult] = []
    text_corpus = ""
    socials_found = False

    # store screenshots (dict objects) we'll pass to LLM later
    kept_screens: List[Dict[str, Any]] = []

    queue = deque([(_clean_url(url), 0)])
    seen = {_clean_url(url)}

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
                final_result = scrapingbee_html_fetcher(current_url, render_js=True)

            # Try to capture one screenshot per page (JS on)
            ss_obj = scrapingbee_screenshot_fetcher(current_url, render_js=True, full_page=False)
            if ss_obj:
                if len(kept_screens) < Config.MAX_SCREENSHOTS_FOR_LLM:
                    kept_screens.append(ss_obj)
                image_id = str(uuid.uuid4())
                cache[image_id] = ss_obj  # store dict {bytes, mime}
                yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            # Process HTML
            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                # Clean & accumulate text
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + soup.get_text(" ", strip=True)

                # Enqueue new links
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
                        if len(pages_analyzed) + len(queue) >= Config.CRAWL_MAX_PAGES:
                            break
                        queue.append((link_url, depth + 1))
                        seen.add(link_url)

            pages_analyzed.append(final_result)

            elapsed = time.time() - start_time
            if not escalated and elapsed < budget:
                pages_rendered_by_bee = sum(1 for p in pages_analyzed if p.from_renderer)
                if len(pages_analyzed) >= 3 and pages_rendered_by_bee >= 2 and not socials_found:
                    budget = Config.SITE_MAX_BUDGET_SECS
                    escalated = True
                    yield {'type': 'status', 'message': f'High JS usage and no socials found → escalating budget to {budget}s.'}

        yield {'type': 'status', 'message': 'Crawl complete. Starting AI analysis...'}

        # Visual features
        visual_feats = extract_visual_features(kept_screens)
        # Convert up to 3 to base64-jpeg
        image_b64s = []
        for i, s in enumerate(kept_screens[:Config.MAX_SCREENSHOTS_FOR_LLM]):
            b64 = safe_b64(s["bytes"])
            image_b64s.append(b64)

        brand_summary = call_openai_for_synthesis(text_corpus)

        all_results = []
        for key in KEYS_ORDER:
            prompt = MEMORABILITY_KEYS_PROMPTS[key]
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            k, result_json = analyze_memorability_key(
                key_name=key,
                prompt_template=prompt,
                text_corpus=text_corpus,
                brand_summary=brand_summary,
                visual_features=visual_feats,
                image_b64s=image_b64s
            )
            result_obj = {'type': 'result', 'key': k, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj

        yield {'type': 'status', 'message': 'Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {'type': 'summary', 'text': summary_text}
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        traceback.print_exc()
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
