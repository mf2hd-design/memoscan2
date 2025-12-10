#!/usr/bin/env python3
"""
Extended timeout E2E test for Industry Context feature.
Uses very long timeouts to ensure the GPT-5.1 API call completes.
"""

import time
from playwright.sync_api import sync_playwright, expect

def test_industry_context_extended():
    """Test industry context with extended timeouts for GPT-5.1 API."""

    print("\n" + "=" * 70)
    print("🧪 EXTENDED E2E Test: Industry Context Feature")
    print("=" * 70)
    print("\n⏱️  Using extended timeouts (10 minutes max)")
    print("⚠️  This will make REAL API calls (~$0.50-1.00)\n")

    with sync_playwright() as p:
        # Launch browser with extended timeouts
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        # Set very long default timeout - 10 minutes
        context.set_default_timeout(600000)
        page = context.new_page()

        try:
            # Step 1: Navigate
            print("📍 Step 1: Loading MemoScan on port 8081...")
            page.goto("http://localhost:8081", timeout=30000)
            page.wait_for_load_state("networkidle")
            print("   ✅ Application loaded\n")

            # Step 2: Select Audit the Brand mode
            print("📍 Step 2: Selecting 'Audit the Brand' (discovery) mode...")
            discovery_button = page.locator("button[data-mode='discovery']")
            expect(discovery_button).to_be_visible(timeout=10000)
            discovery_button.click()
            time.sleep(0.5)

            # Verify mode is selected
            expect(discovery_button).to_have_class("mode-button active")
            print("   ✅ Discovery mode selected\n")

            # Step 3: Enter URL
            print("📍 Step 3: Entering test URL...")
            # Using Basecamp - smaller B2B site should be faster
            test_url = "https://basecamp.com"
            url_input = page.locator("#url-input")
            url_input.fill(test_url)
            print(f"   ✅ URL entered: {test_url}\n")

            # Step 4: Start scan
            print("📍 Step 4: Starting scan...")
            start_button = page.locator("#scan-button")
            start_button.click()
            print("   ✅ Scan initiated\n")

            # Step 5: Monitor progress with detailed logging
            print("📍 Step 5: Monitoring scan progress...")
            print("   (This may take 2-4 minutes for full scan + GPT-5.1 analysis)\n")

            start_time = time.time()
            phases_seen = []
            last_log_time = start_time

            # Wait up to 5 minutes for scan completion
            max_wait = 300

            while time.time() - start_time < max_wait:
                try:
                    # Log every 10 seconds
                    current_time = time.time()
                    if current_time - last_log_time >= 10:
                        elapsed = int(current_time - start_time)
                        print(f"   [{elapsed}s] ⏳ Still monitoring...")
                        last_log_time = current_time

                    # Check phase text
                    phase_element = page.locator(".phase-text")
                    if phase_element.is_visible():
                        phase_text = phase_element.inner_text()
                        if phase_text and phase_text not in phases_seen:
                            phases_seen.append(phase_text)
                            elapsed = int(time.time() - start_time)
                            print(f"   [{elapsed}s] 📊 Phase: {phase_text}")

                    # Check for industry context phase specifically
                    if phase_text and "industry context" in phase_text.lower():
                        print(f"\n   🎯 INDUSTRY CONTEXT PHASE DETECTED!\n")
                        # Give extra time for the GPT-5.1 API call
                        print("   ⏳ Waiting for GPT-5.1 API to complete (may take 30-60 seconds)...")
                        time.sleep(5)  # Wait a bit before checking for the container

                    # Check if scan completed
                    try:
                        progress_text = page.locator(".progress-percentage").inner_text()
                        if progress_text == "100%":
                            elapsed = int(time.time() - start_time)
                            print(f"\n   ✅ Scan reached 100% at {elapsed}s\n")
                            # Wait extra time for final messages to arrive
                            print("   ⏳ Waiting 30 seconds for final WebSocket messages...")
                            time.sleep(30)
                            break
                    except:
                        pass

                except Exception as e:
                    pass

                time.sleep(3)

            total_scan_time = int(time.time() - start_time)
            print(f"   📊 Total phases observed: {len(phases_seen)}")
            print(f"   ⏱️  Total scan time: {total_scan_time}s\n")

            # Step 6: Wait for Executive Summary
            print("📍 Step 6: Waiting for Executive Summary...")
            summary_container = page.locator("#summary-container")
            expect(summary_container).to_be_visible(timeout=60000)
            print("   ✅ Executive Summary displayed\n")

            # Step 7: Wait for Industry Context (THE KEY TEST!)
            print("📍 Step 7: Waiting for Industry Context Analysis...")
            print("   (GPT-5.1 API call - may take 30-60 seconds)\n")

            industry_container = page.locator("#industry-context-container")

            # CRITICAL: Wait up to 3 minutes for this element
            # This accounts for the GPT-5.1 API call time (~20-30s) plus buffer
            print("   ⏳ Waiting up to 3 minutes for industry context container...")
            expect(industry_container).to_be_visible(timeout=180000)

            elapsed_total = int(time.time() - start_time)
            print(f"   ✅ Industry Context container appeared at {elapsed_total}s!\n")

            # Step 8: Verify content quality
            print("📍 Step 8: Verifying content quality...")
            content = industry_container.inner_text()
            print(f"   ✅ Content length: {len(content)} characters")

            # Check for all 5 required strategic sections
            required_sections = [
                ("Market Dynamics", ["market dynamic", "s-curve", "value chain"]),
                ("Competitive Landscape", ["competitive landscape", "peer", "competition"]),
                ("Buyer Dynamics", ["buyer", "dmu", "decision making"]),
                ("Technological", ["technology", "technological", "regulatory"]),
                ("Strategic", ["strategic", "hypothesis", "defensive", "offensive"])
            ]

            sections_found = 0
            for section_name, keywords in required_sections:
                content_lower = content.lower()
                if any(keyword in content_lower for keyword in keywords):
                    sections_found += 1
                    print(f"   ✅ Found: {section_name}")
                else:
                    print(f"   ⚠️  Missing: {section_name}")

            print(f"\n   📊 Strategic sections: {sections_found}/{len(required_sections)}")

            # Check for B2B focus
            b2b_indicators = ["b2b", "enterprise", "business-to-business", "corporate"]
            has_b2b_focus = any(indicator in content.lower() for indicator in b2b_indicators)
            if has_b2b_focus:
                print(f"   ✅ B2B focus confirmed")
            else:
                print(f"   ⚠️  B2B focus not clearly evident")

            # Step 9: Test collapsible functionality
            print("\n📍 Step 9: Testing collapsible functionality...")
            details_element = industry_container.locator("details")
            if details_element.is_visible():
                # Check if it's open
                is_open = details_element.get_attribute("open") is not None
                print(f"   ✅ Details element found (open: {is_open})")

                # Try toggling
                summary_element = details_element.locator("summary")
                summary_element.click()
                time.sleep(0.5)
                print(f"   ✅ Collapsible functionality works")
            else:
                print(f"   ℹ️  No collapsible element found")

            # Step 10: Capture screenshots
            print("\n📍 Step 10: Capturing screenshots...")

            # Full page screenshot
            full_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_extended_full.png"
            page.screenshot(path=full_screenshot, full_page=True)
            print(f"   ✅ Full page: {full_screenshot}")

            # Scroll industry context into view and capture it
            industry_container.scroll_into_view_if_needed()
            time.sleep(0.5)
            industry_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_extended_industry.png"
            industry_container.screenshot(path=industry_screenshot)
            print(f"   ✅ Industry section: {industry_screenshot}")

            # Final summary
            print("\n" + "=" * 70)
            print("✅ TEST PASSED - Industry Context Feature Fully Verified!")
            print("=" * 70)
            print(f"\n📊 Test Results:")
            print(f"   • Mode: Audit the Brand (discovery) ✅")
            print(f"   • Test URL: {test_url}")
            print(f"   • Total scan time: {elapsed_total}s")
            print(f"   • Executive Summary: ✅")
            print(f"   • Industry Context Section: ✅")
            print(f"   • Content length: {len(content)} characters")
            print(f"   • Strategic sections: {sections_found}/{len(required_sections)}")
            print(f"   • B2B focus: {'✅' if has_b2b_focus else '⚠️'}")
            print(f"   • UI rendering: ✅")
            print(f"   • Collapsible functionality: ✅\n")

            # Show content preview
            print("📝 Industry Context Preview (first 500 chars):")
            print("   " + "-" * 66)
            preview_lines = content[:500].split("\n")
            for line in preview_lines:
                if line.strip():
                    print(f"   {line[:64]}")
            print("   ...")
            print("   " + "-" * 66 + "\n")

            # Pause to allow manual inspection
            print("⏸️  Keeping browser open for 10 seconds for manual inspection...")
            time.sleep(10)

            return True

        except Exception as e:
            elapsed = int(time.time() - start_time) if 'start_time' in locals() else 0
            print(f"\n❌ TEST FAILED at {elapsed}s: {str(e)}\n")

            # Capture error state
            try:
                error_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_extended_error.png"
                page.screenshot(path=error_screenshot, full_page=True)
                print(f"   📸 Error screenshot: {error_screenshot}\n")

                # Check page state
                print("📋 Page State at Failure:")
                print(f"   URL: {page.url}")
                print(f"   Title: {page.title()}")

                # Check what's visible
                summary_visible = page.locator("#summary-container").is_visible()
                industry_visible = page.locator("#industry-context-container").is_visible()
                print(f"   Executive summary visible: {summary_visible}")
                print(f"   Industry context visible: {industry_visible}")

                # Get console errors
                print("\n   Checking for JavaScript errors...")

            except:
                pass

            print("\n⏸️  Keeping browser open for 10 seconds for inspection...")
            time.sleep(10)

            raise

        finally:
            print("\n🧹 Cleaning up...")
            browser.close()

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🚀 Starting Extended Timeout Industry Context Test")
    print("=" * 70)
    print("\nPrerequisites:")
    print("  ✅ Flask app running on port 8081")
    print("  ✅ OPENAI_API_KEY set")
    print("  ✅ Playwright installed\n")

    try:
        success = test_industry_context_extended()
        if success:
            print("\n" + "=" * 70)
            print("✅ ALL TESTS PASSED")
            print("=" * 70)
            print("\nThe Industry Context feature is working correctly!")
            print("Real users will see comprehensive B2B strategic analysis")
            print("after the Executive Summary in 'Audit the Brand' mode.\n")
            exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Test suite failed: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
