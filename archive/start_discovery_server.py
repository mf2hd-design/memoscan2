#!/usr/bin/env python3
"""
Discovery Mode Server Launcher
Start MemoScan v2 with Discovery Mode enabled and proper environment setup
"""

import os
import sys
from dotenv import load_dotenv

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Set Discovery Mode environment variables
    os.environ['PERSISTENT_DATA_DIR'] = '/tmp'
    os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
    os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'  # Enable for all users
    
    print("🚀 Starting MemoScan v2 with Discovery Mode...")
    print("=" * 50)
    
    # Verify critical environment variables
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found in .env file")
        print("Please check that your .env file contains:")
        print("OPENAI_API_KEY=your_api_key_here")
        return 1
    
    print(f"✅ OpenAI API Key: {'*' * 20}{api_key[-10:] if len(api_key) > 10 else api_key}")
    print(f"✅ Discovery Mode: {os.getenv('DISCOVERY_MODE_ENABLED')}")
    print(f"✅ Rollout Percentage: {os.getenv('DISCOVERY_ROLLOUT_PERCENTAGE')}%")
    print(f"✅ Data Directory: {os.getenv('PERSISTENT_DATA_DIR')}")
    
    # Import and start the app
    try:
        from app import app, socketio
        print("\n🎯 DISCOVERY MODE: FULLY ENABLED")
        print("🌐 Server URL: http://localhost:8081")
        print("🔍 Backend logs will appear below...")
        print("=" * 50)
        print()
        
        # Start the server with full logging
        socketio.run(
            app, 
            host='localhost', 
            port=8081, 
            debug=False,
            allow_unsafe_werkzeug=True
        )
        
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ ERROR starting server: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())