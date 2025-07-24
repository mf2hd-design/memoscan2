import os
import re
import io
import json
import time
import uuid
import base64
import httpx
import requests
from collections import deque, Counter
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI
from jsonschema import validate, ValidationError

from PIL import Image

load_dotenv()

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

    # Heuristics
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # ScrapingBee
    SCRAPINGBEE_API_KEY      = os.getenv("SCRAPINGBEE_API_KEY", "")
    SB_MAX_RETRIES           = int(os.getenv("SB_MAX_RETRIES", 3))
    SB_PREMIUM_ON_5XX        = os.getenv("SB_PREMIUM_ON_5XX", "false").lower() == "true"

    # LLM
    OPENAI_API_KEY           = os.getenv("OPENAI_API_KEY", "")

    # Socials
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }

    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

    # LLM screenshots
    MAX_LLM_SCREENSHOTS      = int(os.getenv("MAX_LLM_SCREENSHOTS", 3))
    JPEG_MAX_WIDTH           = int(os.getenv("JPEG_MAX_WIDTH", 1024))
    JPEG_QUALITY             = int(os.getenv("JPEG_QUALITY", 72))


# -----------------------------------------------------------------------------------
# FETCH SUPPORT
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


def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]


def _host(u: str) -> str:
    host = urlparse(u).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _is_same_domain(home: str, test: str) -> bool:
    return _host(home) == _host(test)


def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] {url}")
    try:
        res = _basic_client.get(url)
        res.raise_for_status()
        return FetchResult(str(res.url), res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)


def render_policy(result: FetchResult) -> (bool, str):
    """Should we escalate to JS renderer?"""
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


# -----------------------------------------------------------------------------------
# SCRAPINGBEE JS SCENARIO BUILDER (VALIDATED SHAPE)
# -----------------------------------------------------------------------------------

COOKIE_TEXT_NEEDLES = [
    "accept", "agree", "allow", "permitir", "zulassen", "consent",
    "cookies", "ok", "got it", "dismiss", "yes,"
]

COOKIE_CSS_SELECTORS = [
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
    "button[aria-label='I agree']",
    "button[aria-label='Allow all cookies']"
]

KILL_BANNERS_JS = r"""
(function(){
  try {
    const textNeedles = %s;

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

    const cssSelectors = %s;
    for (const sel of cssSelectors) {
      try {
        const el = document.querySelector(sel);
        if (el) { el.click(); }
      } catch(e){}
    }

    clickByText('button') || clickByText('a');

    const kill = [
      "[id*='cookie']","[class*='cookie']",
      "[id*='consent']","[class*='consent']",
      "[id*='gdpr']","[class*='gdpr']",
      "[id*='privacy']","[class*='privacy']",
      "iframe[src*='consent']","iframe[src*='cookie']"
    ];
    document.querySelectorAll(kill.join(',')).forEach(el=>{
      el.style.setProperty('display', 'none', 'important');
      el.style.setProperty('visibility', 'hidden', 'important');
      el.style.setProperty('opacity', '0', 'important');
    });

    if (document.body) {
      document.body.style.overflow = 'auto';
    }
  } catch(e) {}
})();
""" % (json.dumps(COOKIE_TEXT_NEEDLES), json.dumps(COOKIE_CSS_SELECTORS))


def build_js_scenario(wait_ms_first: int = 1200, wait_ms_after: int = 400):
    """
    Return a ScrapingBee-compliant js_scenario dict.
    """
    steps = []
    steps.append({"wait": wait_ms_first})

    for sel in COOKIE_CSS_SELECTORS:
        steps.append({"click": sel, "optional": True})

    steps.append({"script": KILL_BANNERS_JS})
    steps.append({"wait": wait_ms_after})

    return {"instructions": steps}


