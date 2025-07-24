# scanner.py  (drop-in)
# Last updated: 2025-07-25

import os
import re
import json
import time
import uuid
import base64
import httpx
import imghdr
import requests
import tldextract
from collections import deque
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ============================================================
# ----------------------- CONFIG -----------------------------
# ============================================================

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

    # Render policy
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # Visuals
    VISUAL_SCREENSHOTS_PER_SITE = int(os.getenv("VISUAL_SCREENSHOTS_PER_SITE", 2))  # fold + mid
    SCREENSHOT_FULL_PAGE     = os.getenv("SCREENSHOT_FULL_PAGE", "false").lower() == "true"
    SCREENSHOT_WIDTH         = int(os.getenv("SCREENSHOT_WIDTH", 1280))
    SCREENSHOT_HEIGHT        = int(os.getenv("SCREENSHOT_HEIGHT", 1024))

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY", "")
    SCRAPINGBEE_RETRIES      = int(os.getenv("SCRAPINGBEE_RETRIES", 3))
    SCRAPINGBEE_BACKOFF_SECS = float(os.getenv("SCRAPINGBEE_BACKOFF_SECS", 1.5))
    SCRAPINGBEE_PREMIUM      = os.getenv("SCRAPINGBEE_PREMIUM", "false").lower() == "true"
    SCRAPINGBEE_STEALTH      = os.getenv("SCRAPINGBEE_STEALTH", "false").lower() == "true"
    SCRAPINGBEE_JSON_HTML    = os.getenv("SCRAPINGBEE_JSON_HTML", "false").lower() == "true"  # if true, use response_format=json for html

    # Social regex map
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }

    # Skip binaries
    BINARY_RE = re.compile(r'\.(pdf|png|jpe?g|gif|mp4|zip|rar|svg|webp|ico|css|js|woff2?|ttf|eot)$', re.I)

    # OpenAI
    OPENAI_MODEL             = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_TEMPERATURE       = float(os.getenv("OPENAI_TEMPERATURE", 0.3))

# ============================================================
# ---------------------- HELPERS -----------------------------
# ============================================================

def _registrable_domain(u: str) -> str:
    e = tldextract.extract(u)
    return f"{e.domain}.{e.suffix}".lower()

def _is_same_domain(home: str, test: str) -> bool:
    return _registrable_domain(home) == _registrable_domain(test)

def _clean_url(u: str) -> str:
    u = u.strip()
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.split("#")[0]

def _safe_get_text_len(html: str) -> int:
    try:
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return len(soup.get_text(" ", strip=True))
    except Exception:
        return len(html)

def _guess_mime_from_b64(b64_str: str) -> str:
    try:
        head = base64.b64decode(b64_str[:80], validate=False)
    except Exception:
        return "application/octet-stream"
    kind = imghdr.what(None, head)
    if kind == "png":
        return "image/png"
    if kind in ("jpeg", "jpg"):
        return "image/jpeg"
    if kind == "gif":
        return "image/gif"
    if kind == "webp":
        return "image/webp"
    return "application/octet-stream"

def _b64_looks_like_supported_image(b64_str: str) -> bool:
    if not b64_str or len(b64_str) < 100:
        return False
    mime = _guess_mime_from_b64(b64_str)
    return mime in {"image/png", "image/jpeg", "image/gif", "image/webp"}

def _extract_visual_hints(html: str):
    """Very light-weight heuristics to send to the LLM."""
    colors = list(set(re.findall(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b", html)))[:15]
    fonts  = list(set(re.findall(r"font-family\s*:\s*([^;]+);", html, flags=re.I)))[:10]
    return {
        "palette_hex": colors,
        "font_families": [f.strip().strip("\"'") for f in fonts],
    }

# ============================================================
# --------------------- FETCHERS -----------------------------
# ============================================================

class FetchResult:
    def __init__(self, url, html, status_code, from_renderer):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

_basic_client = httpx.Client(
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    },
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS
)

def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] {url}")
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url, f"ERROR: {e}", 500, False)

