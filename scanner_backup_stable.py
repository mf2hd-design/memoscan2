import os
import re
import json
import base64
import uuid
import asyncio
import nest_asyncio
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
import httpx
from playwright.async_api import async_playwright
import requests
from typing import Optional

# --- Guarded DNS-over-HTTPS Import ---
try:
    from httpcore_doh import DnsOverHttpsTransport
    DNS_TRANSPORT = DnsOverHttpsTransport(resolver="https://1.1.1.1/dns-query")
    print("[Network] Using DNS-over-HTTPS for robust name resolution.")
except ImportError:
    DNS_TRANSPORT = None
    print("[Network] `httpcore-doh` not found. Using standard DNS resolver.")

# Apply nest_asyncio to allow running asyncio event loops inside other frameworks like Flask/Gevent
nest_asyncio.apply()

SHARED_CACHE = {}

load_dotenv()

# -----------------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------------

def _clean_url(url: str) -> str:
    """Cleans and standardizes a URL."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]

def _is_same_domain(home: str, test: str) -> bool:
    """Checks if a test URL is on the same domain as the home URL."""
    return urlparse(home).netloc == urlparse(test).netloc

def find_priority_page(discovered_links: list, keywords: list) -> Optional[str]:
    """Searches a list of discovered links for the best match based on keywords."""
    for link_url, link_text in discovered_links:
        for keyword in keywords:
            if keyword in link_url.lower() or keyword in link_text.lower():
                return link_url
    return None

# -----------------------------------------------------------------------------------
# Data Fetching Functions
# -----------------------------------------------------------------------------------

async def prepare_page_for_capture(page, max_ms=45000):
    """
    A sophisticated waiting mechanism for Playwright to ensure a page is fully and visually rendered.
    """
    # 1) Reach DOM ready fast
    await page.wait_for_load_state("domcontentloaded", timeout=max_ms)

    # 2) Dismiss common consent banners (best-effort)
    consent_clicked = False
    for text in ["Accept", "I agree", "Alle akzeptieren", "Zustimmen", "Allow all", "Accept all"]:
        try:
            await page.get_by_role("button", name=re.compile(text, re.I)).click(timeout=1500)
            print(f"[Playwright] Consent banner '{text}' dismissed.")
            consent_clicked = True
            break
        except:
            pass
    if not consent_clicked:
        print("[Playwright] No common consent banner found to click.")

    # 3) Trigger lazy content (auto-scroll)
    await page.evaluate("""async () => {
      const step = 800; let y = 0;
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      while (y < document.body.scrollHeight) { window.scrollBy(0, step); y += step; await sleep(120); }
      window.scrollTo(0, 0);
    }""")

    # 4) Wait for fonts, images, and no skeleton loaders
    await page.wait_for_function("""
      () => {
        const imagesReady = Array.from(document.images).every(img => img.complete && img.naturalWidth > 0);
        const fontsReady = !('fonts' in document) || document.fonts.status === 'loaded';
        const noSkeletons = !document.querySelector('[class*=skeleton],[data-skeleton],[aria-busy="true"]');
        return imagesReady && fontsReady && noSkeletons;
      }
    """, timeout=max_ms)
    
    # 5) Brief network quiet, but don't block forever
    try:
        await page.wait_for_load_state("networkidle", timeout=3000)
    except:
        pass
    
    print("[Playwright] Page is visually ready for capture.")


def fetch_page_data_scrapfly(url: str, take_screenshot: bool = True):
    """
    Uses Scrapfly API to get both the screenshot AND the rendered HTML.
    This is the fast, primary method.
    """
    print(f"[Scrapfly] Fetching data for {url} (Screenshot: {take_screenshot})")
    api_key = os.getenv("SCRAPFLY_KEY")
    if not api_key:
        print("[ERROR] SCRAPFLY_KEY environment variable not set.")
        return None, None

    try:
        endpoint_url = "https://api.scrapfly.io/scrape"
        
        params = {
            "key": api_key,
            "url": url,
            "render_js": True,
            "asp": True,
            "auto_scroll": True,
            "wait_for_selector": "footer a, nav a, main a, [role='main'] a, [class*='footer'] a",
            "rendering_stage": "complete",
            "rendering_wait": 7000,
            "format": "json",
            "country": "us",
            "proxy_pool": "public_residential_pool",
        }
        if take_screenshot:
            params["screenshots[main]"] = "fullpage"
            params["screenshot_flags"] = "load_images,block_banners"

        with httpx.Client(transport=DNS_TRANSPORT, proxies=None) as client:
            response = client.get(endpoint_url, params=params, timeout=180)
            response.raise_for_status()
            data = response.json()

            html_content = data["result"]["content"]
            screenshot_b64 = None

            if take_screenshot and "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
                screenshot_url = data["result"]["screenshots"]["main"]["url"]
                print(f"[Scrapfly] Downloading screenshot from: {screenshot_url}")
                
                img_response = client.get(screenshot_url, params={"key": api_key}, timeout=60)
                img_response.raise_for_status()
                image_bytes = img_response.content
                
                screenshot_b64 = base64.b64encode(image_bytes).decode('utf-8')
                print("[Scrapfly] Screenshot downloaded and encoded.")
            
            print(f"[Scrapfly] Successfully processed data for {url}.")
            return screenshot_b64, html_content

    except httpx.HTTPStatusError as e:
        print(f"[SCRAPFLY ERROR] HTTP Error for {url}: {e.response.status_code} - {e.response.text}")
        return None, None
    except Exception as e:
        print(f"[SCRAPFLY ERROR] General Error for {url}: {e}")
        return None, None

async def fetch_html_with_playwright(url: str) -> Optional[str]:
    """
    Uses Playwright to get the fully rendered HTML of a page.
    This is the slower, more powerful fallback method.
    """
    print(f"[Playwright DOM Fallback] Activating for URL: {url}")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await prepare_page_for_capture(page)
            html_content = await page.content()
            await browser.close()
            print(f"[Playwright DOM Fallback] Successfully retrieved HTML for {url}")
            return html_content
        except Exception as e:
            print(f"[Playwright DOM Fallback] Failed to get HTML for {url}: {e}")
            return None

# -----------------------------------------------------------------------------------
# Social Media Scraping Function
# -----------------------------------------------------------------------------------

def get_social_media_text(soup, base_url):
    """Finds all potential social media links, intelligently selects the best one, and scrapes its content."""
    social_text = ""
    social_platforms = {
        'twitter': re.compile(r'(twitter|x)\.com/'),
        'linkedin': re.compile(r'linkedin\.com/'),
        'facebook': re.compile(r'facebook\.com/'),
        'instagram': re.compile(r'instagram\.com/'),
        'youtube': re.compile(r'youtube\.com/'),
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for platform, pattern in social_platforms.items():
        candidate_tags = soup.find_all('a', href=pattern)
        best_url = None
        
        if candidate_tags:
            good_links = [
                tag['href'] for tag in candidate_tags 
                if 'intent' not in tag['href'] and 'share' not in tag['href'] and '/p/' not in tag['href']
            ]
            if good_links:
                best_url = sorted(good_links, key=len)[0]

        if best_url:
            full_url = urljoin(base_url, best_url)
            print(f"[Scanner] Found and scraping best {platform.capitalize()} link: {full_url}")
            try:
                res = requests.get(full_url, headers=headers, timeout=15)
                if res.ok:
                    social_soup = BeautifulSoup(res.text, "html.parser")
                    for tag in social_soup(["script", "style", "nav", "footer", "header", "aside"]):
                        tag.decompose()
                    social_text += f"\n\n--- Social Media Content ({platform.capitalize()}) ---\n"
                    social_text += social_soup.get_text(" ", strip=True)[:2000]
            except Exception as e:
                print(f"[WARN] Failed to scrape {platform}: {e}")
                
    return social_text

# -----------------------------------------------------------------------------------
# AI Analysis Functions
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
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        synthesis_prompt = f"Analyze the following text from a company's website and social media. Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. This summary will be used as context for further analysis.\n\n---\n{corpus}\n---"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": synthesis_prompt}], temperature=0.2)
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary due to an error."

def analyze_memorability_key(key_name, prompt_template, text_corpus, homepage_screenshot_b64, brand_summary):
    """Analyzes a single memorability key using the full context."""
    print(f"[AI] Analyzing key: {key_name}")
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

def call_openai_for_executive_summary(all_analyses):
    """Generates the final executive summary based on all individual key analyses."""
    print("[AI] Generating Executive Summary...")
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

# -----------------------------------------------------------------------------------
# Playwright Screenshot Function
# -----------------------------------------------------------------------------------
async def capture_screenshots_playwright(urls):
    """Captures screenshots of a list of URLs using Playwright."""
    results = []
    print(f"[Playwright] Starting screenshot capture for {len(urls)} URLs.")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # --- Use one persistent context to handle cookies across pages ---
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
            accept_language="en-US,en;q=0.9",
            timezone_id="Europe/Vienna",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        for url in urls[:4]: # Limit to 4 screenshots for the gallery
            try:
                print(f"[Playwright] Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await prepare_page_for_capture(page)
                
                img_bytes = await page.screenshot(full_page=True, type="jpeg", quality=70)
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                uid = str(uuid.uuid4())
                SHARED_CACHE[uid] = b64
                results.append({"id": uid, "url": url})
                print(f"[Playwright] Successfully captured {url}")
            except Exception as e:
                print(f"[Playwright] Failed to capture screenshot for {url}: {e}")

        await context.close()
        await browser.close()
    return results

# -----------------------------------------------------------------------------------
# Main Orchestrator Function
# -----------------------------------------------------------------------------------

def run_full_scan_stream(url: str, cache: dict):
    """The main generator function that orchestrates the entire scan process."""
    try:
        yield {'type': 'status', 'message': 'Step 1/5: Initializing scan & fetching homepage...'}
        
        cleaned_url = _clean_url(url)
        parsed_uri = urlparse(cleaned_url)
        homepage_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
        
        homepage_screenshot_b64, homepage_html = fetch_page_data_scrapfly(homepage_url, take_screenshot=True)
        if not homepage_html:
            raise Exception("Could not fetch homepage content. The site may be blocking automation.")
        
        if homepage_screenshot_b64:
            image_id = str(uuid.uuid4())
            cache[image_id] = homepage_screenshot_b64
            yield {'type': 'screenshot_ready', 'id': image_id, 'url': homepage_url}

        homepage_soup = BeautifulSoup(homepage_html, "html.parser")
        
        # --- Link Discovery and Fallback Logic ---
        discovered_links = []
        all_links = homepage_soup.find_all("a", href=True)
        print(f"[Scanner] Initial check: Found {len(all_links)} total <a> tags on the homepage.")
        
        for a in all_links:
            href = a.get("href")
            if not href or href.startswith("#") or "javascript:" in href or "{" in href:
                continue
            link_url = urljoin(homepage_url, href)
            if _is_same_domain(homepage_url, link_url):
                discovered_links.append((link_url, a.get_text(strip=True)))
        
        print(f"[Scanner] Discovered {len(discovered_links)} valid, same-domain links from initial scrape.")

        # --- The Playwright DOM Fallback ---
        if len(discovered_links) < 15: # If the initial scrape found very few links...
            yield {'type': 'status', 'message': 'Initial scrape incomplete, activating Playwright fallback...'}
            new_html = asyncio.run(fetch_html_with_playwright(homepage_url))
            if new_html:
                homepage_html = new_html # Replace the incomplete HTML
                homepage_soup = BeautifulSoup(homepage_html, "html.parser")
                
                # Re-run the link discovery on the new, complete HTML
                discovered_links = []
                all_links = homepage_soup.find_all("a", href=True)
                print(f"[Scanner] Playwright Fallback: Found {len(all_links)} total <a> tags.")
                for a in all_links:
                    href = a.get("href")
                    if not href or href.startswith("#") or "javascript:" in href or "{" in href:
                        continue
                    link_url = urljoin(homepage_url, href)
                    if _is_same_domain(homepage_url, link_url):
                        discovered_links.append((link_url, a.get_text(strip=True)))
                print(f"[Scanner] Discovered {len(discovered_links)} links after Playwright fallback.")

        # --- Social Media Discovery (runs on the final, complete HTML) ---
        social_corpus = get_social_media_text(homepage_soup, homepage_url)
        if social_corpus:
             yield {'type': 'status', 'message': 'Social media text captured.'}
        else:
             yield {'type': 'status', 'message': 'No social media links found.'}

        yield {'type': 'status', 'message': 'Identifying key pages...'}
        KEYWORD_MAP = {
            "About Us": ["about", "company", "who we are", "mission", "our story"],
            "Products/Services": ["products", "services", "solutions", "what we do", "platform", "offerings"],
            "News": ["news", "press", "blog", "media", "insights", "resources"],
        }
        
        priority_pages = [homepage_url]
        found_urls = {homepage_url}

        if cleaned_url != homepage_url:
            priority_pages.append(cleaned_url)
            found_urls.add(cleaned_url)
            
        for page_type, keywords in KEYWORD_MAP.items():
            found_url = find_priority_page(discovered_links, keywords)
            if found_url and found_url not in found_urls:
                priority_pages.append(found_url)
                found_urls.add(found_url)
        
        for link_url, _ in discovered_links:
            if len(priority_pages) >= 5: break
            if link_url not in found_urls:
                priority_pages.append(link_url)
                found_urls.add(link_url)

        other_pages_to_screenshot = [p for p in priority_pages if p != homepage_url]
        if other_pages_to_screenshot:
            yield {'type': 'status', 'message': 'Capturing visual evidence from key pages...'}
            screenshot_results = asyncio.run(capture_screenshots_playwright(other_pages_to_screenshot))
            for screenshot_data in screenshot_results:
                yield {'type': 'screenshot_ready', 'id': screenshot_data['id'], 'url': screenshot_data['url']}
        
        yield {'type': 'status', 'message': 'Step 2/5: Analyzing key pages for text content...'}
        text_corpus = ""
        
        for i, page_url in enumerate(priority_pages):
            yield {'type': 'status', 'message': f'Analyzing page {i+1}/{len(priority_pages)}: {page_url.split("?")[0]}'}
            
            if page_url == homepage_url:
                page_html = homepage_html
            else:
                _, page_html = fetch_page_data_scrapfly(page_url, take_screenshot=False)
            
            if page_html:
                soup = BeautifulSoup(page_html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({page_url}) ---\n" + soup.get_text(" ", strip=True)

        full_corpus = (text_corpus + social_corpus)[:40000]
        
        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...'}
        brand_summary = call_openai_for_synthesis(full_corpus)
        
        yield {'type': 'status', 'message': 'Step 4/5: Performing detailed analysis...'}
        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(key, prompt, full_corpus, homepage_screenshot_b64, brand_summary)
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj
        
        yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {'type': 'summary', 'text': summary_text}
        
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        import traceback
        traceback.print_exc()
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}