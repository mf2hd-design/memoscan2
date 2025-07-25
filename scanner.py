import os
import re
import io
import time
import uuid
import math
import json
import base64
import logging
import traceback
from collections import deque, Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests
import httpx
import tldextract
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError
from jsonschema import validate as js_validate, ValidationError

from openai import OpenAI

# ------------------------------------------------------------------------------------
# Global, shared cache (imported by app.py)
# ------------------------------------------------------------------------------------
SHARED_CACHE: Dict[str, str] = {}

# ------------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------------
logger = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------------
class Config:
    # Budgets
    SITE_BUDGET_SECS         = int(os.getenv("SITE_BUDGET_SECS", 120))
    SITE_MAX_BUDGET_SECS     = int(os.getenv("SITE_MAX_BUDGET_SECS", 150))

    # Crawl
    CRAWL_MAX_PAGES          = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH          = int(os.getenv("CRAWL_MAX_DEPTH", 2))

    # Timeouts
    BASIC_TIMEOUT_SECS       = int(os.getenv("BASIC_TIMEOUT_SECS", 20))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 30))

    # Render policy thresholds
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY", "")
    SB_RETRIES               = 3
    SB_PREMIUM_ON_500        = bool(int(os.getenv("SB_PREMIUM_ON_500", "0")))   # escalate only at the last attempt
    SB_STEALTH_ON_500        = bool(int(os.getenv("SB_STEALTH_ON_500", "0")))
    SB_BLOCK_RESOURCES       = os.getenv("SB_BLOCK_RESOURCES", "false").lower() == "true"

    # Image handling
    MAX_SCREENSHOTS_PER_PAGE = int(os.getenv("MAX_SCREENSHOTS_PER_PAGE", 3))  # fold, mid, footer
    JPEG_QUALITY             = int(os.getenv("JPEG_QUALITY", 80))
    RESIZE_LONGEST_PX        = int(os.getenv("RESIZE_LONGEST_PX", 1400))

    # Visual colors extraction
    NUM_DOMINANT_COLORS      = int(os.getenv("NUM_DOMINANT_COLORS", 5))

    # OpenAI
    OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_TEMPERATURE       = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

    # Social patterns
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }

    # Binary file regex
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)


# ------------------------------------------------------------------------------------
# JSON schema for LLM responses (one per key)
# ------------------------------------------------------------------------------------
LLM_KEY_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "analysis": {"type": "string", "minLength": 5},
        "evidence": {"type": "string"},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence_rationale": {"type": "string"},
        "recommendation": {"type": "string"}
    },
    "required": ["score", "analysis", "confidence", "confidence_rationale", "recommendation"],
    "additionalProperties": True
}

# ------------------------------------------------------------------------------------
# Memorability prompts
# ------------------------------------------------------------------------------------
MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
Analyze the **Emotion** key. This is the primary key; without it, nothing is memorable.
- How does the brand connect emotionally (warmth, trust, joy, admiration)?
- Does it use meaningful experiences, human stories, or mission-led language?
- Is there a clear emotional reward for the audience?
""",
    "Attention": """
Analyze the **Attention** key. Stimulus key.
- Distinctiveness and ability to stand out.
- Surprising visuals/headlines?
- Does it sustain interest without cliché CTA spam?
""",
    "Story": """
Analyze the **Story** key. Stimulus key.
- Clarity & power of the narrative: who are they, what they promise.
- Authenticity: does it build trust + curiosity better than raw facts?
""",
    "Involvement": """
Analyze the **Involvement** key. Stimulus key.
- Does the brand make audiences feel like participants (community, belonging)?
- Is the content aligned with what’s meaningful to them?
""",
    "Repetition": """
Analyze the **Repetition** key. Reinforcement key.
- Reuse of brand elements (symbol, tagline, colors) across touchpoints.
- Is repetition thoughtful, or bordering on overexposure?
""",
    "Consistency": """
