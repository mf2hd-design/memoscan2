print(">>> RUNNING FIXED SCANNER VERSION <<<")
import os
import re
import json
import base64
import uuid
import time
import signal
import gc
try:
    from defusedxml import ElementTree as ET
except ImportError:
    # SECURITY: Use safe XML parsing to prevent XXE attacks
    import xml.etree.ElementTree as ET_unsafe
    import warnings
    warnings.warn("defusedxml not available, using xml.etree.ElementTree with custom XXE protection", UserWarning)
    
    # Create a safe XML parser with XXE protection and robust error handling
    class SafeXMLParser:
        @staticmethod
        def fromstring(data):
            # Create parser with disabled external entity processing
            parser = ET_unsafe.XMLParser()
            # Robust XXE protection with proper error handling
            try:
                if hasattr(parser, 'parser') and parser.parser:
                    parser.parser.DefaultHandler = lambda data: None
                    parser.parser.ExternalEntityRefHandler = lambda *args: False
                else:
                    log("warn", "XML parser attributes not accessible, using basic protection")
            except AttributeError as e:
                log("warn", f"Could not configure XML parser security features: {e}")
            
            try:
                return ET_unsafe.fromstring(data, parser=parser)
            except ET_unsafe.ParseError as e:
                log("error", f"XML parsing failed: {e}")
                raise
            except Exception as e:
                log("error", f"Unexpected XML parsing error: {e}")
                raise
    
    ET = SafeXMLParser
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

def detect_primary_language(html_content: str) -> str:
    """Detect the primary language of a website from HTML content.
    
    Returns:
        str: Two-letter language code (e.g., 'en', 'de', 'es') or 'en' as fallback
    """
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Method 1: Check <html lang=""> attribute (most reliable)
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            lang = html_tag.get('lang')[:2].lower()
            # Validate it's a known language code
            if lang in ['en', 'de', 'es', 'fr', 'it', 'pt', 'ja', 'ko', 'zh', 'ru', 'nl', 'sv', 'da', 'no']:
                log("info", f"🌐 Detected primary language: {lang} (from html tag)")
                return lang
        
        # Method 2: Check meta content-language tag
        lang_meta = soup.find('meta', attrs={'http-equiv': 'content-language'})
        if lang_meta and lang_meta.get('content'):
            lang = lang_meta.get('content')[:2].lower()
            if lang in ['en', 'de', 'es', 'fr', 'it', 'pt', 'ja', 'ko', 'zh', 'ru', 'nl', 'sv', 'da', 'no']:
                log("info", f"🌐 Detected primary language: {lang} (from meta tag)")
                return lang
        
        # Method 3: Check for language-specific meta tags
        og_locale = soup.find('meta', attrs={'property': 'og:locale'})
        if og_locale and og_locale.get('content'):
            lang = og_locale.get('content')[:2].lower()
            if lang in ['en', 'de', 'es', 'fr', 'it', 'pt', 'ja', 'ko', 'zh', 'ru', 'nl', 'sv', 'da', 'no']:
                log("info", f"🌐 Detected primary language: {lang} (from og:locale)")
                return lang
        
        log("info", "🌐 No explicit language detected, defaulting to English")
        return 'en'  # Safe fallback
        
    except Exception as e:
        log("warn", f"Language detection failed: {e}, defaulting to English")
        return 'en'

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

# Scoring System Constants
SCORING_CONSTANTS = {
    "MIN_BUSINESS_SCORE": 5,        # Minimum score threshold for business relevance
    "LANGUAGE_PENALTY": 20,         # Penalty for language selection links
    "NEGATIVE_VETO_SCORE": -50,     # Penalty for negative pattern matches
    "LANGUAGE_BONUS": 10,           # Bonus for proper language links
    "PATH_DEPTH_THRESHOLD": 3,      # Path depth before penalties apply
    "PATH_DEPTH_PENALTY": 5,        # Penalty per extra path segment
    "FILE_EXTENSION_PENALTY": 100,  # Penalty for non-HTML file extensions
    "HIGH_VALUE_PORTAL_THRESHOLD": 25,  # Minimum score for high-value portal detection
    "CRITICAL_KEYWORD_PENALTY_REDUCTION": 2,  # Divisor for critical keyword path penalties
}

# Business Tier Scoring Hierarchy
BUSINESS_TIER_SCORES = {
    "identity": 40,    # Highest priority: brand, mission, values
    "strategy": 30,    # High priority: strategy, about, company
    "operations": 20,  # Medium priority: products, services
    "culture": 10,     # Lower priority: culture, sustainability
    "people": 5,       # Lowest priority: leadership, team
}
# --- END: CONFIGURATION AND CONSTANTS ---

