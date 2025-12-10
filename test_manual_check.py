#!/usr/bin/env python3
"""
Manual check - open browser and check if industry context is visible in a completed scan.
"""

import time
from playwright.sync_api import sync_playwright

def test_manual_check():
    """Just open the browser and check the current state."""

    print("🔍 Opening browser to check current scan state...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            # Navigate
            page.goto("http://localhost:8081", timeout=10000)
            print("✅ Loaded page")

            # Wait a moment for any existing content
            time.sleep(2)

            # Check if summary is visible
            summary_visible = page.locator("#summary-container").is_visible()
            print(f"Executive Summary visible: {summary_visible}")

            # Check if industry context is visible
            industry_visible = page.locator("#industry-context-container").is_visible()
            print(f"Industry Context visible: {industry_visible}")

            if industry_visible:
                # Get the content
                content = page.locator("#industry-context-container").inner_text()
                print(f"\n✅ Industry context IS visible!")
                print(f"Content length: {len(content)} characters")
                print(f"First 200 chars: {content[:200]}...")
            else:
                print("\n❌ Industry context NOT visible")

                # Check console for errors
                print("\nChecking browser console...")

            # Take screenshot
            screenshot_path = "/Users/ben/Documents/Saffron/memoscan2/test_manual_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n📸 Screenshot saved: {screenshot_path}")

            # Keep browser open for manual inspection
            print("\n⏸️  Keeping browser open for 30 seconds for manual inspection...")
            time.sleep(30)

        finally:
            browser.close()

if __name__ == "__main__":
    test_manual_check()
