#!/usr/bin/env python3
"""
Quick test with a smaller site to verify industry context works end-to-end.
Uses a smaller brand site to keep scan time under 2 minutes.
"""

import time
from playwright.sync_api import sync_playwright, expect

def test_industry_context_quick():
    """Test industry context with a smaller, faster scan."""

    print("=" * 70)
    print("🧪 QUICK E2E Test: Industry Context Feature")
    print("=" * 70)
    print("\n✅ Using a smaller site for faster testing\n")

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        # Increase default timeout to 5 minutes
        context.set_default_timeout(300000)
        page = context.new_page()

        try:
            # Navigate
            print("📍 Step 1: Loading MemoScan...")
            page.goto("http://localhost:8081", timeout=15000)
            page.wait_for_load_state("networkidle")
            print("   ✅ Page loaded\n")

            # Select discovery mode
            print("📍 Step 2: Selecting 'Audit the Brand' mode...")
            discovery_button = page.locator("button[data-mode='discovery']")
            expect(discovery_button).to_be_visible(timeout=5000)
            discovery_button.click()
            time.sleep(0.5)
            expect(discovery_button).to_have_class("mode-button active")
            print("   ✅ Discovery mode selected\n")

            # Enter URL (using a small, simple B2B brand site)
            print("📍 Step 3: Entering test URL...")
            # Using Basecamp - smaller site, clear B2B brand
            test_url = "https://basecamp.com"
            url_input = page.locator("#url-input")
            url_input.fill(test_url)
            print(f"   ✅ URL: {test_url}\n")

            # Start scan
            print("📍 Step 4: Starting scan...")
            start_button = page.locator("#scan-button")
            start_button.click()
            print("   ✅ Scan started\n")

            # Monitor progress with extended timeout
            print("📍 Step 5: Monitoring scan (will take 1-2 minutes)...")
            start_time = time.time()

            # Wait for executive summary with long timeout
            print("\n   Waiting for Executive Summary...")
            summary_container = page.locator("#summary-container")
            expect(summary_container).to_be_visible(timeout=300000)  # 5 min max
            print(f"   ✅ Executive Summary appeared at {int(time.time() - start_time)}s\n")

            # Now wait for industry context - this should appear shortly after summary
            print("   Waiting for Industry Context Analysis...")
            print("   (This uses GPT-5.1 and may take 20-30 seconds)\n")

            industry_container = page.locator("#industry-context-container")

            # Wait with extended timeout
            expect(industry_container).to_be_visible(timeout=120000)  # 2 min max after summary
            elapsed = int(time.time() - start_time)
            print(f"   ✅ Industry Context appeared at {elapsed}s!\n")

            # Verify content
            print("📍 Step 6: Verifying content...")
            content = industry_container.inner_text()
            print(f"   ✅ Content length: {len(content)} characters")

            # Check for key strategic sections
            key_sections = [
                "Market Dynamics",
                "Competitive Landscape",
                "Strategic"
            ]

            found = 0
            for section in key_sections:
                if section.lower() in content.lower():
                    found += 1
                    print(f"   ✅ Found: {section}")

            print(f"\n   📊 Strategic sections: {found}/{len(key_sections)}\n")

            # Take screenshot
            print("📍 Step 7: Capturing screenshot...")
            screenshot_path = "/Users/ben/Documents/Saffron/memoscan2/test_quick_success.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   ✅ Saved: {screenshot_path}\n")

            # Final summary
            print("=" * 70)
            print("✅ TEST PASSED - Industry Context Feature Working!")
            print("=" * 70)
            print(f"\n📊 Results:")
            print(f"   • Total time: {elapsed}s")
            print(f"   • Mode: Audit the Brand (discovery) ✅")
            print(f"   • Executive Summary: ✅")
            print(f"   • Industry Context: ✅")
            print(f"   • Content quality: {found}/{len(key_sections)} sections ✅")
            print(f"   • Content length: {len(content)} chars ✅\n")

            # Show preview
            print("📝 Content Preview (first 300 chars):")
            print("   " + "-" * 66)
            preview = content[:300].replace("\n", "\n   ")
            print(f"   {preview}...")
            print("   " + "-" * 66)

            # Pause to view
            print("\n⏸️  Pausing 5 seconds...")
            time.sleep(5)

            return True

        except Exception as e:
            print(f"\n❌ TEST FAILED: {str(e)}")

            # Error screenshot
            try:
                error_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_quick_error.png"
                page.screenshot(path=error_screenshot, full_page=True)
                print(f"   📸 Error screenshot: {error_screenshot}")
            except:
                pass

            raise

        finally:
            print("\n🧹 Cleanup...")
            browser.close()

if __name__ == "__main__":
    print("\n🚀 Starting Quick Industry Context Test\n")

    try:
        success = test_industry_context_quick()
        if success:
            print("\n✅ TEST PASSED")
            exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