# --- START: REGEX AND SCORING LOGIC ---
NEGATIVE_REGEX = [
    # Account Management
    r"\b(log(in|out)?|sign(in|up)|register|account|my-account)\b", r"\b(anmelden|abmelden|registrieren|konto)\b", r"\b(iniciar-sesion|cerrar-sesion|crear-cuenta|cuenta)\b",
    
    # Legal & Compliance
    r"\b(impressum|imprint|legal|disclaimer|compliance|datenschutz|data-protection|privacy|terms|cookies?|policy|governance|bylaws|tax[-_]strategy)\b", r"\b(agb|bedingungen|rechtliches|politica-de-privacidad|aviso-legal|terminos|condiciones)\b",
    r"\b(terms[-_]of[-_]sales?|conditions[-_]of[-_]sales?|terms[-_]of[-_]service|general[-_]conditions[-_]of[-_]sales?|general[-_]conditions)\b",

    # Website Tools & Overly Specific Content
    r"\b(finder|selector|database|catalog|category|categories)\b",
    
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

# Pre-compile regex patterns for performance
COMPILED_PATTERNS = {}

def _compile_patterns():
    """Pre-compile all regex patterns to improve performance."""
    global COMPILED_PATTERNS
    
    pattern_groups = {
        "identity": [r"\b(brand|purpose|values|mission|vision)\b"],
        "strategy": [r"\b(strategy|about|company|who[-_]we[-_]are)\b"],
        "operations": [r"\b(products|services|solutions|operations|what[-_]we[-_]do)\b"],
        "culture": [r"\b(story|culture|innovation|sustainability|responsibility|esg)\b"],
        "people": [r"\b(leadership|team|management|history)\b"],
        "language": [r"/en/", r"lang=en"],
        "negative": NEGATIVE_REGEX
    }
    
    for group_name, patterns in pattern_groups.items():
        COMPILED_PATTERNS[group_name] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

# Initialize compiled patterns
_compile_patterns()

LINK_SCORE_MAP = {
    "identity": {"patterns": COMPILED_PATTERNS["identity"], "score": BUSINESS_TIER_SCORES["identity"]},
    "strategy": {"patterns": COMPILED_PATTERNS["strategy"], "score": BUSINESS_TIER_SCORES["strategy"]},
    "operations": {"patterns": COMPILED_PATTERNS["operations"], "score": BUSINESS_TIER_SCORES["operations"]},
    "culture": {"patterns": COMPILED_PATTERNS["culture"], "score": BUSINESS_TIER_SCORES["culture"]},
    "people": {"patterns": COMPILED_PATTERNS["people"], "score": BUSINESS_TIER_SCORES["people"]},
    "language": {"patterns": COMPILED_PATTERNS["language"], "score": SCORING_CONSTANTS["LANGUAGE_BONUS"]},
    "negative": {"patterns": COMPILED_PATTERNS["negative"], "score": SCORING_CONSTANTS["NEGATIVE_VETO_SCORE"]}
}

def score_link(link_url: str, link_text: str, primary_language: str = 'en') -> Tuple[int, str]:
    score = 0
    rationale = []
    lower_text = link_text.lower()
    combined_text = f"{link_url} {lower_text}"

    # Language selection penalty
    language_names = ['english', 'español', 'deutsch', 'français', 'português', 'en', 'es', 'de', 'fr', 'pt']
    if lower_text in language_names:
        score -= SCORING_CONSTANTS["LANGUAGE_PENALTY"]

    # Contextual language penalty - penalize URLs that don't match the site's primary language
    lang_codes = {'/de/': 'de', '/es/': 'es', '/fr/': 'fr', '/it/': 'it', '/pt/': 'pt', '/ja/': 'ja', '/ko/': 'ko', '/zh/': 'zh', '/ru/': 'ru', '/nl/': 'nl'}
    for code, lang in lang_codes.items():
        if code in link_url and lang != primary_language:
            score -= 15
            rationale.append(f"Lang Mismatch: -15 ({lang}≠{primary_language})")
            break

    # --- Main Keyword Scoring (First Past the Post) ---
    tier_order = ["identity", "strategy", "operations", "culture", "people"]
    is_critical = False
    for tier_name in tier_order:
        tier = LINK_SCORE_MAP[tier_name] 
        for compiled_pattern in tier["patterns"]:
            if compiled_pattern.search(combined_text):
                score += tier["score"]
                rationale.append(f"Base: {tier['score']} ({tier_name})")
                if tier_name in ["identity", "strategy"]:
                    is_critical = True
                break
        if rationale:
            break

    # --- Negative Keyword Scoring (Always runs) ---
    for compiled_pattern in LINK_SCORE_MAP["negative"]["patterns"]:
        if compiled_pattern.search(combined_text):
            score += LINK_SCORE_MAP["negative"]["score"]
            rationale.append(f"Veto: {LINK_SCORE_MAP['negative']['score']}")
            break

    # --- Bonuses and Penalties ---
    language_patterns = LINK_SCORE_MAP['language']['patterns']
    for compiled_pattern in language_patterns:
        if compiled_pattern.search(combined_text):
            score += LINK_SCORE_MAP['language']['score']
            rationale.append(f"Lang: +{LINK_SCORE_MAP['language']['score']}")
            break

    try:
        path = urlparse(link_url).path
        # Properly calculate path depth by splitting on '/' and filtering empty segments
        path_segments = [segment for segment in path.split('/') if segment]
        path_depth = len(path_segments)
        
        if path_depth > SCORING_CONSTANTS["PATH_DEPTH_THRESHOLD"]:
            penalty = (path_depth - SCORING_CONSTANTS["PATH_DEPTH_THRESHOLD"]) * SCORING_CONSTANTS["PATH_DEPTH_PENALTY"]
            if is_critical:
                penalty //= SCORING_CONSTANTS["CRITICAL_KEYWORD_PENALTY_REDUCTION"]
            if penalty > 0:
                score -= penalty
                rationale.append(f"Depth: -{penalty}")
    except Exception:
        pass

    # File extension penalty
    if any(link_url.lower().endswith(ext) for ext in CONFIG["ignored_extensions"]): 
        score -= SCORING_CONSTANTS["FILE_EXTENSION_PENALTY"]
        
    return score, " ".join(rationale)
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
    log("info", f"🔍 SCRAPFLY REQUEST: {url} (Screenshot: {take_screenshot})")
    api_key = os.getenv("SCRAPFLY_KEY")
    if not api_key:
        log("error", "❌ SCRAPFLY_KEY environment variable not set.")
        return None, None
    try:
        # Note: Not specifying "format" parameter means Scrapfly returns raw HTML in result.content
        params = {"key": api_key, "url": url, "render_js": True, "asp": True, "auto_scroll": True, "wait_for_selector": "footer a, nav a, main a, [role='main'] a, [class*='footer'] a", "rendering_stage": "domcontentloaded", "rendering_wait": 3000, "retry": True, "country": "us", "proxy_pool": "public_residential_pool"}
        if take_screenshot:
            params["screenshots[main]"] = "fullpage"
            params["screenshot_flags"] = "load_images,block_banners"
        with httpx.Client(proxies=None) as client:
            response = client.get("https://api.scrapfly.io/scrape", params=params, timeout=180)
            response.raise_for_status()
            data = response.json()
            
            # Get raw HTML content from Scrapfly response
            html_content = data["result"]["content"]
            
            # DIAGNOSTIC: Log what Scrapfly actually returned
            if html_content:
                log("info", f"🔍 SCRAPFLY RESPONSE: {len(html_content)} chars, starts: {repr(html_content[:100])}")
            else:
                log("warn", f"🔍 SCRAPFLY RESPONSE: Empty content returned")
                
            screenshot_b64 = None
            if take_screenshot and "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
                screenshot_url = data["result"]["screenshots"]["main"]["url"]
                log("info", f"📸 SCRAPFLY SCREENSHOT URL: {screenshot_url}")
                img_response = client.get(screenshot_url, params={"key": api_key}, timeout=60)
                img_response.raise_for_status()
                screenshot_b64 = base64.b64encode(img_response.content).decode('utf-8')
                log("info", f"✅ SCRAPFLY SCREENSHOT SUCCESS: {len(screenshot_b64)} bytes")
            elif take_screenshot:
                log("error", f"❌ SCRAPFLY SCREENSHOT MISSING: screenshots={data['result'].get('screenshots', 'NOT_FOUND')}")
            return screenshot_b64, html_content
    except Exception as e:
        error_msg = str(e)
        if "UNABLE_TO_TAKE_SCREENSHOT" in error_msg:
            log("warn", f"⏱️ SCRAPFLY TIMEOUT - Screenshot budget exceeded for {url}: {e}")
            log("info", f"🔄 FALLING BACK TO PLAYWRIGHT for screenshot capture")
        else:
            log("error", f"Scrapfly error for {url}: {e}")
        return None, None

def fetch_html_with_playwright(url: str, retried: bool = False, take_screenshot: bool = False) -> Tuple[Optional[str], Optional[str]]:
    log("info", f"Activating Playwright fallback for URL: {url} (Screenshot: {take_screenshot})")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=get_random_user_agent())
            page = context.new_page()
            page.goto(url, wait_until="load", timeout=90000)
            prepare_page_for_capture(page)
            
            html_content = page.content()
            screenshot_b64 = None
            
            if take_screenshot:
                try:
                    screenshot_bytes = page.screenshot(full_page=True, type='png')
                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    log("info", f"✅ PLAYWRIGHT SCREENSHOT SUCCESS: {len(screenshot_b64)} bytes for {url}")
                except Exception as e:
                    log("error", f"❌ PLAYWRIGHT SCREENSHOT FAILED for {url}: {e}")
            
            browser.close()
            return screenshot_b64, html_content
        except Exception as e:
            log("error", f"Playwright failed for {url}: {e}")
            if "browser has crashed" in str(e).lower() and not retried:
                log("warn", "Restarting Playwright browser...")
                return fetch_html_with_playwright(url, retried=True, take_screenshot=take_screenshot)
            return None, None

