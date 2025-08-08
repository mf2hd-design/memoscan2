import os
import re
import json
import base64
import uuid
import time
import signal
import gc
from collections import defaultdict
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
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup, Tag
from openai import OpenAI
from dotenv import load_dotenv
import httpx

from urllib.parse import quote_plus

# Use ThreadPoolExecutor for I/O-bound web scraping tasks (more efficient than ProcessPoolExecutor)
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import sync_playwright
from typing import Optional, Dict, List, Tuple

# --- SHARED HTTP CLIENT ---
# Create a shared httpx client with connection pooling for better performance
SHARED_HTTP_CLIENT = None

def get_shared_http_client():
    """Get or create a shared HTTP client with connection pooling."""
    global SHARED_HTTP_CLIENT
    if SHARED_HTTP_CLIENT is None:
        from random import choice
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
        ]
        SHARED_HTTP_CLIENT = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            follow_redirects=True,
            headers={"User-Agent": choice(user_agents)}
        )
    return SHARED_HTTP_CLIENT

def close_shared_http_client():
    """Close the shared HTTP client to free resources."""
    global SHARED_HTTP_CLIENT
    if SHARED_HTTP_CLIENT is not None:
        SHARED_HTTP_CLIENT.close()
        SHARED_HTTP_CLIENT = None

# --- SHARED PLAYWRIGHT BROWSER ---
# Reuse Playwright browser instance for better performance
SHARED_PLAYWRIGHT = None
SHARED_BROWSER = None

def get_shared_playwright_browser():
    """Get or create a shared Playwright browser instance."""
    global SHARED_PLAYWRIGHT, SHARED_BROWSER
    if SHARED_PLAYWRIGHT is None or SHARED_BROWSER is None:
        SHARED_PLAYWRIGHT = sync_playwright().start()
        SHARED_BROWSER = SHARED_PLAYWRIGHT.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox'
            ]
        )
    return SHARED_BROWSER

def close_shared_playwright_browser():
    """Close the shared Playwright browser to free resources."""
    global SHARED_PLAYWRIGHT, SHARED_BROWSER
    if SHARED_BROWSER is not None:
        SHARED_BROWSER.close()
        SHARED_BROWSER = None
    if SHARED_PLAYWRIGHT is not None:
        SHARED_PLAYWRIGHT.stop()
        SHARED_PLAYWRIGHT = None

# --- START: HELPER FUNCTIONS ---

def safe_api_key(key: str) -> str:
    """Safely format API keys for logging by masking most characters."""
    if not key or len(key) < 8:
        return "INVALID"
    return f"{key[:4]}...{key[-4:]}"

def detect_image_format(image_b64: str) -> str:
    """Detect image format from base64 data and return proper MIME type."""
    try:
        # Decode first few bytes to check image signature
        header_bytes = base64.b64decode(image_b64[:100])
        
        # Check common image format signatures
        if header_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
            return "image/png"
        elif header_bytes.startswith(b'\xff\xd8\xff'):
            return "image/jpeg"
        elif header_bytes.startswith(b'GIF87a') or header_bytes.startswith(b'GIF89a'):
            return "image/gif"
        elif header_bytes.startswith(b'RIFF') and b'WEBP' in header_bytes:
            return "image/webp"
        else:
            # Default to JPEG since Scrapfly typically returns JPEG
            log("warn", f"Unknown image format, defaulting to image/jpeg. Header: {header_bytes[:20]}")
            return "image/jpeg"
    except Exception as e:
        log("warn", f"Failed to detect image format: {e}, defaulting to image/jpeg")
        return "image/jpeg"

def retry_with_backoff(func, max_retries=3, base_delay=1, exceptions=(Exception,)):
    """Retry function with exponential backoff."""
    import random
    import time
    
    for attempt in range(max_retries):
        try:
            return func()
        except exceptions as e:
            if attempt == max_retries - 1:
                raise e
            
            # Exponential backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            log("info", f"🔄 RETRY ATTEMPT {attempt + 1}/{max_retries} after {delay:.2f}s: {type(e).__name__}")
            time.sleep(delay)

def find_sitemap_from_robots_txt(base_url: str) -> Optional[List[str]]:
    """Fetches and parses robots.txt to find all sitemap URLs using industry-standard parser."""
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        log("info", f"Checking for sitemap in {robots_url}")
        client = get_shared_http_client()
        response = client.get(robots_url, timeout=10)
        if response.status_code == 200:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            if parser.sitemaps:
                log("info", f"Found {len(parser.sitemaps)} sitemap(s) in robots.txt: {parser.sitemaps}")
                return list(parser.sitemaps)
    except Exception as e:
        log("warn", f"Could not parse robots.txt: {e}")
    return None

def cleanup_process_pool(executor):
    """Clean up process pool to prevent zombie processes."""
    try:
        executor.shutdown(wait=True, timeout=30)
        log("info", "✅ Process pool cleanly shutdown")
    except Exception as e:
        log("error", f"❌ Failed to cleanly shutdown process pool: {e}")
        # Force terminate remaining processes if possible
        if hasattr(executor, '_processes'):
            for process in executor._processes.values():
                if process.is_alive():
                    log("warn", f"🔪 Force terminating process {process.pid}")
                    process.terminate()

# Environment-based log level configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_LEVELS = {'DEBUG': 0, 'INFO': 1, 'WARN': 2, 'ERROR': 3}

def should_log(level: str) -> bool:
    """Check if message should be logged based on configured log level."""
    return LOG_LEVELS.get(level.upper(), 1) >= LOG_LEVELS.get(LOG_LEVEL, 1)

def log(level, message, data=None):
    import json
    import time
    if not should_log(level):
        return
    
    # Check if we should use structured JSON logging
    use_json_logging = os.getenv('JSON_LOGGING', 'false').lower() == 'true'
    
    if use_json_logging:
        # Structured JSON logging for production
        log_entry = {
            "timestamp": time.time(),
            "level": level.upper(),
            "message": message,
            "service": "memoscan2-scanner"
        }
        
        if data:
            # Sanitize sensitive data before logging
            safe_data = data
            if isinstance(data, dict):
                safe_data = {k: safe_api_key(v) if k.lower().endswith(('key', 'token', 'secret')) and isinstance(v, str) else v 
                            for k, v in data.items()}
            log_entry["data"] = safe_data
        
        print(json.dumps(log_entry, ensure_ascii=False), flush=True)
    else:
        # Traditional logging format
        formatted_message = f"[{level.upper()}] {message}"
        print(formatted_message, flush=True)
        if data:
            # Sanitize sensitive data before logging
            safe_data = data
            if isinstance(data, dict):
                safe_data = {k: safe_api_key(v) if k.lower().endswith(('key', 'token', 'secret')) and isinstance(v, str) else v 
                            for k, v in data.items()}
            details_message = f"[DETAILS] {json.dumps(safe_data, indent=2, ensure_ascii=False)}"
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

def _categorize_veto_term(term: str) -> str:
    """
    Centralized semantic category mapping for veto terms to eliminate redundancy.
    
    Args:
        term: The subdomain or path segment to categorize
        
    Returns:
        Semantic category name for the veto term ('careers', 'commerce', etc.)
    """
    term_clean = term.lower().strip('/')
    
    # Comprehensive multilingual category mappings
    category_mappings = {
        'careers': {'careers', 'jobs', 'karriere', 'empleo', 'trabajo', 'stellenangebote', 'bewerbung', 'praktikum', 'vacantes', 'postulaciones', 'reclutamiento'},
        'commerce': {'shop', 'store', 'tienda', 'warenkorb', 'kasse', 'bestellen', 'einkaufen', 'carrito', 'comprar', 'pago', 'pedido', 'cart', 'checkout', 'ecommerce', 'wishlist'},
        'legal': {'legal', 'rechtliche', 'recht', 'juridico', 'privacy', 'datenschutz', 'privacidad', 'impressum', 'pflichtangaben', 'aviso-legal', 'politica-de-privacidad', 'terminos', 'condiciones', 'terms', 'disclaimer', 'compliance', 'policy'},
        'sustainability': {'sustainability', 'esg', 'nachhaltigkeit', 'sostenibilidad'},
        'support': {'support', 'help', 'hilfe', 'ayuda', 'soporte', 'faq', 'customer-service', 'knowledge-base', 'contact'},
        'developers': {'developer', 'api', 'docs', 'entwickler', 'desarrollador', 'documentation', 'sdk', 'portal'},
        'media': {'press', 'media', 'presse', 'medien', 'prensa', 'pressemitteilung', 'nachrichten', 'noticias', 'news', 'articles', 'updates', 'spotlight', 'stories'}
    }
    
    for category, terms in category_mappings.items():
        if term_clean in terms:
            return category
    
    return 'other'

