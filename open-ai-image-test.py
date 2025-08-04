import base64
from io import BytesIO
from playwright.sync_api import sync_playwright
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def take_screenshot(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 720})
        print(f"🌐 Navigating to {url}...")
        page.goto(url, timeout=60000)

        # Accept cookies if a common button is found
        try:
            consent_button = page.query_selector("button:has-text('Accept')") or page.query_selector("button:has-text('Alle akzeptieren')")
            if consent_button:
                consent_button.click()
                print("✅ Cookie banner accepted.")
        except Exception:
            pass

        page.wait_for_timeout(2000)  # Wait a bit to let page fully render

        screenshot_bytes = page.screenshot(full_page=True)
        browser.close()

        # Encode screenshot to base64
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        return screenshot_b64

def send_to_openai(screenshot_b64: str):
    print("📤 Sending screenshot to OpenAI GPT-4o...\n")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Please describe what is shown in this image."
                    }
                ]
            }
        ]
    )
    return response.choices[0].message.content

if __name__ == "__main__":
    test_url = "https://www.nvidia.com"  # Change this to test another site
    screenshot_b64 = take_screenshot(test_url)
    result = send_to_openai(screenshot_b64)
    print("\n🧠 GPT-4o Response:\n")
    print(result)