def fetch_page_content_robustly(url: str, take_screenshot: bool = False) -> Tuple[Optional[str], Optional[str]]:
    try:
        screenshot, html = _fetch_page_data_scrapfly(url, take_screenshot=take_screenshot)
        # Enhanced HTML validation - check for actual HTML content, not just '<' prefix
        if html and html.strip():
            html_lower = html.lower().strip()
            # Check for various valid HTML patterns
            is_valid_html = (
                html_lower.startswith('<!doctype') or  # DOCTYPE declaration
                html_lower.startswith('<html') or      # HTML tag
                html_lower.startswith('<!--') or       # HTML comment
                '<html' in html_lower[:200] or         # HTML tag within first 200 chars
                '<head' in html_lower[:500]            # HEAD tag within first 500 chars
            )
            
            if is_valid_html:
                log("info", f"✅ SCRAPFLY VALID HTML: {len(html)} characters, starts with: {html[:50].strip()}")
                return screenshot, html
            else:
                log("warn", f"❌ SCRAPFLY INVALID HTML: Content doesn't appear to be HTML. First 100 chars: {html[:100]}")
                # Fall through to Playwright fallback below
        else:
            log("warn", f"❌ SCRAPFLY EMPTY CONTENT for {url}, falling back to Playwright for HTML.")
        
        # Fallback to Playwright for invalid or empty HTML
        log("info", f"🔄 FALLING BACK TO PLAYWRIGHT for {url}")
        
        # ENHANCED FIX: Use Playwright screenshot when Scrapfly fails or when preserving existing screenshot
        if take_screenshot and screenshot:
            # Preserve existing Scrapfly screenshot and get HTML from Playwright
            log("info", f"🔧 PRESERVING SCRAPFLY SCREENSHOT: {len(screenshot)} bytes while using Playwright HTML")
            _, html = fetch_html_with_playwright(url, take_screenshot=False)
            return screenshot, html
        elif take_screenshot:
            # Scrapfly failed to get screenshot, use Playwright for both
            log("info", f"🔧 USING PLAYWRIGHT FOR SCREENSHOT: Scrapfly failed, trying Playwright")
            screenshot, html = fetch_html_with_playwright(url, take_screenshot=True)
            return screenshot, html
        else:
            # No screenshot needed, just get HTML
            _, html = fetch_html_with_playwright(url, take_screenshot=False)
            return None, html
    except Exception as e:
        log("warn", f"Scrapfly failed for {url} with error: {e}. Falling back to Playwright.")
        # Complete fallback to Playwright for both screenshot and HTML
        if take_screenshot:
            log("info", f"🔧 COMPLETE PLAYWRIGHT FALLBACK: Getting both screenshot and HTML from Playwright")
            screenshot, html = fetch_html_with_playwright(url, take_screenshot=True)
            return screenshot, html
        else:
            _, html = fetch_html_with_playwright(url, take_screenshot=False)
            return None, html

# --- END: HELPER CLASSES AND FUNCTIONS ---

SHARED_CACHE = {}
load_dotenv()

def validate_configuration():
    """Validate critical configuration at startup to fail fast if misconfigured."""
    errors = []
    
    # Check required API keys
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key or len(openai_key.strip()) < 10:
        errors.append("OPENAI_API_KEY environment variable is missing or invalid")
    
    # Validate numeric constants
    try:
        for key, value in SCORING_CONSTANTS.items():
            if not isinstance(value, (int, float)):
                errors.append(f"SCORING_CONSTANTS['{key}'] must be a number, got: {value}")
            # Allow negative values for penalty scores
            elif key in ["NEGATIVE_VETO_SCORE"] and value >= 0:
                errors.append(f"SCORING_CONSTANTS['{key}'] should be negative (penalty), got: {value}")
            elif key not in ["NEGATIVE_VETO_SCORE"] and value < 0:
                errors.append(f"SCORING_CONSTANTS['{key}'] should be positive, got: {value}")
    except Exception as e:
        errors.append(f"Error validating SCORING_CONSTANTS: {e}")
    
    # Validate business tier hierarchy makes sense
    tier_scores = list(BUSINESS_TIER_SCORES.values())
    if tier_scores != sorted(tier_scores, reverse=True):
        errors.append("BUSINESS_TIER_SCORES should be in descending order of priority")
    
    # Check file extensions are properly formatted
    for ext in CONFIG["ignored_extensions"]:
        if not ext.startswith('.'):
            errors.append(f"File extension '{ext}' should start with a dot")
    
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors)
        log("error", error_msg)
        raise ValueError(error_msg)
    else:
        log("info", "✅ Configuration validation passed")

# Validate configuration on import
validate_configuration()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Memory management configuration
MAX_CACHE_SIZE = 100  # Maximum cached screenshots
MAX_CORPUS_LENGTH = 50000  # Prevent excessive text processing

def cleanup_cache():
    """Remove oldest entries when cache exceeds limit to prevent memory exhaustion."""
    if len(SHARED_CACHE) > MAX_CACHE_SIZE:
        # Remove oldest 20% of entries to free up memory
        items_to_remove = len(SHARED_CACHE) - int(MAX_CACHE_SIZE * 0.8)
        # Sort by insertion order (keys are UUIDs, so we'll use a simple approach)
        items = list(SHARED_CACHE.items())
        for i in range(min(items_to_remove, len(items))):
            key, _ = items[i]
            del SHARED_CACHE[key]
        log("info", f"Cache cleanup: removed {items_to_remove} old entries, {len(SHARED_CACHE)} remaining")

