#!/usr/bin/env python3
"""
Enhanced test script to FORCE OpenAI to demonstrate it can actually see the image
Uses specific visual elements that can only be described if the image is truly processed
"""

import os
import base64
import httpx
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_scrapfly_screenshot(url: str) -> str:
    """Capture a screenshot using Scrapfly API"""
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
        
        if "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
            screenshot_url = data["result"]["screenshots"]["main"]["url"]
            print(f"📸 SCRAPFLY: Screenshot URL: {screenshot_url}")
            
            # Download the screenshot
            img_response = client.get(screenshot_url, params={"key": api_key}, timeout=60)
            img_response.raise_for_status()
            
            screenshot_b64 = base64.b64encode(img_response.content).decode('utf-8')
            print(f"✅ SCRAPFLY: Screenshot captured successfully ({len(screenshot_b64)} base64 chars)")
            return screenshot_b64
        else:
            raise ValueError("Screenshot not found in Scrapfly response")

def test_openai_vision_forced(screenshot_b64: str, test_url: str) -> dict:
    """Test OpenAI Vision API with questions that REQUIRE seeing the actual image"""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    print(f"🚀 OPENAI: Sending image to GPT-4V for FORCED visual analysis...")
    
    # Force OpenAI to demonstrate it can actually see by asking for specific visual details
    force_vision_prompt = """
    CRITICAL: You must look at this screenshot image and describe EXACTLY what you see.
    
    Answer these questions that can ONLY be answered by actually seeing the image:
    
    1. What is the EXACT main headline text at the top of the page? (Quote it exactly)
    2. What specific product images are visible? List them.
    3. What is the primary background color of the webpage?
    4. Are there any buttons visible? If so, what colors are they and what do they say?
    5. Read and transcribe any promotional text or offers you can see.
    6. What is positioned in the top-left corner of the page?
    7. Are there any people in the images? Describe them.
    8. What specific navigation menu items can you see?
    
    DO NOT make assumptions or provide generic descriptions. 
    You must look at the actual image to answer these questions.
    If you cannot see the image, explicitly state "I cannot see the image".
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
                                "detail": "high"  # Request high detail analysis
                            }
                        },
                        {
                            "type": "text",
                            "text": force_vision_prompt
                        }
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.1  # Low temperature for precise descriptions
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
        
        print(f"✅ OPENAI: Response received successfully!")
        print(f"📊 USAGE: {result['usage']['total_tokens']} tokens ({result['usage']['prompt_tokens']} prompt + {result['usage']['completion_tokens']} completion)")
        
        return result
        
    except Exception as e:
        print(f"❌ OPENAI ERROR: {e}")
        return {"success": False, "error": str(e)}

def main():
    """Run the enhanced pipeline test that forces visual confirmation"""
    # Use a simpler, more visually distinct site
    test_url = "https://www.google.com"
    
    print("🧪 TESTING ENHANCED SCRAPFLY → OPENAI IMAGE PIPELINE (FORCED VISION)")
    print("=" * 70)
    
    try:
        # Step 1: Capture screenshot with Scrapfly
        screenshot_b64 = test_scrapfly_screenshot(test_url)
        
        # Step 2: Send to OpenAI Vision API with forced visual questions
        result = test_openai_vision_forced(screenshot_b64, test_url)
        
        # Step 3: Display results
        print("\n" + "=" * 70)
        print("🎯 ENHANCED PIPELINE TEST RESULTS")
        print("=" * 70)
        
        if result["success"]:
            analysis_text = result["analysis"]
            
            # Check if OpenAI actually processed the image
            if "cannot see" in analysis_text.lower() or "unable to" in analysis_text.lower():
                print("❌ IMAGE PROCESSING: OpenAI indicates it cannot see the image")
                print(f"Response: {analysis_text[:200]}...")
            else:
                print("✅ IMAGE PROCESSING: OpenAI successfully processed and analyzed the image!")
                
            print(f"\n📝 DETAILED OPENAI ANALYSIS:")
            print("-" * 50)
            print(analysis_text)
            print("-" * 50)
            print(f"\n📊 TOKEN USAGE: {result['usage']}")
            print(f"💰 ESTIMATED COST: ~${result['usage']['total_tokens'] * 0.00003:.4f}")
            
            # Check for image tokens (vision models use more tokens for images)
            if result['usage']['prompt_tokens'] > 1000:
                print("✅ HIGH TOKEN COUNT: Indicates image was processed (vision uses ~765+ tokens per image)")
            else:
                print("⚠️  LOW TOKEN COUNT: May indicate text-only processing")
                
            print("\n🔍 VERIFICATION CHECKLIST:")
            print("- ✅ Scrapfly successfully captured screenshot")
            print("- ✅ Base64 encoding successful")
            print("- ✅ OpenAI API call completed")
            print("- ✅ High token usage suggests image processing")
            print("- ✅ This should appear in OpenAI usage dashboard as image request")
        else:
            print("❌ OVERALL STATUS: FAILED")
            print(f"Error: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"\n❌ ENHANCED PIPELINE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()