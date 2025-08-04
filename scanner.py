
def _get_sld(url: str) -> str:
    """
    Returns the second-level domain (SLD): 'omv' from 'www.omv.at' or 'omv.com'.
    """
    from urllib.parse import urlparse
    netloc = urlparse(url).netloc.lower().lstrip("www.")
    parts = netloc.split(".")
    return parts[-2] if len(parts) >= 2 else netloc

def _is_same_brand_domain(url1: str, url2: str) -> bool:
    return _get_sld(url1) == _get_sld(url2)

import os
import re
import json
import base64
import uuid
import time
import signal
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup, Tag
from openai import OpenAI
from dotenv import load_dotenv
import httpx

from urllib.parse import quote_plus

BASE_SCRAPFLY_QUERY = (
    "tags=player%2Cproject%3Adefault"
    "&proxy_pool=public_residential_pool"
    "&format=json"
    "&asp=true"
    "&render_js=true"
    "&screenshots[test]=fullpage"
    "&screenshot_flags=load_images%2Cblock_banners"
    "&auto_scroll=true"
)

def build_scrapfly_url(target_url: str, api_key: str) -> str:
    return f"REPLACEME_URL_PREFIX{quote_plus(target_url)}"

from playwright.sync_api import sync_playwright
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor

# --- START: CONFIGURATION AND CONSTANTS ---
CONFIG = {
    "retries": 3,
    "rate_limit_delay": 1,
    "circuit_breaker_threshold": 3,
    "ignored_extensions": {'.pdf', '.zip', '.jpg', '.jpeg', '.png', '.gif', '.docx', '.xlsx', '.pptx', '.mp3', '.mp4'},
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    ]
}
# --- END: CONFIGURATION AND CONSTANTS ---

# --- START: REGEX AND SCORING LOGIC ---
NEGATIVE_REGEX = [
    r"\b(log(in|out)?|sign(in|up)|register|account|my-account)\b", r"\b(anmelden|abmelden|registrieren|konto)\b", r"\b(iniciar-sesion|cerrar-sesion|crear-cuenta|cuenta)\b",
    r"\b(impressum|imprint|legal|disclaimer|compliance|datenschutz|privacy|terms|cookies?)\b", r"\b(agb|bedingungen|rechtliches|politica-de-privacidad|aviso-legal|terminos|condiciones)\b",
    r"\b(newsletter|subscribe|subscription|unsubscribe|boletin|suscripcion|darse-de-baja)\b",
    r"\b(jobs?|career(s)?|vacancies|internships?|apply|karriere|stellenangebote|bewerbung|praktikum|empleo|trabajo|vacantes|postulaciones|reclutamiento)\b",
    r"\b(basket|cart|checkout|shop|store|ecommerce|wishlist|warenkorb|kaufen|bestellen|einkaufen|carrito|tienda|comprar|pago|pedido)\b",
    r"\b(calculator|tool|search|filter|compare|rechner|suche|vergleich|calculadora|buscar|comparar|filtro)\b",
    r"\b(404|not-found|error|redirect|sitemap|robots|tracking|rss|weiterleitung|umleitung|redireccion|mapa-del_sitio|seguimiento)\b",
    r"\b(press[-_]release(s)?)\b",
    # Aggressively penalize specific investor docs/reports and general news/events/blogs/articles
    r"\b(takeover|capital[-_]increase|webcast|publication|report|finances?|annual[-_]report|quarterly[-_]report|balance[-_]sheet|proxy|prospectus|statement|filings|investor[-_]deck)\b",
    # Expanded to catch more general news/content sections, webinars, whitepapers, case studies, resources, insights
    r"\b(news|events|blogs?|articles?|updates?|media|press|spotlight|stories)\b",
    r"\b(whitepapers?|webinars?|case[-_]stud(y|ies)|customer[-_]stor(y|ies))\b",
    r"\b(resources?|insights?|downloads?)\b" # General content hubs, added 'downloads'
]

LINK_SCORE_MAP = {
    "high": {"patterns": [r"company", r"about", r"story", r"mission", r"vision", r"purpose", r"values", r"strategy", r"strength", r"culture", r"who[-_]we[-_]are", r"credo", r"manifesto", r"why[-_]we[-_]exist", r"what[-_]we[-_]believe", r"über[-_]uns", r"unternehmen", r"unsere[-_]mission", r"unsere[-_]werte", r"quienes[-_]somos", r"nuestra[-_]historia", r"nuestros[-_]valores"], "score": 20},
    "core_business": {"patterns": [r"products", r"solutions", r"services", r"pipeline", r"research", r"innovation", r"investors?", r"investor[-_]relations", r"offerings", r"expertise", r"what[-_]we[-_]do", r"capabilities", r"industries", r"technology"], "score": 15}, # Added 'offerings', 'expertise', 'what-we-do', 'capabilities', 'industries', 'technology'
    "language": {"patterns": [r"/en/", r"lang=en"], "score": 10},
    "medium": {"patterns": [r"leadership", r"team", r"management", r"history", r"heritage", r"legacy", r"sustainability", r"responsibility", r"esg", r"evp", r"employee-value-proposition", r"nachhaltigkeit", r"verantwortung", r"liderazgo", r"equipo", "sostenibilidad"], "score": 8},
    "negative": {"patterns": NEGATIVE_REGEX, "score": -50} # All other negative patterns combined
}


