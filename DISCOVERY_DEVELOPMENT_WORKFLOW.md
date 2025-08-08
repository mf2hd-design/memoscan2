# Discovery Mode Development Workflow

## 🌳 **Branch Strategy**

### Main Branches
- **`main`** - Production-ready code with all stability fixes
- **`feature/discovery-mode`** - Discovery Mode development branch

### Development Process
```bash
# Working on Discovery Mode
git checkout feature/discovery-mode

# Regular commits during development
git add .
git commit -m "feat: implement positioning themes analysis"

# Periodic sync with main (get latest fixes)
git checkout main
git pull origin main
git checkout feature/discovery-mode  
git merge main

# When ready for testing
git push origin feature/discovery-mode
```

## 🚀 **Development Phases**

### **Phase 1: Foundation (Weeks 1-4)**
Current branch status: `feature/discovery-mode`

**Completed:**
- ✅ GPT-5 optimized prompts
- ✅ Schema validation system
- ✅ Feature flag infrastructure
- ✅ Performance monitoring
- ✅ Feedback adaptation
- ✅ Implementation guide

**Next Steps:**
1. Integrate with existing `scanner.py`
2. Modify `app.py` endpoints
3. Build frontend mode selector
4. Internal team testing

### **Phase 2: Visual Analysis (Weeks 5-8)**
Branch: `feature/discovery-mode` (continue on same branch)

**TODO:**
- Implement Brand Elements GPT-5 vision analysis
- Visual-Text Cross-Check logic
- Screenshot analysis pipeline
- Enhanced confidence scoring

### **Phase 3: Export & Polish (Weeks 9-12)**
Branch: `feature/discovery-mode` (continue on same branch)

**TODO:**
- JSON/PDF export functionality
- Feedback analytics dashboard
- Performance optimization
- Documentation updates

## 🔧 **Development Commands**

### Setting Up Development Environment
```bash
# Clone and switch to Discovery branch
git clone <repo-url>
cd memoscan2
git checkout feature/discovery-mode

# Install dependencies
pip install -r requirements.txt

# Set up Discovery Mode environment variables
cp .env.example .env
# Add Discovery variables:
echo "DISCOVERY_MODE_ENABLED=true" >> .env
echo "DISCOVERY_ROLLOUT_PERCENTAGE=100" >> .env
echo "AI_MODEL_ID=gpt-4-turbo" >> .env  # Use GPT-4 for dev/testing
```

### Testing Discovery Mode
```bash
# Run with Discovery Mode enabled
DISCOVERY_MODE_ENABLED=true python app.py

# Test with different rollout percentages
DISCOVERY_ROLLOUT_PERCENTAGE=50 python app.py

# Test feature flags
python -c "from discovery_integration import FeatureFlags; print(FeatureFlags.get_enabled_features())"
```

### Local Development
```bash
# Start development server with Discovery Mode
DISCOVERY_MODE_ENABLED=true \
DISCOVERY_ROLLOUT_PERCENTAGE=100 \
LOG_LEVEL=DEBUG \
python app.py
```

## 🧪 **Testing Strategy**

### Unit Tests
```bash
# Test Discovery components
python -m pytest test_discovery_*.py -v

# Test schema validation
python -c "from discovery_schemas import SchemaValidator; print('Schema validation working')"

# Test feature flags
python -c "from discovery_integration import FeatureFlags; print(f'Discovery enabled: {FeatureFlags.is_discovery_enabled()}')"
```

### Integration Tests
```bash
# Test full Discovery scan (requires OpenAI API key)
curl -X POST http://localhost:5000/api/scan \
  -H "Content-Type: application/json" \
  -d '{"url": "https://apple.com", "mode": "discovery"}'
```

### Manual Testing Checklist
- [ ] Mode selector appears on homepage
- [ ] Discovery scan completes without errors
- [ ] All 3 text-based keys return results
- [ ] Screenshot gallery displays (Phase 1)
- [ ] Feedback widget works
- [ ] Performance metrics logged
- [ ] Feature flags control access properly

## 📊 **Monitoring During Development**

