print(">>> RUNNING FIXED SCANNER VERSION <<<")
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

# Use ProcessPoolExecutor for true isolation and reliability in parallel tasks
from concurrent.futures import ProcessPoolExecutor

from playwright.sync_api import sync_playwright
from typing import Optional, Dict, List, Tuple

# --- START: HELPER FUNCTIONS ---

def log(level, message, data=None):
    import json
    formatted_message = f"[{level.upper()}] {message}"
    print(formatted_message, flush=True)
    if data:
        details_message = f"[DETAILS] {json.dumps(data, indent=2, ensure_ascii=False)}"
        print(details_message, flush=True)

def _get_sld(url: str) -> str:
    """Extracts the Second-Level Domain (e.g., 'google.com', 'google.co.uk')."""
    try:
        netloc = urlparse(url).netloc
        if not netloc:
            return ""
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        parts = netloc.split('.')
        return ".".join(parts[-2:]) if len(parts) >= 2 else netloc
    except Exception as e:
        log("error", f"Failed to extract SLD: {e}")
        return ""

def _get_root_word(url: str) -> str:
    """Extracts the central 'word' of a domain (e.g., 'google' from 'www.google.co.uk')."""
    try:
        netloc = urlparse(url).netloc
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        parts = netloc.split('.')
        if len(parts) > 2 and parts[-2] in ('co', 'com', 'org', 'net', 'gov', 'edu'):
            return parts[-3]
        return parts[-2] if len(parts) >= 2 else parts[0]
    except Exception:
        return ""

def _is_same_root_word_domain(url1: str, url2: str) -> bool:
    """Checks if two URLs share the same core domain word (e.g., 'omv.at' and 'omv.com')."""
    root1 = _get_root_word(url1)
    if not root1:
        return False
    return root1 == _get_root_word(url2)

# --- END: HELPER FUNCTIONS ---

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
    # Account Management
    r"\b(log(in|out)?|sign(in|up)|register|account|my-account)\b", r"\b(anmelden|abmelden|registrieren|konto)\b", r"\b(iniciar-sesion|cerrar-sesion|crear-cuenta|cuenta)\b",
    
    # Legal & Compliance
    r"\b(impressum|imprint|legal|disclaimer|compliance|datenschutz|data-protection|privacy|terms|cookies?|policy|governance|bylaws|tax[-_]strategy)\b", r"\b(agb|bedingungen|rechtliches|politica-de-privacidad|aviso-legal|terminos|condiciones)\b",
    
    # Subscriptions & Marketing
    r"\b(newsletter|subscribe|subscription|unsubscribe|boletin|suscripcion|darse-de-baja)\b",
    
    # Human Resources & Careers
    r"\b(jobs?|career(s)?|vacancies|internships?|apply|karriere|stellenangebote|bewerbung|praktikum|empleo|trabajo|vacantes|postulaciones|reclutamiento)\b",
    
    # E-commerce & Shopping
    r"\b(basket|cart|checkout|shop|store|ecommerce|wishlist|warenkorb|kaufen|bestellen|einkaufen|carrito|tienda|comprar|pago|pedido)\b",
    
    # Website Tools & Technical Pages
    r"\b(calculator|tool|search|filter|compare|rechner|suche|vergleich|calculadora|buscar|comparar|filtro)\b",
    r"\b(404|not-found|error|redirect|sitemap|robots|tracking|rss|weiterleitung|umleitung|redireccion|mapa-del_sitio|seguimiento)\b",
    
    # Customer Support & Help
    r"\b(faq(s)?|help|support|contact|customer[-_]service|knowledge[-_]base)\b",
    
    # Developer & Partner Portals
    r"\b(api|developer(s)?|sdk|docs|documentation|partner(s)?|supplier(s)?|vendor(s)?|affiliate(s)?|portal)\b",
    
    # Location Finders
    r"\b(locations?|store[-_]finder|dealer[-_]locator|find[-_]a[-_]store)\b",

    # Media & Asset Libraries
    r"\b(gallery|media[-_]kit|brand[-_]assets)\b",

    # Accessibility
    r"\b(accessibility|wcag)\b",

    # Press Releases & Content Marketing (often not core brand)
    r"\b(press[-_]release(s)?)\b",
    r"\b(news|events|blogs?|articles?|updates?|media|press|spotlight|stories)\b",
    r"\b(whitepapers?|webinars?|case[-_]stud(y|ies)|customer[-_]stor(y|ies))\b",
    r"\b(resources?|insights?|downloads?)\b",
    
    # Investor Relations & Financial Reporting
    r"\b(takeover|capital[-_]increase|webcast|publication|report|finances?|annual[-_]report|quarterly[-_]report|balance[-_]sheet|proxy|prospectus|statement|filings|investor[-_]deck|shareholder(s)?|stock|sec[-_]filing(s)?|financials?)\b"
]