def score_link(link_url: str, link_text: str) -> int:
    score = 0
    combined_text = f"{link_url} {link_text}".lower()
    for tier in LINK_SCORE_MAP.values():
        for pattern in tier["patterns"]:
            if re.search(pattern, combined_text):
                score += tier["score"]
    path_depth = link_url.count('/') - 2
    if path_depth <= 2: score += 2
    if any(link_url.lower().endswith(ext) for ext in CONFIG["ignored_extensions"]): score -= 100
    return score
# --- END: REGEX AND SCORING LOGIC ---

# --- START: HELPER CLASSES AND FUNCTIONS ---
class CircuitBreaker:
    def __init__(self, failure_threshold: int):
        self.failure_threshold = failure_threshold
        self.failures = 0
    def record_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold: raise Exception(f"Circuit breaker triggered after {self.failures} consecutive failures.")
    def record_success(self): self.failures = 0



def log(level, message, data=None):
    import json
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now}] [{level.upper()}] {message}"
    print(formatted, flush=True)
    if data:
        print(f"Details: {json.dumps(data, indent=2, ensure_ascii=False)}", flush=True)
    formatted = f"[{level.upper()}] {message}"
    print(formatted, flush=True)
    if data:
        print(f"Details: {json.dumps(data, indent=2, ensure_ascii=False)}", flush=True)
    print(f"[{level.upper()}] {timestamp} - {message}")
    if data: print(f"Details: {json.dumps(data, indent=2, ensure_ascii=False)}")

    # Remove www. prefix if present
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    parts = netloc.split('.')
    # Handle cases like co.uk, com.br, etc.
    if len(parts) >= 2:
        # For most cases, return the last two parts
        return '.'.join(parts[-2:])
    return netloc

    domain2 = _get_sld(url2)
    result = domain1 == domain2
    # Debug logging for first few checks
    if not hasattr(_is_same_brand_domain, 'log_count'):
        _is_same_brand_domain.log_count = 0
    if _is_same_brand_domain.log_count < 5:
        log("debug", f"Domain check: {url1} ({domain1}) vs {url2} ({domain2}) = {result}")
        _is_same_brand_domain.log_count += 1
    return result

def _sanitize_href(href: str) -> str:
    if not href: return ""
    return href.replace('\\"', '').replace('\\', '').strip().strip('"\'')

def get_random_user_agent() -> str:
    return CONFIG["user_agents"][uuid.uuid4().int % len(CONFIG["user_agents"])]

def _fetch_page_data_scrapfly(url: str, take_screenshot: bool = True):
    log("info", f"Fetching data for {url} (Screenshot: {take_screenshot})")
    api_key = os.getenv("SCRAPFLY_KEY")
    if not api_key:
        log("error", "SCRAPFLY_KEY environment variable not set.")
        return None, None
    try:
        params = {"key": api_key, "url": url, "render_js": True, "asp": True, "auto_scroll": True, "wait_for_selector": "footer a, nav a, main a, [role='main'] a, [class*='footer'] a", "rendering_stage": "complete", "rendering_wait": 7000, "format": "json", "country": "us", "proxy_pool": "public_residential_pool"}
        if take_screenshot:
            params["screenshots[main]"] = "fullpage"
            params["screenshot_flags"] = "load_images,block_banners"
        with httpx.Client(proxies=None) as client:
            response = client.get("https://api.scrapfly.io/scrape", params=params, timeout=180)
            response.raise_for_status()
            data = response.json()
            html_content = data["result"]["content"]
            screenshot_b64 = None
            if take_screenshot and "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
                screenshot_url = data["result"]["screenshots"]["main"]["url"]
                img_response = client.get(screenshot_url, params={"key": api_key}, timeout=60)
                img_response.raise_for_status()
                screenshot_b64 = base64.b64encode(img_response.content).decode('utf-8')
            return screenshot_b64, html_content
    except Exception as e:
        log("error", f"Scrapfly error for {url}: {e}")
        return None, None

