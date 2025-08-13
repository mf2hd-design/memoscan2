#!/usr/bin/env python3
"""
Automated test for Discovery Mode using Playwright
"""
import asyncio
import json
import time
from playwright.async_api import async_playwright

async def test_discovery_mode():
    """Test Discovery Mode server with automated browser interaction"""
    
    print("🎭 Starting Playwright test for Discovery Mode...")
    print("=" * 50)
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)  # Set to False to see the test
        context = await browser.new_context()
        page = await context.new_page()
        
        # Track console messages and network activity
        console_messages = []
        discovery_results = []
        
        def handle_console(msg):
            text = msg.text
            console_messages.append(text)
            if "DISCOVERY" in text or "discovery_result" in text:
                discovery_results.append(text)
                print(f"🎯 Discovery activity detected: {text[:100]}...")
        
        page.on("console", handle_console)
        
        try:
            # Navigate to Discovery Mode server
            print("📍 Navigating to http://localhost:8085...")
            await page.goto("http://localhost:8085", wait_until="networkidle")
            
            # Wait for connection
            await page.wait_for_selector(".status.connected", timeout=5000)
            print("✅ Connected to Discovery Mode server")
            
            # Get initial status
            status_text = await page.text_content("#status")
            print(f"📊 Status: {status_text}")
            
            # Clear results area
            await page.evaluate("document.getElementById('results').innerHTML = ''")
            
            # Set test URL
            test_url = "https://apple.com"
            await page.fill("#url", test_url)
            print(f"🔍 Testing with URL: {test_url}")
            
            # Take screenshot before scan
            await page.screenshot(path="/tmp/discovery_before_scan.png")
            print("📸 Screenshot saved: /tmp/discovery_before_scan.png")
            
            # Start scan
            print("🚀 Starting Discovery scan...")
            await page.click("button:has-text('Start Discovery Scan')")
            
            # Wait for scan to start
            await page.wait_for_timeout(2000)
            
            # Monitor scan progress
            start_time = time.time()
            max_wait = 120  # 2 minutes max
            discovery_found = False
            
            print("⏳ Monitoring scan progress...")
            
            while time.time() - start_time < max_wait:
                # Check for Discovery results
                discovery_elements = await page.query_selector_all(".discovery-result")
                
                if discovery_elements:
                    discovery_found = True
                    print(f"🎯 Found {len(discovery_elements)} Discovery results!")
                    
                    # Extract Discovery results
                    for i, element in enumerate(discovery_elements):
                        content = await element.text_content()
                        print(f"\n📊 Discovery Result #{i+1}:")
                        print(content[:200] + "..." if len(content) > 200 else content)
                    
                    break
                
                # Check for completion or error
                results_text = await page.text_content("#results")
                if "Scan completed" in results_text or "error" in results_text.lower():
                    break
                
                # Update progress
                elapsed = int(time.time() - start_time)
                if elapsed % 10 == 0:
                    status = await page.text_content("#status")
                    print(f"⏱️ {elapsed}s - Status: {status}")
                
                await page.wait_for_timeout(1000)
            
            # Take final screenshot
            await page.screenshot(path="/tmp/discovery_after_scan.png")
            print("\n📸 Final screenshot saved: /tmp/discovery_after_scan.png")
            
            # Get final results
            final_results = await page.text_content("#results")
            
            # Analyze results
            print("\n" + "=" * 50)
            print("📊 TEST RESULTS:")
            print("=" * 50)
            
            if discovery_found:
                print("✅ SUCCESS: Discovery results were generated!")
                
                # Count specific Discovery keys
                positioning_count = final_results.count("positioning_themes")
                messages_count = final_results.count("key_messages")
                tone_count = final_results.count("tone_of_voice")
                
                print(f"📈 Results breakdown:")
                print(f"   - Positioning Themes: {'✅' if positioning_count > 0 else '❌'}")
                print(f"   - Key Messages: {'✅' if messages_count > 0 else '❌'}")
                print(f"   - Tone of Voice: {'✅' if tone_count > 0 else '❌'}")
                
            elif "error" in final_results.lower():
                print("❌ FAILED: Scan encountered errors")
                error_lines = [line for line in final_results.split('\n') if 'error' in line.lower()]
                for error in error_lines[:3]:  # Show first 3 errors
                    print(f"   ⚠️ {error}")
                    
            elif "Scan completed" in final_results:
                print("⚠️ PARTIAL: Scan completed but no Discovery results found")
                print("   This may indicate the Discovery analysis isn't being triggered")
                
            else:
                print("❌ TIMEOUT: Scan did not complete within 2 minutes")
            
            # Show console messages if any errors
            if any('error' in msg.lower() for msg in console_messages):
                print("\n🔍 Browser console errors:")
                for msg in console_messages:
                    if 'error' in msg.lower():
                        print(f"   ⚠️ {msg}")
            
            print("\n" + "=" * 50)
            print("🎭 Playwright test completed")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            await page.screenshot(path="/tmp/discovery_error.png")
            print("📸 Error screenshot saved: /tmp/discovery_error.png")
            raise
            
        finally:
            await browser.close()

# Run the test
if __name__ == "__main__":
    asyncio.run(test_discovery_mode())