LINK_SCORE_MAP = {
    "critical": {"patterns": [r"\b(brand|purpose|values|strategy|products|services|operations)\b"], "score": 30},
    "high": {"patterns": [r"company", r"about", r"story", r"mission", r"vision", r"culture", r"who[-_]we[-_]are", r"what[-_]we[-_]do", r"investors?"], "score": 20},
    "medium": {"patterns": [r"solutions", r"pipeline", r"research", r"innovation", r"capabilities", r"industries", r"technology"], "score": 10},
    "low": {"patterns": [r"leadership", r"team", "management", r"history", r"sustainability", r"responsibility", r"esg"], "score": 5},
    "language": {"patterns": [r"/en/", r"lang=en"], "score": 10},
    "negative": {"patterns": NEGATIVE_REGEX, "score": -50}
}

def score_link(link_url: str, link_text: str) -> int:
    score = 0
    lower_text = link_text.lower()
    combined_text = f"{link_url} {lower_text}"

    language_names = ['english', 'español', 'deutsch', 'français', 'português', 'en', 'es', 'de', 'fr', 'pt']
    if lower_text in language_names:
        score -= 20

    tier_order = ["critical", "high", "medium", "low"]
    assigned_score = False
    for tier_name in tier_order:
        tier = LINK_SCORE_MAP[tier_name]
        for pattern in tier["patterns"]:
            if re.search(pattern, combined_text):
                score += tier["score"]
                assigned_score = True
                break
        if assigned_score:
            break

    if re.search(LINK_SCORE_MAP['language']['patterns'][0], combined_text) or \
       re.search(LINK_SCORE_MAP['language']['patterns'][1], combined_text):
        score += LINK_SCORE_MAP['language']['score']

    path_depth = link_url.count('/') - 2
    if path_depth <= 2: 
        score += 5

    if any(link_url.lower().endswith(ext) for ext in CONFIG["ignored_extensions"]): 
        score -= 100
        
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
        if html and html.strip().startswith('<'):
            log("info", "Scrapfly returned valid HTML content.")
            return screenshot, html
        else:
            if not html:
                log("warn", f"Scrapfly returned empty content for {url}, falling back to Playwright.")
            else:
                log("warn", f"Scrapfly returned non-HTML content for {url}, falling back to Playwright.")
            html = fetch_html_with_playwright(url)
            return None, html
    except Exception as e:
        log("warn", f"Scrapfly failed for {url} with error: {e}. Falling back to Playwright.")
        html = fetch_html_with_playwright(url)
        return None, html

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
        "feedback_type": feedback_type,
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
    """Clean and validate URL with security checks."""
    url = url.strip()
    if not url.startswith(("http://", "https://")): 
        url = "https://" + url
    return url.split("#")[0]

