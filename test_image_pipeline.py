#!/usr/bin/env python3
"""
Quick test script to verify Scrapfly → OpenAI image pipeline
Tests that images are properly captured, encoded, and processed by OpenAI Vision API
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

def test_openai_vision(screenshot_b64: str, test_url: str) -> dict:
    """Test OpenAI Vision API with the screenshot"""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    print(f"🚀 OPENAI: Sending image to GPT-4V for analysis...")
    
    # Create a detailed prompt that will trigger comprehensive image analysis
    test_prompt = f"""
    I am testing my image processing pipeline. Please analyze this screenshot of {test_url} and provide:
    
    1. CONFIRMATION: Can you see and interpret this image? (Yes/No)
    2. VISUAL DESCRIPTION: Describe what you see in detail (layout, colors, text, elements)
    3. BRAND ANALYSIS: What brand/company is this and what's their main value proposition?
    4. IMAGE QUALITY: Rate the screenshot quality (1-10)
    5. TECHNICAL DETAILS: Image dimensions if visible, any rendering issues
    
    Please be very detailed - this confirms the image was successfully transmitted and processed.
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
                                "url": f"data:image/png;base64,{screenshot_b64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": test_prompt
                        }
                    ]
                }
            ],
            max_tokens=1000,
            temperature=0.3
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
    """Run the complete pipeline test"""
    # Test URL - use a visually rich, well-known site
    test_url = "https://www.apple.com"
    
    print("🧪 TESTING COMPLETE SCRAPFLY → OPENAI IMAGE PIPELINE")
    print("=" * 60)
    
    try:
        # Step 1: Capture screenshot with Scrapfly
        screenshot_b64 = test_scrapfly_screenshot(test_url)
        
        # Step 2: Send to OpenAI Vision API
        result = test_openai_vision(screenshot_b64, test_url)
        
        # Step 3: Display results
        print("\n" + "=" * 60)
        print("🎯 PIPELINE TEST RESULTS")
        print("=" * 60)
        
        if result["success"]:
            print("✅ OVERALL STATUS: SUCCESS - Image pipeline working correctly!")
            print(f"\n📝 OPENAI ANALYSIS:")
            print("-" * 40)
            print(result["analysis"])
            print("-" * 40)
            print(f"\n📊 TOKEN USAGE: {result['usage']}")
            print(f"💰 ESTIMATED COST: ~${result['usage']['total_tokens'] * 0.00003:.4f}")
            print("\n🔍 VERIFICATION:")
            print("- ✅ Scrapfly successfully captured screenshot")
            print("- ✅ OpenAI successfully received and processed image")
            print("- ✅ Detailed visual analysis confirms image interpretation")
            print("- ✅ This should trigger image usage in OpenAI dashboard")
        else:
            print("❌ OVERALL STATUS: FAILED")
            print(f"Error: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"\n❌ PIPELINE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()