import os
import re
import requests
import json
import base64
import uuid
import time
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
import httpx
import gevent

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
    SCRAPINGBEE_TIMEOUT_SECS = int(os.getenv("SCRAPINGBEE_TIMEOUT_SECS", 25))
    RENDER_MIN_LINKS = int(os.getenv("RENDER_MIN_LINKS", 15))
    RENDER_MIN_TEXT_BYTES = int(os.getenv("RENDER_MIN_TEXT_BYTES", 3000))
    SPA_SIGNALS = ["__next", "__nuxt__", "webpackjsonp", "vite", "data-reactroot"]
    SOCIAL_PLATFORMS = {
        "twitter":  re.compile(r"(?:x\.com|twitter\.com)/(?!intent|share|search|home)[a-zA-Z0-9_]{1,15}"),
        "linkedin": re.compile(r"linkedin\.com/(?:company|in)/[\w-]+")
    }

# -----------------------------------------------------------------------------------
# SECTION 4: ARCHITECTURE (Fetchers, Policy, Extractor)
# -----------------------------------------------------------------------------------

class FetchResult:
    def __init__(self, url, html, status_code, from_renderer):
        self.url = url
        self.html = html or ""
        self.status_code = status_code
        self.from_renderer = from_renderer

def basic_fetcher(url: str) -> FetchResult:
    """Performs a simple, fast HTTP GET request."""
    print(f"[BasicFetcher] Fetching {url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        with httpx.Client(headers=headers, follow_redirects=True) as client:
            res = client.get(url, timeout=Config.BASIC_TIMEOUT_SECS)
            res.raise_for_status()
            return FetchResult(url, res.text, res.status_code, from_renderer=False)
    except Exception as e:
        print(f"[BasicFetcher] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed to fetch: {e}", 500, from_renderer=False)

def scrapingbee_fetcher(url: str, get_screenshot: bool = False):
    """Uses ScrapingBee for JavaScript rendering and screenshots."""
    print(f"[ScrapingBeeFetcher] Fetching {url} (screenshot: {get_screenshot})")
    api_key = os.getenv("SCRAPINGBEE_API_KEY")
    if not api_key: return FetchResult(url, "ScrapingBee API Key not set", 500, from_renderer=True), None
    
    params = {
        "api_key": api_key,
        "url": url,
        "render_js": "true",
        "block_ads": "true",
        "block_resources": "image,media,font",
        "screenshot": "true" if get_screenshot else "false",
        "window_width": 1280,
        "window_height": 1024,
    }
    try:
        res = requests.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=Config.SCRAPINGBEE_TIMEOUT_SECS)
        res.raise_for_status()
        
        screenshot_b64 = base64.b64encode(res.content).decode('utf-8') if get_screenshot else None
        
        html = res.headers.get("Spb-Resolved-Url") and res.text or ""
        
        return FetchResult(url, html, res.status_code, from_renderer=True), screenshot_b64
    except Exception as e:
        print(f"[ScrapingBeeFetcher] ERROR for {url}: {e}")
        return FetchResult(url, f"Failed to fetch via ScrapingBee: {e}", 500, from_renderer=True), None