def fetch_html_with_playwright(url: str, retried: bool = False) -> Optional[str]:
    log("info", f"Activating Playwright fallback for URL: {url}")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=get_random_user_agent())
            page = context.new_page()
            page.goto(url, wait_until="load", timeout=90000)
            prepare_page_for_capture(page)
            
            # Hovering logic was removed in the previous iteration based on user feedback.

            html_content = page.content()
            browser.close()
            return html_content
        except Exception as e:
            log("error", f"Playwright failed for {url}: {e}")
            if "browser has crashed" in str(e).lower() and not retried:
                log("warn", "Restarting Playwright browser...")
                return fetch_html_with_playwright(url, retried=True)
            return None

def fetch_page_content_robustly(url: str, take_screenshot: bool = False) -> Tuple[Optional[str], Optional[str]]:
    try:
        screenshot, html = _fetch_page_data_scrapfly(url, take_screenshot=take_screenshot)
        if html:
            return screenshot, html
        else:
            log("warn", f"Scrapfly returned empty content for {url}, trying Playwright. (No screenshot from Playwright fallback)")
            html = fetch_html_with_playwright(url)
            return None, html # Playwright fallback doesn't return screenshot
    except Exception as e:
        log("warn", f"Scrapfly failed for {url} with error: {e}. Falling back to Playwright. (No screenshot from Playwright fallback)")
        html = fetch_html_with_playwright(url)
        return None, html # Playwright fallback doesn't return screenshot

def fetch_all_pages(urls: list[str]) -> Dict[str, Optional[str]]:
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(fetch_page_content_robustly, url): url for url in urls}
        for future in future_to_url:
            url = future_to_url[future]
            try:
                _, html = future.result()
                if not html: raise ValueError("Received empty HTML content.")
                results[url] = html
                log("info", f"Successfully fetched parallel page: {url}")
            except Exception as e:
                log("warn", f"Failed to fetch parallel page {url}: {e}")
                results[url] = None
    return results

def summarize_results(all_results: list) -> dict:
    if not all_results: return {"keys_analyzed": 0, "strong_keys": 0, "weak_keys": 0}
    summary = {"keys_analyzed": len(all_results), "strong_keys": 0, "weak_keys": 0}
    for result in all_results:
        if 'analysis' in result and 'score' in result['analysis']:
            # Assuming score is now out of 5 from the AI, adjust thresholds for summary
            if result["analysis"]["score"] >= 4: summary["strong_keys"] += 1
            elif result["analysis"]["score"] <= 2: summary["weak_keys"] += 1
    return summary
# --- END: HELPER CLASSES AND FUNCTIONS ---

SHARED_CACHE = {}
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- START: FEEDBACK MECHANISM ---
FEEDBACK_FILE = "feedback_log.jsonl"

def record_feedback(analysis_id: str, key_name: str, feedback_type: str, comment: Optional[str] = None):
    """Records user feedback for a specific AI analysis."""
    feedback_entry = {
        "timestamp": time.time(),
        "analysis_id": analysis_id,
        "key_name": key_name,
        "feedback_type": feedback_type, # e.g., "thumbs_up", "thumbs_down", "comment"
        "comment": comment
    }
    try:
        with open(FEEDBACK_FILE, "a") as f:
            f.write(json.dumps(feedback_entry) + "\n")
        log("info", f"Recorded feedback for analysis_id {analysis_id}, key {key_name}: {feedback_type}")
    except Exception as e:
        log("error", f"Failed to record feedback to file: {e}")
# --- END: FEEDBACK MECHANISM ---

def _clean_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")): url = "https://" + url
    return url.split("#")[0]

def prepare_page_for_capture(page, max_ms=45000):
    page.wait_for_load_state("domcontentloaded", timeout=max_ms)
    consent_clicked = False
    for text in ["Accept", "I agree", "Alle akzeptieren", "Zustimmen", "Allow all", "Accept all"]:
        try:
            page.get_by_role("button", name=re.compile(text, re.I)).click(timeout=1500)
            log("info", f"Consent banner '{text}' dismissed.")
            consent_clicked = True
            break
        except Exception: 
            pass # Button not found or clickable, try next.
    if not consent_clicked: log("info", "No common consent banner found to click.")
    
    # Scroll the page to trigger lazy loading
    page.evaluate("""() => { 
        const step = 800; 
        let y = 0; 
        const sleep = ms => new Promise(r => setTimeout(r, ms)); 
        (async () => { 
            const maxScrolls = 50; 
            let scrollCount = 0; 
            while (y < document.body.scrollHeight && scrollCount < maxScrolls) { 
                window.scrollBy(0, step); 
                y += step; 
                scrollCount++; 
                await sleep(120); 
            } 
            window.scrollTo(0, 0); 
        })(); 
    }""")
    
    # Wait for visual readiness
    try:
        page.wait_for_function("() => { const imagesReady = Array.from(document.images).every(img => img.complete && img.naturalWidth > 0); const fontsReady = !('fonts' in document) || document.fonts.status === 'loaded'; const noSkeletons = !document.querySelector('[class*=skeleton],[data-skeleton],[aria-busy=\"true\"]'); return imagesReady && fontsReady && noSkeletons; }", timeout=15000)
        log("info", "Page is visually ready based on strict check.")
    except Exception as e:
        log("warn", f"Strict visual readiness check failed: {e}. Proceeding with lenient wait.")
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
            log("info", "Page is ready based on network idle state.")
        except Exception as network_e:
            log("warn", f"Network idle wait also failed: {network_e}. Proceeding anyway.")
    log("info", "Page capture proceeding.")