### Performance Tracking
```bash
# Monitor token usage
tail -f /tmp/discovery_analysis.jsonl | grep token_usage

# Check scan performance
tail -f /tmp/discovery_metrics.jsonl | grep latency_ms

# Watch for errors
tail -f /tmp/discovery_errors.jsonl
```

### Cost Management
```bash
# Estimate daily costs during development
python -c "
import json
with open('/tmp/discovery_metrics.jsonl', 'r') as f:
    total_tokens = sum(json.loads(line).get('performance', {}).get('token_usage', 0) for line in f)
    cost = total_tokens * 0.00003  # GPT-4 pricing
    print(f'Total tokens: {total_tokens}, Estimated cost: ${cost:.2f}')
"
```

## 🚀 **Deployment Process**

### Internal Testing (Week 1-2)
```bash
# Deploy to staging with whitelist
export DISCOVERY_MODE_ENABLED=true
export DISCOVERY_MODE_WHITELIST="internal_user_1,internal_user_2"
export DISCOVERY_ROLLOUT_PERCENTAGE=0
```

### Beta Testing (Week 3-4)
```bash
# Expand to beta users
export DISCOVERY_MODE_WHITELIST="beta_user_1,beta_user_2,beta_user_3"
export DISCOVERY_ROLLOUT_PERCENTAGE=10
```

### Production Rollout (Week 5+)
```bash
# Gradual rollout
export DISCOVERY_MODE_WHITELIST=""  # Remove whitelist
export DISCOVERY_ROLLOUT_PERCENTAGE=10   # Start with 10%
# Monitor for 48 hours, then increase to 50%, then 100%
```

## 🔀 **Merging Strategy**

### When Ready for Production
```bash
# Ensure all tests pass
python -m pytest

# Merge main into feature branch (get latest)
git checkout main
git pull origin main
git checkout feature/discovery-mode
git merge main

# Resolve any conflicts, test again
python -m pytest

# Create Pull Request
git push origin feature/discovery-mode
# Then create PR: feature/discovery-mode → main
```

### PR Checklist
- [ ] All tests passing
- [ ] Performance benchmarks met (p95 < 90s)
- [ ] Token usage documented and budgeted
- [ ] Feature flags properly configured
- [ ] Documentation updated
- [ ] Rollout plan confirmed
- [ ] Success metrics baseline established

## 🆘 **Emergency Procedures**

### Quick Disable
```bash
# Emergency disable of Discovery Mode
export DISCOVERY_MODE_ENABLED=false
# Restart application
```

### Rollback Plan
```bash
# If issues in production, rollback immediately
git checkout main
git log --oneline -5  # Find stable commit
git reset --hard <stable_commit_hash>
git push origin main --force  # Only in emergency!
```

### Debug Common Issues
```bash
# GPT-5 not available
export AI_MODEL_ID=gpt-4-turbo

# High costs
export DISCOVERY_ROLLOUT_PERCENTAGE=5  # Reduce traffic

# Performance issues  
tail -f /tmp/discovery_analysis.jsonl | grep latency_ms | tail -20
```

## 📝 **Development Notes**

- Always test with both GPT-4-Turbo and GPT-5 when available
- Monitor token usage closely - Discovery Mode is token-intensive
- Use feature flags liberally for safe rollout
- Keep performance budget strict: p95 ≤ 90s
- Document any prompt modifications for future reference
- Test auto-repair logic with malformed AI responses

## 🎯 **Success Criteria for Each Phase**

### Phase 1 Success
- [ ] 3 text-based keys working reliably
- [ ] <5% validation failures
- [ ] p95 latency < 60s (text-only is faster)
- [ ] Feature flags controlling access properly
- [ ] Initial user feedback > 70% helpful

### Phase 2 Success  
- [ ] Visual analysis working with screenshots
- [ ] Cross-check alignment feature functional
- [ ] Overall p95 latency < 90s
- [ ] User feedback > 80% helpful
- [ ] Token costs within budget

### Production Readiness
- [ ] 100% feature rollout stable
- [ ] 20%+ adoption rate achieved
- [ ] >80% helpful feedback rate
- [ ] Mentioned in 30%+ sales conversations
- [ ] Cost per scan within projections