# --- START: FEEDBACK MECHANISM ---
FEEDBACK_FILE = "feedback_log.jsonl"

def record_feedback(analysis_id: str, key_name: str, feedback_type: str, 
                   comment: Optional[str] = None, ai_score: Optional[int] = None, 
                   user_score: Optional[int] = None, confidence: Optional[int] = None,
                   brand_context: Optional[str] = None):
    """Records enhanced user feedback for AI learning and prompt improvement with atomic writes."""
    feedback_entry = {
        "timestamp": time.time(),
        "analysis_id": analysis_id,
        "key_name": key_name,
        "feedback_type": feedback_type,  # "too_high", "about_right", "too_low"
        "comment": comment,
        "ai_score": ai_score,  # What the AI originally scored (0-5)
        "user_score": user_score,  # What the user thinks it should be (0-5)
        "confidence": confidence,  # AI's confidence level (0-100)
        "brand_context": brand_context,  # Brief brand description for pattern analysis
        "score_difference": (user_score - ai_score) if (user_score is not None and ai_score is not None) else None
    }
    
    # Use atomic writes to prevent corruption from concurrent access
    temp_file = f"{FEEDBACK_FILE}.tmp.{uuid.uuid4()}"
    try:
        # Write to temporary file first
        with open(temp_file, "w") as f:
            f.write(json.dumps(feedback_entry) + "\n")
            f.flush()
            os.fsync(f.fileno())  # Force write to disk
        
        # Atomic append by reading existing + new content
        feedback_lines = []
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, "r") as f:
                    feedback_lines = f.readlines()
            except (IOError, OSError):
                log("warn", "Could not read existing feedback file, creating new one")
        
        # Add new feedback
        with open(temp_file, "r") as f:
            feedback_lines.extend(f.readlines())
        
        # Atomic replace
        final_temp = f"{FEEDBACK_FILE}.final.{uuid.uuid4()}"
        with open(final_temp, "w") as f:
            f.writelines(feedback_lines)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic move (rename is atomic on POSIX systems)
        os.rename(final_temp, FEEDBACK_FILE)
        
        log("info", f"Recorded enhanced feedback for analysis_id {analysis_id}, key {key_name}: {feedback_type} (AI: {ai_score}, User: {user_score})")
        
    except OSError as e:
        if e.errno == 28:  # No space left on device
            log("error", "Disk space full - cannot record feedback")
        else:
            log("error", f"OS error recording feedback: {e}")
        raise
    except Exception as e:
        log("error", f"Failed to record feedback to file: {e}")
        raise
    finally:
        # Cleanup temporary files
        for temp in [temp_file, final_temp]:
            try:
                if 'final_temp' in locals() and os.path.exists(temp):
                    os.unlink(temp)
            except:
                pass
# --- START: FEEDBACK ANALYTICS FOR AI LEARNING ---

def analyze_feedback_patterns():
    """Analyze feedback patterns to identify prompt improvement opportunities."""
    if not os.path.exists(FEEDBACK_FILE):
        return {"error": "No feedback data available"}
    
    feedback_data = []
    try:
        with open(FEEDBACK_FILE, "r") as f:
            for line in f:
                if line.strip():
                    feedback_data.append(json.loads(line))
    except Exception as e:
        log("error", f"Failed to read feedback data: {e}")
        return {"error": "Failed to read feedback data"}
    
    if not feedback_data:
        return {"error": "No feedback entries found"}
    
    analysis = {
        "total_feedback": len(feedback_data),
        "by_key": {},
        "systematic_issues": {},
        "confidence_correlation": {},
        "recent_trends": {}
    }
    
    # Analyze by memorability key
    for entry in feedback_data:
        key = entry["key_name"]
        if key not in analysis["by_key"]:
            analysis["by_key"][key] = {
                "total": 0, "too_high": 0, "too_low": 0, "about_right": 0,
                "avg_score_diff": 0, "score_diffs": []
            }
        
        key_stats = analysis["by_key"][key]
        key_stats["total"] += 1
        key_stats[entry["feedback_type"]] += 1
        
        if entry["score_difference"] is not None:
            key_stats["score_diffs"].append(entry["score_difference"])
    
    # Calculate averages and identify systematic issues
    for key, stats in analysis["by_key"].items():
        if stats["score_diffs"]:
            stats["avg_score_diff"] = round(sum(stats["score_diffs"]) / len(stats["score_diffs"]), 2)
        
        # Identify systematic biases
        total_directional = stats["too_high"] + stats["too_low"]
        if total_directional >= 3:  # Need minimum feedback for reliability
            if stats["too_high"] / total_directional > 0.7:
                analysis["systematic_issues"][key] = "AI consistently over-scores"
            elif stats["too_low"] / total_directional > 0.7:
                analysis["systematic_issues"][key] = "AI consistently under-scores"
    
    return analysis

def get_prompt_improvements_from_feedback():
    """Generate specific prompt improvements based on feedback analysis."""
    patterns = analyze_feedback_patterns()
    
    if "error" in patterns:
        return patterns
    
    improvements = {
        "conservative_adjustments": [],  # For over-scoring keys
        "generous_adjustments": [],     # For under-scoring keys
        "examples_needed": [],          # Keys needing better examples
        "confidence_issues": []         # Low confidence correlating with poor feedback
    }
    
    for key, issue in patterns.get("systematic_issues", {}).items():
        if "over-scores" in issue:
            improvements["conservative_adjustments"].append({
                "key": key,
                "adjustment": f"Be more conservative with {key} scoring. Users frequently rate this too high.",
                "avg_diff": patterns["by_key"][key]["avg_score_diff"]
            })
        elif "under-scores" in issue:
            improvements["generous_adjustments"].append({
                "key": key,
                "adjustment": f"Be more generous with {key} scoring. Users frequently rate this too low.",
                "avg_diff": patterns["by_key"][key]["avg_score_diff"]
            })
    
    return improvements

# --- END: FEEDBACK MECHANISM ---

def _clean_url(url: str) -> str:
    """Clean and validate URL with security checks and www normalization."""
    url = url.strip()
    if not url.startswith(("http://", "https://")): 
        url = "https://" + url
    # Remove www. prefix to prevent duplicate URLs (basf.com == www.basf.com)
    url = url.replace('//www.', '//')
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

