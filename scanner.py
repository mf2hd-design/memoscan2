import os
import re
import requests
import json
import base64
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
import httpx

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

# -----------------------------------------------------------------------------------
# Screenshot API Function
# -----------------------------------------------------------------------------------

def take_screenshot_via_api(url: str):
    """Takes a single homepage screenshot using an external API."""
    print(f"[API Screenshot] Requesting screenshot for {url}")
    try:
        api_key = os.getenv("SCREENSHOT_API_KEY")
        if not api_key:
            print("[ERROR] SCREENSHOT_API_KEY environment variable not set.")
            return None
        api_url = "https://shot.screenshotapi.net/screenshot"
        params = {"token": api_key, "url": url, "full_page": "true", "output": "image", "file_type": "png", "wait_for_event": "load"}
        response = requests.get(api_url, params=params, timeout=120)
        response.raise_for_status()
        print("[API Screenshot] Screenshot successful.")
        return base64.b64encode(response.content).decode('utf-8')
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Screenshot API failed: {e}")
        return None

# -----------------------------------------------------------------------------------
# Social Media Scraping Function
# -----------------------------------------------------------------------------------

def get_social_media_text(soup, base_url):
    """Finds social media links and scrapes text from their profiles."""
    social_text = ""
    social_links = {
        'twitter': soup.find('a', href=re.compile(r'twitter\.com/')),
        'linkedin': soup.find('a', href=re.compile(r'linkedin\.com/company/'))
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    for platform, link_tag in social_links.items():
        if link_tag:
            url = urljoin(base_url, link_tag['href'])
            yield {'type': 'status', 'message': f'Found and scraping {platform.capitalize()} profile...'}
            try:
                res = requests.get(url, headers=headers, timeout=15)
                if res.ok:
                    social_soup = BeautifulSoup(res.text, "html.parser")
                    for tag in social_soup(["script", "style", "nav", "footer", "header", "aside"]):
                        tag.decompose()
                    social_text += f"\n\n--- Social Media Content ({platform.capitalize()}) ---\n"
                    social_text += social_soup.get_text(" ", strip=True)[:2000]
            except Exception as e:
                print(f"[WARN] Failed to scrape {platform}: {e}")
    yield social_text

# -----------------------------------------------------------------------------------
# AI Analysis Functions
# -----------------------------------------------------------------------------------

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": """
        Analyze the **Emotion** key.
        - **Lens:** Does the brand evoke warmth, trust, joy, or admiration? Is there emotional resonance in the messaging, values, or human stories?
        - **Source:** Focus on the text corpus. Look for mission statements, 'About Us' narratives, customer testimonials, and overall tone.
    """,
    "Attention": """
        Analyze the **Attention** key.
        - **Lens:** How distinctive and arresting is the brand's first impression? Does it sustain interest?
        - **Source:** Focus heavily on the **website screenshot**. Evaluate the use of color, typography, imagery, and layout in the hero section. Does the headline grab attention? Is there an element of surprise?
    """,
    "Story": """
        Analyze the **Story** key.
        - **Lens:** Is there a clear, coherent narrative? Does it explain who the brand is, why it exists, and what it promises?
        - **Source:** Focus on the text corpus. Synthesize the content from different pages (especially 'About' or 'Mission' if available) to construct the brand's narrative. Is it easy to understand?
    """,
    "Involvement": """
        Analyze the **Involvement** key.
        - **Lens:** Does the brand invite audience participation or make them feel part of a community?
        - **Source:** Analyze both text and screenshot. Look for calls-to-action (e.g., "Join our community," "Share your story"), interactive elements, and inclusive language. Does it feel like a one-way broadcast or a two-way conversation?
    """,
    "Repetition": """
        Analyze the **Repetition** key.
        - **Lens:** Are key verbal or visual signals consistently reused to make them memorable?
        - **Source:** Use both screenshot and text. In the text, look for repeated taglines, slogans, or key phrases. In the screenshot, identify the logo, color palette, and typography. Are these elements likely to be repeated across the site?
    """,
    "Consistency": """
        Analyze the **Consistency** key.
        - **Lens:** Do the brand's touchpoints feel aligned in tone, message, and design?
        - **Source:** Primarily use the screenshot to judge visual consistency. Use the text corpus to evaluate the consistency of the brand's tone and messaging across different pages. Do the parts feel like they belong to a coherent whole?
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
            if value is not None: os.environ[key] = value

def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshot_b64, brand_summary):
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
        if screenshot_b64:
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}})
        system_prompt = f"""You are a senior brand strategist. Your task is to evaluate a brand's memorability for one specific key, using the provided brand summary for high-level context and the full text corpus for detailed evidence. {prompt_template} Provide your analysis in a structured format. Respond with ONLY a JSON object with the following keys: "score" (an integer from 0 to 100), "justification" (a concise, 1-2 sentence explanation), "evidence" (a single, direct quote from the text or a specific visual observation from the screenshot), and "confidence" (an integer from 1 to 5)."""
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}], response_format={"type": "json_object"}, temperature=0.2)
        return key_name, json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        error_response = {"score": 0, "justification": "Analysis failed due to an error.", "evidence": str(e), "confidence": 1}
        return key_name, error_response
    finally:
        for key, value in original_proxies.items():
            if value is not None: os.environ[key] = value

# -----------------------------------------------------------------------------------
# Main Orchestrator Function
# -----------------------------------------------------------------------------------
def run_full_scan_stream(url: str):
    """The main generator function that orchestrates the entire scan process."""
    try:
        yield {'type': 'status', 'message': 'Step 1/4: Initializing scan...'}
        cleaned_url = _clean_url(url)
        
        yield {'type': 'status', 'message': 'Step 2/4: Capturing homepage screenshot...'}
        screenshot_b64 = take_screenshot_via_api(cleaned_url)
        if screenshot_b64:
            yield {'type': 'screenshot', 'data': screenshot_b64}
        
        yield {'type': 'status', 'message': 'Step 3/4: Crawling website and social media...'}
        text_corpus, social_corpus = "", ""
        visited, queue = set(), [cleaned_url]
        headers = {"User-Agent": "Mozilla/5.0"}
        page_count = 0

        while queue and page_count < 5:
            current_url = queue.pop(0)
            if current_url in visited: continue
            visited.add(current_url)
            page_count += 1
            yield {'type': 'status', 'message': f'Crawling page {page_count}/5: {current_url.split("?")[0]}'}
            try:
                res = requests.get(current_url, headers=headers, timeout=10)
                res.raise_for_status()
                soup = BeautifulSoup(res.text, "html.parser")
                
                if current_url == cleaned_url:
                    social_gen = get_social_media_text(soup, cleaned_url)
                    for item in social_gen:
                        if isinstance(item, dict): yield item
                        else: social_corpus += item

                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({current_url}) ---\n" + soup.get_text(" ", strip=True)

                for a in soup.find_all("a", href=True):
                    link = urljoin(current_url, a["href"])
                    if _is_same_domain(cleaned_url, link) and link not in visited and len(queue) < 10:
                        queue.append(link)
            except Exception as e:
                print(f"[WARN] Failed to crawl {current_url}: {e}")

        full_corpus = text_corpus + social_corpus
        final_corpus = full_corpus[:25000]
        
        yield {'type': 'status', 'message': 'Step 4/4: Performing AI analysis...'}
        
        yield {'type': 'status', 'message': 'Synthesizing brand overview...'}
        brand_summary = call_openai_for_synthesis(final_corpus)
        
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(key, prompt, final_corpus, screenshot_b64, brand_summary)
            yield {'type': 'result', 'key': key_name, 'analysis': result_json}
        
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
