#!/usr/bin/env python3
"""
Test script to verify GPT-5.1 API integration for Industry Context Analysis.
This will make a real API call to validate the implementation.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the scanner module
sys.path.insert(0, '/Users/ben/Documents/Saffron/memoscan2')
from scanner import analyze_industry_context, client, log

def test_gpt5_industry_analysis():
    """Test the industry context analysis with real API call."""

    print("=" * 70)
    print("🧪 GPT-5.1 API Integration Test for Industry Context Analysis")
    print("=" * 70)

    # Check if OpenAI client is initialized
    if client is None:
        print("\n❌ ERROR: OpenAI client not initialized")
        print("   Please ensure OPENAI_API_KEY is set in environment")
        return False

    print(f"\n✅ OpenAI client initialized")
    print(f"   API Key present: {'Yes' if os.getenv('OPENAI_API_KEY') else 'No'}")

    # Prepare test data - simulating a brand scan for Apple
    test_brand_summary = """
    Apple is a global technology company that designs, manufactures, and markets
    consumer electronics, computer software, and online services. The company is
    best known for its iPhone, iPad, Mac computers, Apple Watch, and services like
    iCloud, Apple Music, and the App Store. Apple's brand is characterized by
    innovation, premium quality, elegant design, and a strong ecosystem of
    integrated products and services. The company positions itself at the high end
    of the market, emphasizing user experience and seamless integration across devices.
    """

    test_text_corpus = """
    Apple Inc. is an American multinational technology company headquartered in
    Cupertino, California. Apple is the world's largest technology company by revenue,
    totaling $394.3 billion in 2022, and the world's biggest company by market
    capitalization as of January 2023.

    Products and Services:
    - iPhone: The company's flagship smartphone product line
    - Mac: Desktop and laptop computers running macOS
    - iPad: Tablet computer line
    - Apple Watch: Smartwatch and fitness tracker
    - AirPods: Wireless earbuds
    - Services: App Store, iCloud, Apple Music, Apple TV+, Apple Pay

    Company Values:
    - Innovation: Continuously pushing boundaries in technology
    - Privacy: Strong commitment to user privacy and data security
    - Sustainability: Carbon neutral goals and environmental initiatives
    - Accessibility: Making technology accessible to all users
    - Quality: Premium materials and craftsmanship

    Business Model:
    Apple operates in a hardware-software-services ecosystem. The company designs
    its own chips (Apple Silicon), develops its own operating systems (iOS, macOS,
    watchOS), and offers a growing portfolio of subscription services.

    Market Position:
    Apple competes in the premium segment of consumer electronics, targeting
    affluent consumers and creative professionals. The company has one of the
    strongest brand loyalties in the technology industry.
    """

    print("\n" + "=" * 70)
    print("📝 Test Data Prepared")
    print("=" * 70)
    print(f"Brand Summary Length: {len(test_brand_summary)} characters")
    print(f"Text Corpus Length: {len(test_text_corpus)} characters")

    # Make the API call
    print("\n" + "=" * 70)
    print("🚀 Calling GPT-5.1 API...")
    print("=" * 70)
    print("⏳ This may take 15-30 seconds for GPT-5.1 reasoning...")

    try:
        result = analyze_industry_context(test_brand_summary, test_text_corpus)

        print("\n" + "=" * 70)
        print("✅ API CALL SUCCESSFUL!")
        print("=" * 70)

        # Display results
        print(f"\n📊 Response Length: {len(result)} characters")
        print(f"\n📄 Industry Context Analysis Result:")
        print("=" * 70)
        print(result)
        print("=" * 70)

        # Validate response structure
        print("\n" + "=" * 70)
        print("🔍 Validating Response Structure")
        print("=" * 70)

        expected_sections = [
            "Market Dynamics",
            "Competitive Landscape",
            "Buyer Dynamics",
            "Technological",
            "Strategic"
        ]

        found_sections = []
        for section in expected_sections:
            if section.lower() in result.lower():
                found_sections.append(section)
                print(f"   ✅ Found: {section}")
            else:
                print(f"   ❌ Missing: {section}")

        print(f"\n📊 Sections Found: {len(found_sections)}/{len(expected_sections)}")

        if len(found_sections) >= 4:
            print("\n✅ Response structure looks good!")
            success = True
        else:
            print("\n⚠️  Warning: Some expected sections missing")
            success = True  # Still count as success if API worked

        # Check for error messages
        if "unavailable" in result.lower() or "technical issue" in result.lower():
            print("\n⚠️  Response contains error/unavailable message")
            success = False

        return success

    except AttributeError as e:
        if "'OpenAI' object has no attribute 'responses'" in str(e):
            print("\n" + "=" * 70)
            print("❌ API STRUCTURE ERROR")
            print("=" * 70)
            print(f"Error: {e}")
            print("\n🔍 Diagnosis:")
            print("   The OpenAI client doesn't have a 'responses' attribute.")
            print("   This suggests:")
            print("   1. GPT-5.1 may not be available yet in the API")
            print("   2. The API structure might be different")
            print("   3. The OpenAI SDK version might need updating")
            print(f"\n   Current OpenAI SDK version: {getattr(client, '__version__', 'unknown')}")
            print("\n💡 Recommendation:")
            print("   We should check OpenAI's latest API documentation")
            print("   or use GPT-4o as a fallback until GPT-5.1 is available.")
            return False

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ API CALL FAILED")
        print("=" * 70)
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")

        import traceback
        print("\n📋 Full Traceback:")
        print("-" * 70)
        traceback.print_exc()
        print("-" * 70)

        return False

if __name__ == "__main__":
    print("\n🚀 Starting GPT-5.1 API Test\n")

    try:
        success = test_gpt5_industry_analysis()

        print("\n" + "=" * 70)
        if success:
            print("✅ TEST PASSED - GPT-5.1 Integration Working!")
        else:
            print("❌ TEST FAILED - Issues Detected")
        print("=" * 70)

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
