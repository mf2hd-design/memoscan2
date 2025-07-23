import os
import re
import requests
import json
import base64
import uuid
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
import httpx
import gevent

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

def find_priority_page(discovered_links: list, keywords: list) -> str or None:
    """Searches a list of discovered links for the best match based on keywords."""
    for link_url, link_text in discovered_links:
        # Check both the link URL and the visible text of the link for keywords
        for keyword in keywords:
            if keyword in link_url.lower() or keyword in link_text.lower():
                return link_url  # Return the first match found
    return None

# -----------------------------------------------------------------------------------
# UNIFIED Fetching and Screenshot Function (THIS WAS MISSING)
# -----------------------------------------------------------------------------------

def fetch_content_and_screenshot(url: str):
    """
    Uses the screenshot API to get both the screenshot AND the rendered HTML.
    This bypasses anti-bot protections that block simple 'requests.get()'.
    """
    print(f"[API] Fetching content and screenshot for {url}")
    try:
        api_key = os.getenv("SCREENSHOT_API_KEY")
        if not api_key:
            print("[ERROR] SCREENSHOT_API_KEY environment variable not set.")
            return None, None # Return a tuple of two Nones

        api_url = "https://shot.screenshotapi.net/screenshot"
        params = {
            "token": api_key,
            "url": url,
            "output": "json", # We now ask for a JSON response
            "file_type": "png",
            "width": 1280,
            "height": 1024,
            "wait_for_event": "networkidle",
            "hide_cookie_banners": "true",
            "html": "true" # This tells the API to include the HTML in its response
        }
        
        response = requests.get(api_url, params=params, timeout=120)
        response.raise_for_status()
        
        data = response.json()
        
        # The API returns a URL to the image, so we download it.
        screenshot_response = requests.get(data["screenshot"], timeout=60)
        screenshot_response.raise_for_status()
        screenshot_b64 = base64.b64encode(screenshot_response.content).decode('utf-8')
        
        html_content = data.get("html", "")
        
        print(f"[API] Successfully fetched content for {url}.")
        return screenshot_b64, html_content

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API fetch failed for {url}: {e}")
        return None, None

# -----------------------------------------------------------------------------------
# Social Media Scraping Function
# -----------------------------------------------------------------------------------

def get_social_media_text(soup, base_url):
    """Finds social links, scrapes them, and returns a single block of text."""
    social_text = ""
    social_links = {
        'twitter': soup.find('a', href=re.compile(r'twitter\.com/')),
        'linkedin': soup.find('a', href=re.compile(r'linkedin\.com/company/'))
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    for platform, link_tag in social_links.items():
        if link_tag:
            url = urljoin(base_url, link_tag['href'])
            print(f"[Scanner] Scraping {platform.capitalize()} at {url}...")
            try:
                # We can still use requests here as social sites are less likely to block this way
                res = requests.get(url, headers=headers, timeout=15)
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

def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshots: dict, brand_summary):
    """Analyzes a single memorability key using the full context AND multiple screenshots."""
    print(f"[AI] Analyzing key: {key_name}")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        
        content = []
        if screenshots:
            for url, b64_data in screenshots.items():
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_data}"}})
                content.append({"type": "text", "text": f"--- Screenshot from: {url} ---"})

        content.extend([
            {"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"},
            {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"}
        ])
        
        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
        {prompt_template}
        
        Your response MUST be a JSON object with the following keys:
        - "score": An integer from 0 to 100.
        - "analysis": A comprehensive analysis of **at least five sentences** explaining your score, based on the specific criteria provided.
        - "evidence": A single, direct quote from the text or a specific visual observation from **one of the provided screenshots**. **You must reference the screenshot's URL in your evidence** (e.g., "In the screenshot from example.com/about, the color palette is...").
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
# Main Orchestrator Function
# -----------------------------------------------------------------------------------
def run_full_scan_stream(url: str, cache: dict):
    """The main generator function that orchestrates the entire scan process."""
    try:
        yield {'type': 'status', 'message': 'Step 1/5: Initializing scan...'}
        cleaned_url = _clean_url(url)

        yield {'type': 'status', 'message': 'Crawling homepage to discover site structure...'}
        _, homepage_html = fetch_content_and_screenshot(cleaned_url)
        if not homepage_html:
            raise Exception("Could not fetch homepage content. The site may be blocking automation.")
        
        homepage_soup = BeautifulSoup(homepage_html, "html.parser")
        
        discovered_links = []
        for a in homepage_soup.find_all("a", href=True):
            link_url = urljoin(cleaned_url, a["href"])
            if _is_same_domain(cleaned_url, link_url):
                discovered_links.append((link_url, a.get_text(strip=True)))

        yield {'type': 'status', 'message': 'Identifying key pages...'}
        KEYWORD_MAP = {
            "About Us": ["about", "company", "who we are", "mission", "our story"],
            "Products/Services": ["products", "services", "solutions", "what we do", "platform", "offerings"],
            "News": ["news", "press", "blog", "media", "insights", "resources"],
            "Investor Relations": ["investors", "ir", "relations"]
        }
        priority_pages = [cleaned_url]
        found_urls = {cleaned_url}
        for page_type, keywords in KEYWORD_MAP.items():
            found_url = find_priority_page(discovered_links, keywords)
            if found_url and found_url not in found_urls:
                priority_pages.append(found_url)
                found_urls.add(found_url)
        while len(priority_pages) < 5:
            for link_url, _ in discovered_links:
                if len(priority_pages) >= 5: break
                if link_url not in found_urls:
                    priority_pages.append(link_url)
                    found_urls.add(link_url)
            if len(priority_pages) < 5: break

        yield {'type': 'status', 'message': 'Step 2/5: Analyzing key pages...'}
        text_corpus, social_corpus = "", ""
        screenshots = {}
        
        for i, page_url in enumerate(priority_pages):
            yield {'type': 'status', 'message': f'Analyzing page {i+1}/{len(priority_pages)}: {page_url.split("?")[0]}'}
            
            screenshot_b64, page_html = fetch_content_and_screenshot(page_url)
            
            if screenshot_b64:
                image_id = str(uuid.uuid4())
                cache[image_id] = screenshot_b64
                screenshots[page_url] = screenshot_b64
                yield {'type': 'screenshot_ready', 'id': image_id, 'url': page_url}

            if page_html:
                soup = BeautifulSoup(page_html, "html.parser")
                if page_url == cleaned_url:
                    social_corpus = get_social_media_text(soup, cleaned_url)
                    if social_corpus: yield {'type': 'status', 'message': 'Social media text captured.'}

                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]): tag.decompose()
                text_corpus += f"\n\n--- Page Content ({page_url}) ---\n" + soup.get_text(" ", strip=True)

        full_corpus = (text_corpus + social_corpus)[:25000]
        
        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...'}
        brand_summary = call_openai_for_synthesis(full_corpus)
        
        yield {'type': 'status', 'message': 'Step 4/5: Performing detailed analysis...'}
        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(key, prompt, full_corpus, screenshots, brand_summary)
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj
        
        yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results)
        yield {'type': 'summary', 'text': summary_text}
        
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
