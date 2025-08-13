#!/usr/bin/env python3
"""
Quick test of Discovery Mode executive summary function
"""
import sys
import json
sys.path.insert(0, '.')

# Test the executive summary function directly
from scanner import call_openai_for_executive_summary

def test_discovery_executive_summary():
    print("🧪 TESTING DISCOVERY MODE EXECUTIVE SUMMARY")
    print("=" * 50)
    
    # Mock Discovery results (similar to what a real scan would produce)
    mock_discovery_results = [
        {
            'type': 'discovery_result',
            'key': 'positioning_themes',
            'analysis': {
                'themes': [
                    {
                        'theme': 'Innovation Leadership',
                        'confidence': 85,
                        'evidence': 'We pioneer breakthrough technologies that reshape industries'
                    },
                    {
                        'theme': 'Premium Quality',
                        'confidence': 80,
                        'evidence': 'Uncompromising excellence in everything we create'
                    }
                ]
            }
        },
        {
            'type': 'discovery_result',
            'key': 'key_messages',
            'analysis': {
                'messages': [
                    {
                        'message': 'Trusted by industry leaders',
                        'confidence': 90,
                        'evidence': 'Over 10,000 companies rely on our solutions'
                    },
                    {
                        'message': 'Cutting-edge innovation',
                        'confidence': 85,
                        'evidence': 'Leading the next generation of technology'
                    }
                ]
            }
        },
        {
            'type': 'discovery_result',
            'key': 'tone_of_voice',
            'analysis': {
                'tone_descriptors': [
                    {
                        'adjective': 'Authoritative',
                        'justification': 'Uses definitive language and industry expertise',
                        'confidence': 88,
                        'evidence': 'We set the standard for excellence'
                    },
                    {
                        'adjective': 'Innovative',
                        'justification': 'Emphasizes forward-thinking and breakthrough solutions',
                        'confidence': 82,
                        'evidence': 'Pioneering tomorrow\'s technology today'
                    }
                ]
            }
        },
        {
            'type': 'discovery_result',
            'key': 'brand_elements',
            'analysis': {
                'status': 'coming_soon',
                'message': 'Visual brand analysis will be available in Phase 2'
            }
        }
    ]
    
    print("📊 Mock Discovery Results:")
    for result in mock_discovery_results:
        if result['key'] != 'brand_elements':
            analysis = result['analysis']
            if 'themes' in analysis:
                print(f"   - {result['key']}: {len(analysis['themes'])} themes")
            elif 'messages' in analysis:
                print(f"   - {result['key']}: {len(analysis['messages'])} messages")
            elif 'tone_descriptors' in analysis:
                print(f"   - {result['key']}: {len(analysis['tone_descriptors'])} descriptors")
    
    print("\n🔍 Testing Discovery Mode executive summary generation...")
    
    try:
        # Test Discovery mode summary
        summary_text = call_openai_for_executive_summary(mock_discovery_results, mode='discovery')
        
        print("✅ Executive summary generated successfully!")
        print(f"📏 Summary length: {len(summary_text)} characters")
        print("\n📝 EXECUTIVE SUMMARY:")
        print("-" * 60)
        print(summary_text)
        print("-" * 60)
        
        # Check if it contains expected sections
        expected_sections = [
            "Discovery Mode Executive Summary",
            "Brand Overview",
            "Strategic Positioning", 
            "Messaging & Communication",
            "Recommendations"
        ]
        
        print("\n📊 Summary Analysis:")
        for section in expected_sections:
            if section in summary_text:
                print(f"   ✅ Contains '{section}' section")
            else:
                print(f"   ❌ Missing '{section}' section")
                
        return True
        
    except Exception as e:
        print(f"❌ Executive summary generation failed!")
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_discovery_executive_summary()
    print(f"\n🎯 Test Result: {'SUCCESS' if success else 'FAILED'}")