def _build_js_scenario():
    """
    We rely on a SCRIPT step that:
      1) clicks cookie buttons by trying common selectors & text
      2) hides any leftover overlays
    ScrapingBee wants: {"js_scenario": {"instructions": [{"wait": 1200}, {"script": "..."}]}}
    """
    script = r"""
      (function(){
        try {
          const textNeedles = [
            'accept', 'agree', 'allow', 'permitir', 'zulassen', 'consent',
            'cookies', 'ok', 'got it', 'dismiss', 'yes,'
          ];

          // Try clicking based on textContent (case-insensitive)
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
            "[data-testid='cookie-accept']",
            "button[aria-label='Accept']", "button[aria-label='Allow']"
          ];

          // Try CSS selectors first
          for (const sel of cssSelectors) {
            try {
              const el = document.querySelector(sel);
              if (el) { el.click(); console.log('Clicked CSS consent', sel); }
            } catch(e){}
          }

          // Then text-based
          clickByText('button');
          clickByText('a');
          clickByText('div');
          clickByText('span');

          // Force hide if still present
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

          document.body && (document.body.style.overflow='auto');
        } catch(e) {
          console.warn('cookie killer script failed', e);
        }
      })();
    """.strip()

    return {
        "instructions": [
            {"wait": 1200},
            {"script": script}
        ]
    }

def _scrapingbee_request(params, purpose, retries=Config.SCRAPINGBEE_RETRIES):
    """
    Unified GET with retry/backoff, prints bodies on 4xx/5xx once.
    """
    url = "https://app.scrapingbee.com/api/v1/"
    attempt = 0
    last_exc = None
    while attempt < retries:
        try:
            res = requests.get(url, params=params, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
            if res.status_code >= 400:
                body = res.text[:1000]
                print(f"[ScrapingBee] HTTP {res.status_code} attempt={attempt} body={body}")
                attempt += 1
                time.sleep(Config.SCRAPINGBEE_BACKOFF_SECS * attempt)
                continue
            return res
        except Exception as e:
            print(f"[ScrapingBee] EXC attempt={attempt} {e}")
            last_exc = e
            attempt += 1
            time.sleep(Config.SCRAPINGBEE_BACKOFF_SECS * attempt)
    raise RuntimeError(f"ScrapingBee failed after {retries} attempts: {last_exc}")

def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    print(f"[ScrapingBeeHTML] {url} (render_js={render_js})")
    if not Config.SCRAPINGBEE_API_KEY:
        return FetchResult(url, "ScrapingBee API Key not set", 500, render_js)

    params = {
        "api_key": Config.SCRAPINGBEE_API_KEY,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "true",
        "wait": 3000,
        "response_format": "json" if Config.SCRAPINGBEE_JSON_HTML else "html"
    }

    if render_js:
        params["js_scenario"] = json.dumps(_build_js_scenario())

    if Config.SCRAPINGBEE_PREMIUM:
        params["premium_proxy"] = "true"
    if Config.SCRAPINGBEE_STEALTH:
        params["stealth_proxy"] = "true"

    try:
        res = _scrapingbee_request(params, "html")
        if Config.SCRAPINGBEE_JSON_HTML:
            data = res.json()
            html = data.get("body", "") or data.get("content", "")
        else:
            html = res.text
        return FetchResult(url, html, res.status_code, render_js)
    except Exception as e:
        print(f"[ScrapingBeeHTML] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed via ScrapingBee: {e}", 500, render_js)

def scrapingbee_screenshot_fetcher(url: str, render_js: bool) -> str | None:
    """
    Returns base64 (no data: prefix). Uses response_format=b64_bytes.
    """
    print(f"[ScrapingBeeScreenshot] {url} (render_js={render_js})")
    if not Config.SCRAPINGBEE_API_KEY:
        return None

    params = {
        "api_key": Config.SCRAPINGBEE_API_KEY,
        "url": url,
        "render_js": "true" if render_js else "false",
        "screenshot": "true",
        "response_format": "b64_bytes",
        "image_format": "png",
        "window_width": Config.SCREENSHOT_WIDTH,
        "window_height": Config.SCREENSHOT_HEIGHT,
        "screenshot_full_page": "true" if Config.SCREENSHOT_FULL_PAGE else "false",
        "block_resources": "false",
        "wait": 2000
    }
    params["js_scenario"] = json.dumps(_build_js_scenario())

    if Config.SCRAPINGBEE_PREMIUM:
        params["premium_proxy"] = "true"
    if Config.SCRAPINGBEE_STEALTH:
        params["stealth_proxy"] = "true"

    try:
        res = _scrapingbee_request(params, "screenshot")
        b64_bytes = res.text.strip().strip('"')
        if not _b64_looks_like_supported_image(b64_bytes):
            print("[ScrapingBeeScreenshot] WARNING: screenshot not a supported image type for OpenAI, dropping it.")
            return None
        return b64_bytes
    except Exception as e:
        print(f"[ScrapingBeeScreenshot] ERROR for {url}: {e}")
        return None

def render_policy(result: FetchResult) -> (bool, str):
    if result.status_code >= 400:
        return True, "http_error"
    # Fast checks
    html_len = _safe_get_text_len(result.html)
    if html_len < Config.RENDER_MIN_TEXT_BYTES:
        return True, "small_text"
    soup = BeautifulSoup(result.html, "lxml")
    if len(soup.find_all("a", href=True)) < Config.RENDER_MIN_LINKS:
        return True, "few_links"
    lower = result.html.lower()
    for sig in Config.SPA_SIGNALS:
        if sig in lower:
            return True, "spa_signal"
    return False, "ok"

def social_extractor(soup, base_url):
    found = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found[platform] = urljoin(base_url, best_link)
    return found

# ============================================================
# ---------------------- PROMPTS -----------------------------
# ============================================================

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
        Analyze the **Emotion** key. This is the primary key; without it, nothing is memorable.
        Cover: How the brand connects emotionally. Do tone, imagery and copy evoke warmth, trust or admiration?
        Is there a meaningful, human promise? What is the emotional reward?
    """,
    "Attention": """
        Analyze the **Attention** key (distinctiveness, pattern breaking).
        Cover: Visual impact (palette, typography, imagery style, motion), headline craft, and how consistently the
        brand avoids clichés and repetitive CTA spam. Does it hook you quickly? Is the hero section legible?
    """,
    "Story": """
        Analyze the **Story** key.
        Cover: Is there a clear, credible narrative explaining who they are, why they exist, and what change they promise?
        Does it create curiosity and trust beyond functional facts?
    """,
    "Involvement": """
        Analyze **Involvement**.
        Cover: How does the brand invite participation (tools, community, interactive elements, feedback loops)?
        Is the experience inclusive and empowering?
    """,
    "Repetition": """
        Analyze **Repetition** (reinforcement).
        Cover: Are core codes (logo, color, tagline, type, shapes, behaviors) reused with intent across touchpoints?
        Does repetition build new associations or just create fatigue?
    """,
    "Consistency": """
        Analyze **Consistency** (coherence).
        Cover: Tone, message and design alignment. Are components systematically re-applied (design system)?
        Does consistency enable instant recognition without feeling rigid?
    """
}

EXEC_SUMMARY_PROMPT = """
You are a senior brand strategist. Synthesize the 6 memorability key analyses into:

1) **Overall summary** (3–5 sentences)
2) **Top 2–3 strengths** (why they matter)
3) **Top 2–3 weaknesses** (business impact)
4) **Single most important focus** to move the total score
5) A short 90-day action plan (bulleted, prioritized, effort/impact)