def _validate_url(url: str) -> tuple[bool, str]:
    """Comprehensive URL validation with security checks.
    
    Returns:
        tuple: (is_valid, error_message)
    """
    import ipaddress
    
    if not url or len(url) > 2048:  # Reasonable URL length limit
        return False, "URL is empty or too long (max 2048 characters)"
    
    try:
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in ['http', 'https']:
            return False, "Only HTTP and HTTPS URLs are allowed"
        
        # Check if hostname exists
        if not parsed.netloc:
            return False, "Invalid URL: missing hostname"
        
        # Extract hostname without port
        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid hostname"
        
        # Block private/internal IP addresses (SSRF protection)
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, "Private/internal IP addresses are not allowed"
        except ValueError:
            # Not an IP address, continue with hostname validation
            pass
        
        # Block dangerous domains
        blocked_domains = {
            'localhost', '127.0.0.1', '0.0.0.0', '::1',
            'metadata.google.internal',  # GCP metadata
            '169.254.169.254',  # AWS/Azure metadata
            'kubernetes.default.svc.cluster.local'  # Kubernetes internal
        }
        
        if hostname.lower() in blocked_domains:
            return False, f"Blocked domain: {hostname}"
        
        # Block internal TLDs
        if hostname.endswith(('.local', '.internal', '.test')):
            return False, "Internal domain suffixes are not allowed"
        
        return True, ""
        
    except Exception as e:
        return False, f"URL validation error: {str(e)}"

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
            pass
    if not consent_clicked: log("info", "No common consent banner found to click.")
    
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
            
            for container_tag in soup.find_all(
                ['footer', 'header', 'nav', 'div', 'ul', 'p'],
                class_=re.compile(r'(social|footer|header|contact|follow|icons|menu)', re.IGNORECASE)
            ):
                for a_tag in container_tag.find_all('a', href=True):
                    candidate_tags.append(a_tag)

            if not candidate_tags:
                 for a_tag in soup.find_all('a', href=True):
                    candidate_tags.append(a_tag)

            unique_good_links = set()

            for a_tag in candidate_tags:
                href = a_tag.get('href', '')
                aria_label = a_tag.get('aria-label', '').lower()
                title = a_tag.get('title', '').lower()
                text = a_tag.get_text(" ", strip=True).lower()

                is_relevant_link = False

                if domain_regex.search(href):
                    is_relevant_link = True
                
                elif any(p.search(aria_label) for p in id_patterns) or \
                     any(p.search(title) for p in id_patterns) or \
                     any(p.search(text) for p in id_patterns):
                    is_relevant_link = True

                link_classes = ' '.join(a_tag.get('class', [])).lower()
                if any(p.search(link_classes) for p in id_patterns):
                    is_relevant_link = True

                child_icon = a_tag.find(['i', 'img', 'svg'])
                if child_icon:
                    child_classes = ' '.join(child_icon.get('class', [])).lower()
                    child_alt = child_icon.get('alt', '').lower()
                    if any(p.search(child_classes) for p in id_patterns) or \
                       any(p.search(child_alt) for p in id_patterns):
                        is_relevant_link = True

                if is_relevant_link:
                    full_url = urljoin(base_url, href)
                    if domain_regex.search(full_url) and \
                       'intent' not in href and 'share' not in href and \
                       (platform != 'instagram' or '/p/' not in href):
                        unique_good_links.add(full_url)
            
            good_links_list = sorted(list(unique_good_links), key=len)

            if not good_links_list:
                log("warn", f"Found {platform.capitalize()} candidate links, but none were relevant or resolved to the correct domain.")
                continue

            best_url = good_links_list[0]
            
            log("info", f"Found and scraping best {platform.capitalize()} link: {best_url}")
            
            try:
                res = social_client.get(best_url, timeout=20)
                if res.is_success:
                    social_soup = BeautifulSoup(res.text, "html.parser")
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
    initial_root_word = _get_root_word(initial_url)
    initial_netloc = urlparse(initial_url).netloc

    if not initial_root_word:
        log("warn", "Could not determine initial root word, cannot pivot.")
        return None

    for link_url, link_text in discovered_links:
        if "http" in link_url and _get_root_word(link_url) == initial_root_word and urlparse(link_url).netloc != initial_netloc:
            score = score_link(link_url, link_text)
            if score > highest_score:
                highest_score = score
                best_candidate = link_url
    
    if highest_score > 25:
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
                best_sitemap_url = sitemaps[0]
            
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
        
        if all_links_found <= 5:
            log("debug", f"Found link: {href_raw} -> {link_url}")
        
        if _is_same_root_word_domain(base_url, link_url):
            links.append((link_url, a.get_text(strip=True)))
    
    log("info", f"HTML link discovery: Found {all_links_found} total links, {len(links)} from same root domain")
    
    if all_links_found == 0:
        log("warn", "No <a> tags found in HTML. This might be a JavaScript-rendered site.")
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
        for url in urls[:4]:
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