def find_best_corporate_portal(discovered_links: List[Tuple[str, str]], initial_url: str, primary_language: str = 'en') -> Optional[str]:
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
            score, _ = score_link(link_url, link_text, primary_language)  # Unpack tuple, ignore rationale
            if score > highest_score:
                highest_score = score
                best_candidate = link_url
    
    if highest_score > SCORING_CONSTANTS["HIGH_VALUE_PORTAL_THRESHOLD"]:
        log("info", f"High-quality portal found with score {highest_score}. Pivoting to: {best_candidate}")
        return best_candidate
    else:
        log("info", "No high-quality corporate portal found. Continuing with the initial URL.")
        return None

def discover_links_from_sitemap(homepage_url: str) -> Optional[Tuple[List[Tuple[str, str]], Optional[str]]]:
    """Discover links from sitemap and return detected language context.
    
    Returns:
        Tuple of (links, detected_language) where detected_language is extracted from chosen sitemap URL
    """
    log("info", "Attempting to discover links from sitemap...")
    sitemap_url = urljoin(homepage_url, "/sitemap.xml")
    detected_sitemap_lang = None
    
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

            # IMPROVED: Implement intelligent sitemap scoring to find the most relevant one
            best_sitemap_url = None
            highest_score = -1
            
            for sm_url in sitemaps:
                score = 0
                # Heavily prioritize global/corporate sitemaps
                if "global" in sm_url or "corporate" in sm_url: score += 150
                if "main" in sm_url or "pages" in sm_url: score += 50
                if "/en" in sm_url or "en/" in sm_url: score += 25  # Stronger preference for English
                
                # Penalize country-specific sitemaps heavily
                if re.search(r'/[a-z]{2}/', sm_url) and "global" not in sm_url: score -= 50
                
                # Additional preferences for brand-relevant content
                if any(keyword in sm_url for keyword in ['page', 'post', 'company', 'about', 'article']): score += 25
                
                log("debug", f"Sitemap {sm_url} scored {score}")
                if score > highest_score:
                    highest_score = score
                    best_sitemap_url = sm_url

            if best_sitemap_url:
                log("info", f"Fetching prioritized sub-sitemap: {best_sitemap_url} (Score: {highest_score})")
                
                # DYNAMIC LANGUAGE CONTEXT: Extract language from chosen sitemap URL
                lang_patterns = {
                    '/en/': 'en', '/en.': 'en', '_en.': 'en', '-en.': 'en',
                    '/de/': 'de', '/de.': 'de', '_de.': 'de', '-de.': 'de',
                    '/es/': 'es', '/es.': 'es', '_es.': 'es', '-es.': 'es',
                    '/fr/': 'fr', '/fr.': 'fr', '_fr.': 'fr', '-fr.': 'fr',
                    '/it/': 'it', '/it.': 'it', '_it.': 'it', '-it.': 'it',
                    '/pt/': 'pt', '/pt.': 'pt', '_pt.': 'pt', '-pt.': 'pt',
                    '/ja/': 'ja', '/ja.': 'ja', '_ja.': 'ja', '-ja.': 'ja',
                    '/zh/': 'zh', '/zh.': 'zh', '_zh.': 'zh', '-zh.': 'zh',
                    '/global/en': 'en', 'global-en': 'en'  # Special cases for global sitemaps
                }
                
                for pattern, lang in lang_patterns.items():
                    if pattern in best_sitemap_url.lower():
                        detected_sitemap_lang = lang
                        log("info", f"🌐 Dynamic Language Context: Detected '{lang}' from sitemap URL")
                        break
                
                response = httpx.get(best_sitemap_url, headers={"User-Agent": get_random_user_agent()}, follow_redirects=True, timeout=20)
                response.raise_for_status()
                root = ET.fromstring(response.content)
            else:
                log("warn", "No suitable sitemap found in sitemap index.")
                return None, None

        urls = [elem.text for elem in root.findall('sm:url/sm:loc', namespace)]
        if not urls:
            return None, None

        log("info", f"Found {len(urls)} links in sitemap.")
        return [(url, url.split('/')[-1].replace('-', ' ')) for url in urls], detected_sitemap_lang
    except Exception as e:
        log("warn", f"Sitemap not found or failed to parse: {e}")
        return None, None

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
    
    # DIAGNOSTIC: Check screenshot parameter
    has_screenshot = homepage_screenshot_b64 is not None
    screenshot_size = len(homepage_screenshot_b64) if has_screenshot else 0
    log("info", f"🔍 SCREENSHOT DIAGNOSTIC - {key_name}: has_screenshot={has_screenshot}, size={screenshot_size} bytes")
    
    try:
        content = [{"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"}, {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"}]
        if homepage_screenshot_b64:
            # DIAGNOSTIC: Validate base64 format
            try:
                import base64
                base64.b64decode(homepage_screenshot_b64[:100])  # Test decode first 100 chars
                log("info", f"✅ BASE64 VALIDATION - {key_name}: Screenshot data is valid base64 format")
            except Exception as e:
                log("error", f"❌ BASE64 VALIDATION - {key_name}: Invalid base64 data: {e}")
            
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{homepage_screenshot_b64}"}})
            log("info", f"🖼️ OPENAI REQUEST - {key_name}: Including screenshot in OpenAI API call ({len(homepage_screenshot_b64)} bytes)")
        else:
            log("warn", f"❌ OPENAI REQUEST - {key_name}: NO SCREENSHOT - sending text-only to OpenAI")
        
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
        
        # Make OpenAI API call
        log("info", f"🚀 CALLING OPENAI API - {key_name}: Sending request with {len(content)} content items")
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}], response_format={"type": "json_object"}, temperature=0.3)
        
        # Log successful API response
        log("info", f"✅ OPENAI API SUCCESS - {key_name}: Received response from GPT-4V")
        if homepage_screenshot_b64:
            log("info", f"🎯 CONFIRMED: OpenAI processed image data for {key_name} analysis")
        
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
                # Clean up cache before adding new screenshot
                cleanup_cache()
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
        return {"keys_analyzed": 0, "strong_keys": 0, "weak_keys": 0, "adequate_keys": 0, "average_score": 0.0}
    
    summary = {"keys_analyzed": len(all_results), "strong_keys": 0, "weak_keys": 0, "adequate_keys": 0}
    total_score = 0
    valid_scores = 0
    
    for result in all_results:
        if 'analysis' in result and 'score' in result['analysis']:
            score = result["analysis"]["score"]
            total_score += score
            valid_scores += 1
            
            if score >= 4:  # Strong performance (4-5 on 0-5 scale)
                summary["strong_keys"] += 1
            elif score <= 2:  # Weak performance (0-2 on 0-5 scale)
                summary["weak_keys"] += 1
            else:  # Score of 3 is adequate
                summary["adequate_keys"] += 1
    
    # Calculate average score
    summary["average_score"] = round(total_score / valid_scores, 2) if valid_scores > 0 else 0.0
    
    return summary

