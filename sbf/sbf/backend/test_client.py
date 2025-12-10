#!/usr/bin/env python3
"""
SBF Test Client - Manual testing utility for the API.
Usage: python test_client.py [report_type] [--url URL]
"""

import argparse
import json
import sys
import time
import httpx
from typing import Optional


DEFAULT_URL = "http://localhost:8000"


def stream_report(
    base_url: str,
    report_type: str,
    params: dict,
    timeout: float = 300.0
) -> None:
    """Stream a report from the API and display progress."""
    
    url = f"{base_url}/api/v1/generate-report"
    
    print(f"\n{'='*60}")
    print(f"Generating {report_type} report...")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    
    try:
        with httpx.stream(
            "POST",
            url,
            data=params,
            timeout=timeout
        ) as response:
            request_id = response.headers.get("x-request-id", "unknown")
            print(f"Request ID: {request_id}\n")
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    msg_type = data.get("type", "unknown")
                    
                    if msg_type == "progress":
                        percent = data.get("progress_percent", 0)
                        message = data.get("message", "")
                        step = data.get("step", "")
                        bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
                        print(f"\r[{bar}] {percent:3d}% - {message}", end="", flush=True)
                    
                    elif msg_type == "result":
                        print("\n\n" + "="*60)
                        print("REPORT GENERATED SUCCESSFULLY")
                        print("="*60 + "\n")
                        
                        markdown = data.get("markdown", "")
                        print(markdown[:2000])
                        if len(markdown) > 2000:
                            print(f"\n... [truncated, {len(markdown)} chars total]")
                        
                        if data.get("chart"):
                            print("\n\n--- CHART DATA ---")
                            print(json.dumps(data["chart"], indent=2)[:500])
                        
                        metadata = data.get("metadata", {})
                        print(f"\n\n--- METADATA ---")
                        print(f"Duration: {metadata.get('duration_seconds', 0):.2f}s")
                        print(f"Workflow ID: {metadata.get('workflow_id', 'unknown')}")
                    
                    elif msg_type == "error":
                        print(f"\n\n❌ ERROR: {data.get('message', 'Unknown error')}")
                        print(f"   Details: {data.get('details', 'None')}")
                        if data.get("recoverable"):
                            print("   (This error may be recoverable)")
                
                except json.JSONDecodeError:
                    print(f"\n⚠️  Invalid JSON: {line[:100]}")
    
    except httpx.TimeoutException:
        print(f"\n\n❌ Request timed out after {timeout}s")
    except httpx.ConnectError:
        print(f"\n\n❌ Could not connect to {base_url}")
        print("   Make sure the server is running: uvicorn app.main:app --reload")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
    
    elapsed = time.time() - start_time
    print(f"\n\nTotal time: {elapsed:.2f}s")


def test_health(base_url: str) -> bool:
    """Test the health endpoint."""
    try:
        response = httpx.get(f"{base_url}/health", timeout=5.0)
        data = response.json()
        print(f"✅ Health check passed: {data}")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="SBF API Test Client")
    parser.add_argument(
        "report_type",
        nargs="?",
        default="brand_audit",
        choices=[
            "brand_audit", "meeting_brief", "industry_profile",
            "brand_house", "four_cs", "competitive_landscape", "audience_profile"
        ],
        help="Type of report to generate"
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="API base URL")
    parser.add_argument("--health", action="store_true", help="Run health check only")
    
    # Report-specific arguments
    parser.add_argument("--brand", default="Nike", help="Brand name")
    parser.add_argument("--brand-url", default="https://nike.com", help="Brand URL")
    parser.add_argument("--person", default="Tim Cook", help="Person name (meeting brief)")
    parser.add_argument("--role", default="CEO", help="Person role (meeting brief)")
    parser.add_argument("--company", default="Apple", help="Company name (meeting brief)")
    parser.add_argument("--industry", default="Athletic Footwear", help="Industry name")
    parser.add_argument("--audience", default="Gen Z Consumers", help="Audience name")
    parser.add_argument("--geography", default="US", help="Geographic market")
    parser.add_argument("--competitors", default="", help="Comma-separated competitors")
    
    args = parser.parse_args()
    
    print(f"\n🚀 SBF Test Client")
    print(f"   Server: {args.url}")
    
    if args.health:
        test_health(args.url)
        return
    
    # Check health first
    if not test_health(args.url):
        print("\n⚠️  Server may not be running. Continue anyway? (y/n) ", end="")
        if input().lower() != "y":
            return
    
    # Build params based on report type
    params = {
        "report_type": args.report_type,
        "geography": args.geography
    }
    
    if args.report_type == "brand_audit":
        params.update({
            "brand_name": args.brand,
            "brand_url": args.brand_url,
            "competitors": args.competitors
        })
    
    elif args.report_type == "meeting_brief":
        params.update({
            "person_name": args.person,
            "person_role": args.role,
            "company_name": args.company
        })
    
    elif args.report_type == "industry_profile":
        params["industry_name"] = args.industry
    
    elif args.report_type in ["brand_house", "four_cs", "competitive_landscape"]:
        params.update({
            "brand_name": args.brand,
            "brand_url": args.brand_url
        })
    
    elif args.report_type == "audience_profile":
        params["audience_name"] = args.audience
    
    print(f"\n📋 Parameters: {json.dumps(params, indent=2)}")
    
    stream_report(args.url, args.report_type, params)


if __name__ == "__main__":
    main()
