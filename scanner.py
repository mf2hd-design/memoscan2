import httpx
import logging
import base64
import time
import json
from typing import List, Dict
from PIL import Image
from io import BytesIO

logger = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO)

# --- Comprehensive Cookie Banner Avoidance JS ---
EVALUATE_COOKIE_JS = """
(() => {
  const cookieWords = [
    'accept', 'agree', 'ok', 'got it', 'allow', 'dismiss', 'consent', 'yes', 'continue',
    'zulassen', 'akzeptieren', 'erlauben',      // German
    'permitir', 'aceptar', 'consentir',         // Spanish/Portuguese
    'accepter', 'autoriser', 'oui',             // French
    'accetta', 'consenti',                      // Italian
    'akkoord', 'toestaan',                      // Dutch
    'zgadzam', 'zezwalaj',                      // Polish
    'принять', 'согласен',                      // Russian
    'allow all', 'accept all', 'alle akzeptieren', 'tout accepter', 'permit all'
  ];
  function normalize(txt) {
    return (txt || '').toLowerCase().replace(/\\s+/g, ' ').trim();
  }
  function tryClickAll(root=document) {
    let clicked = 0;
    // Buttons and inputs
    root.querySelectorAll('button, input[type=button], input[type=submit]').forEach(btn => {
      let txt = normalize(btn.textContent) || normalize(btn.value);
      if (cookieWords.some(w => txt.includes(w))) { try { btn.click(); clicked++; } catch(e){} }
    });
    // Links
    root.querySelectorAll('a').forEach(a => {
      let txt = normalize(a.textContent);
      if (cookieWords.some(w => txt.includes(w))) { try { a.click(); clicked++; } catch(e){} }
    });
    // Divs, spans with role/button/cookie classes
    root.querySelectorAll('div[role=button],span[role=button],div[class*="cookie"],div[id*="cookie"],span[class*="cookie"],span[id*="cookie"]').forEach(el => {
      let txt = normalize(el.textContent);
      if (cookieWords.some(w => txt.includes(w))) { try { el.click(); clicked++; } catch(e){} }
    });
    // Try shadow DOMs
    root.querySelectorAll('*').forEach(node => {
      if (node.shadowRoot) {
        try { clicked += tryClickAll(node.shadowRoot); } catch(e){}
      }
    });
    return clicked;
  }
  // Retry multiple times for slow banners
  let tries = 0, maxTries = 4;
  function doIt() {
    tries++;
    let res = tryClickAll();
    if (res === 0 && tries < maxTries) setTimeout(doIt, 1200);
  }
  doIt();
})();
"""

# --- Helper: Ensure HTTPS URL ---
def ensure_full_url(url):
    url = url.strip()
    if not url.startswith('http://') and not url.startswith('https://'):
        return 'https://' + url
    return url

# --- ScrapingBee Screenshot API Call ---
def get_screenshot_scrapingbee(url: str) -> bytes:
    api_key = "G3Z0MTEBG3P5E4AM2VM4S24MA5GTH1Q5ARZ86YWAJJMTHO4U6V3F5CQACMUUCUZISHGHPNLUYQ7J83JY"  # <-- Put your API key here
    endpoint = "https://app.scrapingbee.com/api/v1/"
    url = ensure_full_url(url)
    params = {
        "api_key": api_key,
        "url": url,
        "screenshot": "true",
        "render_js": "true",
        "js_scenario": json.dumps({
            "strict": False,
            "instructions": [
                {
                    "evaluate": EVALUATE_COOKIE_JS
                },
                {
                    "wait": 1200  # Give a little more time for banners to close before screenshot
                }
            ]
        }),
    }
    try:
        logger.info(f"[ScrapingBee]Screenshot {url}")
        resp = httpx.get(endpoint, params=params, timeout=40)
        if resp.status_code == 200:
            # Validate PNG by attempting to open with PIL
            try:
                img = Image.open(BytesIO(resp.content))
                img.verify()  # Will raise if not a valid image
            except Exception as e:
                logger.error(f"[IMG] Compress failed: {e}")
                return None
            return resp.content
        else:
            logger.error(f"[ScrapingBee] HTTP {resp.status_code} for {url}: {resp.text}")
    except Exception as e:
        logger.error(f"[ScrapingBee] EXC {url}: {e}")
    return None

# --- Example Visual Feature Extraction Stub ---
def extract_visual_features(image_bytes: bytes) -> Dict:
    # You could add more image analysis here if you want
    try:
        img = Image.open(BytesIO(image_bytes))
        return {
            "format": img.format,
            "size": img.size,
            "mode": img.mode,
        }
    except Exception as e:
        logger.error(f"[VisualExtraction] Failed: {e}")
        return {}

# --- Example JSON Schema Validator Stub ---
def validate_json_schema(data: dict, schema: dict) -> bool:
    try:
        from jsonschema import validate
        validate(instance=data, schema=schema)
        return True
    except Exception as e:
        logger.warning(f"[Schema] Validation failed: {e}")
        return False

# --- Main Scan Routine ---
def run_full_scan_stream(target_url: str, screenshot_cache: dict = None):
    """
    Crawl, collect up to three screenshots, and emit data for QA.
    """
    screenshot_cache = screenshot_cache if screenshot_cache is not None else {}

    urls_to_screenshot = []
    main_url = ensure_full_url(target_url)
    urls_to_screenshot.append(main_url)

    # Fetch up to two more internal links from the homepage for extra screenshots
    try:
        resp = httpx.get(main_url, timeout=15)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'lxml')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # Ignore mailto/phone/jump links
            if href.startswith('http'):
                links.append(href)
            elif href.startswith('/'):
                links.append(main_url.rstrip('/') + href)
            if len(links) >= 2:
                break
        urls_to_screenshot += links
    except Exception as e:
        logger.warning(f"[BasicFetcher] Could not parse links: {e}")

    screenshots = []
    for idx, url in enumerate(urls_to_screenshot[:3]):
        logger.info(f"[ScrapingBee]Screenshot {url} (Page {idx+1})")
        img_bytes = get_screenshot_scrapingbee(url)
        if img_bytes:
            img_id = f"{hash(url)}"
            if screenshot_cache is not None:
                screenshot_cache[img_id] = base64.b64encode(img_bytes).decode("utf-8")
            screenshots.append({
                "img_id": img_id,
                "url": url,
                "visual_features": extract_visual_features(img_bytes),
            })
        else:
            logger.warning(f"[ScrapingBee] No screenshot for {url}")

    logger.info(f"[Visuals] Collected {len(screenshots)} screenshots for {target_url}")

    # --- For QA, just yield screenshots and their info, no LLM calls ---
    yield {
        "type": "visual_evidence",
        "screenshots": screenshots,
        "count": len(screenshots),
    }

    # Optionally: validate output with JSON schema (stub below)
    # schema = {...}
    # valid = validate_json_schema({"screenshots": screenshots}, schema)
    # logger.info(f"[Schema] Output valid? {valid}")

# --- For local/manual testing ---
if __name__ == "__main__":
    cache = {}
    for data in run_full_scan_stream("repsol.com", cache):
        print(json.dumps(data, indent=2))