Analyze the **Consistency** key. Reinforcement key.
- Coherence across all touchpoints (tone, message, design).
- Does it build familiarity & predictable pattern recognition?
"""
}

# ------------------------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------------------------
@dataclass
class FetchResult:
    url: str
    html: str
    status_code: int
    from_renderer: bool

# ------------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------------
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

def _safe_b64_to_jpeg_data_url(raw_bytes: bytes) -> Optional[str]:
    """
    Convert raw PNG bytes to JPEG, resize and return data URL.
    """
    try:
        im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    except UnidentifiedImageError:
        logger.warning("[IMG] Could not identify image; probably not a screenshot.")
        return None

    # resize if needed
    w, h = im.size
    longest = max(w, h)
    if longest > Config.RESIZE_LONGEST_PX:
        scale = Config.RESIZE_LONGEST_PX / float(longest)
        im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    out = io.BytesIO()
    im.save(out, format="JPEG", quality=Config.JPEG_QUALITY, optimize=True)
    out.seek(0)
    b64 = base64.b64encode(out.read()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"

def _extract_dominant_colors(raw_bytes: bytes, k: int = 5) -> List[Tuple[int, int, int]]:
    """
    Simple dominant color extraction via counting (no KMeans for speed).
    """
    try:
        im = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    except UnidentifiedImageError:
        return []

    im = im.resize((64, 64))  # speed up
    pixels = list(im.getdata())
    counts = Counter(pixels)
    most_common = counts.most_common(k)
    return [rgb for rgb, _ in most_common]

def _color_to_hex(c: Tuple[int, int, int]) -> str:
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"

def _avg_luminance(colors: List[Tuple[int, int, int]]) -> float:
    if not colors:
        return 0.0
    def lum(c):
        r, g, b = c
        return 0.2126*r + 0.7152*g + 0.0722*b
    return sum(lum(c) for c in colors) / len(colors)

def _contrast_ratio(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    def rel_lum(c):
        r, g, b = [x/255.0 for x in c]
        def channel(v):
            return v/12.92 if v <= 0.03928 else ((v+0.055)/1.055) ** 2.4
        R, G, B = channel(r), channel(g), channel(b)
        return 0.2126*R + 0.7152*G + 0.0722*B
    L1 = rel_lum(c1)
    L2 = rel_lum(c2)
    lighter = max(L1, L2)
    darker  = min(L1, L2)
    return (lighter + 0.05) / (darker + 0.05)

def _visual_features_from_screenshots(raw_images: List[bytes]) -> Dict:
    """
    Aggregate visual hints from up to 3 screenshots.
    """
    features = {
        "num_screens": len(raw_images),
        "dominant_colors_hex": [],
        "avg_luminance": 0.0,
        "max_contrast_ratio": None,
    }
    all_colors = []
    for raw in raw_images:
        cols = _extract_dominant_colors(raw, k=Config.NUM_DOMINANT_COLORS)
        all_colors.extend(cols)
        features["dominant_colors_hex"].extend([_color_to_hex(c) for c in cols])

    if all_colors:
        features["avg_luminance"] = _avg_luminance(all_colors)
        # compute max contrast among top few
        if len(all_colors) > 1:
            mx = 0.0
            for i in range(len(all_colors)):
                for j in range(i+1, len(all_colors)):
                    mx = max(mx, _contrast_ratio(all_colors[i], all_colors[j]))
            features["max_contrast_ratio"] = round(mx, 2)
    return features

def _validate_json_against_schema(obj: dict, schema: dict) -> Tuple[bool, Optional[str]]:
    try:
        js_validate(instance=obj, schema=schema)
        return True, None
    except ValidationError as ve:
        return False, str(ve)

# ------------------------------------------------------------------------------------
# HTTP clients
# ------------------------------------------------------------------------------------
_basic_client = httpx.Client(
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    },
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS,
)

# ------------------------------------------------------------------------------------
# Fetchers & ScrapingBee
# ------------------------------------------------------------------------------------
def basic_fetcher(url: str) -> FetchResult:
    logger.info(f"[BasicFetcher] {url}")
    try:
        r = _basic_client.get(url)
        r.raise_for_status()
        return FetchResult(url=str(r.url), html=r.text, status_code=r.status_code, from_renderer=False)
    except Exception as e:
        logger.warning(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url=url, html=f"Failed to fetch: {e}", status_code=500, from_renderer=False)

def build_js_scenario() -> dict:
    # All "click: selector" steps must be real CSS/XPATH instructions. We'll do everything in evaluate.
    # 'strict': false to prevent selector failures from killing the scenario.
    code = r"""
      (function(){
        try {
          const textNeedles = [
            'accept','agree','allow','permitir','zulassen','consent',
            'cookies','ok','got it','dismiss','yes'
          ];

          // Click by text content
          const clickByText = (rootSelectorList, tagList) => {
            const rootEls = rootSelectorList.length ? document.querySelectorAll(rootSelectorList.join(',')) : [document];
            for (const root of rootEls) {
              for (const t of tagList) {
                const els = root.querySelectorAll(t);
                for (const el of els) {
                  const txt = (el.innerText || el.textContent || '').toLowerCase();
                  if (textNeedles.some(n => txt.includes(n))) {
                    try { el.click(); } catch(e){}
                  }
                }
              }
            }
          };

          // CSS selectors commonly used by cookie banners
          const cssSelectors = [
            '#onetrust-accept-btn-handler', '.onetrust-accept-btn-handler',
            '#CybotCookiebotDialogBodyLevelButtonAccept',
            '#cookie-accept', '.cookie-accept', '.cookies-accept',
            '.cc-allow', '.cky-btn-accept',
            "[aria-label='Accept']", "[aria-label='I agree']"
          ];
          for (const sel of cssSelectors) {
            const btn = document.querySelector(sel);
            if (btn) { try { btn.click(); } catch(e){} }
          }

          // Fallback click-by-text search
          clickByText([], ['button', 'a', 'div', 'span']);

          // Hide everything that looks like a banner
          const kill = [
            "[id*='cookie']", "[class*='cookie']",
            "[id*='consent']", "[class*='consent']",
            "[id*='gdpr']",   "[class*='gdpr']",
            "[id*='privacy']","[class*='privacy']",
            "iframe[src*='consent']", "iframe[src*='cookie']"
          ];
          document.querySelectorAll(kill.join(',')).forEach(el => {
            try {
              el.style.cssText = "display:none!important;visibility:hidden!important;opacity:0!important;";
            } catch(e){}
          });

          document.body.style.overflow = 'auto';
        } catch(e) {
          console.log('cookie killer error', e);
        }
      })();
    """.strip()

    return {
        "strict": False,
        "instructions": [
            {"wait": 1500},
            {"evaluate": code},
            {"wait": 500}
        ]
    }

def _scrapingbee_request(
    url: str,
    *,
    render_js: bool,
    want_html: bool = True,
    want_screenshot: bool = False,
    with_js: bool = True,
    try_premium: bool = False,
    try_stealth: bool = False
) -> Tuple[Optional[str], Optional[bytes], int, bool]:
    """
    Returns (html_text, screenshot_bytes, status_code, from_renderer)
    html_text iff want_html
    screenshot_bytes iff want_screenshot
    """
    api_key = Config.SCRAPINGBEE_API_KEY
    if not api_key:
        return None, None, 500, False

    base_params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "true" if Config.SB_BLOCK_RESOURCES else "false",
        "wait": 2000
    }

    if try_premium:
        base_params["premium_proxy"] = "true"
    if try_stealth:
        base_params["stealth_proxy"] = "true"

    if want_screenshot:
        base_params["screenshot"] = "true"
        # ScrapingBee returns PNG bytes for screenshot

    if with_js and render_js:
        base_params["js_scenario"] = json.dumps(build_js_scenario())

    url_endpoint = "https://app.scrapingbee.com/api/v1/"

    for attempt in range(Config.SB_RETRIES):
        with_js_this_try = with_js if attempt == 0 else False
        if not with_js_this_try and "js_scenario" in base_params:
            del base_params["js_scenario"]

        try:
            logger.info(f"[ScrapingBee]{'Screenshot' if want_screenshot else 'HTML'} {url} attempt={attempt} render_js={render_js} with_js={with_js_this_try}")
            r = requests.get(url_endpoint, params=base_params, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
            if r.status_code >= 400:
                logger.warning(f"[ScrapingBee] HTTP {r.status_code} attempt={attempt} body={r.text[:400]}")
                # last attempt escalate if configured
                if attempt == Config.SB_RETRIES - 1 and r.status_code >= 500 and (Config.SB_PREMIUM_ON_500 or Config.SB_STEALTH_ON_500):
                    # one final escalate
                    base_params["premium_proxy"] = "true" if Config.SB_PREMIUM_ON_500 else base_params.get("premium_proxy", None)
                    base_params["stealth_proxy"] = "true" if Config.SB_STEALTH_ON_500 else base_params.get("stealth_proxy", None)
                    continue
                # else retry without js_scenario or just exit after final
                continue

            # Success
            from_renderer = render_js
            if want_screenshot:
                # content is PNG bytes
                return None, r.content, r.status_code, from_renderer
            else:
                return r.text, None, r.status_code, from_renderer

        except Exception as e:
            logger.warning(f"[ScrapingBee] EXC attempt={attempt} {e}")
            if attempt == Config.SB_RETRIES - 1:
                return None, None, 500, render_js

    return None, None, 500, render_js

def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    html, _, status, from_renderer = _scrapingbee_request(
        url,
        render_js=render_js,
        want_html=True,
        want_screenshot=False,
        with_js=True
    )
    if html is None:
        return FetchResult(url, f"ScrapingBee failed for HTML: HTTP {status}", status, from_renderer)
    return FetchResult(url, html, status, from_renderer)

def scrapingbee_screenshot_fetcher(url: str, render_js: bool) -> Optional[List[bytes]]:
    """
    Returns list of up to MAX_SCREENSHOTS_PER_PAGE PNG raw bytes:
    fold, mid-page, footer (we just take 1 screenshot for now – full page requires premium;
    you can re-enable full page with screenshot_full_page=true if your plan allows).
    """
    # We'll keep it simple: single "fold" screenshot. You can extend to 3 by
    # doing multiple scroll_to / screenshot_selector instructions in your js_scenario
    # + repeated calls. For now, return 1 screenshot.
    _, content, status, _ = _scrapingbee_request(
        url,
        render_js=render_js,
        want_html=False,
        want_screenshot=True,
        with_js=True
    )
    if content is None:
        return None
    return [content]

# ------------------------------------------------------------------------------------
# Render policy
# ------------------------------------------------------------------------------------
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

def social_extractor(soup, base_url):
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = requests.compat.urljoin(base_url, best_link)
    return found_socials

# ------------------------------------------------------------------------------------
# OpenAI helpers
# ------------------------------------------------------------------------------------
def _get_openai_client():
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
    # We return a tuple (client, restore_fn)
    def _restore():
        for key, value in original.items():
            if value is not None:
                os.environ[key] = value
    http_client = httpx.Client(proxies=None)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
    return client, _restore

def call_openai_for_synthesis(corpus: str) -> str:
    logger.info("[AI] Synthesizing brand overview...")
    client, restore = _get_openai_client()
    try:
        synthesis_prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n---\n"
            f"{corpus}\n---"
        )
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=Config.OPENAI_TEMPERATURE
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("[ERROR] AI synthesis failed: %s", e)
        return "Could not generate brand summary due to an error."
    finally:
        restore()

def analyze_memorability_key(
    key_name: str,
    prompt_template: str,
    text_corpus: str,
    brand_summary: str,
    image_data_urls: List[str],
    visual_hints: Dict
):
    logger.info(f"[AI] Analyzing key: {key_name}")
    client, restore = _get_openai_client()
    try:
        # Build content
        content = []
        # Add up to 3 images
        for data_url in image_data_urls[:3]:
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        content.append({"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"})
        content.append({"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"})
        content.append({"type": "text", "text": f"VISUAL HINTS (auto-extracted):\n{json.dumps(visual_hints, indent=2)}"})

        system_prompt = f"""
