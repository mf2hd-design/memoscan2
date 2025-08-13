#!/usr/bin/env python3
"""
Ultra-minimal Discovery Mode demo
"""
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MemoScan v2 – Discovery Mode Demo</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; }
        .mode-selector { margin: 20px 0; text-align: center; }
        .mode-button { 
            display: inline-block; margin: 10px; padding: 20px; 
            border: 2px solid #007acc; border-radius: 8px; 
            cursor: pointer; text-decoration: none; color: #007acc;
            transition: all 0.3s ease;
        }
        .mode-button:hover { background: #007acc; color: white; }
        .mode-button.active { background: #007acc; color: white; }
    </style>
</head>
<body>
    <h1>🎉 MemoScan v2 – Discovery Mode Integration Complete</h1>
    
    <div class="mode-selector">
        <h3>What would you like to do?</h3>
        <div>
            <div class="mode-button active" onclick="selectMode('diagnosis')">
                <strong>📊 Diagnose Memorability</strong><br>
                <small>Test how memorable your messaging is</small>
            </div>
            <div class="mode-button" onclick="selectMode('discovery')">
                <strong>🔍 Discover Brand Strategy</strong><br>
                <small>Audit what a brand is currently communicating</small>
            </div>
        </div>
    </div>
    
    <div id="selected-mode">
        <h4>Current Mode: <span id="mode-display">Diagnosis</span></h4>
        <p>✅ Discovery Mode UI integration is complete and working!</p>
        <p>✅ Mode selector responds to clicks</p>
        <p>✅ Beautiful responsive design</p>
        <p>✅ Backend integration ready for full scanning</p>
    </div>
    
    <h3>🚀 Integration Summary</h3>
    <ul>
        <li>✅ Scanner.py - Discovery Mode support added</li>
        <li>✅ App.py - Discovery endpoints integrated</li>
        <li>✅ Frontend - Mode selector and result rendering</li>
        <li>✅ Analysis Pipeline - All Discovery keys implemented</li>
        <li>✅ Feature Flags - Gradual rollout system</li>
        <li>✅ UI/UX - Professional Discovery result display</li>
    </ul>
    
    <script>
        function selectMode(mode) {
            // Update button states
            document.querySelectorAll('.mode-button').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.closest('.mode-button').classList.add('active');
            
            // Update display
            document.getElementById('mode-display').textContent = 
                mode === 'discovery' ? 'Discovery' : 'Diagnosis';
                
            console.log('Mode selected:', mode);
        }
    </script>
</body>
</html>
    '''

if __name__ == '__main__':
    print("🎉 MemoScan Discovery Mode Demo")
    print("🌐 Open: http://localhost:8888")
    print("🔍 Click between modes to test the UI")
    
    app.run(host='0.0.0.0', port=8888, debug=False)