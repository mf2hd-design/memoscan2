#!/usr/bin/env python3
"""
Backend monitor - shows what the Discovery server is actually doing
"""
import os
import sys
import time
import subprocess
import threading

def monitor_logs():
    """Monitor the backend activity"""
    print("🔍 DISCOVERY MODE BACKEND MONITOR")
    print("=" * 50)
    print("Monitoring backend activity for Discovery Mode scans...")
    print("Press Ctrl+C to stop monitoring")
    print("-" * 50)
    
    try:
        # Check if server is running
        result = subprocess.run(['pgrep', '-f', 'final_discovery_server.py'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            pid = result.stdout.strip()
            print(f"✅ Discovery server running (PID: {pid})")
        else:
            print("❌ Discovery server not found")
            return
        
        # Monitor system activity
        print("\n📊 System Activity:")
        print(f"⏰ {time.strftime('%H:%M:%S')} - Backend monitor started")
        
        # Check network connections
        try:
            netstat_result = subprocess.run(['netstat', '-an'], 
                                          capture_output=True, text=True)
            if ':8081' in netstat_result.stdout:
                print("✅ Port 8081 is bound and listening")
            else:
                print("❌ Port 8081 not found in netstat")
        except:
            print("⚠️  Could not check network status")
        
        # Check if Discovery components are working
        print("\n🧪 Testing Discovery Mode components:")
        test_result = subprocess.run([
            'python3', '-c',
            '''
import sys
sys.path.insert(0, '.')
import os
os.environ["PERSISTENT_DATA_DIR"] = "/tmp"

try:
    from scanner import init_discovery_mode, DISCOVERY_AVAILABLE
    print(f"✅ Discovery available: {DISCOVERY_AVAILABLE}")
    
    result = init_discovery_mode()
    print(f"✅ Discovery init result: {result}")
    
    from discovery_integration import FeatureFlags
    print(f"✅ Feature flags work: {FeatureFlags.is_discovery_enabled()}")
    
except Exception as e:
    print(f"❌ Error: {e}")
            '''
        ], capture_output=True, text=True)
        
        print(test_result.stdout)
        if test_result.stderr:
            print("Warnings:", test_result.stderr)
        
        # Monitor file changes (scan activity)
        print(f"\n📁 Monitoring /tmp for scan activity...")
        
        start_time = time.time()
        last_activity = start_time
        
        while True:
            current_time = time.time()
            
            # Check for new log files or changes
            try:
                discovery_files = []
                for file in os.listdir('/tmp'):
                    if 'discovery' in file.lower() or 'scan' in file.lower():
                        file_path = os.path.join('/tmp', file)
                        if os.path.isfile(file_path):
                            mod_time = os.path.getmtime(file_path)
                            if mod_time > last_activity:
                                discovery_files.append((file, mod_time))
                
                if discovery_files:
                    print(f"📝 {time.strftime('%H:%M:%S')} - Activity detected:")
                    for file, mod_time in discovery_files:
                        print(f"   📄 {file} (modified: {time.strftime('%H:%M:%S', time.localtime(mod_time))})")
                    last_activity = current_time
                
            except Exception as e:
                pass
            
            # Show periodic status
            elapsed = int(current_time - start_time)
            if elapsed % 10 == 0 and elapsed > 0:
                print(f"⏰ {time.strftime('%H:%M:%S')} - Monitor running ({elapsed}s elapsed)")
            
            time.sleep(2)
            
    except KeyboardInterrupt:
        print(f"\n🛑 Monitor stopped at {time.strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ Monitor error: {e}")

if __name__ == '__main__':
    monitor_logs()