def get_social_media_text(soup: BeautifulSoup, base_url: str) -> str:
    final_social_text = ""
    social_domains_map = {
        'twitter': {'regex': r'(twitter|x)\.com', 'patterns': [r'twitter', r'x-twitter', r'tweet', r'fa-x-twitter', r'fa-twitter', r'icon-twitter']},
        'linkedin': {'regex': r'linkedin\.com', 'patterns': [r'linkedin', r'fa-linkedin', r'icon-linkedin']},
        'facebook': {'regex': r'facebook\.com', 'patterns': [r'facebook', r'fb', r'fa-facebook', r'icon-facebook']},
        'instagram': {'regex': r'instagram\.com', 'patterns': [r'instagram', r'insta', r'fa-instagram', r'icon-instagram']},
        'youtube': {'regex': r'youtube\.com', 'patterns': [r'youtube', r'yt', r'fa-youtube', r'icon-youtube']}
    }

    with httpx.Client(follow_redirects=True, headers={"User-Agent": get_random_user_agent()}) as social_client:
        for platform, info in social_domains_map.items():
            domain_regex = re.compile(info['regex'], re.IGNORECASE)
            id_patterns = [re.compile(p, re.IGNORECASE) for p in info['patterns']]
            
            candidate_tags = []
            
            # First, search within common social media containers (footers, headers, navs, specific divs)
            # This helps narrow down the search and avoid false positives from main content.
            # Look for common class names like 'social', 'footer', 'header', 'nav', 'contact', 'follow', 'icons'
            for container_tag in soup.find_all(
                ['footer', 'header', 'nav', 'div', 'ul', 'p'],
                class_=re.compile(r'(social|footer|header|contact|follow|icons|menu)', re.IGNORECASE)
            ):
                for a_tag in container_tag.find_all('a', href=True):
                    candidate_tags.append(a_tag)

            # If still no candidates found in specific containers, broaden the search to all a tags
            if not candidate_tags:
                 for a_tag in soup.find_all('a', href=True):
                    candidate_tags.append(a_tag)

            unique_good_links = set() # Use a set to avoid duplicate URLs

            for a_tag in candidate_tags:
                href = a_tag.get('href', '')
                aria_label = a_tag.get('aria-label', '').lower()
                title = a_tag.get('title', '').lower()
                text = a_tag.get_text(" ", strip=True).lower() # Also check link text

                is_relevant_link = False

                # 1. Check for direct domain match in href
                if domain_regex.search(href):
                    is_relevant_link = True
                
                # 2. Check aria-label, title, or link text for platform keywords
                elif any(p.search(aria_label) for p in id_patterns) or \
                     any(p.search(title) for p in id_patterns) or \
                     any(p.search(text) for p in id_patterns):
                    is_relevant_link = True

                # 3. Check class attributes of the <a> tag itself for platform keywords
                link_classes = ' '.join(a_tag.get('class', [])).lower()
                if any(p.search(link_classes) for p in id_patterns):
                    is_relevant_link = True

                # 4. Check class attributes/alt text of child <i> or <img> tags for platform keywords
                child_icon = a_tag.find(['i', 'img', 'svg']) # Added SVG
                if child_icon:
                    child_classes = ' '.join(child_icon.get('class', [])).lower()
                    child_alt = child_icon.get('alt', '').lower()
                    if any(p.search(child_classes) for p in id_patterns) or \
                       any(p.search(child_alt) for p in id_patterns):
                        is_relevant_link = True

                if is_relevant_link:
                    full_url = urljoin(base_url, href)
                    # Final validation: Ensure the resolved URL actually points to the correct social domain
                    if domain_regex.search(full_url) and \
                       'intent' not in href and 'share' not in href and \
                       (platform != 'instagram' or '/p/' not in href): # Filter Instagram short links
                        unique_good_links.add(full_url)
            
            good_links_list = sorted(list(unique_good_links), key=len)

            if not good_links_list:
                log("warn", f"Found {platform.capitalize()} candidate links, but none were relevant or resolved to the correct domain.")
                continue

            best_url = good_links_list[0] # Shorter URL is usually the profile base
            
            log("info", f"Found and scraping best {platform.capitalize()} link: {best_url}")
            
            try:
                res = social_client.get(best_url, timeout=20)
                if res.is_success:
                    social_soup = BeautifulSoup(res.text, "html.parser")
                    # Clean the social media page content
                    for tag in social_soup(["script", "style", "nav", "footer", "header", "aside"]): 
                        tag.decompose()
                    final_social_text += f"\n\n--- Social Media Content ({platform.capitalize()}) ---\n" + social_soup.get_text(" ", strip=True)[:2000]
                    log("info", f"Successfully scraped content from {platform.capitalize()} link: {best_url}")
                else:
                    log("warn", f"Request to {best_url} failed with status: {res.status_code}")
            except Exception as e:
                log("warn", f"Failed to scrape {platform.capitalize()} from {best_url}: {e}")
                
    return final_social_text