def scrapingbee_call(url: str, render_js: bool, want_html: bool, with_js: bool, attempt: int):
    """
    One low-level call to ScrapingBee.
    """
    api_key = Config.SCRAPINGBEE_API_KEY
    if not api_key:
        return None, 500, "ScrapingBee API Key not set"

    params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true" if render_js else "false",
        "block_resources": "true" if want_html else "false",
        "wait": "networkidle" if render_js else "0"
    }

    if with_js and render_js:
        js_payload = build_js_scenario()
        params["js_scenario"] = json.dumps(js_payload)

    endpoint = "https://app.scrapingbee.com/api/v1/"

    try:
        print(f"[ScrapingBee]{'HTML' if want_html else 'Screenshot'} {url} attempt={attempt} render_js={render_js} with_js={with_js}")
        res = requests.get(endpoint, params=params, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
        status = res.status_code

        if status >= 400:
            body = res.text[:1000]
            print(f"[ScrapingBee] HTTP {status} attempt={attempt} body={body}")
            return None, status, body

        return res, status, ""
    except Exception as ex:
        print(f"[ScrapingBee] EXC attempt={attempt} {ex}")
        return None, 500, str(ex)


def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    api_key = Config.SCRAPINGBEE_API_KEY
    if not api_key:
        return FetchResult(url, "ScrapingBee API Key not set", 500, from_renderer=render_js)

    last_err = ""
    last_status = 500

    for attempt in range(Config.SB_MAX_RETRIES):
        # with js_scenario first
        res, status, err = scrapingbee_call(url, render_js=render_js, want_html=True, with_js=True, attempt=attempt)
        if res is not None and status < 400:
            return FetchResult(url, res.text, status, from_renderer=render_js)

        # then without js_scenario
        res, status, err = scrapingbee_call(url, render_js=render_js, want_html=True, with_js=False, attempt=attempt)
        if res is not None and status < 400:
            return FetchResult(url, res.text, status, from_renderer=render_js)

        last_err = err
        last_status = status

    return FetchResult(url, f"ScrapingBee failed after {Config.SB_MAX_RETRIES} attempts: {last_err}", last_status, from_renderer=render_js)


def scrapingbee_screenshot_fetcher(url: str, render_js: bool) -> str | None:
    api_key = Config.SCRAPINGBEE_API_KEY
    if not api_key:
        return None

    last_err = None
    last_status = 0

    for attempt in range(Config.SB_MAX_RETRIES):
        # with js_scenario
        res, status, err = scrapingbee_call(url, render_js=render_js, want_html=False, with_js=True, attempt=attempt)
        if res is not None and status < 400:
            return base64.b64encode(res.content).decode("utf-8")

        # without js_scenario
        res, status, err = scrapingbee_call(url, render_js=render_js, want_html=False, with_js=False, attempt=attempt)
        if res is not None and status < 400:
            return base64.b64encode(res.content).decode("utf-8")

        last_err = err
        last_status = status

    print(f"[ScrapingBeeScreenshot] ERROR for {url}: HTTP {last_status}")
    return None


def social_extractor(soup, base_url):
    found_socials = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best_link = min(links, key=len)
            found_socials[platform] = urljoin(base_url, best_link)
    return found_socials


# -----------------------------------------------------------------------------------
# VISUAL FEATURES (colors & fonts from inline CSS / style tags present in the HTML)
# -----------------------------------------------------------------------------------

HEX_RE = re.compile(r'#[0-9a-fA-F]{3,8}')
FONT_FAMILY_RE = re.compile(r'font-family\s*:\s*([^;]+);?', re.IGNORECASE)

def extract_visual_features(html: str) -> dict:
    """
    Very heuristic:
      - find hex colors (#fff, #ffffff, etc) in style tags and inline styles
      - find font-family declarations
    """
    colors = Counter()
    fonts  = Counter()

    soup = BeautifulSoup(html, "lxml")

    # Style tags
    for style in soup.find_all("style"):
        text = style.get_text() or ""
        for c in HEX_RE.findall(text):
            colors[c.lower()] += 1
        for m in FONT_FAMILY_RE.finditer(text):
            raw = m.group(1)
            family = normalize_font_family(raw)
            if family:
                fonts[family] += 1

    # Inline styles
    for el in soup.select("[style]"):
        style_text = el.get("style", "")
        for c in HEX_RE.findall(style_text):
            colors[c.lower()] += 1
        fm = FONT_FAMILY_RE.search(style_text)
        if fm:
            family = normalize_font_family(fm.group(1))
            if family:
                fonts[family] += 1

    top_colors = [c for c, _ in colors.most_common(8)]
    top_fonts  = [f for f, _ in fonts.most_common(6)]

    return {
        "top_colors": top_colors,
        "top_fonts": top_fonts
    }

def normalize_font_family(raw: str) -> str:
    # take first family, strip quotes etc
    families = [x.strip().strip("'\"") for x in raw.split(",")]
    if not families:
        return None
    return families[0].lower()


# -----------------------------------------------------------------------------------
# IMAGE UTILS
# -----------------------------------------------------------------------------------

def safe_b64_to_bytes(data: str) -> bytes:
    if data.startswith("data:image"):
        data = data.split(",", 1)[-1]
    missing = len(data) % 4
    if missing:
        data += "=" * (4 - missing)
    return base64.b64decode(data, validate=False)

def compress_b64_image_to_jpeg(b64_png: str, max_w: int, quality: int) -> str:
    """
    Decode base64 (png or whatever), convert to RGB JPEG, resize to max_w, return base64 string.
    """
    try:
        raw = safe_b64_to_bytes(b64_png)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        if w > max_w:
            ratio = max_w / float(w)
            img = img.resize((max_w, int(h * ratio)), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format='JPEG', quality=quality, optimize=True)
        return base64.b64encode(out.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"[IMG] Compress failed: {e}")
        return b64_png  # fallback: return original


# -----------------------------------------------------------------------------------
# AI PROMPTS & JSON SCHEMA VALIDATION
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

MEMO_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "analysis": {"type": "string", "minLength": 10},
        "evidence": {"type": "string", "minLength": 1},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence_rationale": {"type": "string", "minLength": 3},
        "recommendation": {"type": "string", "minLength": 3}
    },
    "required": [
        "score", "analysis", "evidence",
        "confidence", "confidence_rationale",
        "recommendation"
    ],
    "additionalProperties": False
}


