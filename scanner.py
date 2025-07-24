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

# ===================================================================================
# CONFIG
# ===================================================================================
class Config:
    # Budgets
    SITE_BUDGET_SECS         = int(os.getenv("SITE_BUDGET_SECS", 60))
    SITE_MAX_BUDGET_SECS     = int(os.getenv("SITE_MAX_BUDGET_SECS", 90))

    # Crawl
    CRAWL_MAX_PAGES          = int(os.getenv("CRAWL_MAX_PAGES", 5))
    CRAWL_MAX_DEPTH          = int(os.getenv("CRAWL_MAX_DEPTH", 2))
    MAX_SCREENSHOTS          = int(os.getenv("MAX_SCREENSHOTS", 3))

    # Timeouts
    BASIC_TIMEOUT_SECS       = int(os.getenv("BASIC_TIMEOUT_SECS", 10))
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 30))

    # ScrapingBee retries/backoff
    SCRAPINGBEE_MAX_RETRIES  = int(os.getenv("SCRAPINGBEE_MAX_RETRIES", 1))
    SCRAPINGBEE_BACKOFF_SECS = float(os.getenv("SCRAPINGBEE_BACKOFF_SECS", 1.5))
    SCRAPINGBEE_PROXY_MODE   = os.getenv("SCRAPINGBEE_PROXY_MODE", "none")  # none|premium|stealth
    SCRAPINGBEE_ALLOW_SCRIPT = os.getenv("SCRAPINGBEE_ALLOW_SCRIPT", "true").lower() == "true"
    SCRAPINGBEE_JS_MODE      = os.getenv("SCRAPINGBEE_JS_MODE", "light")  # light|heavy

    # Render heuristics
    RENDER_MIN_LINKS         = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES    = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS              = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]

    # Socials
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }

    # Skip binaries
    BINARY_RE = re.compile(r'\.(pdf|png|jpg|jpeg|gif|mp4|zip|rar|svg|webp|ico|css|js)$', re.I)

    # Strip from corpus
    COOKIE_GDPR_KILL_SELECTORS = [
        "[id*='cookie']", "[class*='cookie']",
        "[id*='consent']", "[class*='consent']",
        "[id*='gdpr']",   "[class*='gdpr']",
        "[id*='privacy']", "[class*='privacy']",
        "iframe[src*='consent']", "iframe[src*='cookie']"
    ]


# ===================================================================================
# HELPERS
# ===================================================================================
def _reg_domain(u: str) -> str:
    e = tldextract.extract(u)
    return f"{e.domain}.{e.suffix}".lower()

def _is_same_domain(home: str, test: str) -> bool:
    return _reg_domain(home) == _reg_domain(test)

def _clean_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.strip()
    return url.split("#")[0]


# ===================================================================================
# FETCHERS
# ===================================================================================
class FetchResult:
    def __init__(self, url, html, status_code, from_renderer):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer


_basic_client = httpx.Client(
    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    follow_redirects=True,
    timeout=Config.BASIC_TIMEOUT_SECS
)