def render_policy(result: FetchResult) -> (bool, str):
    """Decides if we need to use ScrapingBee based on heuristics."""
    if result.status_code >= 400:
        return True, "http_error"
    if len(result.html) < Config.RENDER_MIN_TEXT_BYTES:
        return True, "small_text"
    
    soup = BeautifulSoup(result.html, "html.parser")
    if len(soup.find_all("a")) < Config.RENDER_MIN_LINKS:
        return True, "few_links"
    
    for signal in Config.SPA_SIGNALS:
        if signal in result.html:
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
# AI Analysis Functions (COMPLETE AND UNTRUNCATED)
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
        synthesis_prompt = f"Analyze the following text from a company's website and social media. Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. This summary will be used as context for further analysis.\n\n---\n{corpus}\n---"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": synthesis_prompt}], temperature=0.2)
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
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.3
        )
        return key_name, json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        error_response = {"score": 0, "analysis": "Analysis failed due to a server error.", "evidence": str(e), "confidence": 1, "confidence_rationale": "System error.", "recommendation": "Resolve the technical error to proceed."}
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
        
        analyses_text = "\n\n".join([f"Key: {data['key']}\nScore: {data['analysis']['score']}\nAnalysis: {data['analysis']['analysis']}" for data in all_analyses])
        
        summary_prompt = f"""You are a senior brand strategist delivering a final executive summary. Based on the following six key analyses, please provide:
        1.  **Overall Summary:** A brief, high-level overview of the brand's memorability performance.
        2.  **Key Strengths:** Identify the 2-3 strongest keys for the brand and explain why.
        3.  **Primary Weaknesses:** Identify the 2-3 weakest keys and explain the impact.
        4.  **Strategic Focus:** State the single most important key the brand should focus on to improve its overall memorability.

        Here are the individual analyses to synthesize:
        ---
        {analyses_text}
        ---
        """
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": summary_prompt}], temperature=0.3)
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
    social_corpus = ""
    homepage_screenshot_b64 = None
    socials_found = False
    
    queue = [(_clean_url(url), 0)]
    seen_urls = {_clean_url(url)}

    try:
        yield {'type': 'status', 'message': f'Scan initiated. Budget: {budget}s.'}

        while queue and len(pages_analyzed) < Config.CRAWL_MAX_PAGES:
            elapsed = time.time() - start_time
            if elapsed > budget:
                yield {'type': 'status', 'message': 'Time budget exceeded. Finalizing analysis.'}
                break

            current_url, depth = queue.pop(0)
            yield {'type': 'status', 'message': f'Analyzing page {len(pages_analyzed) + 1}/{Config.CRAWL_MAX_PAGES}: {current_url}'}

            basic_result = basic_fetcher(current_url)
            should_render, reason = render_policy(basic_result)
            
            final_result = basic_result
            if should_render:
                yield {'type': 'status', 'message': f'Basic fetch insufficient ({reason}). Escalating to JS renderer...'}
                rendered_result, _ = scrapingbee_fetcher(current_url, get_screenshot=False)
                if rendered_result and rendered_result.html:
                    final_result = rendered_result

            _, screenshot_b64 = scrapingbee_fetcher(current_url, get_screenshot=True)
            if screenshot_b64:
                if len(pages_analyzed) == 0: homepage_screenshot_b64 = screenshot_b64
                image_id = str(uuid.uuid4())
                cache[image_id] = screenshot_b64
                yield {'type': 'screenshot_ready', 'id': image_id, 'url': current_url}

            if final_result.html:
                soup = BeautifulSoup(final_result.html, "html.parser")
                if len(pages_analyzed) == 0:
                    found = social_extractor(soup, current_url)
                    if found:
                        socials_found = True
                        yield {'type': 'status', 'message': f'Found social links: {list(found.values())}'}

                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]): tag.decompose()
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + soup.get_text(" ", strip=True)
                
                if depth < Config.CRAWL_MAX_DEPTH:
                    for a in soup.find_all("a", href=True):
                        link_url = _clean_url(urljoin(current_url, a["href"]))
                        if _is_same_domain(url, link_url) and link_url not in seen_urls:
                            queue.append((link_url, depth + 1))
                            seen_urls.add(link_url)
            
            pages_analyzed.append(final_result)

            if not escalated and elapsed < Config.SITE_BUDGET_SECS:
                pages_rendered_by_bee = sum(1 for p in pages_analyzed if p.from_renderer)
                if len(pages_analyzed) >= 3 and pages_rendered_by_bee >= 2 and not socials_found:
                    budget = Config.SITE_MAX_BUDGET_SECS
                    escalated = True
                    yield {'type': 'status', 'message': f'Warning: High JS usage and no socials found. Escalating budget to {budget}s.'}

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