def call_openai_for_synthesis(corpus, visual_hints):
    print("[AI] Synthesizing brand overview...")
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=Config.OPENAI_API_KEY, http_client=http_client)
        synthesis_prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n"
            "VISUAL HINTS (heuristic, extracted from HTML/CSS we saw):\n"
            f"{json.dumps(visual_hints, indent=2)}\n\n"
            "---\n" + corpus + "\n---"
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


def call_llm_json_with_schema(client, model, system_prompt, user_content, schema, temperature=0.3, max_retries=1):
    """
    Call the LLM, enforce schema. If it fails, retry once with an explicit
    schema reminder and the validation error.
    """
    def _one_call(extra_msg=None):
        messages = [{"role": "system", "content": system_prompt}]
        if extra_msg:
            messages.append({"role": "system", "content": extra_msg})
        messages.append({"role": "user", "content": user_content})
        return client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=temperature
        )

    try:
        resp = _one_call()
        payload = json.loads(resp.choices[0].message.content)
        validate(instance=payload, schema=schema)
        return payload
    except (ValidationError, json.JSONDecodeError) as ve:
        if max_retries <= 0:
            raise ve
        # retry once
        try:
            hint = f"Your previous output did not match this JSON schema. Fix it.\nSchema:\n{json.dumps(schema)}\nError:{str(ve)}"
            resp = _one_call(extra_msg=hint)
            payload = json.loads(resp.choices[0].message.content)
            validate(instance=payload, schema=schema)
            return payload
        except Exception as ve2:
            # give up
            raise ve2