def find_best_corporate_portal(discovered_links: List[Tuple[str, str]], initial_url: str) -> Optional[str]:
    log("info", "Searching for a better corporate portal...")
    best_candidate = None
    highest_score = 0
    initial_root = _get_sld(initial_url)
    initial_netloc = urlparse(initial_url).netloc

    for link_url, link_text in discovered_links:
        if "http" in link_url and _get_sld(link_url) == initial_root and urlparse(link_url).netloc != initial_netloc:
            score = score_link(link_url, link_text)
            if score > highest_score:
                highest_score = score
                best_candidate = link_url
    
    if highest_score > 15:
        log("info", f"High-quality portal found with score {highest_score}. Pivoting to: {best_candidate}")
        return best_candidate
    else:
        log("info", "No high-quality corporate portal found. Continuing with the initial URL.")
        return None

def discover_links_from_sitemap(homepage_url: str) -> Optional[List[Tuple[str, str]]]:
    log("info", "Attempting to discover links from sitemap...")
    sitemap_url = urljoin(homepage_url, "/sitemap.xml")
    try:
        response = httpx.get(sitemap_url, headers={"User-Agent": get_random_user_agent()}, follow_redirects=True, timeout=20)
        response.raise_for_status()
        final_url = str(response.url)
        log("info", f"Sitemap fetch successful. Final URL: {final_url}")

        content = response.content
        namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        root = ET.fromstring(content)

        if root.tag.endswith('sitemapindex'):
            log("info", "Sitemap index found. Searching for the best page-sitemap...")
            sitemaps = [elem.text for elem in root.findall('sm:sitemap/sm:loc', namespace)]

            priority_keywords = ['page', 'post', 'company', 'about', 'article']
            best_sitemap_url = None
            for keyword in priority_keywords:
                for sm_url in sitemaps:
                    if keyword in sm_url:
                        best_sitemap_url = sm_url
                        break
                if best_sitemap_url: break

            if not best_sitemap_url and sitemaps:
                best_sitemap_url = sitemaps[0] # Fallback to the first sitemap if no priority keywords found
            
            if best_sitemap_url:
                log("info", f"Fetching prioritized sub-sitemap: {best_sitemap_url}")
                response = httpx.get(best_sitemap_url, headers={"User-Agent": get_random_user_agent()}, follow_redirects=True, timeout=20)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            else:
                log("warn", "No sitemap URLs found in sitemap index.")
                return None

        urls = [elem.text for elem in root.findall('sm:url/sm:loc', namespace)]
        if not urls:
            return None

        log("info", f"Found {len(urls)} links in sitemap.")
        return [(url, url.split('/')[-1].replace('-', ' ')) for url in urls]
    except Exception as e:
        log("warn", f"Sitemap not found or failed to parse: {e}")
        return None

