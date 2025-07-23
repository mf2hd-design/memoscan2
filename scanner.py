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

load_dotenv()

# --- Helper Functions (Unchanged) ---
def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")): url = "https://" + url
    return url.split("#")[0]

def _is_same_domain(home: str, test: str) -> bool:
    return urlparse(home).netloc == urlparse(test).netloc

# --- Screenshot API Function (Unchanged) ---
def take_screenshot_via_api(url: str):
    print(f"[API Screenshot] Requesting screenshot for {url}")
    try:
        api_key = os.getenv("SCREENSHOT_API_KEY")
        if not api_key:
            print("[ERROR] SCREENSHOT_API_KEY not set."); return None
        api_url = "https://shot.screenshotapi.net/screenshot"
        params = {"token": api_key, "url": url, "full_page": "true", "output": "image", "file_type": "png", "wait_for_event": "networkidle"}
        response = requests.get(api_url, params=params, timeout=120)
        response.raise_for_status()
        print("[API Screenshot] Screenshot successful.")
        return base64.b64encode(response.content).decode('utf-8')
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Screenshot API failed: {e}"); return None

# --- Social Media Scraping Function (Unchanged) ---
def get_social_media_text(soup, base_url):
    social_text = ""
    social_links = {
        'twitter': soup.find('a', href=re.compile(r'twitter\.com/')),
        'linkedin': soup.find('a', href=re.compile(r'linkedin\.com/company/'))
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    for platform, link_tag in social_links.items():
        if link_tag:
            url = urljoin(base_url, link_tag['href'])
            print(f"[Scanner] Scraping {platform.capitalize()}...")
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
    return social_text

# --- AI Analysis Functions (HEAVILY UPDATED) ---
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
    print("[AI] Synthesizing brand overview...")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        synthesis_prompt = f"Analyze the following text... Provide a concise summary...\n\n---\n{corpus}\n---"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": synthesis_prompt}], temperature=0.2)
        return response.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] AI synthesis failed: {e}")
        return "Could not generate brand summary."
    finally:
        for key, value in original_proxies.items():
            if value is not None: os.environ[key] = value

def analyze_memorability_key(key_name, prompt_template, text_corpus, screenshot_b64, brand_summary):
    print(f"[AI] Analyzing key: {key_name}")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        content = [{"type": "text", "text": f"FULL TEXT CORPUS:\n---\n{text_corpus}\n---"}, {"type": "text", "text": f"BRAND SUMMARY:\n---\n{brand_summary}\n---"}]
        if screenshot_b64:
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}})
        
        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
        {prompt_template}
        
        Your response MUST be a JSON object with the following keys:
        - "score": An integer from 0 to 100.
        - "analysis": A comprehensive analysis of **at least five sentences** explaining your score, based on the specific criteria provided.
        - "evidence": A single, direct quote from the text or a specific visual observation from the screenshot that powerfully supports your analysis.
        - "confidence": An integer from 1 to 5.
        - "confidence_rationale": A brief explanation for your confidence score (e.g., "High confidence due to clear mission statement").
        - "recommendation": A concise, actionable recommendation for how the brand could improve its score for this specific key.
        """
        
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}], response_format={"type": "json_object"}, temperature=0.3)
        return key_name, json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"[ERROR] LLM analysis failed for key '{key_name}': {e}")
        error_response = {"score": 0, "analysis": "Analysis failed due to a server error.", "evidence": str(e), "confidence": 1, "confidence_rationale": "System error.", "recommendation": "Resolve the technical error to proceed."}
        return key_name, error_response
    finally:
        for key, value in original_proxies.items():
            if value is not None: os.environ[key] = value

def call_openai_for_executive_summary(all_analyses):
    print("[AI] Generating Executive Summary...")
    proxy_keys = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
    original_proxies = {key: os.environ.pop(key, None) for key in proxy_keys}
    try:
        http_client = httpx.Client(proxies=None)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=http_client)
        
        # Format the individual analyses into a string for the prompt.
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
            if value is not None: os.environ[key] = value

# --- Main Orchestrator Function ---
def run_full_scan_stream(url: str, cache: dict):
    try:
        # ... (Initial setup and screenshot logic is unchanged) ...
        
        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            key_name, result_json = analyze_memorability_key(key, prompt, full_corpus, screenshot_b64, brand_summary)
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