def basic_fetcher(url: str) -> FetchResult:
    print(f"[BasicFetcher] {url}")
    try:
        r = _basic_client.get(url)
        r.raise_for_status()
        return FetchResult(str(r.url), r.text, r.status_code, False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR {e}")
        return FetchResult(url, "", 500, False)


# ---------- ScrapingBee scenario building ----------
CSS_CLICK_SELECTORS = [
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
    "button[aria-label='Accept all']",
    "button[name='accept']",
    "button#accept",
    "button#acceptAll",
    "button.consent-accept",
    "button.cookie-accept",
    "[id*='accept'][class*='cookie']",
    "[class*='accept'][class*='cookie']",
    "button[aria-label='Zulassen']",
    "button[aria-label='Permitirlas']",
]

TEXT_WORDS = [
    "accept", "agree", "allow", "zulassen", "permitirlas",
    "alle akzeptieren", "accept all", "accept cookies", "akzeptieren",
    "i agree", "consent", "permit", "permite", "permitir"
]

def build_light_js_scenario() -> dict:
    instr = [{"wait": 1500}]
    for sel in CSS_CLICK_SELECTORS[:10]:  # keep it short for reliability
        instr.append({"click": sel, "optional": True})
    # short, compact hide script
    small_script = """
      (function(){
        try {
          var kill=["[id*='cookie']","[class*='cookie']","[id*='consent']","[class*='consent']","[id*='gdpr']","[class*='gdpr']","[id*='privacy']","[class*='privacy']","iframe[src*='consent']","iframe[src*='cookie']"];
          document.querySelectorAll(kill.join(',')).forEach(function(el){
            el.style.setProperty('display','none','important');
            el.style.setProperty('visibility','hidden','important');
            el.style.setProperty('opacity','0','important');
          });
          if(document.body){document.body.style.overflow='auto';}
        } catch(e){}
      })();
    """.strip().replace("\n", "")
    instr.append({"script": small_script})
    instr.append({"wait": 400})
    return {"instructions": instr}

def build_heavy_js_scenario() -> dict:
    words_json = json.dumps(TEXT_WORDS)
    kill_js = """
      (function(){
        try {
          var kill=["[id*='cookie']","[class*='cookie']","[id*='consent']","[class*='consent']","[id*='gdpr']","[class*='gdpr']","[id*='privacy']","[class*='privacy']","iframe[src*='consent']","iframe[src*='cookie']"];
          document.querySelectorAll(kill.join(',')).forEach(function(el){
            el.style.setProperty('display','none','important');
            el.style.setProperty('visibility','hidden','important');
            el.style.setProperty('opacity','0','important');
          });
          if(document.body){document.body.style.overflow='auto';}
        } catch(e){}
      })();
    """.strip().replace("\n", "")
    click_by_text_js = f"""
      (function(){{
        try {{
          var words = {words_json}.map(function(w){{return w.toLowerCase();}});
          var nodes = Array.from(document.querySelectorAll('button,a,[role="button"]'));
          for (var i=0;i<nodes.length;i++) {{
            var el = nodes[i];
            var txt = (el.textContent||'').trim().toLowerCase();
            if(!txt) continue;
            var hit=false;
            for (var j=0;j<words.length;j++) {{
              if(txt.indexOf(words[j])!==-1) {{ hit=true; break; }}
            }}
            if(hit) try{{ el.click(); }}catch(e){{}}
          }}
        }} catch(e) {{}}
      }})();
    """.strip().replace("\n", "")

    instr = [{"wait": 1500}]
    for sel in CSS_CLICK_SELECTORS[:15]:
        instr.append({"click": sel, "optional": True})
    instr.append({"script": click_by_text_js})
    instr.append({"script": kill_js})
    instr.append({"wait": 500})
    return {"instructions": instr}

def make_js_scenario() -> dict:
    if not Config.SCRAPINGBEE_ALLOW_SCRIPT:
        instr = [{"wait": 1500}]
        for sel in CSS_CLICK_SELECTORS[:10]:
            instr.append({"click": sel, "optional": True})
        instr.append({"wait": 400})
        return {"instructions": instr}

    if Config.SCRAPINGBEE_JS_MODE == "heavy":
        return build_heavy_js_scenario()
    return build_light_js_scenario()


def _bee_params(url: str, *, render_js: bool, screenshot: bool, with_js: bool, wait_ms: int):
    p = {
        "api_key": os.getenv("SCRAPINGBEE_API_KEY"),
        "url": url,
        "render_js": True if render_js else False,
        "wait": wait_ms
    }

    # Attach js_scenario ONLY when we actually render (and only on 1st try)
    if render_js and with_js:
        p["js_scenario"] = json.dumps(make_js_scenario())

    if screenshot:
        p.update({
            "screenshot": True,
            "window_width": 1280,
            "window_height": 1024,
            "screenshot_full_page": False,
        })
        p["block_resources"] = False
    else:
        p["block_resources"] = True

    mode = Config.SCRAPINGBEE_PROXY_MODE
    if mode == "premium":
        p["premium_proxy"] = True
    elif mode == "stealth":
        p["stealth_proxy"] = True

    return p


def _bee_call(url: str, *, render_js: bool, screenshot: bool):
    # force JS for screenshots to ensure cookie banner removal logic runs
    if screenshot:
        render_js = True

    tries = Config.SCRAPINGBEE_MAX_RETRIES + 1
    for attempt in range(tries):
        with_js = (attempt == 0)
        params = _bee_params(
            url, render_js=render_js, screenshot=screenshot, with_js=with_js,
            wait_ms=2000 if with_js else 2500
        )
        try:
            r = requests.get(
                "https://app.scrapingbee.com/api/v1/",
                params=params,
                timeout=(10, Config.SCRAPINGBEE_TIMEOUT_SECS)
            )
            if r.status_code < 400:
                return r
            print(f"[ScrapingBee] HTTP {r.status_code} attempt={attempt} body={r.text[:400]}")
        except requests.RequestException as e:
            print(f"[ScrapingBee] EXC attempt={attempt} {e}")

        if attempt < tries - 1:
            time.sleep(Config.SCRAPINGBEE_BACKOFF_SECS * (attempt + 1))

    return None


def scrapingbee_html_fetcher(url: str, render_js: bool) -> FetchResult:
    print(f"[ScrapingBeeHTML] {url} (render_js={render_js})")
    r = _bee_call(url, render_js=render_js, screenshot=False)
    if not r:
        return FetchResult(url, "", 500, render_js)
    return FetchResult(url, r.text, r.status_code, render_js)


def scrapingbee_screenshot_fetcher(url: str, render_js: bool) -> str | None:
    print(f"[ScrapingBeeScreenshot] {url} (render_js=True)")
    r = _bee_call(url, render_js=True, screenshot=True)  # force render_js
    if not r:
        return None
    return base64.b64encode(r.content).decode("utf-8")


# ===================================================================================
# POLICY & EXTRACT
# ===================================================================================
def render_policy(result: FetchResult) -> (bool, str):
    if result.status_code >= 400:
        return True, "http_error"

    soup = BeautifulSoup(result.html, "lxml")
    visible_text_len = len(soup.get_text(" ", strip=True))
    if visible_text_len < Config.RENDER_MIN_TEXT_BYTES:
        return True, "small_text"
    if len(soup.find_all("a", href=True)) < Config.RENDER_MIN_LINKS:
        return True, "few_links"
    lower = result.html.lower()
    for sig in Config.SPA_SIGNALS:
        if sig in lower:
            return True, "spa_signal"
    return False, "ok"


def _strip_cookie_nodes(soup: BeautifulSoup):
    for sel in Config.COOKIE_GDPR_KILL_SELECTORS:
        for el in soup.select(sel):
            el.decompose()


def social_extractor(soup: BeautifulSoup, base_url: str) -> dict:
    out = {}
    for platform, pattern in Config.SOCIAL_PLATFORMS.items():
        links = {tag['href'] for tag in soup.find_all('a', href=pattern)}
        if links:
            best = min(links, key=len)
            out[platform] = urljoin(base_url, best)
    return out


# ===================================================================================
# LLM HELPERS
# ===================================================================================
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


def call_openai_for_synthesis(corpus: str) -> str:
    print("[AI] Synthesizing brand overview...")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

        prompt = (
            "Analyze the following text from a company's website and social media. "
            "Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. "
            "This summary will be used as context for further analysis.\n\n---\n" + corpus + "\n---"
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
        for k, v in original.items():
            if v is not None:
                os.environ[k] = v


def analyze_memorability_key(key_name, prompt_template, text_corpus, homepage_screenshot_b64, brand_summary):
    print(f"[AI] Analyzing key: {key_name}")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
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

        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return key_name, json.loads(resp.choices[0].message.content)
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
        for k, v in original.items():
            if v is not None:
                os.environ[k] = v


def call_openai_for_executive_summary(all_analyses):
    print("[AI] Generating Executive Summary...")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original = {k: os.environ.pop(k, None) for k in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)

        analyses_text = "\n\n".join(
            [f"Key: {d['key']}\nScore: {d['analysis']['score']}\nAnalysis: {d['analysis']['analysis']}"
             for d in all_analyses]
        )
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
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI summary failed: {e}")
        return "Could not generate the executive summary due to an error."
    finally:
        for k, v in original.items():
            if v is not None:
                os.environ[k] = v


# ===================================================================================
# MAIN ORCHESTRATOR
# ===================================================================================
def run_full_scan_stream(url: str, cache: dict):
    start_time = time.time()
    budget = Config.SITE_BUDGET_SECS
    escalated = False

    pages_analyzed = []
    text_corpus = ""
    homepage_screenshot_b64 = None
    socials_found = False
    screenshots_taken = 0

    q = deque([(_clean_url(url), 0)])
    seen = {_clean_url(url)}

    try:
        yield {"type": "status", "message": f"Scan initiated. Budget: {budget}s."}

        while q and len(pages_analyzed) < Config.CRAWL_MAX_PAGES:
            elapsed = time.time() - start_time
            if elapsed > budget:
                yield {"type": "status", "message": "Time budget exceeded. Finalizing analysis."}
                break

            current_url, depth = q.popleft()
            yield {"type": "status", "message": f"Analyzing page {len(pages_analyzed)+1}/{Config.CRAWL_MAX_PAGES}: {current_url}"}

            basic_result = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_result)
            final_result = basic_result

            if should_render:
                yield {"type": "status", "message": f"Basic fetch insufficient ({reason}). Escalating to JS renderer..."}
                final_result = scrapingbee_html_fetcher(current_url, render_js=True)

            # Screenshots – cap them
            if screenshots_taken < Config.MAX_SCREENSHOTS:
                b64 = scrapingbee_screenshot_fetcher(current_url, render_js=final_result.from_renderer)
                if b64:
                    if len(pages_analyzed) == 0:
                        homepage_screenshot_b64 = b64
                    image_id = str(uuid.uuid4())
                    cache[image_id] = b64
                    yield {"type": "screenshot_ready", "id": image_id, "url": current_url}
                    screenshots_taken += 1

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "lxml")
                print(f"[DEBUG] Links found on {current_url}: {len(soup.find_all('a', href=True))} (rendered={final_result.from_renderer})")

                _strip_cookie_nodes(soup)

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
                        next_url = _clean_url(urljoin(current_url, href))
                        if not _is_same_domain(url, next_url) or next_url in seen:
                            continue

                        remaining_slots = Config.CRAWL_MAX_PAGES - (len(pages_analyzed) + len(q))
                        if remaining_slots <= 0:
                            break

                        q.append((next_url, depth + 1))
                        seen.add(next_url)

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
        summary_text = call_openai_for_executive_summary(all_analyses=all_results)
        yield {"type": "summary", "text": summary_text}
        yield {"type": "complete", "message": "Analysis finished."}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {"type": "error", "message": f"A critical error occurred: {e}"}
