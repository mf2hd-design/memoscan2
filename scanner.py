import os
import logging
import time
import httpx
import base64
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")

def get_cookiefree_screenshot(url):
    # Aggressive cookie banner remover for EN and DE
    js_scenario = {
        "strict": False,
        "instructions": [
            {
                "evaluate": """
                (() => {
                  const cookieWords = [
                    'accept', 'ok', 'agree', 'zulassen', 'akzeptieren', 'consent'
                  ];
                  // Click buttons
                  Array.from(document.querySelectorAll('button')).forEach(btn => {
                    let txt = (btn.textContent || '').toLowerCase();
                    if (cookieWords.some(w => txt.includes(w))) { try { btn.click(); } catch(e){} }
                  });
                  // Click links
                  Array.from(document.querySelectorAll('a')).forEach(a => {
                    let txt = (a.textContent || '').toLowerCase();
                    if (cookieWords.some(w => txt.includes(w))) { try { a.click(); } catch(e){} }
                  });
                  // Click input[type=button], input[type=submit]
                  Array.from(document.querySelectorAll('input[type=button],input[type=submit]')).forEach(inp => {
                    let val = (inp.value || '').toLowerCase();
                    if (cookieWords.some(w => val.includes(w))) { try { inp.click(); } catch(e){} }
                  });
                })();
                """
            },
            {"wait": 800}
        ]
    }
    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": url,
        "screenshot": "true",
        "render_js": "true",
        "js_scenario": json.dumps(js_scenario)
    }
    try:
        logger.info(f"[ScrapingBee]Screenshot {url}")
        resp = httpx.get("https://app.scrapingbee.com/api/v1/", params=params, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            img_b64 = data.get("screenshot")
            if img_b64:
                return base64.b64decode(img_b64)
            else:
                logger.error(f"[ScrapingBee] No screenshot field in response for {url}")
        else:
            logger.error(f"[ScrapingBee] HTTP {resp.status_code} for {url}: {resp.text}")
    except Exception as e:
        logger.error(f"[ScrapingBee] EXC for {url}: {e}")
    return None

def run_full_scan_stream(url, screenshot_cache=None):
    # List of URLs to screenshot (simulate 3 pages for test)
    # In real crawler: replace with the crawl logic and get top 3 links after the main page.
    pages = [url]
    logger.info(f"[BasicFetcher] {url}")

    # Simulate finding up to 2 more pages for demo/testing
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=20)
        html = resp.text
        import re
        links = re.findall(r'href="(http[^"]+)"', html)
        for link in links:
            if link not in pages and len(pages) < 3:
                pages.append(link)
    except Exception as e:
        logger.warning(f"[BasicFetcher] Failed to get links from {url}: {e}")

    screenshots = []
    for i, page_url in enumerate(pages[:3]):
        logger.info(f"[ScrapingBee]Screenshot {page_url} (Page {i+1})")
        img_bytes = get_cookiefree_screenshot(page_url)
        if img_bytes:
            # If using a cache (for /screenshot route): generate a uuid and cache the base64
            if screenshot_cache is not None:
                img_id = f"{str(i)}-{int(time.time())}"
                screenshot_cache[img_id] = base64.b64encode(img_bytes).decode("utf-8")
                screenshots.append({"id": img_id, "url": page_url})
            else:
                screenshots.append({"img_bytes": img_bytes, "url": page_url})
        else:
            logger.warning(f"[ScrapingBee] No screenshot for {page_url}")

    # Only emit screenshot data, no LLM analysis
    logger.info(f"[Visuals] Collected {len(screenshots)} screenshots for {url}")
    yield {
        "type": "screenshots",
        "url": url,
        "screenshots": screenshots
    }

# (Optional) If you want to easily test as a script
if __name__ == "__main__":
    test_url = "https://www.lohmann-rauscher.com/us-en/"
    for msg in run_full_scan_stream(test_url):
        print(msg)