You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
{prompt_template}

Your response MUST be a JSON object with the following keys:
- "score": An integer from 0 to 100.
- "analysis": A comprehensive analysis of **at least five sentences** explaining your score, based on the specific criteria provided.
- "evidence": A single, direct quote from the text or a specific visual observation from the provided screenshots.
- "confidence": An integer from 1 to 5.
- "confidence_rationale": A brief explanation for your confidence score.
- "recommendation": A concise, actionable recommendation for how the brand could improve its score for this specific key.
"""

        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)
        ok, err = _validate_json_against_schema(parsed, LLM_KEY_SCHEMA)
        if not ok:
            logger.warning("[SCHEMA] Invalid JSON for key %s: %s. Will wrap into fallback.", key_name, err)
            parsed = {
                "score": int(parsed.get("score", 0)) if isinstance(parsed.get("score"), int) else 0,
                "analysis": parsed.get("analysis", "Invalid JSON, but here is the raw response."),
                "evidence": parsed.get("evidence", ""),
                "confidence": int(parsed.get("confidence", 1)) if isinstance(parsed.get("confidence"), int) else 1,
                "confidence_rationale": parsed.get("confidence_rationale", "Schema validation failed."),
                "recommendation": parsed.get("recommendation", "Re-run analysis with valid schema.")
            }
        return key_name, parsed
    except Exception as e:
        logger.exception(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        return key_name, {
            "score": 0,
            "analysis": "Analysis failed due to a server error.",
            "evidence": str(e),
            "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Resolve the technical error to proceed."
        }
    finally:
        restore()

def call_openai_for_executive_summary(all_analyses: List[dict]) -> str:
    logger.info("[AI] Generating Executive Summary...")
    client, restore = _get_openai_client()
    try:
        analyses_text = "\n\n".join([
            f"Key: {d['key']}\nScore: {d['analysis']['score']}\nAnalysis: {d['analysis']['analysis']}"
            for d in all_analyses
        ])
        prompt = f"""You are a senior brand strategist delivering a final executive summary. Based on the following six key analyses, please provide:
