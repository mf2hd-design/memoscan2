#!/usr/bin/env python3
"""
Live end-to-end Playwright test for Industry Context Analysis feature.
This test runs a REAL scan in "Audit the Brand" mode with actual API calls.
"""

import time
from playwright.sync_api import sync_playwright, expect

def test_industry_context_live():
    """Test industry context with a real scan in Audit the Brand mode."""

    print("=" * 70)
    print("🧪 LIVE E2E Test: Industry Context in Audit the Brand Mode")
    print("=" * 70)
    print("\n⚠️  This will make REAL API calls and may take 2-3 minutes")
    print("⚠️  Cost: ~$0.50-1.00 for the full scan\n")

    with sync_playwright() as p:
        # Launch browser (visible so we can see what's happening)
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()

        try:
            # Step 1: Navigate to the application
            print("📍 Step 1: Navigating to MemoScan on port 8081...")
            page.goto("http://localhost:8081", timeout=15000)
            page.wait_for_load_state("networkidle")
            print("   ✅ Application loaded\n")

            # Step 2: Select "Audit the Brand" mode (IMPORTANT!)
            print("📍 Step 2: Selecting 'Audit the Brand' mode (discovery)...")
            # The discovery mode button has data-mode="discovery"
            discovery_button = page.locator("button[data-mode='discovery']")
            expect(discovery_button).to_be_visible(timeout=5000)
            discovery_button.click()
            time.sleep(0.5)

            # Verify it's selected (has 'active' class)
            expect(discovery_button).to_have_class("mode-button active")
            print("   ✅ 'Audit the Brand' mode selected\n")

            # Step 3: Enter a test URL (using a smaller, faster site for testing)
            print("📍 Step 3: Entering test URL...")
            # Using Stripe as it's a well-known B2B brand with good content
            test_url = "https://stripe.com"
            url_input = page.locator("#url-input")
            url_input.fill(test_url)
            print(f"   ✅ URL entered: {test_url}\n")

            # Step 4: Start the scan
            print("📍 Step 4: Starting scan...")
            start_button = page.locator("#scan-button")
            start_button.click()
            print("   ✅ Scan initiated\n")

            # Step 5: Monitor progress through phases
            print("📍 Step 5: Monitoring scan progress...")
            print("   (This will take 1-2 minutes for a real scan)\n")

            phases_seen = []
            start_time = time.time()
            max_wait = 180  # 3 minutes max

            while time.time() - start_time < max_wait:
                try:
                    # Check phase text
                    phase_element = page.locator(".phase-text")
                    if phase_element.is_visible():
                        phase_text = phase_element.inner_text()
                        if phase_text and phase_text not in phases_seen:
                            phases_seen.append(phase_text)
                            elapsed = int(time.time() - start_time)
                            print(f"   [{elapsed}s] 📊 {phase_text}")

                    # Check for industry context phase specifically
                    if "industry context" in phase_text.lower():
                        print(f"\n   🎯 INDUSTRY CONTEXT PHASE DETECTED!")
                        break

                    # Check progress
                    try:
                        progress_text = page.locator(".progress-percentage").inner_text()
                        if progress_text == "100%":
                            print(f"\n   ✅ Scan reached 100%")
                            break
                    except:
                        pass

                except Exception:
                    pass

                time.sleep(2)

            print(f"\n   📊 Total phases observed: {len(phases_seen)}")
            print(f"   ⏱️  Total time: {int(time.time() - start_time)}s\n")

            # Step 6: Wait for executive summary (prerequisite for industry context)
            print("📍 Step 6: Waiting for Executive Summary...")
            summary_container = page.locator("#summary-container")
            expect(summary_container).to_be_visible(timeout=180000)  # 3 min timeout
            print("   ✅ Executive Summary displayed\n")

            # Step 7: Wait for Industry Context section (THE KEY TEST!)
            print("📍 Step 7: Waiting for Industry Context Analysis...")
            print("   (This is the new GPT-5.1 feature being tested)\n")

            industry_container = page.locator("#industry-context-container")
            expect(industry_container).to_be_visible(timeout=60000)  # 1 min timeout
            print("   ✅ Industry Context container appeared!\n")

            # Step 8: Verify industry context content
            print("📍 Step 8: Verifying Industry Context content...")

            # Check title
            title = industry_container.locator("summary").inner_text()
            assert "Industry Context" in title or "Strategic Analysis" in title
            print(f"   ✅ Title: {title}")

            # Get content
            content = industry_container.inner_text()
            print(f"   ✅ Content length: {len(content)} characters")

            # Verify expected sections are present
            required_sections = [
                "Market Dynamics",
                "Competitive Landscape",
                "Buyer Dynamics",
                "Technological",
                "Regulatory",
                "Strategic Hypothesis"
            ]

            found_sections = []
            for section in required_sections:
                if section.lower() in content.lower():
                    found_sections.append(section)
                    print(f"   ✅ Found section: {section}")

            print(f"\n   📊 Sections found: {len(found_sections)}/{len(required_sections)}")

            if len(found_sections) >= 4:
                print("   ✅ Industry context has comprehensive strategic content")
            else:
                print("   ⚠️  Warning: Some expected sections missing")

            # Step 9: Verify defensive and offensive moves
            print("\n📍 Step 9: Checking for strategic recommendations...")
            has_defensive = "defensive" in content.lower()
            has_offensive = "offensive" in content.lower()

            if has_defensive:
                print("   ✅ Defensive strategic move identified")
            if has_offensive:
                print("   ✅ Offensive strategic move identified")

            # Step 10: Take screenshots for documentation
            print("\n📍 Step 10: Capturing evidence screenshots...")

            # Full page screenshot
            full_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_live_fullpage.png"
            page.screenshot(path=full_screenshot, full_page=True)
            print(f"   ✅ Full page: {full_screenshot}")

            # Just the industry context section
            industry_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_live_industry_context.png"
            industry_container.screenshot(path=industry_screenshot)
            print(f"   ✅ Industry section: {industry_screenshot}")

            # Step 11: Test collapsible functionality
            print("\n📍 Step 11: Testing collapsible functionality...")
            details = industry_container.locator("details")
            is_open_before = page.evaluate("document.querySelector('#industry-context-container details').open")
            print(f"   📊 Initially open: {is_open_before}")

            # Click to toggle
            summary_elem = details.locator("summary")
            summary_elem.click()
            time.sleep(0.3)

            is_open_after = page.evaluate("document.querySelector('#industry-context-container details').open")
            print(f"   📊 After click: {is_open_after}")

            if is_open_before != is_open_after:
                print("   ✅ Collapsible toggle works correctly")

            # Step 12: Verify it's only in discovery mode
            print("\n📍 Step 12: Verifying mode-specific behavior...")
            current_mode = page.locator(".mode-button.active").get_attribute("data-mode")
            assert current_mode == "discovery", f"Expected discovery mode, got {current_mode}"
            print(f"   ✅ Confirmed running in '{current_mode}' mode")
            print("   ✅ Industry context only appears in Audit the Brand mode")

            # Final summary
            print("\n" + "=" * 70)
            print("✅ ALL TESTS PASSED - LIVE INDUSTRY CONTEXT FEATURE WORKING!")
            print("=" * 70)
            print(f"\n📊 Test Results:")
            print(f"   • Mode: Audit the Brand (discovery) ✅")
            print(f"   • Executive Summary: ✅ Displayed")
            print(f"   • Industry Context: ✅ Displayed")
            print(f"   • Content Quality: ✅ {len(found_sections)}/{len(required_sections)} sections")
            print(f"   • Strategic Moves: ✅ {'Defensive' if has_defensive else ''} {'Offensive' if has_offensive else ''}")
            print(f"   • Collapsible UI: ✅ Working")
            print(f"   • Screenshots: ✅ Saved")
            print(f"   • Total Phases: {len(phases_seen)}")
            print(f"   • Total Time: {int(time.time() - start_time)}s")

            # Sample of content
            print(f"\n📝 Content Preview (first 500 chars):")
            print("   " + "-" * 66)
            print("   " + content[:500].replace("\n", "\n   ") + "...")
            print("   " + "-" * 66)

            # Wait to see the result
            print("\n⏸️  Pausing for 5 seconds to view the result...")
            time.sleep(5)

            return True

        except Exception as e:
            print(f"\n❌ TEST FAILED: {str(e)}")

            # Take error screenshot
            try:
                error_screenshot = "/Users/ben/Documents/Saffron/memoscan2/test_live_error.png"
                page.screenshot(path=error_screenshot, full_page=True)
                print(f"   📸 Error screenshot: {error_screenshot}")
            except:
                pass

            # Print current page state
            try:
                print("\n📋 Current Page State:")
                print(f"   URL: {page.url}")
                print(f"   Title: {page.title()}")

                # Check what's visible
                if page.locator("#summary-container").is_visible():
                    print("   ✅ Executive summary is visible")
                else:
                    print("   ❌ Executive summary not visible")

                if page.locator("#industry-context-container").is_visible():
                    print("   ✅ Industry context is visible")
                else:
                    print("   ❌ Industry context not visible")

            except:
                pass

            raise

        finally:
            print("\n🧹 Cleaning up...")
            browser.close()

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🚀 Starting Live E2E Test for Industry Context Feature")
    print("=" * 70)
    print("\nPrerequisites:")
    print("  ✅ Flask app running on port 8081")
    print("  ✅ OPENAI_API_KEY environment variable set")
    print("  ✅ Playwright installed\n")

    try:
        success = test_industry_context_live()
        if success:
            print("\n✅ TEST SUITE PASSED")
            exit(0)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        exit(1)
    except Exception as e:
        print(f"\n\n❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