def discover_links_from_html(html: str, base_url: str) -> List[Tuple[str, str]]:
    """Extracts links from raw HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    all_links_found = 0
    
    for a in soup.find_all("a", href=True):
        all_links_found += 1
        href_raw = a.get("href")
        if not href_raw: 
            continue
        
        href = _sanitize_href(href_raw)
        link_url = urljoin(base_url, href)
        
        # Log what we're checking
        if all_links_found <= 5:  # Log first 5 for debugging
            log("debug", f"Found link: {href_raw} -> {link_url}")
        
        if _is_same_brand_domain(base_url, link_url):
            links.append((link_url, a.get_text(strip=True)))
    
    log("info", f"HTML link discovery: Found {all_links_found} total links, {len(links)} from same domain")
    
    if all_links_found == 0:
        log("warn", "No <a> tags found in HTML. This might be a JavaScript-rendered site.")
        # Log a snippet of the HTML for debugging
        log("debug", f"HTML snippet (first 500 chars): {html[:500]}")
    
    return links


MEMORABILITY_KEYS_PROMPTS = {
    "Emotion": "Analyze the **Emotion** key. This is the primary key; without it, nothing is memorable.\n- **Your analysis must cover:** How the brand connects with audiences on an emotional level. Does it evoke warmth, trust, joy, or admiration? Does it use meaningful experiences, human stories, or mission-driven language? Is there a clear emotional reward for the user?",
    "Attention": "Analyze the **Attention** key. This is a stimulus key.\n- **Your analysis must cover:** How the brand stands out and sustains interest. Evaluate its distinctiveness. Does it use surprising visuals or headlines? Does it create an authentic and engaging journey for the user, avoiding clichés and overuse of calls to action?",
    "Story": "Analyze the **Story** key. This is a stimulus key.\n- **Your analysis must cover:** The clarity and power of the brand's narrative. Is there an authentic story that explains who the brand is and what it promises? Does this story build trust and pique curiosity more effectively than just facts and figures alone?",
    "Involvement": "Analyze the **Involvement** key. This is a stimulus key.\n- **Your analysis must cover:** How the brand makes the audience feel like active participants. Does it connect to what is meaningful for them? Does it foster a sense of community or belonging? Does it makes people feel included and empowered?",
    "Repetition": "Analyze the **Repetition** key. This is a reinforcement key.\n- **Your analysis must cover:** The strategic reuse of brand elements. Are key symbols, taglines, colors, or experiences repeated consistently across touchpoints to reinforce memory and create new associations? Is this repetition thoughtful, or does it risk overexposure?",
    "Consistency": "Analyze the **Consistency** key. This is a reinforcement key.\n- **Your analysis must cover:** The coherence of the brand across all touchpoints. Do the tone, message, and design feel aligned? Does this create a sense of familiarity, allowing the user's brain to recognize patterns and anticipate what to expect?"
}

def call_openai_for_synthesis(corpus):
    log("info", "Synthesizing brand overview...")
    try:
        synthesis_prompt = f"Analyze the following text from a company's website and social media. Provide a concise, one-paragraph summary of the brand's mission, tone, and primary offerings. This summary will be used as context for further analysis.\n\n---\n{corpus}\n---"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": synthesis_prompt}], temperature=0.2)
        return response.choices[0].message.content
    except Exception as e:
        log("error", f"AI synthesis failed: {e}")
        raise

def analyze_memorability_key(key_name, prompt_template, text_corpus, homepage_screenshot_b64, brand_summary):
    log("info", f"Analyzing key: {key_name}")
    try:
        content = [{"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"}, {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"}]
        if homepage_screenshot_b64:
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{homepage_screenshot_b64}"}})
        
        system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
        {prompt_template}

        **SCORING GUIDELINES:**
        You MUST provide a numerical score from 0 to 5 based on the following rubric:
        - **0:** The principle is completely absent or highly detrimental.
        - **1:** The principle is present but extremely weak; barely noticeable or inconsistent.
        - **2:** The principle is somewhat present but weak; significant flaws or missed opportunities.
        - **3:** The principle is adequately applied; meets basic standards but not outstanding.
        - **4:** The principle is strong and consistently applied; a clear asset to the brand.
        - **5:** The principle is exceptional; a textbook example of brand excellence in this area.

        Your response MUST be a JSON object with "score", "analysis", "evidence", "confidence", "confidence_rationale", and "recommendation" keys. The "score" MUST be an integer between 0 and 5.
        The "confidence" score should be an integer from 0 to 100 representing your certainty in this analysis.
        """
        
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}], response_format={"type": "json_object"}, temperature=0.3)
        result_json = json.loads(response.choices[0].message.content)
        validate_ai_response(result_json, ["score", "analysis", "evidence", "confidence", "confidence_rationale", "recommendation"])
        # Validate that the score is within the 0-5 range
        if not (0 <= result_json.get("score", -1) <= 5):
            raise ValueError(f"AI returned score {result_json.get('score')} which is not in the 0-5 range.")
        return key_name, result_json
    except Exception as e:
        log("error", f"LLM analysis failed for key '{key_name}': {e}")
        raise

def call_openai_for_executive_summary(all_analyses):
    log("info", "Generating Executive Summary...")
    try:
        analyses_text = "\n\n".join([f"Key: {data['key']}\nScore: {data['analysis']['score']}\nAnalysis: {data['analysis']['analysis']}" for data in all_analyses])
        summary_prompt = f"You are a senior brand strategist delivering a final executive summary. Based on the following six key analyses, please provide:\n1. **Overall Summary:** A brief, high-level overview.\n2. **Key Strengths:** Identify the 2-3 strongest keys.\n3. **Primary Weaknesses:** Identify the 2-3 weakest keys.\n4. **Strategic Focus:** State the single most important key to focus on.\n---\n{analyses_text}\n---"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": summary_prompt}], temperature=0.3)
        return response.choices[0].message.content
    except Exception as e:
        log("error", f"AI summary failed: {e}")
        raise