1) Overall Summary: A brief, high-level overview of the brand's memorability performance.
2) Key Strengths: Identify the 2-3 strongest keys and explain why.
3) Primary Weaknesses: Identify the 2-3 weakest keys and explain the impact.
4) Strategic Focus: State the single most important key the brand should focus on to improve overall memorability.

Here are the individual analyses to synthesize:
---
{analyses_text}
---
"""
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("[ERROR] AI summary failed: %s", e)
        return "Could not generate the executive summary due to an error."
    finally:
        restore()

# ------------------------------------------------------------------------------------
# Main Orchestrator (generator)
# ------------------------------------------------------------------------------------
def run_full_scan_stream(url: str, cache: Dict[str, str]):
    start = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed: List[FetchResult] = []
    text_corpus = ""
    socials_found = False
    homepage_jpegs: List[str] = []   # data URLs (JPEG) – send to LLM
    homepage_raws: List[bytes] = []  # raw bytes for visual extraction

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
            yield {'type': 'status', 'message': f'Analyzing page {len(pages_analyzed) + 1}/{Config.CRAWL_MAX_PAGES}: {current_url}'}

            # 1) basic
            basic_res = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_res)
            final_res = basic_res

            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                final_res = scrapingbee_html_fetcher(current_url, render_js=True)

            # 2) screenshot (only for first page OR if you want per page – we keep it first page for cost)
            if len(pages_analyzed) == 0:
                raw_pngs = scrapingbee_screenshot_fetcher(current_url, render_js=final_res.from_renderer)
                if raw_pngs:
                    # store up to MAX_SCREENSHOTS_PER_PAGE as data URLs in cache
                    for raw in raw_pngs[:Config.MAX_SCREENSHOTS_PER_PAGE]:
                        data_url = _safe_b64_to_jpeg_data_url(raw)
                        if data_url:
                            image_id = str(uuid.uuid4())
                            cache[image_id] = data_url.split(",")[1]  # store only b64 for HTTP endpoint (png->jpeg still fine)
                            SHARED_CACHE[image_id] = cache[image_id]
                            yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}
                            homepage_jpegs.append(data_url)
                            homepage_raws.append(raw)

            # 3) HTML parsing
            if final_res.html:
                soup = BeautifulSoup(final_res.html, "lxml")
                logger.info(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_res.from_renderer})")

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
                        link = _clean_url(requests.compat.urljoin(current_url, href))
                        if not _is_same_domain(url, link) or link in seen:
                            continue

                        remaining_slots = Config.CRAWL_MAX_PAGES - (len(pages_analyzed) + len(queue))
                        if remaining_slots <= 0:
                            break

                        queue.append((link, depth + 1))
                        seen.add(link)

            pages_analyzed.append(final_res)

            # escalate global budget if needed
            elapsed = time.time() - start
            if not escalated and elapsed < budget:
                pages_rendered_by_bee = sum(1 for p in pages_analyzed if p.from_renderer)
                if len(pages_analyzed) >= 3 and pages_rendered_by_bee >= 2 and not socials_found:
                    budget = Config.SITE_MAX_BUDGET_SECS
                    escalated = True
                    yield {'type': 'status', 'message': f'High JS usage and no socials found → escalating budget to {budget}s.'}

        # -----------------------------------------
        # AI analysis
        # -----------------------------------------
        yield {'type': 'status', 'message': 'Crawl complete. Starting AI analysis...'}

        brand_summary = call_openai_for_synthesis(text_corpus)

        # Visual hints from up to 3 screenshots
        visual_hints = _visual_features_from_screenshots(homepage_raws[:3])

        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                key,
                prompt,
                text_corpus,
                brand_summary,
                homepage_jpegs[:3],
                visual_hints
            )
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj

        yield {'type': 'status', 'message': 'Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {'type': 'summary', 'text': summary_text}
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        logger.exception("[CRITICAL ERROR] The main stream failed: %s", e)
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
