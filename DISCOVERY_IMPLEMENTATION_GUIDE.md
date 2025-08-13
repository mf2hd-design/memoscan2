# Discovery Mode Implementation Guide

## Phase 1 Implementation Checklist

### 1. Scanner.py Modifications (Minimal)

Add these lines to scanner.py to integrate Discovery Mode:

```python
# At the top of scanner.py, add:
from discovery_integration import enhance_scanner_for_discovery, FeatureFlags
from discovery_prompts import DECONSTRUCTION_KEYS_PROMPTS

# Add to the prompt registry section:
PROMPT_REGISTRY = {
    "diagnosis": MEMORABILITY_KEYS_PROMPTS,
    "discovery": DECONSTRUCTION_KEYS_PROMPTS
}

# Modify run_full_scan_stream signature:
def run_full_scan_stream(url: str, cache: dict, preferred_lang: str = 'en', 
                         scan_id: str = None, mode: str = 'diagnosis'):
    
    # Add mode tracking
    yield {'type': 'scan_metadata', 'mode': mode, 'scan_id': scan_id}
    
    # Check if Discovery Mode
    if mode == 'discovery' and FeatureFlags.is_discovery_enabled():
        # Use Discovery prompts
        prompts = PROMPT_REGISTRY['discovery']
        # ... rest of Discovery logic
    else:
        # Existing diagnosis logic
        prompts = PROMPT_REGISTRY['diagnosis']
        # ... existing code
```

### 2. App.py Modifications

```python
# Add to imports:
from discovery_integration import DiscoveryFeedbackHandler, FeatureFlags
from discovery_schemas import DiscoveryFeedback

# Modify start_scan endpoint:
@socketio.on('start_scan')
def handle_start_scan(data):
    url = data.get("url")
    mode = data.get("mode", "diagnosis")  # New parameter
    
    # Check feature flag
    if mode == "discovery" and not FeatureFlags.is_discovery_enabled(user_id=get_user_session_id()):
        emit("scan_update", {"type": "error", "message": "Discovery Mode not available"})
        return
    
    # Pass mode to scanner
    socketio.start_background_task(
        run_scan_in_background, 
        request.sid, 
        data, 
        scan_id, 
        user_id,
        mode=mode  # Pass mode
    )

# Add Discovery feedback endpoint:
@app.route("/feedback/discovery", methods=["POST"])
def handle_discovery_feedback():
    try:
        data = request.get_json()
        
        # Validate CSRF token (reuse existing logic)
        csrf_token = request.headers.get('X-CSRF-Token')
        if not validate_csrf_token(csrf_token):
            return jsonify({"status": "error", "message": "Invalid CSRF token"}), 403
        
        # Validate and record feedback
        feedback = DiscoveryFeedback(**data)
        success = DiscoveryFeedbackHandler.record_feedback(feedback)
        
        if success:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "error"}), 500
            
    except Exception as e:
        log("error", f"Discovery feedback error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# Add feature flag status endpoint:
@app.route("/api/features")
def get_features():
    user_id = get_user_session_id()
    return jsonify({
        "discovery_mode": FeatureFlags.is_discovery_enabled(user_id),
        "features": FeatureFlags.get_enabled_features()
    })
```

### 3. Frontend Modifications

```javascript
// Add mode selector to main scan page
const ModeSelector = () => {
    const [mode, setMode] = useState(
        localStorage.getItem('scanMode') || 'diagnosis'
    );
    
    // Check if Discovery is enabled
    const [discoveryEnabled, setDiscoveryEnabled] = useState(false);
    
    useEffect(() => {
        fetch('/api/features')
            .then(res => res.json())
            .then(data => setDiscoveryEnabled(data.discovery_mode));
    }, []);
    
    if (!discoveryEnabled) {
        return null; // Don't show selector if not enabled
    }
    
    return (
        <div className="mode-selector">
            <button 
                className={mode === 'discovery' ? 'active' : ''}
                onClick={() => {
                    setMode('discovery');
                    localStorage.setItem('scanMode', 'discovery');
                }}
            >
                🔍 Discover Brand Strategy
            </button>
            <button 
                className={mode === 'diagnosis' ? 'active' : ''}
                onClick={() => {
                    setMode('diagnosis');
                    localStorage.setItem('scanMode', 'diagnosis');
                }}
            >
                📊 Diagnose Memorability
            </button>
        </div>
    );
};

// Modify scan submission to include mode
const startScan = (url) => {
    const mode = localStorage.getItem('scanMode') || 'diagnosis';
    
    socket.emit('start_scan', {
        url: url,
        mode: mode
    });
};

// Add Discovery result rendering
const DiscoveryResults = ({ results }) => {
    const [expandedKeys, setExpandedKeys] = useState({});
    
    return (
        <div className="discovery-results">
            {/* Positioning Themes */}
            <div className="discovery-key">
                <h3>Positioning Themes</h3>
                {results.positioning_themes?.themes.map((theme, i) => (
                    <details key={i}>
                        <summary>
                            {theme.theme} 
                            <span className="confidence">{theme.confidence}%</span>
                        </summary>
                        <p className="evidence">{theme.evidence}</p>
                    </details>
                ))}
            </div>
            
            {/* Similar for other keys */}
        </div>
    );
};

// Add feedback component
const DiscoveryFeedback = ({ scanId, keyName }) => {
    const [helpful, setHelpful] = useState(null);
    
    const submitFeedback = async (isHelpful) => {
        const response = await fetch('/feedback/discovery', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrfToken
            },
            body: JSON.stringify({
                scan_id: scanId,
                key_name: keyName,
                helpful: isHelpful,
                timestamp: new Date().toISOString()
            })
        });
        
        if (response.ok) {
            setHelpful(isHelpful);
        }
    };
    
    return (
        <div className="feedback-widget">
            <span>Was this helpful?</span>
            <button 
                className={helpful === true ? 'selected' : ''}
                onClick={() => submitFeedback(true)}
            >
                👍 Yes
            </button>
            <button 
                className={helpful === false ? 'selected' : ''}
                onClick={() => submitFeedback(false)}
            >
                👎 No
            </button>
        </div>
    );
};
```

