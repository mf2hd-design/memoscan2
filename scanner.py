import os, re, requests, json, base64
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
import httpx # Re-add httpx import

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
# AI Analysis Logic (With Defense-in-Depth)
# -----------------------------------------------------------------------------------

MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": "Analyze the Emotion key...", "Attention": "Analyze the Attention key...", "Story": "Analyze the Story key...",
    "Involvement": "Analyze the Involvement key...", "Repetition": "Analyze the Repetition key...", "Consistency": "Analyze the Consistency key..."
} # Prompts are truncated for brevity, the original content is correct.

def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshot_b64):
    print(f"[Analyzer] Analyzing key: {key_name}")

    # --- DEFENSE IN DEPTH AGAINST PROXY INJECTION ---
    # 1. Store original proxy settings and then clear them from the environment.
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}

    try:
        # 2. Explicitly create an HTTP client that does not use any proxies.
        http_client = httpx.Client(proxies=None)

        # 3. Initialize the OpenAI client with the custom, proxy-free client.
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=http_client
        )
        
        content = [{"type": "text", "text": f"Text corpus from the brand's website:\\n\\n---\\n{text_corpus}\\n---"}]
        if screenshot_b64:
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}})

        system_prompt = f"""
            You are a senior brand strategist... 
            {prompt_template}
            Provide your analysis in a structured format...
        """ # System prompt is truncated for brevity, the original content is correct.

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
        # 4. Restore the original environment variables to not affect other processes.
        for key, value in original_proxies.items():
            if value is not None:
                os.environ[key] = value

# -----------------------------------------------------------------------------------
# Final, Synchronous Streaming Orchestrator
# -----------------------------------------------------------------------------------

def run_full_scan_stream(url: str):
    try:
        yield "data: [STATUS] Request received! Your brand analysis is starting now...\n\n"
        brand_data = crawl_and_screenshot(url)
        yield "data: [STATUS] Data collection complete. Analyzing with AI...\n\n"
        
        if not brand_data["text_corpus"] and not brand_data["screenshot_b64"]:
            yield "data: [ERROR] Could not gather any content or visuals from the URL...\n\n"
            return

        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            key_name, result_json = analyze_memorability_key(key, prompt, brand_data["text_corpus"], brand_data["screenshot_b64"])
            yield f"data: {{\"key\": \"{key_name}\", \"analysis\": {result_json}}}\\n\\n"
        
        yield "data: [COMPLETE] Analysis finished.\\n\\n"
    except Exception as e:
        print(f"[CRITICAL ERROR] The main stream failed: {e}")
        yield f"data: [ERROR] A critical error occurred during the scan: {e}\\n\\n"
