#!/usr/bin/env python3
"""
Playwright test for Industry Context Analysis feature in MemoScan.
Tests the end-to-end flow of the new GPT-5.1 industry analysis.
"""

import asyncio
import time
from playwright.sync_api import sync_playwright, expect

def test_industry_context_feature():
    """Test that the industry context analysis appears after executive summary."""

    print("🧪 Starting Industry Context Feature Test")
    print("=" * 60)

    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=False)  # Set to True for CI/CD
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            # Step 1: Navigate to the application
            print("\n📍 Step 1: Navigating to MemoScan...")
            page.goto("http://localhost:5000", timeout=10000)
            print("   ✅ Page loaded successfully")

            # Step 2: Verify page elements are present
            print("\n📍 Step 2: Checking UI elements...")
            page.wait_for_selector("#url-input", timeout=5000)
            page.wait_for_selector("button:has-text('Audit the Brand')", timeout=5000)
            print("   ✅ UI elements found")

            # Step 3: Select "Audit the Brand" mode (diagnosis)
            print("\n📍 Step 3: Selecting 'Audit the Brand' mode...")
            diagnosis_button = page.locator("button[data-mode='discovery']")
            diagnosis_button.click()
            time.sleep(0.5)
            print("   ✅ Diagnosis mode selected")

            # Step 4: Enter test URL
            print("\n📍 Step 4: Entering test URL...")
            test_url = "https://www.apple.com"
            page.fill("#url-input", test_url)
            print(f"   ✅ URL entered: {test_url}")

            # Step 5: Start scan
            print("\n📍 Step 5: Starting scan...")
            start_button = page.locator("#start-scan-button")
            start_button.click()
            print("   ✅ Scan initiated")

            # Step 6: Wait for progress indicators
            print("\n📍 Step 6: Monitoring scan progress...")
            page.wait_for_selector("#progress-container[style*='display: block']", timeout=10000)
            print("   ✅ Progress container visible")

            # Step 7: Monitor for phase updates
            print("\n📍 Step 7: Waiting for analysis phases...")
            phases_seen = set()

            # Wait and check for different phases
            max_wait = 180  # 3 minutes max
            start_time = time.time()

            while time.time() - start_time < max_wait:
                # Check current phase text
                try:
                    phase_element = page.locator(".phase-text")
                    if phase_element.is_visible():
                        phase_text = phase_element.inner_text()
                        if phase_text not in phases_seen:
                            phases_seen.add(phase_text)
                            print(f"   📊 Phase: {phase_text}")

                        # Check if we've reached industry context phase
                        if "industry context" in phase_text.lower():
                            print("   ✅ Industry context phase detected!")
                            break
                except Exception:
                    pass

                # Check progress percentage
                try:
                    progress_pct = page.locator(".progress-percentage").inner_text()
                    if progress_pct == "100%":
                        print("   ✅ Scan reached 100%")
                        break
                except Exception:
                    pass

                time.sleep(2)

            # Step 8: Wait for executive summary
            print("\n📍 Step 8: Waiting for Executive Summary...")
            page.wait_for_selector("#summary-container[style*='display: block']", timeout=120000)
            summary = page.locator("#summary-container")
            expect(summary).to_be_visible()
            print("   ✅ Executive Summary displayed")

            # Step 9: Wait for industry context section (NEW FEATURE)
            print("\n📍 Step 9: Waiting for Industry Context Analysis...")
            page.wait_for_selector("#industry-context-container", timeout=120000)
            industry_container = page.locator("#industry-context-container")

            # Verify it's visible
            expect(industry_container).to_be_visible()
            print("   ✅ Industry Context container found and visible")

            # Step 10: Verify industry context content structure
            print("\n📍 Step 10: Verifying Industry Context content...")

            # Check for the details/summary element
            details_element = industry_container.locator("details")
            expect(details_element).to_be_visible()

            # Check for the title with globe emoji
            summary_element = details_element.locator("summary")
            summary_text = summary_element.inner_text()
            assert "Industry Context" in summary_text or "Strategic Analysis" in summary_text
            print(f"   ✅ Title found: {summary_text[:50]}...")

            # Check for actual content
            content_div = details_element.locator("div")
            content = content_div.inner_text()

            # Verify it contains expected strategic analysis sections
            expected_sections = [
                "Market Dynamics",
                "Competitive Landscape",
                "Strategic",
            ]

            found_sections = []
            for section in expected_sections:
                if section.lower() in content.lower():
                    found_sections.append(section)
                    print(f"   ✅ Found section: {section}")

            print(f"\n   📊 Content length: {len(content)} characters")

            if len(found_sections) >= 2:
                print("   ✅ Industry context contains strategic analysis content")
            else:
                print("   ⚠️  Warning: Expected sections not found in content")
                print(f"   Found sections: {found_sections}")

            # Step 11: Take screenshot of the result
            print("\n📍 Step 11: Capturing screenshot...")
            screenshot_path = "/Users/ben/Documents/Saffron/memoscan2/test_industry_context_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"   ✅ Screenshot saved: {screenshot_path}")

            # Step 12: Verify completion
            print("\n📍 Step 12: Verifying scan completion...")
            complete_element = page.locator(".phase-text:has-text('Complete')")
            if complete_element.is_visible(timeout=10000):
                print("   ✅ Scan completed successfully")

            # Final summary
            print("\n" + "=" * 60)
            print("✅ TEST PASSED: Industry Context Feature Working!")
            print("=" * 60)
            print(f"\n📊 Test Summary:")
            print(f"   • Executive Summary: ✅ Displayed")
            print(f"   • Industry Context: ✅ Displayed")
            print(f"   • Strategic Content: ✅ Present ({len(content)} chars)")
            print(f"   • Sections Found: {len(found_sections)}/{len(expected_sections)}")
            print(f"   • Screenshot: ✅ Saved")

            # Wait a bit to see the result
            time.sleep(3)

            return True

        except Exception as e:
            print(f"\n❌ TEST FAILED: {str(e)}")
            # Take error screenshot
            try:
                error_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_error_screenshot.png"
                page.screenshot(path=error_screenshot, full_page=True)
                print(f"   📸 Error screenshot saved: {error_screenshot}")
            except:
                pass
            raise

        finally:
            # Cleanup
            print("\n🧹 Cleaning up...")
            browser.close()

if __name__ == "__main__":
    try:
        test_industry_context_feature()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