Be succinct but specific.
"""

# ============================================================
# ----------------- OPENAI ANALYSIS --------------------------
# ============================================================

def _new_openai_client():
    # Remove proxies if any (Render can inject them)
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {k: os.environ.pop(k, None) for k in proxy_keys}
    http_client = httpx.Client(proxies=None, timeout=60)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
    # restore after create
    for k, v in original_proxies.items():
        if v is not None:
            os.environ[k] = v
    return client

def call_openai_for_synthesis(corpus):
    print("[AI] Synthesizing brand overview...")
    try:
        client = _new_openai_client()
        prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings.\n\n---\n"
            f"{corpus}\n---"
        )
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."

def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshots_b64, brand_summary, visual_hints):
    print(f"[AI] Analyzing key: {key_name}")
    try:
        client = _new_openai_client()

        # Compose multimodal content
        content_blocks = []
        # Attach up to N screenshots
        for b64 in screenshots_b64[:Config.VISUAL_SCREENSHOTS_PER_SITE]:
            if not _b64_looks_like_supported_image(b64):
                continue
            mime = _guess_mime_from_b64(b64)
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            })

        # textual
        content_blocks.append({"type": "text", "text": f"VISUAL HINTS:\n{json.dumps(visual_hints, indent=2)}"})
        content_blocks.append({"type": "text", "text": f"BRAND SUMMARY:\n{brand_summary}"})
        content_blocks.append({"type": "text", "text": f"FULL CORPUS:\n{text_corpus[:120000]}"} )  # keep it large but safe

        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants.
        {prompt_template}

        Return ONLY valid JSON with keys:
        - "score": Integer 0..100
        - "analysis": ≥5 sentences, grounded in criteria above, referencing visuals if provided
        - "evidence": A single short quote or concrete visual detail
        - "confidence": Integer 1..5
        - "confidence_rationale": Short reason
        - "recommendation": One practical fix that would most move this key
        """

        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            temperature=Config.OPENAI_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_blocks}
            ]
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
            "recommendation": "Retry after fixing the technical issue."
        }