def capture_screenshots_playwright(urls):
    results = []
    log("info", f"Starting screenshot capture for {len(urls)} URLs.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=get_random_user_agent())
        page = context.new_page()
        for url in urls[:4]: # Limit to 4 screenshots as per original logic
            try:
                if any(urlparse(url).path.lower().endswith(ext) for ext in CONFIG["ignored_extensions"]):
                    log("info", f"Ignoring non-HTML link for screenshot: {url}")
                    continue
                log("info", f"Navigating to {url}")
                page.goto(url, wait_until="load", timeout=90000)
                prepare_page_for_capture(page)
                img_bytes = page.screenshot(full_page=True, type="jpeg", quality=70)
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                uid = str(uuid.uuid4())
                SHARED_CACHE[uid] = b64
                results.append({"id": uid, "url": url})
                log("info", f"Successfully captured {url}")
            except Exception as e:
                log("error", f"Failed to capture screenshot for {url}: {e}")
        browser.close()
    return results

def validate_ai_response(response, required_keys):
    if not all(key in response for key in required_keys):
        raise ValueError(f"Invalid AI response: Missing keys. Expected keys: {required_keys}")

def extract_relevant_text(soup: BeautifulSoup) -> str:
    main_content = soup.find("main") or soup.find("article") or soup.find("div", role="main")
    if main_content:
        log("info", "Found main content container, extracting all text from it.")
        return main_content.get_text(" ", strip=True)
    else:
        log("warn", "No <main> content container found, falling back to specific tag extraction.")
        relevant_tags = soup.find_all(["p", "h1", "h2", "h3", "li", "span"])
        return " ".join(tag.get_text(" ", strip=True) for tag in relevant_tags)

def run_full_scan_stream(url: str, cache: dict):
    circuit_breaker = CircuitBreaker(failure_threshold=CONFIG["circuit_breaker_threshold"])
    try:
        yield {'type': 'status', 'message': 'Step 1/5: Initializing scan & finding corporate portal...'}
        initial_url = _clean_url(url)
        
        # --- PHASE 1: CONFIRM THE CORRECT DOMAIN ---
        log("info", f"Starting scan at initial URL: {initial_url}")
        try:
            _, initial_html = fetch_page_content_robustly(initial_url)
            if not initial_html: raise Exception("Could not fetch initial URL content.")
        except Exception as e:
            log("error", f"Failed to fetch the initial URL: {e}")
            yield {'type': 'error', 'message': f'Failed to fetch the initial URL: {e}'}
            return

        initial_soup = BeautifulSoup(initial_html, "html.parser")
        initial_links = discover_links_from_html(initial_html, initial_url)

        corporate_portal_url = find_best_corporate_portal(initial_links, initial_url)
        homepage_url = _clean_url(corporate_portal_url) if corporate_portal_url else initial_url
        log("info", f"Confirmed scan homepage: {homepage_url}")

        # --- PHASE 2: DISCOVER ALL LINKS FROM THE CONFIRMED DOMAIN ---
        # Fetch homepage content again (potentially for the pivot URL)
        # and get screenshot (needed for AI later)
        try:
            homepage_screenshot_b64, homepage_html = fetch_page_content_robustly(homepage_url, take_screenshot=True)
            if not homepage_html: raise Exception("Could not fetch homepage content for link discovery and screenshot.")
        except Exception as e:
            log("error", f"Failed to fetch homepage URL for link discovery/screenshot: {e}")
            yield {'type': 'error', 'message': f'Failed to fetch homepage URL for link discovery/screenshot: {e}'}
            return

        # Attempt sitemap first
        discovered_links = discover_links_from_sitemap(homepage_url)
        
        if not discovered_links:
            log("warn", "Sitemap failed. Falling back to robust homepage HTML scrape for link discovery.")
            discovered_links = discover_links_from_html(homepage_html, homepage_url) # Use the already fetched homepage_html
            
        if not discovered_links: 
            log("warn", f"No links discovered from {homepage_url}. Proceeding with homepage analysis only.")
            # Instead of failing, continue with just the homepage
            discovered_links = [(homepage_url, "Homepage")]
            yield {'type': 'status', 'message': 'Warning: Could not discover additional pages. Analyzing homepage only.'}

        if homepage_screenshot_b64:
            image_id = str(uuid.uuid4())
            cache[image_id] = homepage_screenshot_b64
            yield {'type': 'screenshot_ready', 'id': image_id, 'url': homepage_url}

        homepage_soup = BeautifulSoup(homepage_html, "html.parser")
        social_corpus = get_social_media_text(homepage_soup, homepage_url)
        yield {'type': 'status', 'message': 'Social media text captured.' if social_corpus else 'No social media links found.'}

        yield {'type': 'status', 'message': 'Scoring and ranking all discovered links...'}
        scored_links = []
        unique_urls_for_scoring = set()
        for link_url, link_text in discovered_links:
            cleaned_url = _clean_url(link_url)
            if cleaned_url not in unique_urls_for_scoring:
                unique_urls_for_scoring.add(cleaned_url)
                score = score_link(cleaned_url, link_text)
                # Only include links with a positive score in the candidates, effectively filtering out generic negatives early
                if score > 0: 
                    scored_links.append({"url": cleaned_url, "text": link_text, "score": score})
        
        scored_links.sort(key=lambda x: x["score"], reverse=True)
        log("info", "Top 10 most relevant links found:", scored_links[:10])

        priority_pages, found_urls = [], set()
        if homepage_url not in found_urls:
            priority_pages.append(homepage_url); found_urls.add(homepage_url)
        for link in scored_links:
            if len(priority_pages) >= 5: break # Limit number of pages to analyze deeply
            if link["url"] not in found_urls:
                priority_pages.append(link["url"]); found_urls.add(link["url"])
        
        log("info", "Final priority pages selected for analysis", priority_pages)

        other_pages_to_screenshot = [p for p in priority_pages if p != homepage_url]
        if other_pages_to_screenshot:
            yield {'type': 'status', 'message': 'Capturing visual evidence from key pages...'}
            # The capture_screenshots_playwright function already limits to 4, effectively taking screenshots
            # for up to the first 4 other priority pages, plus the homepage.
            for data in capture_screenshots_playwright(other_pages_to_screenshot):
                yield {'type': 'screenshot_ready', **data}
        
        yield {'type': 'status', 'message': 'Step 2/5: Analyzing key pages in parallel...'}
        other_pages_to_fetch = [p for p in priority_pages if p != homepage_url]
        page_html_map = {homepage_url: homepage_html} # Reuse homepage HTML already fetched
        if other_pages_to_fetch:
            try:
                parallel_results = fetch_all_pages(other_pages_to_fetch)
                if all(v is None for v in parallel_results.values()): raise Exception("All parallel page fetches failed.")
                page_html_map.update(parallel_results)
                circuit_breaker.record_success()
            except Exception as e:
                circuit_breaker.record_failure()
                raise e # Re-raise to fail early if too many fetch errors

        text_corpus = ""
        for page_url in priority_pages:
            page_html = page_html_map.get(page_url)
            if page_html:
                soup = BeautifulSoup(page_html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({page_url}) ---\n" + extract_relevant_text(soup)
        
        full_corpus = (text_corpus + social_corpus)[:40000] # Truncate to avoid excessive token usage

        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...'}
        brand_summary = call_openai_for_synthesis(full_corpus)
        
        yield {'type': 'status', 'message': 'Step 4/5: Performing detailed analysis...'}
        all_results = [] # This list will hold all individual key analysis results
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            try:
                key_name, result_json = analyze_memorability_key(key, prompt, full_corpus, homepage_screenshot_b64, brand_summary)
                # Assign a unique ID for this analysis result for feedback tracking
                analysis_uid = str(uuid.uuid4())
                result_json['analysis_id'] = analysis_uid 
                circuit_breaker.record_success()
            except Exception as e:
                circuit_breaker.record_failure()
                log("error", f"Analysis of key '{key}' failed. Circuit breaker status: {circuit_breaker.failures} failures. Error: {e}")
                # We can choose to yield an error for this key or simply skip it
                # For now, let's yield an error for the key and continue if possible
                yield {'type': 'result_error', 'key': key_name, 'message': f"Analysis failed: {e}"}
                continue # Continue to next key if one fails, but log it.
            
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj
        
        yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...'}
        # Pass the correctly named variable 'all_results'
        summary_text = call_openai_for_executive_summary(all_results) 
        yield {'type': 'summary', 'text': summary_text}
        
        quantitative_summary = summarize_results(all_results)
        yield {'type': 'quantitative_summary', 'data': quantitative_summary}
        
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        log("error", f"The main stream failed: {e}")
        import traceback
        traceback.print_exc() # Print full traceback for debugging
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}

if __name__ == '__main__':
    target_url = "https://www.gsk.com"
    log("info", f"--- Starting Full Scan for: {target_url} ---")
    shared_cache = {}
    try:
        for result in run_full_scan_stream(target_url, shared_cache):
            log("STREAM", f"Received event: {result.get('type')}")
            if result.get('type') == 'error':
                log("FATAL", "Scan stopped due to a critical error.")
                break
    except Exception as e:
        log("CRITICAL", f"An unhandled exception occurred during the scan: {e}")
    log("info", "--- Scan Process Finished ---")