### 4. Environment Variables

Add to your .env file:

```bash
# Discovery Mode Feature Flags
DISCOVERY_MODE_ENABLED=true
DISCOVERY_ROLLOUT_PERCENTAGE=10  # Start with 10% rollout
DISCOVERY_MODE_WHITELIST=user123,user456  # Optional whitelist

# Model Configuration
AI_MODEL_ID=gpt-5  # Or gpt-4-turbo for testing

# Phase 2 Features (disabled initially)
DISCOVERY_VISUAL_ANALYSIS=false
DISCOVERY_EXPORT_ENABLED=false
DISCOVERY_ADVANCED_FEEDBACK=false
```

### 5. Testing Strategy

```python
# test_discovery.py
import pytest
from discovery_schemas import SchemaValidator, PositioningThemesResult

def test_schema_validation():
    """Test schema validation with auto-repair."""
    validator = SchemaValidator()
    
    # Test valid JSON
    valid_json = '''
    {
        "themes": [
            {
                "theme": "Innovation",
                "confidence": 85,
                "evidence": "We pioneer breakthrough technologies"
            }
        ]
    }
    '''
    result, repairs = validator.validate_with_repair(
        valid_json, 
        PositioningThemesResult,
        "positioning_themes"
    )
    assert result is not None
    assert repairs == ["No repairs needed"]
    
    # Test auto-repair
    repairable_json = '''
    {
        "themes": [
            {
                "theme": "Innovation",
                "confidence": "85",
                "evidence": "We pioneer breakthrough technologies"
            }
        ]
    }
    '''
    result, repairs = validator.validate_with_repair(
        repairable_json,
        PositioningThemesResult,
        "positioning_themes"
    )
    assert result is not None
    assert "confidence_type_cast" in str(repairs)

def test_feature_flags():
    """Test feature flag logic."""
    from discovery_integration import FeatureFlags
    
    # Test with environment variables
    os.environ['DISCOVERY_MODE_ENABLED'] = 'true'
    os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '100'
    
    assert FeatureFlags.is_discovery_enabled() == True
    
    # Test rollout percentage
    os.environ['DISCOVERY_ROLLOUT_PERCENTAGE'] = '0'
    assert FeatureFlags.is_discovery_enabled() == False
```

## Deployment Checklist

### Phase 1 Launch (Week 1-4)
- [ ] Deploy code with feature flag OFF
- [ ] Enable for internal team only (whitelist)
- [ ] Test all 3 text-based keys
- [ ] Verify feedback collection
- [ ] Monitor token usage and costs
- [ ] Collect initial feedback

### Phase 1 Rollout (Week 5-8)
- [ ] Enable for 10% of users
- [ ] Monitor performance metrics (p95 < 90s)
- [ ] Track adoption rate
- [ ] Analyze feedback patterns
- [ ] Increase to 50% if metrics are good
- [ ] Prepare Phase 2 visual analysis

### Success Metrics Tracking
```sql
-- Sample queries for your analytics platform

-- Adoption Rate
SELECT 
    COUNT(DISTINCT CASE WHEN mode = 'discovery' THEN user_id END) / 
    COUNT(DISTINCT user_id) * 100 as adoption_rate
FROM scans
WHERE timestamp > NOW() - INTERVAL '7 days';

-- Helpful Rate
SELECT 
    SUM(CASE WHEN helpful = true THEN 1 ELSE 0 END) / 
    COUNT(*) * 100 as helpful_rate
FROM discovery_feedback
WHERE timestamp > NOW() - INTERVAL '7 days';

-- Performance Metrics
SELECT 
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration,
    AVG(token_usage) as avg_tokens,
    AVG(token_usage) * 0.00003 as avg_cost_per_scan
FROM discovery_metrics
WHERE timestamp > NOW() - INTERVAL '24 hours';
```

## Risk Mitigation

1. **Cost Overrun**: Monitor token usage hourly, set alerts at 80% of budget
2. **Performance Issues**: Auto-disable if p95 > 120s
3. **Quality Issues**: If helpful rate < 60%, pause rollout and analyze
4. **GPT-5 Unavailability**: Fallback to GPT-4-Turbo configured via env var

## Phase 2 Preview

Phase 2 will add:
- Brand Elements visual analysis using GPT-5 vision
- Visual-Text Cross-Check alignment analysis
- PDF/JSON export functionality
- Advanced feedback with categories

All Phase 2 features are already stubbed in the code with feature flags.