def call_openai_for_executive_summary(all_analyses):
    print("[AI] Generating Executive Summary...")
    try:
        client = _new_openai_client()

        analyses_text = "\n\n".join([
            f"Key: {r['key']}\nScore: {r['analysis']['score']}\nAnalysis: {r['analysis']['analysis']}"
            for r in all_analyses
        ])

        prompt = f"{EXEC_SUMMARY_PROMPT}\n\n---\n{analyses_text}\n---"
        resp = client.chat.completions.create(
            model=Config.OPENAI_MODEL,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."

# ============================================================
# ------------------- MAIN ORCHESTRATOR ----------------------
# ============================================================

def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget     = Config.SITE_BUDGET_SECS
    escalated  = False

    pages_analyzed = []
    text_corpus    = ""
    screenshots    = []  # store base64 strings
    homepage_shots = []

    socials_found  = False
    visual_hints   = {"palette_hex": [], "font_families": []}

    queue     = deque([(_clean_url(url), 0)])
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

            # 1) Basic fetch
            basic_result = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_result)
            final_result = basic_result

            # 2) escalate to JS if needed
            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                rendered = scrapingbee_html_fetcher(current_url, render_js=True)
                if 200 <= rendered.status_code < 400 and rendered.html.strip():
                    final_result = rendered

            # 3) Screenshots (only collect VISUAL_SCREENSHOTS_PER_SITE total across scan)
            if len(screenshots) < Config.VISUAL_SCREENSHOTS_PER_SITE:
                shot = scrapingbee_screenshot_fetcher(current_url, render_js=final_result.from_renderer)
                if shot:
                    if not homepage_shots:
                        homepage_shots.append(shot)
                    screenshots.append(shot)
                    image_id = str(uuid.uuid4())
                    cache[image_id] = shot
                    yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            # 4) Parse page
            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                # socials only from first page (cheap)
                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                # build text corpus
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                page_text = soup.get_text(" ", strip=True)
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n{page_text}"

                # extract quick visual hints from HTML (first page only, to keep prompt small)
                if len(pages_analyzed) == 0:
                    visual_hints = _extract_visual_hints(final_result.html)

                # queue next links
                if depth < Config.CRAWL_MAX_DEPTH:
                    for a in soup.find_all("a", href=True):
                        href = a.get("href")
                        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
                            continue
                        if Config.BINARY_RE.search(href):
                            continue
                        link = _clean_url(urljoin(current_url, href))
                        if not _is_same_domain(url, link) or link in seen_urls:
                            continue
                        remaining = Config.CRAWL_MAX_PAGES - (len(pages_analyzed) + len(queue))
                        if remaining <= 0:
                            break
                        queue.append((link, depth + 1))
                        seen_urls.add(link)

            pages_analyzed.append(final_result)

            # 5) dynamic budget escalation (unchanged)
            elapsed = time.time() - start_time
            if not escalated and elapsed < budget:
                pages_rendered_by_bee = sum(1 for p in pages_analyzed if p.from_renderer)
                if len(pages_analyzed) >= 3 and pages_rendered_by_bee >= 2 and not socials_found:
                    budget = Config.SITE_MAX_BUDGET_SECS
                    escalated = True
                    yield {'type': 'status', 'message': f'High JS usage and no socials found → escalating budget to {budget}s.'}

        # 6) LLM analysis pipeline
        yield {'type': 'status', 'message': 'Crawl complete. Starting AI analysis...'}
        brand_summary = call_openai_for_synthesis(text_corpus)

        all_results = []
        for key, prompt_tmpl in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                key, prompt_tmpl, text_corpus, screenshots, brand_summary, visual_hints
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
