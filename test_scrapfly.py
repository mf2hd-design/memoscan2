import os
import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def check_scrapfly_connection():
    """A minimal script to test the Scrapfly API connection."""
    api_key = os.getenv("SCRAPFLY_KEY")
    if not api_key:
        print("🔴 ERROR: SCRAPFLY_KEY not found in your .env file.")
        return

    print(f"🔑 Found API Key ending in: ...{api_key[-4:]}")

    target_url = "https://httpbin.org/get"
    endpoint_url = "https://api.scrapfly.io/scrape"
    
    # --- THIS IS THE FIX ---
    # The 'url' parameter is moved here, alongside the 'key'.
    params = {
        "key": api_key,
        "url": target_url
    }
    # The payload now only contains options, not the URL itself.
    payload = {"render_js": False}

    print(f"📡 Contacting Scrapfly endpoint: {endpoint_url}")
    print(f"🎯 Targeting URL: {target_url}")

    try:
        with httpx.Client() as client:
            response = client.post(endpoint_url, params=params, json=payload, timeout=60)
            
            print(f"\n📊 Scrapfly responded with HTTP Status Code: {response.status_code}")

            if response.status_code == 200:
                print("✅ SUCCESS! The connection to Scrapfly is working correctly.")
            else:
                print("❌ FAILED! The connection to Scrapfly is not working.")
                print("\n--- Server Response ---")
                try:
                    print(response.json())
                except Exception:
                    print(response.text)
                print("-----------------------\n")

    except httpx.RequestError as e:
        print(f"❌ FAILED! A network error occurred.")
        print(f"   Error: {e}")

if __name__ == "__main__":
    check_scrapfly_connection()