def is_vetoed_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if a URL should be pre-emptively vetoed based on its subdomain or path.
    Returns (is_vetoed, category) for transparency in logging.
    """
    try:
        # First check exceptions - these override any veto
        url_lower = url.lower()
        if any(exception in url_lower for exception in VETO_EXCEPTIONS):
            return False, None
            
        parsed_url = urlparse(url)
        hostname = parsed_url.hostname
        path = parsed_url.path.lower()
        
        # Check subdomain vetoes
        if hostname:
            subdomain = hostname.split('.')[0].lower()
            if subdomain in VETO_SUBDOMAINS:
                category = _categorize_veto_term(subdomain)
                return True, category
        
        # Check path segment vetoes
        for segment in VETO_PATH_SEGMENTS:
            if segment in path:
                category = _categorize_veto_term(segment)
                return True, category
                    
    except Exception as e:
        log("debug", f"Error in veto check for {url}: {e}")
        return False, None  # Fail open for safety
        
    return False, None

def get_subdomain_category(url: str) -> str:
    """
    Categorizes a subdomain URL to determine appropriate link extraction limits.
    Uses centralized multilingual categorization for consistency.
    Returns category name for DISCOVERY_LINK_LIMITS lookup.
    """
    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return 'default'
            
        subdomain = parsed.hostname.split('.')[0].lower()
        
        # Use centralized categorization with comprehensive multilingual support
        category = _categorize_veto_term(subdomain)
        
        # Map to discovery limits categories (some categories need mapping)
        category_mapping = {
            'careers': 'careers',
            'news': 'news',
            'investor': 'investor',
            'about': 'about',
            'brand': 'brand',
            'corporate': 'corporate',
            'commerce': 'default',  # Shopping sites get default treatment
            'legal': 'default',     # Legal pages get default treatment
            'support': 'default',   # Support pages get default treatment
            'technical': 'default', # Technical pages get default treatment
            'other': 'default'      # Catch-all gets default treatment
        }
        
        return category_mapping.get(category, 'default')
            
    except Exception as e:
        log("debug", f"Error categorizing subdomain {url}: {e}")
        return 'default'

def get_top_links_from_subdomain(subdomain_url: str, preferred_lang: str, num_links: int = None) -> List[Tuple[str, str]]:
    """
    Performs a "surgical strike" on a subdomain to find only its top N most relevant links.
    Does NOT crawl the subdomain's sitemap to prevent noise.
    
    Args:
        subdomain_url: The subdomain URL to analyze
        preferred_lang: Language preference for scoring
        num_links: Number of links to extract (if None, uses category-based limit)
    
    Returns:
        List of (url, text) tuples for the top N links
    """
    log("info", f"🎯 Surgically striking subdomain {subdomain_url}")
    
    try:
        # Determine number of links to extract based on subdomain category
        if num_links is None:
            category = get_subdomain_category(subdomain_url)
            num_links = DISCOVERY_LINK_LIMITS.get(category, DISCOVERY_LINK_LIMITS['default'])
            log("info", f"📊 Subdomain category: {category}, extracting top {num_links} links")
        
        # Fetch only the subdomain's homepage
        _, html = fetch_page_content_robustly(subdomain_url)
        if not html:
            log("warn", f"Failed to fetch content from subdomain {subdomain_url}")
            return []
        
        # Discover links from the homepage only
        links = discover_links_from_html(html, subdomain_url)
        if not links:
            log("info", f"No links found on subdomain homepage {subdomain_url}")
            return []
        
        # Pre-filter vetoed links before scoring
        filtered_links = []
        vetoed_count = 0
        for url, text in links:
            is_vetoed, _ = is_vetoed_url(url)
            if not is_vetoed:
                filtered_links.append((url, text))
            else:
                vetoed_count += 1
                
        if vetoed_count > 0:
            log("info", f"🛡️ Pre-vetoed {vetoed_count} links from subdomain")
            
        # Score the filtered links
        scored_links = score_link_pool(filtered_links, preferred_lang)
        
        # Return the original (url, text) tuples for the top N links  
        # OPTIMIZED: URLs already cleaned, direct slicing instead of complex mapping
        result = [(link['url'], link['text']) for link in scored_links[:num_links]]
        
        log("info", f"✅ Extracted {len(result)} high-value links from subdomain")
        return result
        
    except Exception as e:
        log("warn", f"Failed surgical strike on subdomain {subdomain_url}: {e}")
        return []

# --- END: HELPER FUNCTIONS ---

# --- START: CONFIGURATION AND CONSTANTS ---
# Environment-configurable timeouts and limits
TIMEOUTS = {
    "scrapfly_request": int(os.getenv('SCRAPFLY_TIMEOUT', '180')),
    "playwright_page_load": int(os.getenv('PLAYWRIGHT_TIMEOUT', '90000')),  # in milliseconds
    "playwright_screenshot": int(os.getenv('SCREENSHOT_TIMEOUT', '60')),
    "openai_request": int(os.getenv('OPENAI_TIMEOUT', '120')),
}

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
    "HIGH_VALUE_PORTAL_THRESHOLD": 20,  # Minimum score for high-value portal detection (recalibrated)
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

# Pre-emptive Veto Configuration - Multilingual
VETO_SUBDOMAINS = [
    # English
    'careers', 'jobs', 'shop', 'store', 'legal', 'sustainability', 'esg', 
    'support', 'help', 'developer', 'api', 'docs', 'press', 'media',
    # German
    'karriere', 'rechtliche', 'recht', 'nachhaltigkeit', 'hilfe', 'entwickler',
    'presse', 'medien', 'datenschutz',
    # Spanish  
    'empleo', 'trabajo', 'tienda', 'juridico', 'sostenibilidad',
    'ayuda', 'soporte', 'desarrollador', 'prensa'
]

VETO_PATH_SEGMENTS = [
    # English
    '/careers/', '/jobs/', '/shop/', '/store/', '/legal/', '/privacy/', 
    '/sustainability/', '/esg/', '/support/', '/help/', '/faq/', '/api/',
    '/developer/', '/docs/', '/documentation/', '/press/', '/media/',
    # German
    '/karriere/', '/rechtliche/', '/recht/', '/datenschutz/', '/nachhaltigkeit/',
    '/hilfe/', '/entwickler/', '/presse/', '/medien/', '/impressum/',
    # Spanish
    '/empleo/', '/trabajo/', '/tienda/', '/juridico/', '/privacidad/',
    '/sostenibilidad/', '/ayuda/', '/soporte/', '/desarrollador/', '/prensa/'
]

# Veto exceptions - patterns that should NOT be vetoed despite matching veto keywords
VETO_EXCEPTIONS = [
    'about-sustainability',     # Company's sustainability strategy might be brand-relevant
    'legal-structure',          # Corporate governance info
    'investor-esg',            # ESG information for investors
    'brand-story',             # Even if in /media/ or /press/
    'our-approach-to',         # Often followed by sustainability, legal, etc.
    'brand-values',            # Core brand values content
    'company-culture',         # Corporate culture information
    'corporate-responsibility', # CSR strategy content
    'our-story',              # Brand narrative
    'sustainability-commitment', # Environmental/social commitments
    'legal-framework',         # Legal structure as business info
    'governance-structure',    # Corporate governance
    'brand-mission',          # Mission statements
    'company-values',         # Value propositions
    'our-purpose',            # Purpose-driven content
    'corporate-governance'     # Governance as transparency
]

# Discovery link limits for surgical strikes - comprehensive and granular
DISCOVERY_LINK_LIMITS = {
    'investor': 3,    # More links for investor relations
    'investors': 3,   # Handle both singular/plural  
    'ir': 3,
    'brand': 2,
    'branding': 2,
    'about': 2,
    'corporate': 2,
    'corp': 2,
    'group': 2,
    'news': 1,        # Limit news content
    'press': 1,
    'media': 1,
    'careers': 1,     # Minimal extraction from careers sites
    'default': 2,     # Fallback for unrecognized subdomains
    'high_value_paths': 3  # Main domain high-value path extraction
}
# --- END: CONFIGURATION AND CONSTANTS ---

# --- START: REGEX AND SCORING LOGIC ---
NEGATIVE_REGEX = [
    # --- English ---
    r"\b(log(in|out)?|sign(in|up)|register|account|my-account)\b",
    r"\b(impressum|imprint|legal|disclaimer|compliance|privacy|terms|cookies?|policy|governance|bylaws|tax[-_]strategy)\b",
    r"\b(terms[-_]of[-_]sale|conditions[-_]of[-_]sale|terms[-_]of[-_]service|general[-_]conditions)\b",
    r"\b(finder|selector|database|catalog|category|categories)\b",
    r"\b(newsletter|subscribe|subscription|unsubscribe)\b",
    r"\b(jobs?|career(s)?|vacancies|internships?|apply)\b",
    r"\b(basket|cart|checkout|shop|store|ecommerce|wishlist)\b",
    r"\b(calculator|tool|search|filter|compare)\b",
    r"\b(404|not-found|error|redirect|sitemap|robots|tracking|rss)\b",
    r"\b(faq(s)?|help|support|contact|customer[-_]service|knowledge[-_]base)\b",
    r"\b(api|developer(s)?|sdk|docs|documentation|partner(s)?|supplier(s)?|vendor(s)?|affiliate(s)?|portal)\b",
    r"\b(locations?|store[-_]finder|dealer[-_]locator|find[-_]a[-_]store)\b",
    r"\b(gallery|media[-_]kit|brand[-_]assets)\b",
    r"\b(accessibility|wcag)\b",
    r"\b(press[-_]release(s)?|news|blogs?|articles?|updates?|media|press|spotlight|stories)\b",
    r"\b(whitepapers?|case[-_]stud(y|ies)|customer[-_]stor(y|ies))\b",
    r"\b(resources?|insights?|downloads?)\b",
    r"\b(takeover|capital[-_]increase|webcast|publication|report|finances?|annual[-_]report|quarterly[-_]report|balance[-_]sheet|proxy|prospectus|statement|filings|investor[-_]deck|shareholder(s)?|stock|sec[-_]filing(s)?|financials?)\b",

    # --- German ---
    r"\b(anmelden|abmelden|registrieren|konto)\b", # Login/Account
    r"\b(datenschutz|agb|rechtliche[-_]hinweise|pflichtangaben)\b", # Legal
    r"\b(karriere|stellenangebote|bewerbung|praktikum)\b", # Careers
    r"\b(warenkorb|kasse|bestellen|einkaufen)\b", # E-commerce
    r"\b(hilfe|kontakt)\b", # Help/Contact
    r"\b(pressemitteilung|nachrichten)\b", # Press/News

    # --- Spanish ---
    r"\b(iniciar-sesion|cerrar-sesion|crear-cuenta|cuenta)\b", # Login/Account
    r"\b(aviso-legal|politica-de-privacidad|terminos|condiciones)\b", # Legal
    r"\b(empleo|trabajo|vacantes|postulaciones)\b", # Careers
    r"\b(carrito|tienda|comprar|pago|pedido)\b", # E-commerce
    r"\b(ayuda|contacto)\b", # Help/Contact
    r"\b(noticias|prensa)\b" # Press/News
]

# Temporal and Event-Based Content Detection
TEMPORAL_EVENT_REGEX = [
    # English
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
    r"\b(201[8-9]|202[0-9])\b",
    r"\b(annual|conference|forum|webinar|event)\b",
    # German
    r"\b(jan|feb|mär|apr|mai|jun|jul|aug|sep|okt|nov|dez)\b",
    r"\b(konferenz|veranstaltung)\b",
    # Spanish
    r"\b(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b",
    r"\b(conferencia|evento)\b"
]

# Pre-compile regex patterns for performance
COMPILED_PATTERNS = {}
# Additional precompiled patterns
LANGUAGE_PATH_PATTERN = re.compile(r'/[a-z]{2}/', re.IGNORECASE)
SOCIAL_FOOTER_PATTERN = re.compile(r'(social|footer|header|contact|follow|icons|menu)', re.IGNORECASE)

def _compile_patterns():
    """Pre-compile all regex patterns to improve performance."""
    global COMPILED_PATTERNS
    
    pattern_groups = {
        "identity": [r"\b(brand|marke|marca|purpose|zweck|propósito|values|werte|valores|mission|vision)\b"],
        "strategy": [r"\b(strategy|strategie|estrategia|about|über[-_]uns|sobre[-_]nosotros|company|unternehmen|empresa|who[-_]we[-_]are|wer[-_]wir[-_]sind|quienes[-_]somos)\b"],
        "operations": [r"\b(products|produkte|productos|services|leistungen|servicios|solutions|lösungen|soluciones|operations|geschäftsbereiche|operaciones|what[-_]we[-_]do)\b"],
        "culture": [r"\b(story|geschichte|historia|culture|kultur|cultura|innovation|nachhaltigkeit|sostenibilidad|responsibility|verantwortung|responsabilidad|esg)\b"],
        "people": [r"\b(leadership|führung|liderazgo|team|equipo|management|vorstand|dirección|history)\b"],
        "language": [r"/en/", r"lang=en"],
        "negative": NEGATIVE_REGEX,
        "temporal": TEMPORAL_EVENT_REGEX
    }
    
    for group_name, patterns in pattern_groups.items():
        COMPILED_PATTERNS[group_name] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

# Initialize compiled patterns with multilingual support
_compile_patterns()

# Define raw multilingual patterns for LINK_SCORE_MAP
LINK_SCORE_PATTERNS = {
    "identity": [r"\b(brand|marke|marca|purpose|zweck|propósito|values|werte|valores|mission|vision)\b"],
    "strategy": [r"\b(strategy|strategie|estrategia|about|über[-_]uns|sobre[-_]nosotros|company|unternehmen|empresa|who[-_]we[-_]are|wer[-_]wir[-_]sind|quienes[-_]somos)\b"],
    "operations": [r"\b(products|produkte|productos|services|leistungen|servicios|solutions|lösungen|soluciones|operations|geschäftsbereiche|operaciones|what[-_]we[-_]do)\b"],
    "culture": [r"\b(story|geschichte|historia|culture|kultur|cultura|innovation|nachhaltigkeit|sostenibilidad|responsibility|verantwortung|responsabilidad|esg)\b"],
    "people": [r"\b(leadership|führung|liderazgo|team|equipo|management|vorstand|dirección|history)\b"],
    "language": [r"/en/", r"lang=en"]
}

# Compile the multilingual patterns
COMPILED_LINK_PATTERNS = {}
for category, patterns in LINK_SCORE_PATTERNS.items():
    COMPILED_LINK_PATTERNS[category] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

LINK_SCORE_MAP = {
    "identity": {"patterns": COMPILED_LINK_PATTERNS["identity"], "score": 40},
    "strategy": {"patterns": COMPILED_LINK_PATTERNS["strategy"], "score": 30},
    "operations": {"patterns": COMPILED_LINK_PATTERNS["operations"], "score": 20},
    "culture": {"patterns": COMPILED_LINK_PATTERNS["culture"], "score": 10},
    "people": {"patterns": COMPILED_LINK_PATTERNS["people"], "score": 5},
    "language": {"patterns": COMPILED_LINK_PATTERNS["language"], "score": 10},
    "negative": {"patterns": COMPILED_PATTERNS["negative"], "score": -50}
}

def score_link(link_url: str, link_text: str, preferred_lang: str = 'en') -> Tuple[int, str]:
    score = 0
    rationale = []
    lower_text = link_text.lower()
    combined_text = f"{link_url} {lower_text}"

    # Language selection penalty
    language_names = ['english', 'español', 'deutsch', 'français', 'português', 'en', 'es', 'de', 'fr', 'pt']
    if lower_text in language_names:
        score -= SCORING_CONSTANTS["LANGUAGE_PENALTY"]

    # --- Language Penalty (User-Aligned) ---
    # Penalize URLs that contain a language code that is NOT the preferred one.
    lang_codes = ['/de/', '/es/', '/fr/', '/it/', '/pt/', '/ja/', '/ko/', '/zh/', '/ru/', '/nl/']
    for code in lang_codes:
        if code in link_url and code.strip('/') != preferred_lang:
            score -= 15
            rationale.append(f"Lang Penalty: -15 (non-{preferred_lang})")
            break  # Apply penalty only once

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

    # --- Temporal Penalty: Time-Sensitive Content Detection ---
    for compiled_pattern in COMPILED_PATTERNS["temporal"]:
        if compiled_pattern.search(combined_text):
            score -= 20
            rationale.append("Temporal: -20")
            break  # Apply penalty only once

    # --- Path Context Bonus: Well-Structured Corporate Paths ---
    positive_paths = ['/about/', '/who-we-are/', '/company/', '/info/', '/mission/', '/vision/', '/values/', '/leadership/']
    if any(path in link_url for path in positive_paths):
        score += 5
        rationale.append("Path Bonus: +5")

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
    
    def _make_request():
        return _scrapfly_request_inner(url, api_key, take_screenshot)
    
    try:
        # Retry transient errors with exponential backoff
        return retry_with_backoff(
            _make_request, 
            max_retries=3, 
            base_delay=1,
            exceptions=(httpx.TimeoutException, httpx.ConnectError, httpx.RequestError)
        )
    except httpx.HTTPStatusError as e:
        # Don't retry client errors (4xx)
        return _handle_scrapfly_error(url, e)
    except Exception as e:
        # Other non-transient issues
        return _handle_scrapfly_error(url, e)

def _scrapfly_request_inner(url: str, api_key: str, take_screenshot: bool):
    # Note: Not specifying "format" parameter means Scrapfly returns raw HTML in result.content
    params = {"key": api_key, "url": url, "render_js": True, "asp": True, "auto_scroll": True, "wait_for_selector": "footer a, nav a, main a, [role='main'] a, [class*='footer'] a", "rendering_stage": "domcontentloaded", "rendering_wait": 3000, "retry": True, "country": "us", "proxy_pool": "public_residential_pool"}
    if take_screenshot:
        params["screenshots[main]"] = "fullpage"
        params["screenshot_flags"] = "load_images,block_banners"
    with httpx.Client(proxies=None) as client:
        response = client.get("https://api.scrapfly.io/scrape", params=params, timeout=TIMEOUTS["scrapfly_request"])
        response.raise_for_status()
        data = response.json()
        
        # Track API usage for cost monitoring
        track_api_usage("scrapfly", pages=1)
        
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
            img_response = client.get(screenshot_url, params={"key": api_key}, timeout=TIMEOUTS["playwright_screenshot"])
            img_response.raise_for_status()
            
            # Enhanced diagnostic logging for screenshot
            image_bytes = img_response.content
            screenshot_b64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Detect image format and dimensions from raw bytes
            image_info = "unknown format"
            try:
                if image_bytes.startswith(b'\xff\xd8\xff'):
                    image_info = "JPEG format"
                elif image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                    image_info = "PNG format"
                elif image_bytes.startswith(b'RIFF') and b'WEBP' in image_bytes[:20]:
                    image_info = "WEBP format"
            except:
                pass
                
            log("info", f"✅ SCRAPFLY SCREENSHOT SUCCESS: {len(image_bytes)} bytes, {image_info}")
            log("info", f"📊 SCRAPFLY SCREENSHOT ENCODING: {len(screenshot_b64)} base64 chars")
            
            # Log screenshot dimensions if available from Scrapfly response
            if "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
                screenshot_meta = data["result"]["screenshots"]["main"]
                if "size" in screenshot_meta:
                    log("info", f"📏 SCRAPFLY SCREENSHOT METADATA: {screenshot_meta.get('size', 'unknown')} bytes, format: {screenshot_meta.get('format', 'unknown')}, extension: {screenshot_meta.get('extension', 'unknown')}")
        elif take_screenshot:
            log("error", f"❌ SCRAPFLY SCREENSHOT MISSING: screenshots={data['result'].get('screenshots', 'NOT_FOUND')}")
        return screenshot_b64, html_content

def _handle_scrapfly_error(url: str, e: Exception) -> Tuple[None, None]:
    """Handle different types of Scrapfly errors with appropriate logging."""
    if isinstance(e, httpx.TimeoutException):
        log("warn", f"⏱️ SCRAPFLY TIMEOUT for {url}: Request timed out after {TIMEOUTS['scrapfly_request']}s")
    elif isinstance(e, httpx.ConnectError):
        log("warn", f"🔌 SCRAPFLY CONNECTION ERROR for {url}: Unable to connect to Scrapfly service")
    elif isinstance(e, httpx.RequestError):
        log("warn", f"📡 SCRAPFLY REQUEST ERROR for {url}: Network or request issue - {type(e).__name__}")
    elif isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code == 429:
            log("warn", f"🚫 SCRAPFLY RATE LIMIT for {url}: Too many requests")
        elif e.response.status_code == 422:
            log("warn", f"❌ SCRAPFLY VALIDATION ERROR for {url}: {e.response.text[:200]}")
        elif e.response.status_code >= 500:
            log("warn", f"🚨 SCRAPFLY SERVER ERROR {e.response.status_code} for {url}: Service temporarily unavailable")
        else:
            log("error", f"❌ SCRAPFLY HTTP ERROR {e.response.status_code} for {url}: {e.response.text[:200]}")
    else:
        error_msg = str(e)
        if "UNABLE_TO_TAKE_SCREENSHOT" in error_msg:
            log("warn", f"⏱️ SCRAPFLY SCREENSHOT TIMEOUT for {url}: Screenshot budget exceeded")
            log("info", f"🔄 FALLING BACK TO PLAYWRIGHT for screenshot capture")
        else:
            log("error", f"❌ SCRAPFLY UNEXPECTED ERROR for {url}: {type(e).__name__}: {e}")
    return None, None

def fetch_html_with_playwright(url: str, retried: bool = False, take_screenshot: bool = False) -> Tuple[Optional[str], Optional[str]]:
    log("info", f"Activating Playwright fallback for URL: {url} (Screenshot: {take_screenshot})")
    try:
        browser = get_shared_playwright_browser()
        context = browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = context.new_page()
        
        # Block unnecessary resources for faster loading
        page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot}", lambda route: route.abort())
        page.route("**/analytics/**", lambda route: route.abort())
        page.route("**/googletagmanager/**", lambda route: route.abort())
        
        page.goto(url, wait_until="load", timeout=TIMEOUTS["playwright_page_load"])
        prepare_page_for_capture(page)
        
        html_content = page.content()
        screenshot_b64 = None
        
        if take_screenshot:
            try:
                # Re-enable images for screenshot
                page.route("**/*", lambda route: route.continue_())
                page.reload(wait_until="networkidle")
                screenshot_bytes = page.screenshot(full_page=True, type='png')
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                log("info", f"✅ PLAYWRIGHT SCREENSHOT SUCCESS: {len(screenshot_b64)} bytes for {url}")
            except Exception as e:
                log("error", f"❌ PLAYWRIGHT SCREENSHOT FAILED for {url}: {e}")
        
        context.close()
        return screenshot_b64, html_content
    except Exception as e:
        log("error", f"Playwright failed for {url}: {e}")
        if "browser has crashed" in str(e).lower() and not retried:
            log("warn", "Restarting Playwright browser...")
            close_shared_playwright_browser()
            return fetch_html_with_playwright(url, retried=True, take_screenshot=take_screenshot)
        return None, None

def fetch_page_content_robustly(url: str, take_screenshot: bool = False) -> Tuple[Optional[str], Optional[str]]:
    MAX_HTML_SIZE = 10 * 1024 * 1024  # 10MB limit
    
    try:
        screenshot, html = _fetch_page_data_scrapfly(url, take_screenshot=take_screenshot)
        
        # Check and limit HTML size to prevent memory issues
        if html and len(html) > MAX_HTML_SIZE:
            log("warn", f"📄 HTML CONTENT TOO LARGE for {url}: {len(html)} bytes, truncating to {MAX_HTML_SIZE}")
            html = html[:MAX_HTML_SIZE]
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

# Enhanced cache with size limits and LRU eviction
class LimitedCache:
    def __init__(self, max_size_mb=100, max_items=1000):
        self._cache = {}
        self._access_times = {}
        self._sizes = {}
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_items = max_items
        self.total_size = 0
        self._lock = None
        try:
            import threading
            self._lock = threading.Lock()
        except:
            pass
    
    def __setitem__(self, key, value):
        if self._lock:
            with self._lock:
                self._set_item(key, value)
        else:
            self._set_item(key, value)
    
    def _set_item(self, key, value):
        # Calculate size
        size = len(value) if isinstance(value, (str, bytes)) else len(str(value))
        
        # Remove old value if exists
        if key in self._cache:
            self.total_size -= self._sizes.get(key, 0)
        
        # Evict if necessary
        while (self.total_size + size > self.max_size_bytes or 
               len(self._cache) >= self.max_items) and self._cache:
            self._evict_lru()
        
        # Add new item
        self._cache[key] = value
        self._sizes[key] = size
        self._access_times[key] = time.time()
        self.total_size += size
    
    def __getitem__(self, key):
        if self._lock:
            with self._lock:
                return self._get_item(key)
        else:
            return self._get_item(key)
    
    def _get_item(self, key):
        if key in self._cache:
            self._access_times[key] = time.time()
            return self._cache[key]
        raise KeyError(key)
    
    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
    
    def __contains__(self, key):
        return key in self._cache
    
    def __len__(self):
        return len(self._cache)
    
    def __delitem__(self, key):
        if self._lock:
            with self._lock:
                self._del_item(key)
        else:
            self._del_item(key)
    
    def _del_item(self, key):
        if key in self._cache:
            self.total_size -= self._sizes.get(key, 0)
            del self._cache[key]
            del self._access_times[key]
            del self._sizes[key]
    
    def _evict_lru(self):
        """Evict least recently used item."""
        if not self._cache:
            return
        
        lru_key = min(self._access_times.keys(), key=self._access_times.get)
        self._del_item(lru_key)
        log("debug", f"Cache evicted LRU item: {lru_key}")
    
    def items(self):
        return self._cache.items()
    
    def get_stats(self):
        """Get cache statistics."""
        return {
            "items": len(self._cache),
            "size_mb": self.total_size / (1024 * 1024),
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "max_items": self.max_items
        }

# Configure cache limits via environment variables
CACHE_MAX_SIZE_MB = int(os.getenv("CACHE_MAX_SIZE_MB", "100"))
CACHE_MAX_ITEMS = int(os.getenv("CACHE_MAX_ITEMS", "1000"))

SHARED_CACHE = LimitedCache(max_size_mb=CACHE_MAX_SIZE_MB, max_items=CACHE_MAX_ITEMS)
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
    
    # Validate veto configuration
    try:
        # Check for duplicates in veto subdomains
        if len(VETO_SUBDOMAINS) != len(set(VETO_SUBDOMAINS)):
            duplicates = [x for x in VETO_SUBDOMAINS if VETO_SUBDOMAINS.count(x) > 1]
            errors.append(f"VETO_SUBDOMAINS contains duplicates: {list(set(duplicates))}")
        
        # Check for duplicates in veto path segments
        if len(VETO_PATH_SEGMENTS) != len(set(VETO_PATH_SEGMENTS)):
            duplicates = [x for x in VETO_PATH_SEGMENTS if VETO_PATH_SEGMENTS.count(x) > 1]
            errors.append(f"VETO_PATH_SEGMENTS contains duplicates: {list(set(duplicates))}")
        
        # Validate path segment format
        for segment in VETO_PATH_SEGMENTS:
            if not isinstance(segment, str):
                errors.append(f"Path segment must be string, got: {type(segment)} - {segment}")
            elif not segment.startswith('/') or not segment.endswith('/'):
                errors.append(f"Path segment '{segment}' should be wrapped in slashes (e.g., '/careers/')")
            elif len(segment) < 3:  # At least '/x/'
                errors.append(f"Path segment '{segment}' is too short (minimum: '/x/')")
        
        # Validate subdomain entries
        for subdomain in VETO_SUBDOMAINS:
            if not isinstance(subdomain, str):
                errors.append(f"Subdomain must be string, got: {type(subdomain)} - {subdomain}")
            elif '.' in subdomain:
                errors.append(f"Subdomain '{subdomain}' should not contain dots (just the subdomain part)")
            elif len(subdomain.strip()) == 0:
                errors.append("Empty subdomain found in VETO_SUBDOMAINS")
        
        # Validate exception patterns
        for exception in VETO_EXCEPTIONS:
            if not isinstance(exception, str):
                errors.append(f"Exception pattern must be string, got: {type(exception)} - {exception}")
            elif len(exception.strip()) == 0:
                errors.append("Empty exception pattern found in VETO_EXCEPTIONS")
        
        # Validate discovery link limits
        for category, limit in DISCOVERY_LINK_LIMITS.items():
            if not isinstance(limit, int):
                errors.append(f"DISCOVERY_LINK_LIMITS['{category}'] must be integer, got: {limit}")
            elif limit < 0:
                errors.append(f"DISCOVERY_LINK_LIMITS['{category}'] must be non-negative, got: {limit}")
            elif limit > 10:
                errors.append(f"DISCOVERY_LINK_LIMITS['{category}'] unusually high ({limit}), recommend ≤ 10 for efficiency")
                
    except Exception as e:
        errors.append(f"Error validating veto configuration: {e}")
    
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
# Use persistent storage directory - configure via environment variable
PERSISTENT_DATA_DIR = os.getenv("PERSISTENT_DATA_DIR", "/data")
os.makedirs(PERSISTENT_DATA_DIR, exist_ok=True)
FEEDBACK_FILE = os.path.join(PERSISTENT_DATA_DIR, "feedback_log.jsonl")

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

# --- START: COST TRACKING ---
COST_LOG_FILE = os.path.join(PERSISTENT_DATA_DIR, "api_costs.jsonl")

# Approximate costs per API call (update these based on current pricing)
API_COSTS = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},  # per 1K tokens
    "gpt-4o-vision": {"input": 0.005, "output": 0.015},  # per 1K tokens
    "scrapfly": 0.001,  # per page
    "playwright": 0.0  # free but resource intensive
}

def track_api_usage(api_type: str, tokens_in: int = 0, tokens_out: int = 0, pages: int = 0):
    """Track API usage and estimated costs."""
    cost = 0
    details = {"api_type": api_type, "timestamp": time.time()}
    
    if api_type.startswith("gpt"):
        details["tokens_in"] = tokens_in
        details["tokens_out"] = tokens_out
        cost = (tokens_in / 1000 * API_COSTS.get(api_type, {}).get("input", 0) +
                tokens_out / 1000 * API_COSTS.get(api_type, {}).get("output", 0))
    elif api_type == "scrapfly":
        details["pages"] = pages
        cost = pages * API_COSTS.get("scrapfly", 0)
    
    details["estimated_cost"] = cost
    
    # Atomic write to cost log
    temp_file = f"{COST_LOG_FILE}.tmp.{uuid.uuid4()}"
    try:
        with open(temp_file, "w") as f:
            f.write(json.dumps(details) + "\n")
        
        # Append to existing log
        with open(COST_LOG_FILE, "a") as f:
            with open(temp_file, "r") as tmp:
                f.write(tmp.read())
    except Exception as e:
        log("error", f"Failed to track API cost: {e}")
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    # Alert if costs exceed threshold
    if cost > 1.0:  # $1 per call threshold
        log("warn", f"High cost API call: ${cost:.2f} for {api_type}")
    
    return cost

def get_cost_summary(hours: int = 24) -> dict:
    """Get cost summary for the last N hours."""
    if not os.path.exists(COST_LOG_FILE):
        return {"error": "No cost data available"}
    
    cutoff_time = time.time() - (hours * 3600)
    costs = {"total": 0, "by_api": {}, "high_cost_calls": []}
    
    try:
        with open(COST_LOG_FILE, "r") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry["timestamp"] > cutoff_time:
                        costs["total"] += entry.get("estimated_cost", 0)
                        api = entry["api_type"]
                        costs["by_api"][api] = costs["by_api"].get(api, 0) + entry.get("estimated_cost", 0)
                        
                        if entry.get("estimated_cost", 0) > 0.5:
                            costs["high_cost_calls"].append(entry)
    except Exception as e:
        log("error", f"Failed to analyze costs: {e}")
    
    return costs

# --- END: COST TRACKING ---

# --- START: DATA RETENTION ---
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "90"))  # Default 90 days
CLEANUP_BATCH_SIZE = 1000  # Process in batches to avoid memory issues

def cleanup_old_logs(log_file: str, retention_days: int = RETENTION_DAYS):
    """Remove log entries older than retention period."""
    if not os.path.exists(log_file):
        return 0, 0
    
    cutoff_time = time.time() - (retention_days * 86400)
    temp_file = f"{log_file}.cleanup.{uuid.uuid4()}"
    
    kept_count = 0
    removed_count = 0
    
    try:
        with open(temp_file, "w") as out_file:
            with open(log_file, "r") as in_file:
                batch = []
                for line in in_file:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            if entry.get("timestamp", 0) > cutoff_time:
                                batch.append(line)
                                kept_count += 1
                            else:
                                removed_count += 1
                            
                            # Write batch to avoid memory issues
                            if len(batch) >= CLEANUP_BATCH_SIZE:
                                out_file.writelines(batch)
                                batch = []
                        except json.JSONDecodeError:
                            # Keep malformed entries
                            batch.append(line)
                            kept_count += 1
                
                # Write remaining batch
                if batch:
                    out_file.writelines(batch)
        
        # Atomic replace
        if removed_count > 0:
            os.rename(temp_file, log_file)
            log("info", f"Data retention cleanup: removed {removed_count} old entries, kept {kept_count}")
        else:
            os.unlink(temp_file)
            log("debug", f"Data retention: no old entries to remove")
        
        return kept_count, removed_count
        
    except Exception as e:
        log("error", f"Data retention cleanup failed: {e}")
        if os.path.exists(temp_file):
            os.unlink(temp_file)
        return -1, -1

def run_retention_cleanup():
    """Run data retention cleanup for all log files."""
    log_files = [
        (FEEDBACK_FILE, "feedback"),
        (COST_LOG_FILE, "costs")
    ]
    
    for log_file, log_type in log_files:
        if os.path.exists(log_file):
            kept, removed = cleanup_old_logs(log_file)
            if kept >= 0:
                log("info", f"Retention cleanup for {log_type}: kept {kept}, removed {removed} entries")

# Schedule cleanup on startup
import threading
def schedule_retention_cleanup():
    """Schedule periodic retention cleanup."""
    def cleanup_task():
        while True:
            try:
                run_retention_cleanup()
            except Exception as e:
                log("error", f"Retention cleanup scheduler error: {e}")
            
            # Run daily
            time.sleep(86400)
    
    cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
    cleanup_thread.start()
    log("info", f"Data retention cleanup scheduled (retention: {RETENTION_DAYS} days)")

# --- END: DATA RETENTION ---

# Initialize data retention cleanup after all functions are defined
try:
    schedule_retention_cleanup()
except Exception as e:
    log("error", f"Failed to initialize retention cleanup: {e}")

# --- START: METRICS TRACKING ---
METRICS_FILE = os.path.join(PERSISTENT_DATA_DIR, "scan_metrics.jsonl")

def track_scan_metric(scan_id: str, event_type: str, details: dict = None):
    """Track scan metrics for analytics."""
    metric_entry = {
        "timestamp": time.time(),
        "scan_id": scan_id,
        "event_type": event_type,  # "started", "completed", "failed", "cancelled"
        "details": details or {}
    }
    
    # Atomic write
    temp_file = f"{METRICS_FILE}.tmp.{uuid.uuid4()}"
    try:
        with open(temp_file, "w") as f:
            f.write(json.dumps(metric_entry) + "\n")
        
        # Append to metrics log
        with open(METRICS_FILE, "a") as f:
            with open(temp_file, "r") as tmp:
                f.write(tmp.read())
    except Exception as e:
        log("error", f"Failed to track metric: {e}")
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)

def get_scan_metrics(hours: int = 24) -> dict:
    """Get scan metrics for the last N hours."""
    if not os.path.exists(METRICS_FILE):
        return {"error": "No metrics data available"}
    
    cutoff_time = time.time() - (hours * 3600)
    metrics = {
        "total_scans": 0,
        "completed": 0,
        "failed": 0,
        "cancelled": 0,
        "completion_rate": 0.0,
        "avg_duration": 0.0,
        "by_hour": defaultdict(lambda: {"started": 0, "completed": 0})
    }
    
    scans = {}
    
    try:
        with open(METRICS_FILE, "r") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry["timestamp"] > cutoff_time:
                        scan_id = entry["scan_id"]
                        event_type = entry["event_type"]
                        
                        if scan_id not in scans:
                            scans[scan_id] = {"started": None, "completed": None, "status": "unknown"}
                        
                        if event_type == "started":
                            scans[scan_id]["started"] = entry["timestamp"]
                            metrics["total_scans"] += 1
                            
                            # Track by hour
                            hour = time.strftime("%Y-%m-%d %H:00", time.localtime(entry["timestamp"]))
                            metrics["by_hour"][hour]["started"] += 1
                            
                        elif event_type == "completed":
                            scans[scan_id]["completed"] = entry["timestamp"]
                            scans[scan_id]["status"] = "completed"
                            metrics["completed"] += 1
                            
                            hour = time.strftime("%Y-%m-%d %H:00", time.localtime(entry["timestamp"]))
                            metrics["by_hour"][hour]["completed"] += 1
                            
                        elif event_type == "failed":
                            scans[scan_id]["status"] = "failed"
                            metrics["failed"] += 1
                            
                        elif event_type == "cancelled":
                            scans[scan_id]["status"] = "cancelled"
                            metrics["cancelled"] += 1
        
        # Calculate completion rate and average duration
        if metrics["total_scans"] > 0:
            metrics["completion_rate"] = metrics["completed"] / metrics["total_scans"]
            
            # Calculate average duration for completed scans
            durations = []
            for scan_data in scans.values():
                if scan_data["started"] and scan_data["completed"]:
                    duration = scan_data["completed"] - scan_data["started"]
                    durations.append(duration)
            
            if durations:
                metrics["avg_duration"] = sum(durations) / len(durations)
        
        # Convert defaultdict to regular dict for JSON serialization
        metrics["by_hour"] = dict(metrics["by_hour"])
        
    except Exception as e:
        log("error", f"Failed to analyze metrics: {e}")
        return {"error": str(e)}
    
    return metrics

# --- END: METRICS TRACKING ---

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
    
    # FIX: More aggressive and reliable scrolling to trigger all lazy-loaded content
    log("info", "🔄 Starting aggressive scroll to trigger lazy loading...")
    page.evaluate("""
        async () => {
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            const maxScrolls = 75; // Increased scroll attempts for very long pages
            let lastHeight = -1;
            let scrolls = 0;

            while (scrolls < maxScrolls) {
                window.scrollBy(0, 800);
                await sleep(150); // Increased wait time for content to load
                let newHeight = document.body.scrollHeight;
                if (newHeight === lastHeight) {
                    break; // Stop if we're not getting any new content
                }
                lastHeight = newHeight;
                scrolls++;
            }
            // Final scroll to the absolute bottom, then back to the top
            window.scrollTo(0, document.body.scrollHeight);
            await sleep(500);
            window.scrollTo(0, 0);
            await sleep(200);
        }
    """)
    log("info", "✅ Aggressive scroll complete.")
    
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
                class_=SOCIAL_FOOTER_PATTERN
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

def find_high_value_paths(discovered_links: List[Tuple[str, str]], initial_url: str, preferred_lang: str = 'en', max_paths: int = None) -> List[Tuple[str, str]]:
    """
    Tier 3: High-Value Path Strike - Extract the most valuable paths from the main domain.
    
    This function implements targeted path discovery for brand-relevant content
    from the main domain, filtering out noise and focusing on memorability factors.
    
    Args:
        discovered_links: All discovered links from the domain
        initial_url: The base URL being scanned
        preferred_lang: Language preference for scoring
        max_paths: Maximum number of paths to return (uses category-based defaults if None)
    
    Returns:
        List of (url, text) tuples for the highest-value paths from main domain
    """
    log("info", f"🎯 Tier 3: High-Value Path Strike on main domain")
    
    try:
        if max_paths is None:
            max_paths = DISCOVERY_LINK_LIMITS.get('default', 15)
            
        initial_netloc = urlparse(initial_url).netloc.lower()
        
        # Filter to only same-domain paths (not subdomains)
        same_domain_links = []
        different_domain_count = 0
        
        for url, text in discovered_links:
            try:
                link_netloc = urlparse(url).netloc.lower()
                if link_netloc == initial_netloc:
                    same_domain_links.append((url, text))
                else:
                    different_domain_count += 1
            except Exception as e:
                log("debug", f"Error parsing URL {url}: {e}")
                continue
        
        log("info", f"📊 Found {len(same_domain_links)} same-domain paths, filtered out {different_domain_count} cross-domain links")
        
        if not same_domain_links:
            log("warn", f"No same-domain paths found for {initial_url}")
            return []
        
        # Pre-filter vetoed paths before scoring for performance
        filtered_paths = []
        vetoed_count = 0
        vetoed_by_category = {}
        
        for url, text in same_domain_links:
            is_vetoed, veto_category = is_vetoed_url(url)
            if not is_vetoed:
                filtered_paths.append((url, text))
            else:
                vetoed_count += 1
                if veto_category:
                    vetoed_by_category[veto_category] = vetoed_by_category.get(veto_category, 0) + 1
        
        if vetoed_count > 0:
            log("info", f"🛡️ Path-level veto: Filtered {vetoed_count} paths from main domain")
            for category, count in vetoed_by_category.items():
                log("debug", f"  - {category}: {count} paths vetoed")
        
        if not filtered_paths:
            log("warn", f"All paths on main domain were vetoed - returning empty list")
            return []
        
        # Score and select top paths
        scored_paths = score_link_pool(filtered_paths, preferred_lang)
        
        # Return top N paths using optimized O(n) mapping
        top_urls = {link['url'] for link in scored_paths[:max_paths]}
        clean_url_to_original = {_clean_url(url): (url, text) for url, text in filtered_paths}
        result = [clean_url_to_original[url] for url in top_urls if url in clean_url_to_original]
        
        log("info", f"✅ High-Value Path Strike: Selected {len(result)} top paths from {len(filtered_paths)} candidates")
        return result
        
    except Exception as e:
        log("warn", f"Failed high-value path extraction for {initial_url}: {e}")
        return []

def normalize_netloc(netloc: str) -> str:
    """
    Normalize domain for comparison by removing www. prefix.
    This treats www.example.com and example.com as the same domain.
    
    Examples:
        www.basf.com -> basf.com
        basf.com -> basf.com
        investor.basf.com -> investor.basf.com (unchanged)
    """
    if netloc and netloc.startswith('www.'):
        return netloc[4:]
    return netloc

def find_high_value_subdomain(discovered_links: List[Tuple[str, str]], initial_url: str, preferred_lang: str = 'en') -> Optional[str]:
    """
    Finds a high-value corporate portal on a DIFFERENT SUBDOMAIN.
    This is a strict check to prevent false positives from paths on the same domain.
    
    CRITICAL FIX: Now normalizes www. prefix to treat www.example.com and example.com as the same domain.
    """
    log("info", "🔍 Searching for high-value subdomains...")
    best_candidate = None
    highest_score = -1
    
    try:
        initial_netloc = urlparse(initial_url).netloc
        initial_netloc_normalized = normalize_netloc(initial_netloc)
        log("info", f"🔍 Searching for subdomains different from: {initial_netloc} (normalized: {initial_netloc_normalized})")
    except Exception:
        return None # Cannot proceed with an invalid initial URL

    vetoed_links = defaultdict(int)
    same_domain_paths = 0
    different_subdomains = 0

    for link_url, link_text in discovered_links:
        try:
            link_netloc = urlparse(link_url).netloc
            link_netloc_normalized = normalize_netloc(link_netloc)
            
            # --- CRITICAL FIX: Compare NORMALIZED domains to handle www. prefix ---
            if link_netloc_normalized == initial_netloc_normalized:
                same_domain_paths += 1
                # Log first few for debugging
                if same_domain_paths <= 3:
                    log("debug", f"SAME DOMAIN (normalized): {link_url} -> '{link_netloc}' normalized to '{link_netloc_normalized}' == '{initial_netloc_normalized}'")
                continue
            
            # Check if it's a true subdomain (different normalized netloc but same root domain)
            if link_netloc and link_netloc_normalized != initial_netloc_normalized and _is_same_root_word_domain(initial_url, link_url):
                different_subdomains += 1
                log("debug", f"DIFFERENT SUBDOMAIN: {link_url} -> '{link_netloc}' normalized to '{link_netloc_normalized}' != '{initial_netloc_normalized}'")
                
                # Now that we know it's a true subdomain, check if it's vetoed.
                is_vetoed, category = is_vetoed_url(link_url)
                if is_vetoed:
                    vetoed_links[category] += 1
                    continue
                
                score, _ = score_link(link_url, link_text, preferred_lang)
                if score > highest_score:
                    highest_score = score
                    best_candidate = link_url
        except Exception:
            continue
    
    log("info", f"📊 Subdomain Analysis: {same_domain_paths} same-domain paths rejected, {different_subdomains} different subdomains found")

    if vetoed_links:
        log("info", f"🛡️ Vetoed {sum(vetoed_links.values())} subdomain links: {dict(vetoed_links)}")

    if highest_score > SCORING_CONSTANTS["HIGH_VALUE_PORTAL_THRESHOLD"]:
        # NUCLEAR SAFETY VALVE: Final validation before returning
        if best_candidate:
            result_netloc = urlparse(best_candidate).netloc
            result_netloc_normalized = normalize_netloc(result_netloc)
            if result_netloc_normalized == initial_netloc_normalized:
                log("error", f"🚨 CRITICAL BUG DETECTED: About to return same-domain URL as 'subdomain'!")
                log("error", f"🚨 URL: {best_candidate}")
                log("error", f"🚨 Initial netloc: {initial_netloc} (normalized: {initial_netloc_normalized})")
                log("error", f"🚨 Result netloc: {result_netloc} (normalized: {result_netloc_normalized})")
                return None  # Refuse to return false positive
        
        log("info", f"🎯 Found high-value subdomain: {best_candidate} (Score: {highest_score})")
        return best_candidate
    else:
        log("info", "📍 No high-value subdomains found.")
        return None

def find_true_corporate_site(discovered_links: List[Tuple[str, str]], initial_url: str) -> Optional[str]:
    """Proactively search for a link to the true global/corporate site on a different TLD.
    
    This function implements the "Global Site Heuristic" - a tenacious discovery step
    that looks for corporate headquarters sites when scanning regional domains.
    
    Args:
        discovered_links: List of (url, text) tuples from initial link discovery
        initial_url: The original URL being scanned
    
    Returns:
        URL of the true corporate site if found, None otherwise
    """
    log("info", "🌍 Proactively searching for a global corporate site link...")
    initial_tld = _get_sld(initial_url).split('.')[-1]
    
    # Enhanced corporate signal strength mapping
    CORPORATE_SIGNALS = {
        'global': 10, 'international': 8, 'corporate': 7, 'worldwide': 8,
        'company site': 6, 'headquarters': 6, 'company': 5, 'main site': 5,
        'english': 4, 'us site': 4, 'america': 3
    }
    
    # Corporate TLD patterns - regional to global mappings
    CORPORATE_TLD_PATTERNS = {
        '.de': ['.com', '.global', '.org', '.net'],
        '.fr': ['.com', '.global', '.org', '.net'], 
        '.uk': ['.com', '.global', '.org', '.net'],
        '.it': ['.com', '.global', '.org', '.net'],
        '.es': ['.com', '.global', '.org', '.net'],
        '.jp': ['.com', '.global', '.org', '.net'],
        '.cn': ['.com', '.global', '.org', '.net']
    }
    
    best_candidate = None
    highest_signal_strength = 0
    
    for url, text in discovered_links:
        try:
            text_lower = text.lower().strip()
            
            # Calculate signal strength based on link text
            signal_strength = 0
            for signal, weight in CORPORATE_SIGNALS.items():
                if signal in text_lower:
                    signal_strength += weight
                    log("debug", f"Corporate signal '{signal}' found in '{text}' (+{weight})")
            
            # Only proceed if we have a strong corporate signal
            if signal_strength >= 5:  # Minimum threshold for corporate signals
                try:
                    link_tld = _get_sld(url).split('.')[-1]
                    target_tlds = CORPORATE_TLD_PATTERNS.get(initial_tld, ['.com'])
                    
                    # Check if it's a different TLD but same root company
                    if link_tld in target_tlds and link_tld != initial_tld:
                        if _is_same_root_word_domain(initial_url, url):
                            # Bonus for .com (most common global TLD)
                            if link_tld == 'com':
                                signal_strength += 3
                            
                            if signal_strength > highest_signal_strength:
                                highest_signal_strength = signal_strength
                                best_candidate = url
                                log("info", f"🎯 Strong corporate site candidate: {url} (signal strength: {signal_strength})")
                    
                except Exception as e:
                    log("debug", f"Error processing URL {url}: {e}")
                    continue
        except Exception as e:
            log("debug", f"Error processing link text '{text}': {e}")
            continue
    
    if best_candidate and highest_signal_strength >= 7:  # High confidence threshold
        log("info", f"✅ Found high-confidence global corporate site: {best_candidate} (strength: {highest_signal_strength})")
        return best_candidate
    elif best_candidate:
        log("info", f"🔍 Found potential corporate site: {best_candidate} (strength: {highest_signal_strength}) - but confidence too low")
    else:
        log("info", "📍 No global corporate site link found in discovered links")
    
    return None

def discover_links_from_sitemap(homepage_url: str, preferred_lang: str = 'en') -> Optional[List[Tuple[str, str]]]:
    """Discover links from sitemap using preferred language as source of truth.
    
    Args:
        homepage_url: The base URL to search for sitemaps
        preferred_lang: The preferred language code (default: 'en') - drives all decisions
    
    Returns:
        List of (url, title) tuples from sitemap, or None if no sitemap found
    """
    log("info", "Attempting to discover links from sitemap...")
    sitemap_urls = [urljoin(homepage_url, "/sitemap.xml")]
    
    try:
        client = get_shared_http_client()
        response = client.get(sitemap_urls[0], timeout=20)
        response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError):
        log("warn", f"/sitemap.xml not found or failed. Checking robots.txt as a fallback.")
        robots_sitemaps = find_sitemap_from_robots_txt(homepage_url)
        if not robots_sitemaps:
            log("warn", "Sitemap not found in /sitemap.xml or robots.txt.")
            return None
        sitemap_urls = robots_sitemaps
    
    # Process all sitemap URLs, prioritizing based on preferred_lang
    all_links = []
    processed_sitemaps = []
    
    for sitemap_url in sitemap_urls:
        try:
            log("info", f"Processing sitemap: {sitemap_url}")
            client = get_shared_http_client()
            response = client.get(sitemap_url, timeout=20)
            response.raise_for_status()
            
            content = response.content
            namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            root = ET.fromstring(content)

            if root.tag.endswith('sitemapindex'):
                log("info", "Sitemap index found. Searching for the best page-sitemap...")
                sitemaps = [elem.text for elem in root.findall('sm:sitemap/sm:loc', namespace)]

                # IMPROVED: Intelligent sitemap scoring aligned with preferred language
                scored_sitemaps = []
                for sm_url in sitemaps:
                    score = 0
                    # Heavily prioritize global/corporate sitemaps
                    if "global" in sm_url or "corporate" in sm_url: score += 150
                    if "main" in sm_url or "pages" in sm_url: score += 50
                    # Use preferred_lang parameter for language bonus
                    if f"/{preferred_lang}" in sm_url: score += 25
                    
                    # Penalize non-preferred language sitemaps
                    if LANGUAGE_PATH_PATTERN.search(sm_url) and not f"/{preferred_lang}" in sm_url: score -= 50
                    
                    # Additional preferences for brand-relevant content
                    if any(keyword in sm_url for keyword in ['page', 'post', 'company', 'about', 'article']): score += 25
                    
                    scored_sitemaps.append((sm_url, score))
                    log("debug", f"Sitemap {sm_url} scored {score}")
                
                # Sort by score and process the best sitemaps
                scored_sitemaps.sort(key=lambda x: x[1], reverse=True)
                best_sitemap_url = scored_sitemaps[0][0] if scored_sitemaps else None
                
                if best_sitemap_url:
                    log("info", f"Fetching prioritized sub-sitemap: {best_sitemap_url} (Score: {scored_sitemaps[0][1]})")
                    client = get_shared_http_client()
                    response = client.get(best_sitemap_url, timeout=20)
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                else:
                    log("warn", "No suitable sitemap found in sitemap index.")
                    continue

            urls = [elem.text for elem in root.findall('sm:url/sm:loc', namespace)]
            if urls:
                # Pre-filter vetoed URLs from sitemap
                vetoed_count = 0
                vetoed_by_category = {}
                filtered_links = []
                
                for url in urls:
                    is_vetoed, veto_category = is_vetoed_url(url)
                    if not is_vetoed:
                        filtered_links.append((url, url.split('/')[-1].replace('-', ' ')))
                    else:
                        vetoed_count += 1
                        if veto_category:
                            vetoed_by_category[veto_category] = vetoed_by_category.get(veto_category, 0) + 1
                
                all_links.extend(filtered_links)
                processed_sitemaps.append(sitemap_url)
                
                # Log results with veto transparency
                if vetoed_count > 0:
                    log("info", f"🛡️ Sitemap {sitemap_url}: Found {len(urls)} links, vetoed {vetoed_count} ({dict(vetoed_by_category)}), kept {len(filtered_links)}")
                else:
                    log("info", f"Found {len(filtered_links)} links in sitemap: {sitemap_url}")
        
        except Exception as e:
            log("warn", f"Failed to process sitemap {sitemap_url}: {e}")
            continue
    
    if not all_links:
        log("warn", "No links found in any sitemap.")
        return None

    log("info", f"Total found {len(all_links)} links from {len(processed_sitemaps)} sitemap(s)")
    return all_links

def discover_links_from_html(html: str, base_url: str) -> List[Tuple[str, str]]:
    """Extracts links from raw HTML content with optimized parsing."""
    # PERFORMANCE OPTIMIZATION: Parse only <a> tags instead of full DOM
    from bs4 import SoupStrainer
    parse_only = SoupStrainer("a", href=True)
    soup = BeautifulSoup(html, "html.parser", parse_only=parse_only)
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
            # PERFORMANCE OPTIMIZATION: Clean URLs once during discovery, not during scoring
            cleaned_url = _clean_url(link_url)
            links.append((cleaned_url, a.get_text(strip=True)))
    
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
        # Track API usage
        if hasattr(response, 'usage'):
            track_api_usage("gpt-4o", response.usage.prompt_tokens, response.usage.completion_tokens)
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
            # DIAGNOSTIC: Validate base64 format and detect image type
            try:
                import base64
                base64.b64decode(homepage_screenshot_b64[:100])  # Test decode first 100 chars
                log("info", f"✅ BASE64 VALIDATION - {key_name}: Screenshot data is valid base64 format")
                
                # Detect proper image format
                image_mime_type = detect_image_format(homepage_screenshot_b64)
                log("info", f"🔍 IMAGE FORMAT - {key_name}: Detected {image_mime_type}")
                
                # Get image size info
                full_decoded = base64.b64decode(homepage_screenshot_b64)
                log("info", f"📏 IMAGE SIZE - {key_name}: {len(full_decoded)} bytes, {len(homepage_screenshot_b64)} base64 chars")
                
            except Exception as e:
                log("error", f"❌ BASE64 VALIDATION - {key_name}: Invalid base64 data: {e}")
                image_mime_type = "image/jpeg"  # Fallback
            
            content.insert(0, {"type": "image_url", "image_url": {"url": f"data:{image_mime_type};base64,{homepage_screenshot_b64}"}})
            log("info", f"🖼️ OPENAI REQUEST - {key_name}: Including screenshot as {image_mime_type} ({len(homepage_screenshot_b64)} base64 chars)")
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
        
        # Log successful API response with token usage
        usage = response.usage
        log("info", f"✅ OPENAI API SUCCESS - {key_name}: Received response from GPT-4V")
        log("info", f"📊 TOKEN USAGE - {key_name}: {usage.total_tokens} total ({usage.prompt_tokens} prompt + {usage.completion_tokens} completion)")
        
        # Track API usage for cost monitoring
        api_type = "gpt-4o-vision" if any(isinstance(item, dict) and item.get("type") == "image_url" for item in content if isinstance(item, list) for item in content) else "gpt-4o"
        track_api_usage(api_type, usage.prompt_tokens, usage.completion_tokens)
        
        if homepage_screenshot_b64:
            log("info", f"🎯 CONFIRMED: OpenAI processed image data for {key_name} analysis")
            if usage.prompt_tokens > 1000:
                log("info", f"🖼️ VISION TOKENS - {key_name}: High prompt token count ({usage.prompt_tokens}) confirms image processing")
            else:
                log("warn", f"⚠️ VISION TOKENS - {key_name}: Low prompt token count ({usage.prompt_tokens}) may indicate image processing issue")
        
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
        summary_prompt = f"You are a senior brand strategist delivering a comprehensive executive summary. Based on the following six memorability key analyses, create a detailed strategic assessment of 600-800 words following this EXACT structure:\n\n## Executive Summary\n\n### Overall Summary\nWrite 2-3 paragraphs providing a comprehensive overview of the brand's memorability performance across all six dimensions (**Emotion**, **Attention**, **Story**, **Involvement**, **Repetition**, **Consistency**). Analyze patterns, interdependencies, and overall brand coherence. Be specific about what the brand does well and areas needing improvement.\n\n### Key Strengths\nIdentify the 2-3 highest scoring memorability keys. For each strength:\n• **[Key Name] (Score: X):** Write a detailed paragraph explaining why this key performs well, its strategic value, and how it contributes to brand recall and recognition. Use specific evidence from the analysis.\n\n### Primary Weaknesses\nIdentify the 2-3 lowest scoring memorability keys. For each weakness:\n• **[Key Name] (Score: X):** Write a detailed paragraph explaining the deficiencies, potential impact on brand memorability, and why it's underperforming. Reference specific gaps or missed opportunities.\n\n### Strategic Focus\nWrite 2-3 paragraphs identifying the single most critical memorability key to address first. Provide comprehensive strategic rationale explaining WHY this key should be the priority, HOW addressing it will impact overall brand performance, and WHAT the expected outcomes are.\n\nFORMATTING REQUIREMENTS:\n- Always bold memorability key names: **Emotion**, **Attention**, **Story**, **Involvement**, **Repetition**, **Consistency**\n- Include score numbers for each key mentioned: **(Score: X)**\n- Use bullet points for listing strengths and weaknesses\n- Write in professional, executive-level language\n- Provide specific, actionable insights\n\n---\n{analyses_text}\n---"
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": summary_prompt}], temperature=0.4)
        # Track API usage
        if hasattr(response, 'usage'):
            track_api_usage("gpt-4o", response.usage.prompt_tokens, response.usage.completion_tokens)
        return response.choices[0].message.content
    except Exception as e:
        log("error", f"AI summary failed: {e}")
        raise

def capture_screenshots_playwright(urls):
    results = []
    log("info", f"Starting screenshot capture for {len(urls)} URLs.")
    
    browser = get_shared_playwright_browser()
    context = browser.new_context(
        user_agent=get_random_user_agent(),
        viewport={'width': 1920, 'height': 1080},
        ignore_https_errors=True
    )
    page = context.new_page()
    
    for url in urls[:4]:
        try:
            if any(urlparse(url).path.lower().endswith(ext) for ext in CONFIG["ignored_extensions"]):
                log("info", f"Ignoring non-HTML link for screenshot: {url}")
                continue
            log("info", f"Navigating to {url}")
            page.goto(url, wait_until="load", timeout=TIMEOUTS["playwright_page_load"])
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
    
    context.close()
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

def score_link_pool(links: List[Tuple[str, str]], lang: str) -> List[dict]:
    """Helper function to score a list of links with a given language context.
    
    This function supports the "Language Fallback" mechanism by allowing
    scoring with different language preferences.
    
    Args:
        links: List of (url, text) tuples to score
        lang: Language code to use for scoring ('en', 'de', etc.)
    
    Returns:
        List of scored link dictionaries sorted by score (highest first)
    """
    log("info", f"🎯 Scoring {len(links)} links with language preference: '{lang}'")
    
    scored_links = []
    unique_urls = set()
    
    for url, text in links:
        try:
            # URLs are already cleaned during discovery phase
            if url not in unique_urls:
                unique_urls.add(url)
                score, rationale = score_link(url, text, lang)
                if score > SCORING_CONSTANTS["MIN_BUSINESS_SCORE"]:
                    scored_links.append({
                        "url": url, 
                        "text": text, 
                        "score": score, 
                        "rationale": rationale,
                        "language": lang
                    })
        except Exception as e:
            log("debug", f"Error scoring link {url}: {e}")
            continue
    
    # Sort by score (highest first)
    scored_links.sort(key=lambda x: x["score"], reverse=True)
    
    log("info", f"📊 Found {len(scored_links)} qualifying links (score > {SCORING_CONSTANTS['MIN_BUSINESS_SCORE']}) using language '{lang}'")
    
    return scored_links

def run_full_scan_stream(url: str, cache: dict, preferred_lang: str = 'en', scan_id: str = None, depth: int = 0):
    # Generate scan ID if not provided
    if not scan_id:
        scan_id = str(uuid.uuid4())
    
    # Track scan start
    track_scan_metric(scan_id, "started", {"url": url})
    
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
            track_scan_metric(scan_id, "failed", {"reason": "invalid_url", "error": error_msg})
            yield {'type': 'error', 'message': f'Invalid URL: {error_msg}'}
            return

        yield debug_yield({'type': 'status', 'message': 'Step 1/5: Discovering all brand pages...', 'phase': 'discovery', 'progress': 10})
        yield debug_yield({'type': 'activity', 'message': f'🌐 Starting scan at {initial_url}', 'timestamp': time.time()})
        log("info", f"Starting scan at validated URL: {initial_url}")

        # --- Phase 1: Initial Domain Discovery ---
        try:
            _, homepage_html = fetch_page_content_robustly(initial_url)
            if not homepage_html: raise Exception("Could not fetch initial URL content.")
        except (httpx.TimeoutException, httpx.ConnectTimeout) as e:
            log("error", f"Timeout fetching initial URL: {e}")
            track_scan_metric(scan_id, "failed", {"reason": "timeout", "error": str(e)})
            yield {'type': 'error', 'message': f'Request timed out. The website may be slow or unavailable: {e}'}
            return
        except (httpx.ConnectError, httpx.NetworkError) as e:
            log("error", f"Network error fetching initial URL: {e}")
            track_scan_metric(scan_id, "failed", {"reason": "network_error", "error": str(e)})
            yield {'type': 'error', 'message': f'Unable to connect to the website. Please check the URL: {e}'}
            return
        except httpx.HTTPStatusError as e:
            log("error", f"HTTP error fetching initial URL: {e.response.status_code} - {e}")
            track_scan_metric(scan_id, "failed", {"reason": "http_error", "status_code": e.response.status_code, "error": str(e)})
            if e.response.status_code == 403:
                yield {'type': 'error', 'message': 'Access forbidden. The website may be blocking automated requests.'}
            elif e.response.status_code == 404:
                yield {'type': 'error', 'message': 'Page not found. Please check the URL is correct.'}
            elif e.response.status_code >= 500:
                yield {'type': 'error', 'message': 'The website is experiencing server issues. Please try again later.'}
            else:
                yield {'type': 'error', 'message': f'HTTP error {e.response.status_code}: Unable to access the website.'}
            return
        except Exception as e:
            log("error", f"Unexpected error fetching initial URL: {e}")
            track_scan_metric(scan_id, "failed", {"reason": "fetch_failed", "error": str(e)})
            yield {'type': 'error', 'message': f'Unexpected error accessing the website: {e}'}
            return

        yield debug_yield({'type': 'activity', 'message': f'🔍 Analyzing HTML structure...', 'timestamp': time.time()})
        all_discovered_links = discover_links_from_html(homepage_html, initial_url)
        yield debug_yield({'type': 'metric', 'key': 'html_links', 'value': len(all_discovered_links)})
        yield debug_yield({'type': 'activity', 'message': f'✅ Found {len(all_discovered_links)} links in HTML', 'timestamp': time.time()})
        
        # --- NEW: Phase 1.5: Global Site Heuristic (Tenacious Discovery) ---
        # Proactively search for the true corporate site BEFORE continuing with current site
        yield debug_yield({'type': 'activity', 'message': f'🌍 Checking for global corporate site...', 'timestamp': time.time()})
        true_corporate_url = find_true_corporate_site(all_discovered_links, initial_url)
        
        if true_corporate_url:
            log("info", f"➡️ PIVOTING SCAN to high-confidence global corporate site: {true_corporate_url}")
            yield {'type': 'status', 'message': f'Found global site - pivoting to {urlparse(true_corporate_url).netloc}', 'progress': 15}
            yield debug_yield({'type': 'activity', 'message': f'🎯 Pivoting to global corporate site...', 'timestamp': time.time()})
            
            # RESTART discovery process from the new URL
            initial_url = true_corporate_url
            try:
                _, homepage_html = fetch_page_content_robustly(initial_url)
                if not homepage_html: 
                    log("warn", f"Failed to fetch content from global site {initial_url}, reverting to original")
                    # Revert to original URL and continue
                    initial_url = _clean_url(url)
                    _, homepage_html = fetch_page_content_robustly(initial_url)
                else:
                    # Successfully pivoted - rediscover links from the new site
                    all_discovered_links = discover_links_from_html(homepage_html, initial_url)
                    yield debug_yield({'type': 'activity', 'message': f'✅ Rediscovered {len(all_discovered_links)} links from global site', 'timestamp': time.time()})
            except Exception as e:
                log("warn", f"Failed to pivot to global site {true_corporate_url}: {e} - continuing with original site")
                initial_url = _clean_url(url)
        
        yield debug_yield({'type': 'activity', 'message': f'📄 Searching for sitemap...', 'timestamp': time.time()})
        sitemap_links = discover_links_from_sitemap(initial_url, preferred_lang)
        if sitemap_links:
            all_discovered_links.extend(sitemap_links)
            yield debug_yield({'type': 'activity', 'message': f'✅ Found {len(sitemap_links)} pages in sitemap', 'timestamp': time.time()})
            yield debug_yield({'type': 'metric', 'key': 'sitemap_links', 'value': len(sitemap_links)})
        else:
            yield debug_yield({'type': 'activity', 'message': f'📄 No sitemap found - proceeding with HTML links', 'timestamp': time.time()})

        # Detect the primary language from HTML for informational logging only
        detected_lang = detect_primary_language(homepage_html)
        log("info", f"🌐 Detected primary language: {detected_lang} (from HTML) - informational only")
        log("info", f"🎯 Using preferred language: {preferred_lang} (source of truth for all decisions)")
        yield {'type': 'status', 'message': f'Detected language: {detected_lang.upper()}, Using preference: {preferred_lang.upper()}'}

        # --- Phase 2: High-Value Subdomain Discovery ---
        # FIXED: True Two-Pocket Strategy - find additional sources without pivoting
        yield debug_yield({'type': 'activity', 'message': f'🔎 Searching for corporate portals...', 'timestamp': time.time()})
        high_value_subdomain = find_high_value_subdomain(all_discovered_links, initial_url, preferred_lang)
        if high_value_subdomain:
            log("info", f"🎯 Found high-value subdomain: {high_value_subdomain}. Performing surgical strike.")
            yield debug_yield({'type': 'activity', 'message': f'🎯 Performing surgical strike on subdomain...', 'timestamp': time.time()})
            
            # Use surgical strike instead of full discovery
            top_subdomain_links = get_top_links_from_subdomain(high_value_subdomain, preferred_lang)
            if top_subdomain_links:
                all_discovered_links.extend(top_subdomain_links)
                log("info", f"✅ Surgical Strike: Added {len(top_subdomain_links)} top links from high-value subdomain")
                yield debug_yield({'type': 'activity', 'message': f'🎯 Added {len(top_subdomain_links)} precision links from subdomain', 'timestamp': time.time()})
                yield debug_yield({'type': 'metric', 'key': 'subdomain_links', 'value': len(top_subdomain_links)})
            else:
                log("info", "🎯 Surgical strike yielded no qualifying links from subdomain")
                yield debug_yield({'type': 'activity', 'message': f'⚠️ Subdomain surgical strike found no qualifying links', 'timestamp': time.time()})
        else:
            yield debug_yield({'type': 'activity', 'message': f'📍 No high-value subdomains found - focusing on main site', 'timestamp': time.time()})

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

        yield {'type': 'status', 'message': f'Using preferred language: {preferred_lang.upper()}'}

        # --- NEW: Pre-emptive Veto Filtering ---
        initial_link_count = len(all_discovered_links)
        vetoed_by_category = {}
        filtered_links = []
        
        for url, text in all_discovered_links:
            is_vetoed, veto_category = is_vetoed_url(url)
            if not is_vetoed:
                filtered_links.append((url, text))
            else:
                if veto_category:
                    vetoed_by_category[veto_category] = vetoed_by_category.get(veto_category, 0) + 1
        
        all_discovered_links = filtered_links
        vetoed_count = initial_link_count - len(all_discovered_links)
        
        if vetoed_count > 0:
            log("info", f"🛡️ Pre-emptive veto: Filtered out {vetoed_count} links from {initial_link_count} total")
            for category, count in vetoed_by_category.items():
                log("info", f"  - {category}: {count} links")
            yield {'type': 'activity', 'message': f'🛡️ Vetoed {vetoed_count} irrelevant links, analyzing {len(all_discovered_links)} remaining', 'timestamp': time.time()}
        else:
            yield {'type': 'activity', 'message': f'✅ All {len(all_discovered_links)} links passed veto screening', 'timestamp': time.time()}

        yield {'type': 'status', 'message': 'Scoring and ranking all discovered links...', 'phase': 'scoring', 'progress': 30}
        yield {'type': 'activity', 'message': f'📊 Analyzing {len(all_discovered_links)} discovered links...', 'timestamp': time.time()}
        yield {'type': 'metric', 'key': 'total_links', 'value': len(all_discovered_links)}
        
        # Use the centralized scoring function with language fallback
        scored_links = score_link_pool(all_discovered_links, preferred_lang)
        
        # Language fallback mechanism - if results are poor, try detected language
        if len(scored_links) < 10 and detected_lang and detected_lang != preferred_lang:
            yield {'type': 'activity', 'message': f'⚠️ Only {len(scored_links)} pages found with {preferred_lang.upper()}. Retrying with detected language {detected_lang.upper()}...', 'timestamp': time.time()}
            log("warn", f"🔄 Language fallback triggered: {len(scored_links)} pages with {preferred_lang} < 10, trying {detected_lang}")
            
            fallback_scored_links = score_link_pool(all_discovered_links, detected_lang)
            if len(fallback_scored_links) > len(scored_links):
                log("info", f"✅ Language fallback successful: {len(fallback_scored_links)} pages with {detected_lang} > {len(scored_links)} with {preferred_lang}")
                scored_links = fallback_scored_links
                preferred_lang = detected_lang  # Update the language we're using
                yield {'type': 'activity', 'message': f'✅ Language fallback successful - using {detected_lang.upper()} for better results', 'timestamp': time.time()}
                yield {'type': 'status', 'message': f'Language switched to: {detected_lang.upper()}'}
            else:
                log("info", f"❌ Language fallback ineffective: {len(fallback_scored_links)} pages with {detected_lang} <= {len(scored_links)} with {preferred_lang}")
                yield {'type': 'activity', 'message': f'Language fallback provided no improvement - continuing with {preferred_lang.upper()}', 'timestamp': time.time()}
        
        yield {'type': 'metric', 'key': 'high_value_pages', 'value': len(scored_links)}
        yield {'type': 'activity', 'message': f'✨ Identified {len(scored_links)} business-relevant pages using {preferred_lang.upper()}', 'timestamp': time.time()}
        
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
            
            executor = ThreadPoolExecutor(max_workers=2)
            try:
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
            finally:
                # Ensure proper cleanup
                cleanup_process_pool(executor)

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
        
        # Track successful completion
        track_scan_metric(scan_id, "completed", {
            "processing_mode": processing_mode,
            "pages_analyzed": len(all_discovered_links) if 'all_discovered_links' in locals() else 0,
            "average_score": quantitative_summary.get("average_score", 0)
        })

    except Exception as e:
        log("error", f"The main stream failed: {e}")
        import traceback
        traceback.print_exc()
        track_scan_metric(scan_id, "failed", {"reason": "critical_error", "error": str(e)})
        yield {'type': 'error', 'message': f'A critical error occurred: {e}'}
    finally:
        # Clean up resources
        close_shared_http_client()
        close_shared_playwright_browser()

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