def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshots_b64_list, brand_summary, visual_hints):
    print(f"[AI] Analyzing key: {key_name}")
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=Config.OPENAI_API_KEY, http_client=http_client)

        # Compose the "user content" with multi-image (if available)
        user_content = []

        for b64 in screenshots_b64_list:
            user_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})

        user_content.extend([
            {"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"},
            {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"},
            {"type": "text", "text": f"VISUAL HINTS (colors, fonts extracted heuristically):\n{json.dumps(visual_hints, indent=2)}"}
        ])

        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
        {prompt_template}
        
        You MUST output valid JSON that strictly complies with this schema:
        {json.dumps(MEMO_SCHEMA)}
        """

        result = call_llm_json_with_schema(
            client=client,
            model="gpt-4o",
            system_prompt=system_prompt,
            user_content=user_content,
            schema=MEMO_SCHEMA,
            temperature=0.3,
            max_retries=1
        )
        return key_name, result

    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        error_response = {
            "score": 0,
            "analysis": "Analysis failed due to a server or schema error.",
            "evidence": str(e),
            "confidence": 1,
            "confidence_rationale": "System error.",
            "recommendation": "Resolve the technical error to proceed."
        }
        return key_name, error_response


def call_openai_for_executive_summary(all_analyses, visual_hints):
    print("[AI] Generating Executive Summary...")
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=Config.OPENAI_API_KEY, http_client=http_client)

        analyses_text = "\n\n".join([
            f"Key: {data['key']}\nScore: {data['analysis'].get('score', 'N/A')}\nAnalysis: {data['analysis'].get('analysis', '')}"
            for data in all_analyses
        ])

        summary_prompt = f"""You are a senior brand strategist delivering a final executive summary. 
        Use the 6-key analyses (Emotion, Attention, Story, Involvement, Repetition, Consistency) AND the visual hints to:
        1) Overall Summary (short).
        2) Key Strengths (2-3).
        3) Primary Weaknesses (2-3).
        4) The single most important key to focus on.
        
        VISUAL HINTS:
        {json.dumps(visual_hints, indent=2)}
        
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


# -----------------------------------------------------------------------------------
# MAIN ORCHESTRATOR
# -----------------------------------------------------------------------------------

def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed = []
    text_corpus = ""
    socials_found = False

    # visual feature aggregation
    all_colors = Counter()
    all_fonts = Counter()

    # store up to 3 screenshots that we will compress & pass to LLM
    llm_screenshots_b64 = []

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
                final_result = scrapingbee_html_fetcher(current_url, render_js=True)

            # screenshot (we only need up to MAX_LLM_SCREENSHOTS)
            if len(llm_screenshots_b64) < Config.MAX_LLM_SCREENSHOTS:
                screenshot_b64 = scrapingbee_screenshot_fetcher(current_url, render_js=final_result.from_renderer)
                if screenshot_b64:
                    # compress to jpeg
                    jpg_b64 = compress_b64_image_to_jpeg(
                        screenshot_b64,
                        max_w=Config.JPEG_MAX_WIDTH,
                        quality=Config.JPEG_QUALITY
                    )
                    llm_screenshots_b64.append(jpg_b64)

                    image_id = str(uuid.uuid4())
                    cache[image_id] = jpg_b64
                    yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            # parse page
            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                # Visual Features
                vf = extract_visual_features(final_result.html)
                # aggregate
                for c in vf["top_colors"]:
                    all_colors[c] += 1
                for f in vf["top_fonts"]:
                    all_fonts[f] += 1

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
                    yield {'type': 'status', 'message': f'High JS usage and no socials found → escalating budget to {budget}s.'}

        yield {'type': 'status', 'message': 'Crawl complete. Starting AI analysis...'}

        visual_hints = {
            "top_colors": [c for c, _ in all_colors.most_common(8)],
            "top_fonts": [f for f, _ in all_fonts.most_common(6)]
        }

        brand_summary = call_openai_for_synthesis(text_corpus, visual_hints)

        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(
                key, prompt, text_corpus,
                screenshots_b64_list=llm_screenshots_b64,
                brand_summary=brand_summary,
                visual_hints=visual_hints
            )
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj

        yield {'type': 'status', 'message': 'Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results, visual_hints)
        yield {'type': 'summary', 'text': summary_text}
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