def run_full_scan_stream(url: str, cache: dict):
    # DEBUG: Message tracking
    def debug_yield(message_data):
        """Debug wrapper to log all yielded messages"""
        log("debug", f"🚀 YIELDING MESSAGE: {message_data}")
        return message_data
    
    # Bulletproof environment detection
    IS_PRODUCTION = (
        os.getenv('SCANNER_ENV', '').lower() == 'production' or
        os.getenv('RENDER_SERVICE_ID', '') != '' or
        os.getenv('RENDER', '').lower() == 'true' or
        'render.com' in os.getenv('RENDER_EXTERNAL_URL', '')
    )
    
    processing_mode = "Sequential (Production)" if IS_PRODUCTION else "Parallel (Development)"
    log("info", f"Environment: {processing_mode} processing mode enabled")
    
    circuit_breaker = CircuitBreaker(failure_threshold=CONFIG["circuit_breaker_threshold"])
    try:
        # Validate URL before processing
        initial_url = _clean_url(url)
        is_valid, error_msg = _validate_url(initial_url)
        if not is_valid:
            log("error", f"URL validation failed: {error_msg}")
            yield {'type': 'error', 'message': f'Invalid URL: {error_msg}'}
            return

        yield debug_yield({'type': 'status', 'message': 'Step 1/5: Discovering all brand pages...', 'phase': 'discovery', 'progress': 10})
        yield debug_yield({'type': 'activity', 'message': f'🌐 Starting scan at {initial_url}', 'timestamp': time.time()})
        log("info", f"Starting scan at validated URL: {initial_url}")

        # --- Phase 1: Initial Domain Discovery ---
        try:
            _, homepage_html = fetch_page_content_robustly(initial_url)
            if not homepage_html: raise Exception("Could not fetch initial URL content.")
        except Exception as e:
            log("error", f"Failed to fetch the initial URL: {e}")
            yield {'type': 'error', 'message': f'Failed to fetch the initial URL: {e}'}
            return

        yield debug_yield({'type': 'activity', 'message': f'🔍 Analyzing HTML structure...', 'timestamp': time.time()})
        all_discovered_links = discover_links_from_html(homepage_html, initial_url)
        yield debug_yield({'type': 'metric', 'key': 'html_links', 'value': len(all_discovered_links)})
        yield debug_yield({'type': 'activity', 'message': f'✅ Found {len(all_discovered_links)} links in HTML', 'timestamp': time.time()})
        
        yield debug_yield({'type': 'activity', 'message': f'📄 Searching for sitemap...', 'timestamp': time.time()})
        sitemap_result = discover_links_from_sitemap(initial_url)
        sitemap_links = None
        sitemap_detected_lang = None
        if sitemap_result:
            sitemap_links, sitemap_detected_lang = sitemap_result
            if sitemap_links:
                all_discovered_links.extend(sitemap_links)
                yield debug_yield({'type': 'activity', 'message': f'✅ Found {len(sitemap_links)} pages in sitemap', 'timestamp': time.time()})
                yield debug_yield({'type': 'metric', 'key': 'sitemap_links', 'value': len(sitemap_links)})
        else:
            yield debug_yield({'type': 'activity', 'message': f'📄 No sitemap found - proceeding with HTML links', 'timestamp': time.time()})

        # Detect the primary language from HTML first
        primary_language = detect_primary_language(homepage_html)
        
        # DYNAMIC LANGUAGE CONTEXT: Update language based on sitemap if detected
        if sitemap_detected_lang:
            log("info", f"🔄 Updating language context from '{primary_language}' to '{sitemap_detected_lang}' based on chosen sitemap")
            primary_language = sitemap_detected_lang
            yield debug_yield({'type': 'activity', 'message': f'🌍 Detected site language: {sitemap_detected_lang.upper()}', 'timestamp': time.time()})

        # --- Phase 2: High-Value Subdomain Discovery ---
        # FIXED: True Two-Pocket Strategy - find additional sources without pivoting
        yield debug_yield({'type': 'activity', 'message': f'🔎 Searching for corporate portals...', 'timestamp': time.time()})
        subdomain_portal_url = find_best_corporate_portal(all_discovered_links, initial_url, primary_language)
        if subdomain_portal_url:
            log("info", f"🎯 Found high-value subdomain: {subdomain_portal_url}. Adding its links to our discovery pool.")
            yield debug_yield({'type': 'activity', 'message': f'🎯 Found corporate portal - expanding discovery...', 'timestamp': time.time()})
            try:
                yield debug_yield({'type': 'activity', 'message': f'📥 Fetching portal content...', 'timestamp': time.time()})
                _, subdomain_html = fetch_page_content_robustly(subdomain_portal_url)
                if subdomain_html:
                    yield debug_yield({'type': 'activity', 'message': f'🔗 Discovering portal links...', 'timestamp': time.time()})
                    subdomain_links = discover_links_from_html(subdomain_html, subdomain_portal_url)
                    # Additional sitemap discovery from the subdomain
                    yield debug_yield({'type': 'activity', 'message': f'📄 Checking portal sitemap...', 'timestamp': time.time()})
                    subdomain_sitemap_result = discover_links_from_sitemap(subdomain_portal_url)
                    if subdomain_sitemap_result:
                        subdomain_sitemap_links, subdomain_lang = subdomain_sitemap_result
                        if subdomain_sitemap_links:
                            subdomain_links.extend(subdomain_sitemap_links)
                            log("info", f"✅ Added {len(subdomain_sitemap_links)} links from subdomain sitemap")
                            yield debug_yield({'type': 'activity', 'message': f'✅ Added {len(subdomain_sitemap_links)} portal sitemap links', 'timestamp': time.time()})
                            # Update language context if subdomain provides clearer signal
                            if subdomain_lang and subdomain_lang != primary_language:
                                log("info", f"🔄 Subdomain sitemap suggests '{subdomain_lang}' language context")
                    all_discovered_links.extend(subdomain_links)
                    log("info", f"✅ Two-Pocket Strategy: Added {len(subdomain_links)} links from high-value subdomain")
                    yield debug_yield({'type': 'activity', 'message': f'🎯 Added {len(subdomain_links)} links from corporate portal', 'timestamp': time.time()})
                    yield debug_yield({'type': 'metric', 'key': 'subdomain_links', 'value': len(subdomain_links)})
            except Exception as e:
                log("warn", f"Could not fetch high-value subdomain {subdomain_portal_url}: {e}")
                yield debug_yield({'type': 'activity', 'message': f'⚠️ Portal fetch failed - continuing with main site', 'timestamp': time.time()})
        else:
            yield debug_yield({'type': 'activity', 'message': f'📍 No additional portals found - using main site', 'timestamp': time.time()})

        # --- Phase 3: Scoring and Analysis ---
        # CRITICAL: Never pivot - always use initial URL as homepage
        homepage_url = initial_url
        log("info", f"✅ Confirmed scan homepage (no pivot): {homepage_url}")

        if not all_discovered_links:
            log("warn", f"No links discovered from {homepage_url}. Proceeding with homepage analysis only.")
            all_discovered_links = [(homepage_url, "Homepage")]
            yield {'type': 'status', 'message': 'Warning: Could not discover additional pages. Analyzing homepage only.'}

        try:
            log("info", f"🔍 ATTEMPTING HOMEPAGE SCREENSHOT: {homepage_url}")
            homepage_screenshot_b64, final_homepage_html = fetch_page_content_robustly(homepage_url, take_screenshot=True)
            if homepage_screenshot_b64:
                log("info", f"✅ HOMEPAGE SCREENSHOT SUCCESS: {len(homepage_screenshot_b64)} bytes - FOR AI ANALYSIS AND FRONTEND DISPLAY")
                # Homepage screenshot is used for BOTH AI analysis AND frontend display
                cleanup_cache()
                image_id = str(uuid.uuid4())
                cache[image_id] = homepage_screenshot_b64
                yield debug_yield({'type': 'screenshot_ready', 'id': image_id, 'url': homepage_url})
                log("info", f"🎯 HOMEPAGE SCREENSHOT EMITTED: id={image_id}, url={homepage_url}")
                yield debug_yield({'type': 'activity', 'message': f'📸 Homepage screenshot captured for AI and display', 'timestamp': time.time()})
            else:
                log("error", f"❌ HOMEPAGE SCREENSHOT FAILED: No screenshot data returned")
                yield debug_yield({'type': 'activity', 'message': f'⚠️ Homepage screenshot failed - AI will run without visual context', 'timestamp': time.time()})
        except Exception as e:
            log("error", f"❌ HOMEPAGE SCREENSHOT EXCEPTION: {e}")
            homepage_screenshot_b64 = None
            final_homepage_html = homepage_html
            yield debug_yield({'type': 'activity', 'message': f'⚠️ Homepage screenshot error - AI will run without visual context', 'timestamp': time.time()})

        homepage_soup = BeautifulSoup(final_homepage_html, "html.parser")
        social_corpus = get_social_media_text(homepage_soup, homepage_url)
        yield {'type': 'status', 'message': 'Social media text captured.' if social_corpus else 'No social media links found.'}

        yield {'type': 'status', 'message': f'Detected primary language: {primary_language.upper()}'}

        yield {'type': 'status', 'message': 'Scoring and ranking all discovered links...', 'phase': 'scoring', 'progress': 30}
        yield {'type': 'activity', 'message': f'📊 Analyzing {len(all_discovered_links)} discovered links...', 'timestamp': time.time()}
        yield {'type': 'metric', 'key': 'total_links', 'value': len(all_discovered_links)}
        scored_links = []
        unique_urls_for_scoring = set()
        processed_count = 0
        total_unique = len(set(_clean_url(url) for url, _ in all_discovered_links))  # Estimate unique count
        
        yield debug_yield({'type': 'activity', 'message': f'🔍 Removing {len(all_discovered_links) - total_unique} duplicate URLs...', 'timestamp': time.time()})
        
        for link_url, link_text in all_discovered_links:
            cleaned_url = _clean_url(link_url)
            if cleaned_url not in unique_urls_for_scoring:
                unique_urls_for_scoring.add(cleaned_url)
                processed_count += 1
                
                # Progress updates every 20% of links processed
                if processed_count % max(1, total_unique // 5) == 0 or processed_count == total_unique:
                    progress_pct = int((processed_count / total_unique) * 100) if total_unique > 0 else 100
                    yield debug_yield({'type': 'activity', 'message': f'📊 Scoring links... {processed_count}/{total_unique} ({progress_pct}%)', 'timestamp': time.time()})
                
                score, rationale = score_link(cleaned_url, link_text, primary_language)
                if score > SCORING_CONSTANTS["MIN_BUSINESS_SCORE"]:  # Business-relevant content threshold
                    scored_links.append({"url": cleaned_url, "text": link_text, "score": score, "rationale": rationale})
        
        scored_links.sort(key=lambda x: x["score"], reverse=True)
        yield {'type': 'metric', 'key': 'high_value_pages', 'value': len(scored_links)}
        yield {'type': 'activity', 'message': f'✨ Identified {len(scored_links)} business-relevant pages', 'timestamp': time.time()}
        
        # Enhanced logging with rationale display
        top_10 = scored_links[:10]
        log("info", f"🎯 Top {len(top_10)} Business-Relevant Links (Score > {SCORING_CONSTANTS['MIN_BUSINESS_SCORE']}):")
        for i, link in enumerate(top_10, 1):
            url_display = link["url"] if len(link["url"]) <= 60 else link["url"][:57] + "..."
            text_display = link["text"] if len(link["text"]) <= 30 else link["text"][:27] + "..."
            log("info", f"  {i}. {url_display} (Score: {link['score']}) - \"{text_display}\"")
            log("info", f"     📝 Rationale: {link['rationale']}")

        priority_pages, found_urls = [], set()
        if homepage_url not in found_urls:
            priority_pages.append(homepage_url); found_urls.add(homepage_url)
        for link in scored_links:
            if len(priority_pages) >= 5: break
            if link["url"] not in found_urls:
                priority_pages.append(link["url"]); found_urls.add(link["url"])
        
        log("info", f"📋 Final priority pages selected for analysis ({len(priority_pages)} pages):", priority_pages)

        other_pages_to_screenshot = [p for p in priority_pages if p != homepage_url]
        if other_pages_to_screenshot:
            yield {'type': 'status', 'message': 'Capturing visual evidence from key pages...'}
            for data in capture_screenshots_playwright(other_pages_to_screenshot):
                log("info", f"🎯 PLAYWRIGHT SCREENSHOT EMITTED: id={data.get('id')}, url={data.get('url')}")
                yield {'type': 'screenshot_ready', **data}
        
        yield {'type': 'status', 'message': 'Step 2/5: Analyzing key pages...', 'phase': 'analysis', 'progress': 40}
        yield {'type': 'activity', 'message': f'📑 Processing {len(priority_pages)} priority pages...', 'timestamp': time.time()}
        page_html_map = {homepage_url: final_homepage_html}
        
        other_pages_to_fetch = [p for p in priority_pages if p != homepage_url]
        
        # Hybrid processing logic
        if IS_PRODUCTION or len(other_pages_to_fetch) <= 2:
            # Sequential processing for production environments
            log("info", f"🔄 Using sequential processing for {len(other_pages_to_fetch)} pages (Production mode)")
            yield debug_yield({'type': 'activity', 'message': f'📥 Fetching {len(other_pages_to_fetch)} priority pages (sequential)...', 'timestamp': time.time()})
            
            for i, url in enumerate(other_pages_to_fetch, 1):
                yield debug_yield({'type': 'activity', 'message': f'📄 Fetching page {i}/{len(other_pages_to_fetch)}: {url.split("/")[-1] or "homepage"}...', 'timestamp': time.time()})
                try:
                    _, html = fetch_page_content_robustly(url)
                    if html:
                        page_html_map[url] = html
                        circuit_breaker.record_success()
                        log("info", f"✅ Sequential fetch successful for {url}")
                        yield {'type': 'activity', 'message': f'✅ Analyzed page {len(page_html_map)}/{len(priority_pages)}', 'timestamp': time.time()}
                        yield {'type': 'progress', 'current': len(page_html_map), 'total': len(priority_pages), 'phase': 'page_fetch'}
                    else:
                        log("warn", f"⚠️ Sequential fetch for {url} returned no content.")
                        circuit_breaker.record_failure()
                    
                    # Force garbage collection after each page to manage memory
                    gc.collect()
                except Exception as e:
                    log("error", f"❌ Sequential fetch for {url} failed: {e}")
                    circuit_breaker.record_failure()
                    # Continue with other pages even if one fails
                    continue
        else:
            # Parallel processing for local/development environments
            log("info", f"⚡ Using parallel processing for {len(other_pages_to_fetch)} pages (Development mode)")
            yield debug_yield({'type': 'activity', 'message': f'⚡ Fetching {len(other_pages_to_fetch)} priority pages (parallel)...', 'timestamp': time.time()})
            
            with ProcessPoolExecutor(max_workers=2) as executor:
                future_to_url = {executor.submit(fetch_page_content_robustly, url): url for url in other_pages_to_fetch}
                completed_count = 0
                total_count = len(other_pages_to_fetch)
                
                for future in future_to_url:
                    url = future_to_url[future]
                    completed_count += 1
                    try:
                        _, html = future.result(timeout=60)
                        if html:
                            page_html_map[url] = html
                            circuit_breaker.record_success()
                            log("info", f"✅ Parallel fetch successful for {url}")
                            yield debug_yield({'type': 'activity', 'message': f'✅ Fetched page {completed_count}/{total_count}: {url.split("/")[-1] or "homepage"}', 'timestamp': time.time()})
                        else:
                            log("warn", f"⚠️ Parallel fetch for {url} returned no content.")
                            circuit_breaker.record_failure()
                            yield debug_yield({'type': 'activity', 'message': f'⚠️ Page {completed_count}/{total_count} returned no content', 'timestamp': time.time()})
                    except Exception as e:
                        log("error", f"❌ Parallel fetch for {url} failed: {e}")
                        circuit_breaker.record_failure()
                        yield debug_yield({'type': 'activity', 'message': f'❌ Page {completed_count}/{total_count} fetch failed', 'timestamp': time.time()})

        yield debug_yield({'type': 'activity', 'message': f'📝 Extracting text from {len(priority_pages)} pages...', 'timestamp': time.time()})        
        text_corpus = ""
        processed_pages = 0
        
        for page_url in priority_pages:
            page_html = page_html_map.get(page_url)
            if page_html:
                processed_pages += 1
                yield debug_yield({'type': 'activity', 'message': f'📝 Processing text {processed_pages}/{len(priority_pages)}: {page_url.split("/")[-1] or "homepage"}...', 'timestamp': time.time()})
                soup = BeautifulSoup(page_html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
                    tag.decompose()
                text_corpus += f"\n\n--- Page Content ({page_url}) ---\n" + extract_relevant_text(soup)
        
        # Limit corpus length to prevent memory exhaustion and improve AI analysis quality
        full_corpus = (text_corpus + social_corpus)[:MAX_CORPUS_LENGTH]
        if len(text_corpus + social_corpus) > MAX_CORPUS_LENGTH:
            log("info", f"📄 Text corpus truncated from {len(text_corpus + social_corpus)} to {MAX_CORPUS_LENGTH} characters")
            yield debug_yield({'type': 'activity', 'message': f'📄 Trimmed text corpus to optimal length ({MAX_CORPUS_LENGTH} chars)', 'timestamp': time.time()})

        yield {'type': 'status', 'message': 'Step 3/5: Synthesizing brand overview...', 'phase': 'synthesis', 'progress': 60}
        yield {'type': 'activity', 'message': '🧠 AI analyzing brand identity...', 'timestamp': time.time()}
        brand_summary = call_openai_for_synthesis(full_corpus)
        
        yield {'type': 'status', 'message': 'Step 4/5: Performing detailed analysis...', 'phase': 'ai_analysis', 'progress': 70}
        all_results = []
        for i, (key, prompt) in enumerate(MEMORABILITY_KEYS_PROMPTS.items()):
            yield {'type': 'status', 'message': f'Analyzing key: {key}...', 'phase': 'ai_analysis', 'progress': 70 + (i * 5)}
            yield {'type': 'activity', 'message': f'🔍 Evaluating {key} memorability...', 'timestamp': time.time()}
            try:
                has_screenshot = homepage_screenshot_b64 is not None
                screenshot_size = len(homepage_screenshot_b64) if has_screenshot else 0
                log("info", f"🧠 AI ANALYSIS {key}: Screenshot={has_screenshot}, Size={screenshot_size} bytes")
                
                # DIAGNOSTIC: Double-check screenshot before sending to OpenAI
                if has_screenshot and screenshot_size > 0:
                    log("info", f"✅ PASSING SCREENSHOT TO OPENAI - {key}: {screenshot_size} bytes of screenshot data")
                else:
                    log("error", f"❌ NO SCREENSHOT DATA TO SEND TO OPENAI - {key}: This will be text-only analysis")
                
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
        
        yield {'type': 'status', 'message': 'Step 5/5: Generating Executive Summary...', 'phase': 'summary', 'progress': 95}
        yield {'type': 'activity', 'message': '📝 Generating strategic recommendations...', 'timestamp': time.time()}
        summary_text = call_openai_for_executive_summary(all_results) 
        yield {'type': 'summary', 'text': summary_text}
        
        quantitative_summary = summarize_results(all_results)
        yield {'type': 'quantitative_summary', 'data': quantitative_summary}
        
        yield {'type': 'complete', 'message': f'✅ Analysis complete! Used {processing_mode} processing.', 'progress': 100}
        yield {'type': 'activity', 'message': '🎉 Scan completed successfully!', 'timestamp': time.time()}

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
