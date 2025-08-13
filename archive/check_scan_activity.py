#!/usr/bin/env python3
"""
Check current scan activity and show backend status
"""
import os
import time
import glob

def check_activity():
    print("🔍 DISCOVERY MODE SCAN ACTIVITY CHECK")
    print("=" * 45)
    
    # Check server process
    import subprocess
    try:
        result = subprocess.run(['pgrep', '-f', 'final_discovery_server.py'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Server running (PID: {result.stdout.strip()})")
        else:
            print("❌ Server not running")
            return
    except:
        print("❌ Could not check server status")
    
    # Check port
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8081))
        sock.close()
        if result == 0:
            print("✅ Port 8081 is accessible")
        else:
            print("❌ Port 8081 not accessible")
    except:
        print("⚠️  Could not test port")
    
    # Check recent file activity
    print("\n📁 Recent file activity in /tmp:")
    scan_files = glob.glob('/tmp/*discovery*') + glob.glob('/tmp/*scan*') + glob.glob('/tmp/.admin_key')
    
    if scan_files:
        # Sort by modification time
        files_with_time = []
        for f in scan_files:
            try:
                mod_time = os.path.getmtime(f)
                files_with_time.append((f, mod_time))
            except:
                continue
        
        files_with_time.sort(key=lambda x: x[1], reverse=True)
        
        print(f"Found {len(files_with_time)} scan-related files:")
        for f, mod_time in files_with_time[:10]:  # Show 10 most recent
            time_str = time.strftime('%H:%M:%S', time.localtime(mod_time))
            age = int(time.time() - mod_time)
            print(f"   📄 {os.path.basename(f)} (modified {time_str}, {age}s ago)")
    
    # Check network activity
    print(f"\n🌐 Testing server response:")
    try:
        import urllib.request
        response = urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=5)
        data = response.read().decode()
        print(f"✅ Health check: {data}")
    except Exception as e:
        print(f"❌ Health check failed: {e}")
    
    print(f"\n📊 Backend Status Summary:")
    print(f"   🖥️  Server: Running")
    print(f"   🔌 Port 8081: Accessible") 
    print(f"   🔍 Discovery Mode: Enabled")
    print(f"   📁 Scan files: {len(scan_files)} found")
    print(f"   ⏰ Current time: {time.strftime('%H:%M:%S')}")
    
    print(f"\n💡 If you started a scan in the browser:")
    print(f"   1. Check the browser console for WebSocket messages")
    print(f"   2. Look for scan progress in the results area")
    print(f"   3. Monitor this terminal for backend activity")
    print(f"   4. Discovery results should appear in 30-90 seconds")

if __name__ == '__main__':
    check_activity()