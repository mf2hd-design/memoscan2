#!/usr/bin/env python3
"""
Diagnostic test script to verify image capture and encoding
Saves the Scrapfly image locally to verify what we're actually getting
"""

import os
import base64
import httpx
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_scrapfly_screenshot_with_save(url: str) -> tuple[str, str]:
    """Capture a screenshot using Scrapfly API and save locally for inspection"""
    api_key = os.getenv("SCRAPFLY_KEY")
    if not api_key:
        raise ValueError("SCRAPFLY_KEY environment variable not set")
    
    print(f"🔍 SCRAPFLY: Capturing screenshot of {url}")
    
    params = {
        "key": api_key,
        "url": url,
        "render_js": True,
        "screenshots[main]": "fullpage",
        "screenshot_flags": "load_images,block_banners",
        "rendering_stage": "domcontentloaded",
        "rendering_wait": 3000,
        "retry": True,
        "country": "us",
        "proxy_pool": "public_residential_pool"
    }
    
    with httpx.Client() as client:
        response = client.get("https://api.scrapfly.io/scrape", params=params, timeout=180)
        response.raise_for_status()
        data = response.json()
        
        print(f"🔍 SCRAPFLY RESPONSE DEBUG:")
        print(f"  - Status: {response.status_code}")
        print(f"  - Result keys: {list(data.get('result', {}).keys())}")
        
        if "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
            screenshot_info = data["result"]["screenshots"]["main"]
            screenshot_url = screenshot_info["url"]
            print(f"📸 SCRAPFLY: Screenshot info: {screenshot_info}")
            print(f"📸 SCRAPFLY: Screenshot URL: {screenshot_url}")
            
            # Download the screenshot
            img_response = client.get(screenshot_url, params={"key": api_key}, timeout=60)
            img_response.raise_for_status()
            
            # Save the raw image file for inspection
            local_filename = "scrapfly_screenshot.png"
            with open(local_filename, 'wb') as f:
                f.write(img_response.content)
            print(f"💾 SAVED: Screenshot saved to {local_filename} ({len(img_response.content)} bytes)")
            
            # Create base64 encoding
            screenshot_b64 = base64.b64encode(img_response.content).decode('utf-8')
            print(f"✅ SCRAPFLY: Base64 encoding created ({len(screenshot_b64)} chars)")
            
            # Validate base64 can be decoded
            try:
                decoded_test = base64.b64decode(screenshot_b64)
                print(f"✅ BASE64 VALIDATION: Successfully decoded ({len(decoded_test)} bytes)")
            except Exception as e:
                print(f"❌ BASE64 VALIDATION FAILED: {e}")
                
            return screenshot_b64, local_filename
        else:
            print(f"❌ No screenshot in response. Available keys: {data.get('result', {}).keys()}")
            raise ValueError("Screenshot not found in Scrapfly response")

def test_openai_vision_diagnostic(screenshot_b64: str, test_url: str) -> dict:
    """Test OpenAI Vision API with diagnostic information"""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    print(f"🚀 OPENAI: Sending image to GPT-4V...")
    print(f"🔍 IMAGE DATA: {len(screenshot_b64)} base64 chars")
    print(f"🔍 DATA PREFIX: {screenshot_b64[:50]}...")
    
    # Simple, clear prompt
    simple_prompt = """
    Can you see this image? Please answer with either:
    - YES: I can see the image, and describe what you see in detail
    - NO: I cannot see the image, and explain why
    
    If you can see it, describe the main elements, colors, and any text visible.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user", 
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot_b64}",
                                "detail": "high"
                            }
                        },
                        {
                            "type": "text",
                            "text": simple_prompt
                        }
                    ]
                }
            ],
            max_tokens=800,
            temperature=0.1
        )
        
        result = {
            "success": True,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            "analysis": response.choices[0].message.content
        }
        
        print(f"✅ OPENAI: Response received!")
        print(f"📊 TOKEN BREAKDOWN:")
        print(f"  - Prompt tokens: {result['usage']['prompt_tokens']}")
        print(f"  - Completion tokens: {result['usage']['completion_tokens']}")
        print(f"  - Total tokens: {result['usage']['total_tokens']}")
        
        return result
        
    except Exception as e:
        print(f"❌ OPENAI ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

def main():
    """Run the diagnostic pipeline test"""
    test_url = "https://www.google.com"
    
    print("🧪 DIAGNOSTIC SCRAPFLY → OPENAI IMAGE PIPELINE TEST")
    print("=" * 60)
    
    try:
        # Step 1: Capture and save screenshot
        screenshot_b64, local_file = test_scrapfly_screenshot_with_save(test_url)
        
        print(f"\n📁 You can inspect the captured image at: {local_file}")
        
        # Step 2: Test with OpenAI
        result = test_openai_vision_diagnostic(screenshot_b64, test_url)
        
        # Step 3: Analysis
        print("\n" + "=" * 60)
        print("🎯 DIAGNOSTIC RESULTS")
        print("=" * 60)
        
        if result["success"]:
            print(f"📝 OPENAI RESPONSE:")
            print("-" * 40)
            print(result["analysis"])
            print("-" * 40)
            
            # Token analysis for vision
            prompt_tokens = result['usage']['prompt_tokens']
            if prompt_tokens > 1000:
                print(f"✅ IMAGE PROCESSING: {prompt_tokens} prompt tokens suggests image was processed")
                print("   (Vision API uses ~765+ tokens per image)")
            else:
                print(f"⚠️  POSSIBLE TEXT-ONLY: {prompt_tokens} prompt tokens may indicate text-only")
            
            # Check response content
            if "YES" in result["analysis"] or "can see" in result["analysis"].lower():
                print("✅ VISION CONFIRMED: OpenAI confirms it can see the image")
            elif "NO" in result["analysis"] or "cannot see" in result["analysis"].lower():
                print("❌ VISION FAILED: OpenAI cannot see the image")
            else:
                print("⚠️  UNCLEAR: Response is ambiguous about vision capability")
                
        else:
            print("❌ OPENAI API FAILED")
            print(f"Error: {result.get('error')}")
        
        print(f"\n🔍 NEXT STEPS:")
        print(f"1. Check the saved image: open {local_file}")
        print(f"2. Verify image is valid PNG/JPEG")
        print(f"3. Check OpenAI usage dashboard for image requests")
        print(f"4. Monitor for any API billing related to vision")
            
    except Exception as e:
        print(f"\n❌ DIAGNOSTIC TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()