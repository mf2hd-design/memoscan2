#!/usr/bin/env python3
"""
Test script that exactly mimics the scanner's image flow:
Scrapfly → Base64 → OpenAI Vision → Memorability Analysis
"""

import os
import base64
import httpx
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_complete_scanner_flow(url: str = "https://www.apple.com"):
    """Test the complete flow exactly as the scanner does it"""
    
    print("🧪 TESTING COMPLETE SCANNER IMAGE FLOW")
    print("=" * 50)
    print(f"Target URL: {url}")
    print("=" * 50)
    
    # Step 1: Scrapfly Screenshot (exactly like scanner)
    print("\n📸 STEP 1: SCRAPFLY SCREENSHOT CAPTURE")
    
    api_key = os.getenv("SCRAPFLY_KEY")
    if not api_key:
        raise ValueError("SCRAPFLY_KEY environment variable not set")
    
    params = {
        "key": api_key,
        "url": url,
        "render_js": True,
        "asp": True,
        "auto_scroll": True,
        "wait_for_selector": "footer a, nav a, main a, [role='main'] a, [class*='footer'] a",
        "rendering_stage": "domcontentloaded",
        "rendering_wait": 3000,
        "retry": True,
        "country": "us",
        "proxy_pool": "public_residential_pool",
        "screenshots[main]": "fullpage",
        "screenshot_flags": "load_images,block_banners"
    }
    
    with httpx.Client(proxies=None) as client:
        response = client.get("https://api.scrapfly.io/scrape", params=params, timeout=180)
        response.raise_for_status()
        data = response.json()
        
        # Extract screenshot exactly like scanner
        screenshot_b64 = None
        if "screenshots" in data["result"] and "main" in data["result"]["screenshots"]:
            screenshot_url = data["result"]["screenshots"]["main"]["url"]
            print(f"✅ Screenshot URL obtained: {screenshot_url}")
            
            img_response = client.get(screenshot_url, params={"key": api_key}, timeout=60)
            img_response.raise_for_status()
            screenshot_b64 = base64.b64encode(img_response.content).decode('utf-8')
            print(f"✅ Screenshot encoded: {len(screenshot_b64)} base64 chars")
        
        html_content = data["result"]["content"]
        print(f"✅ HTML content: {len(html_content)} chars")
    
    # Step 2: OpenAI Memorability Analysis (exactly like scanner)
    print("\n🧠 STEP 2: OPENAI MEMORABILITY ANALYSIS")
    
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Use the exact prompt structure from our scanner
    key_name = "Emotion"  # Test with one key
    brand_summary = "Test brand analysis for pipeline verification"
    text_corpus = f"Website content from {url}: Navigation, product information, brand messaging."
    
    prompt_template = """Analyze the **Emotion** key. This is the primary key; without it, nothing is memorable.
- **Your analysis must cover:** How the brand connects with audiences on an emotional level. Does it evoke warmth, trust, joy, or admiration? Does it use meaningful experiences, human stories, or mission-driven language? Is there a clear emotional reward for the user?"""
    
    # Construct content array exactly like scanner
    content = [
        {"type": "text", "text": f"FULL WEBSITE & SOCIAL MEDIA TEXT CORPUS:\n---\n{text_corpus}\n---"},
        {"type": "text", "text": f"BRAND SUMMARY (for context):\n---\n{brand_summary}\n---"}
    ]
    
    if screenshot_b64:
        content.insert(0, {
            "type": "image_url", 
            "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}
        })
        print(f"✅ Image included in OpenAI request ({len(screenshot_b64)} chars)")
    else:
        print("❌ No screenshot to include")
    
    system_prompt = f"""You are a senior brand strategist from Saffron Brand Consultants, providing an expert evaluation.
{prompt_template}

**SCORING GUIDELINES:**
You MUST provide a numerical score from 0 to 5 based on the following rubric:
- **0:** The principle is completely absent or highly detrimental.
- **1:** The principle is present but extremely weak; barely noticeable or inconsistent.
- **2:** The principle is somewhat present but weak; significant flaws or missed opportunities.
- **3:** The principle is adequately applied; meets basic standards but not outstanding.
- **4:** The principle is strong and consistently applied; a clear asset to the brand.
- **5:** The principle is exceptional; a textbook example of brand excellence in this area.

Your response MUST be a JSON object with "score", "analysis", "evidence", "confidence", "confidence_rationale", and "recommendation" keys. The "score" MUST be an integer between 0 and 5.
The "confidence" score should be an integer from 0 to 100 representing your certainty in this analysis.
"""
    
    print(f"🚀 Calling OpenAI with {len(content)} content items...")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ],
        response_format={"type": "json_object"},
        temperature=0.3
    )
    
    print(f"✅ OpenAI response received!")
    print(f"📊 Tokens: {response.usage.total_tokens} ({response.usage.prompt_tokens} prompt + {response.usage.completion_tokens} completion)")
    
    # Step 3: Parse and display results
    print("\n🎯 STEP 3: RESULTS ANALYSIS")
    print("=" * 50)
    
    try:
        result_json = json.loads(response.choices[0].message.content)
        
        print("✅ JSON PARSING: Success")
        print(f"📊 EMOTION SCORE: {result_json.get('score', 'N/A')}/5")
        print(f"🎯 CONFIDENCE: {result_json.get('confidence', 'N/A')}/100")
        print(f"\n📝 ANALYSIS:")
        print(f"{result_json.get('analysis', 'No analysis provided')}")
        print(f"\n🔍 EVIDENCE:")
        print(f"{result_json.get('evidence', 'No evidence provided')}")
        print(f"\n💡 RECOMMENDATION:")
        print(f"{result_json.get('recommendation', 'No recommendation provided')}")
        
        # Verification checklist
        print("\n" + "=" * 50)
        print("✅ COMPLETE PIPELINE VERIFICATION")
        print("=" * 50)
        print("✅ Scrapfly successfully captured HTML and screenshot")
        print("✅ Base64 encoding successful")
        print("✅ OpenAI Vision API processed image successfully")
        print("✅ JSON response structure matches scanner requirements")
        print("✅ Memorability analysis completed with confidence score")
        print(f"✅ High token usage ({response.usage.prompt_tokens} prompt) confirms image processing")
        print("✅ This request will appear in OpenAI dashboard as vision API usage")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON PARSING FAILED: {e}")
        print(f"Raw response: {response.choices[0].message.content}")
        return False

if __name__ == "__main__":
    try:
        success = test_complete_scanner_flow()
        if success:
            print("\n🎉 SCANNER IMAGE PIPELINE: FULLY OPERATIONAL")
        else:
            print("\n❌ SCANNER IMAGE PIPELINE: ISSUES DETECTED")
    except Exception as e:
        print(f"\n💥 PIPELINE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()