def summarize_results(all_results: list) -> dict:
    """Analyzes memorability analysis results and provides quantitative summary."""
    if not all_results:
        return {"keys_analyzed": 0, "strong_keys": 0, "weak_keys": 0}
    
    summary = {"keys_analyzed": len(all_results), "strong_keys": 0, "weak_keys": 0}
    for result in all_results:
        if 'analysis' in result and 'score' in result['analysis']:
            score = result["analysis"]["score"]
            if score >= 4:  # Strong performance (4-5 on 0-5 scale)
                summary["strong_keys"] += 1
            elif score <= 2:  # Weak performance (0-2 on 0-5 scale)
                summary["weak_keys"] += 1
            # Scores of 3 are considered "adequate" and not counted as strong/weak
    
    return summary

def run_full_scan_stream(url: str, cache: dict):
    circuit_breaker = CircuitBreaker(failure_threshold=CONFIG["circuit_breaker_threshold"])
    try:
        # Validate URL before processing
        initial_url = _clean_url(url)
        is_valid, error_msg = _validate_url(initial_url)
        if not is_valid:
            log("error", f"URL validation failed: {error_msg}")
            yield {'type': 'error', 'message': f'Invalid URL: {error_msg}'}
            return

        yield {'type': 'status', 'message': 'Step 1/5: Discovering all brand pages...'}
        log("info", f"Starting scan at validated URL: {initial_url}")

        # --- Phase 1: Initial Domain Discovery ---
        try:
            _, homepage_html = fetch_page_content_robustly(initial_url)
            if not homepage_html: raise Exception("Could not fetch initial URL content.")
        except Exception as e:
            log("error", f"Failed to fetch the initial URL: {e}")
            yield {'type': 'error', 'message': f'Failed to fetch the initial URL: {e}'}
            return

        all_discovered_links = discover_links_from_html(homepage_html, initial_url)
        sitemap_links = discover_links_from_sitemap(initial_url)
        if sitemap_links:
            all_discovered_links.extend(sitemap_links)

        # --- Phase 2: High-Value Subdomain Discovery ---
        subdomain_portal_url = find_best_corporate_portal(all_discovered_links, initial_url)
        if subdomain_portal_url:
            log("info", f"Found high-value subdomain: {subdomain_portal_url}. Scanning it for additional links.")
            try:
                _, subdomain_html = fetch_page_content_robustly(subdomain_portal_url)
                if subdomain_html:
                    subdomain_links = discover_links_from_html(subdomain_html, subdomain_portal_url)
                    all_discovered_links.extend(subdomain_links)
            except Exception as e:
                log("warn", f"Could not fetch high-value subdomain {subdomain_portal_url}: {e}")

        # --- Phase 3: Scoring and Analysis ---
        homepage_url = initial_url
        log("info", f"Confirmed scan homepage: {homepage_url}")

        if not all_discovered_links:
            log("warn", f"No links discovered from {homepage_url}. Proceeding with homepage analysis only.")
            all_discovered_links = [(homepage_url, "Homepage")]
            yield {'type': 'status', 'message': 'Warning: Could not discover additional pages. Analyzing homepage only.'}

        try:
            homepage_screenshot_b64, final_homepage_html = fetch_page_content_robustly(homepage_url, take_screenshot=True)
            if homepage_screenshot_b64:
                image_id = str(uuid.uuid4())
                cache[image_id] = homepage_screenshot_b64
                yield {'type': 'screenshot_ready', 'id': image_id, 'url': homepage_url}
        except Exception as e:
            log("warn", f"Could not take homepage screenshot: {e}")
            homepage_screenshot_b64 = None
            final_homepage_html = homepage_html

        homepage_soup = BeautifulSoup(final_homepage_html, "html.parser")
        social_corpus = get_social_media_text(homepage_soup, homepage_url)
        yield {'type': 'status', 'message': 'Social media text captured.' if social_corpus else 'No social media links found.'}

        yield {'type': 'status', 'message': 'Scoring and ranking all discovered links...'}
        scored_links = []
        unique_urls_for_scoring = set()
        for link_url, link_text in all_discovered_links:
            cleaned_url = _clean_url(link_url)
            if cleaned_url not in unique_urls_for_scoring:
                unique_urls_for_scoring.add(cleaned_url)
                score = score_link(cleaned_url, link_text)
                if score > 0: 
                    scored_links.append({"url": cleaned_url, "text": link_text, "score": score})
        
        scored_links.sort(key=lambda x: x["score"], reverse=True)
        log("info", "Top 10 most relevant links found:", scored_links[:10])

        priority_pages, found_urls = [], set()
        if homepage_url not in found_urls:
            priority_pages.append(homepage_url); found_urls.add(homepage_url)
        for link in scored_links:
            if len(priority_pages) >= 5: break
            if link["url"] not in found_urls:
                priority_pages.append(link["url"]); found_urls.add(link["url"])
        
        log("info", "Final priority pages selected for analysis", priority_pages)

        other_pages_to_screenshot = [p for p in priority_pages if p != homepage_url]
        if other_pages_to_screenshot:
            yield {'type': 'status', 'message': 'Capturing visual evidence from key pages...'}
            for data in capture_screenshots_playwright(other_pages_to_screenshot):
                yield {'type': 'screenshot_ready', **data}
        
        yield {'type': 'status', 'message': 'Step 2/5: Analyzing key pages...'}
        page_html_map = {homepage_url: final_homepage_html}
        
        other_pages_to_fetch = [p for p in priority_pages if p != homepage_url]
        with ProcessPoolExecutor(max_workers=4) as executor:
            future_to_url = {executor.submit(fetch_page_content_robustly, url): url for url in other_pages_to_fetch}
            for future in future_to_url:
                url = future_to_url[future]
                try:
                    _, html = future.result()
                    if html:
                        page_html_map[url] = html
                        circuit_breaker.record_success()
                    else:
                        log("warn", f"Parallel fetch for {url} returned no content.")
                        circuit_breaker.record_failure()
                except Exception as e:
                    log("error", f"Parallel fetch for {url} failed: {e}")
                    circuit_breaker.record_failure()

        text_corpus = ""
        for page_url in priority_pages:
            page_html = page_html_map.get(page_url)
            if page_html:
                soup = BeautifulSoup(page_html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({page_url}) ---\n" + extract_relevant_text(soup)
        
        full_corpus = (text_corpus + social_corpus)[:40000]

        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...'}
        brand_summary = call_openai_for_synthesis(full_corpus)
        
        yield {'type': 'status', 'message': 'Step 4/5: Performing detailed analysis...'}
        all_results = []
        for key, prompt in MEMORABILITY_KEYS_PROMPTS.items():
            yield {'type': 'status', 'message': f'Analyzing key: {key}...'}
            try:
                key_name, result_json = analyze_memorability_key(key, prompt, full_corpus, homepage_screenshot_b64, brand_summary)
                analysis_uid = str(uuid.uuid4())
                result_json['analysis_id'] = analysis_uid 
                circuit_breaker.record_success()
            except Exception as e:
                circuit_breaker.record_failure()
                log("error", f"Analysis of key '{key}' failed. Circuit breaker status: {circuit_breaker.failures} failures. Error: {e}")
                yield {'type': 'result_error', 'key': key_name, 'message': f"Analysis failed: {e}"}
                continue
            
            result_obj = {'type': 'result', 'key': key_name, 'analysis': result_json}
            all_results.append(result_obj)
            yield result_obj
        
        yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...'}
        summary_text = call_openai_for_executive_summary(all_results) 
        yield {'type': 'summary', 'text': summary_text}
        
        quantitative_summary = summarize_results(all_results)
        yield {'type': 'quantitative_summary', 'data': quantitative_summary}
        
        yield {'type': 'complete', 'message': 'Analysis finished.'}

    except Exception as e:
        log("error", f"The main stream failed: {e}")
        import traceback
        traceback.print_exc()
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