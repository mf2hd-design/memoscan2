import os, re, requests, json, base64
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
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.split("#")[0]

def _is_same_domain(home: str, test: str) -> bool:
    return urlparse(home).netloc == urlparse(test).netloc

# -----------------------------------------------------------------------------------
# Screenshot API Function
# -----------------------------------------------------------------------------------
def take_screenshot_via_api(url: str):
    print(f"[API Screenshot] Requesting screenshot for {url}")
    try:
        api_key = os.getenv("SCREENSHOT_API_KEY")
        if not api_key:
            print("[ERROR] SCREENSHOT_API_KEY environment variable not set.")
            return None
        api_url = "https://shot.screenshotapi.net/screenshot"
        params = {"token": api_key, "url": url, "full_page": "true", "fresh": "true", "output": "image", "file_type": "png", "wait_for_event": "load"}
        response = requests.get(api_url, params=params, timeout=120)
        response.raise_for_status()
        print("[API Screenshot] Screenshot successful.")
        return base64.b64encode(response.content).decode('utf-8')
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Could not take screenshot via API: {e}")
        return None

# -----------------------------------------------------------------------------------
# Data Collection Logic
# -----------------------------------------------------------------------------------
def crawl_and_screenshot(start_url: str, max_pages: int = 5, max_chars: int = 15000):
    cleaned_url = _clean_url(start_url)
    screenshot_b64 = take_screenshot_via_api(cleaned_url)
    visited, queue, text_corpus = set(), [cleaned_url], ""
    print(f"[Scanner] Starting crawl at {cleaned_url}")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    try:
        sitemap_url = urljoin(cleaned_url, "/sitemap.xml")
        res = requests.get(sitemap_url, headers=headers, timeout=10, allow_redirects=True)
        if res.ok:
            sitemap_soup = BeautifulSoup(res.text, "xml")
            urls = [loc.text for loc in sitemap_soup.find_all("loc")]
            if urls:
                print(f"[Scanner] Found {len(urls)} URLs in sitemap.xml.")
                queue.extend(urls)
    except Exception as e:
        print(f"[Scanner] No sitemap.xml found or error parsing it: {e}")
    while queue and len(visited) < max_pages and len(text_corpus) < max_chars:
        url = queue.pop(0)
        if url in visited or not _is_same_domain(cleaned_url, url):
            continue
        visited.add(url)
        try:
            print(f"[Scanner] Crawling: {url}")
            res = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            title = soup.find("title").get_text() if soup.find("title") else ""
            meta_desc = soup.find("meta", attrs={"name": "description"})
            description = meta_desc['content'] if meta_desc else ""
            page_content = f"Page URL: {url}\\nTitle: {title}\\nDescription: {description}\\n"
            for tag in soup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            page_content += soup.get_text(" ", strip=True)
            text_corpus += page_content + "\\n\\n"
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])
                if _is_same_domain(cleaned_url, link) and link not in visited and link not in queue:
                    queue.append(link)
        except Exception as e:
            print(f"[WARN] Failed to crawl {url}: {e}")
    print(f"[Scanner] Crawl complete. Total text corpus size: {len(text_corpus)} chars.")
    return {"text_corpus": text_corpus[:max_chars], "screenshot_b64": screenshot_b64}

# -----------------------------------------------------------------------------------
# AI Analysis Logic
# -----------------------------------------------------------------------------------

# --- FULL PROMPTS RESTORED ---
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

def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshot_b64):
    print(f"[Analyzer] Analyzing key: {key_name}")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        content = [{"type": "text", "text": f"Text corpus from the brand's website:\\n\\n---\\n{text_corpus}\\n---"}]
        if screenshot_b64:
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}})

        # --- FULL SYSTEM PROMPT RESTORED ---
        system_prompt = f"""
            You are a senior brand strategist at Saffron Brand Consultants. Your task is to evaluate a brand's memorability for one specific key.
            
            {prompt_template}

            Provide your analysis in a structured format. Respond with ONLY a JSON object with the following keys:
            - "score": An integer from 0 to 100.
            - "justification": A concise, 1-2 sentence explanation for your score.
            - "evidence": A single, a direct quote from the text or a specific visual observation from the screenshot that supports your analysis.
            - "confidence": An integer from 1 to 5 representing your confidence in the analysis, where 1 is low (major guess) and 5 is high (strong evidence).
        """
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return key_name, response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        error_response = {"score": 0, "justification": "Analysis failed due to an internal error.", "evidence": str(e), "confidence": 1}
        return key_name, json.dumps(error_response)
    finally:
        for key, value in original_proxies.items():
            if value is not None:
                os.environ[key] = value

# -----------------------------------------------------------------------------------
# Final, Synchronous Streaming Orchestrator (With Heartbeat)
# -----------------------------------------------------------------------------------

def run_full_scan_stream(url: str):
    try:
        yield "data: [STATUS] Request received! Your brand analysis is starting now. This can take up to 90 seconds, so we appreciate your patience.\\n\\n"
        
        brand_data = crawl_and_screenshot(url)
        
        yield "data: [STATUS] Data collection complete. Analyzing with AI...\\n\\n"
        
        if not brand_data["text_corpus"] and not brand_data["screenshot_b64"]:
            yield "data: [ERROR] Could not gather any content or visuals from the URL. Cannot perform analysis.\\n\\n"
            return

        # --- THIS LOOP IS THE ONLY PART THAT HAS CHANGED ---
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            # Send a "heartbeat" status update BEFORE the slow network call.
            # This keeps the proxy connection alive.
            yield f"data: [STATUS] Analyzing key: {key}...\\n\\n"
            
            # This is the slow part.
            key_name, result_json = analyze_memorability_key(key, prompt, brand_data["text_corpus"], brand_data["screenshot_b64"])
            
            # Send the actual result.
            yield f"data: {{\"key\": \"{key_name}\", \"analysis\": {result_json}}}\\n\\n"
        
        yield "data: [COMPLETE] Analysis finished.\\n\\n"

    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield f"data: [ERROR] A critical error occurred during the scan: {e}\\n\\n"
