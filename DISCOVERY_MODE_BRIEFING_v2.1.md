# Final Master Briefing – MemoScan Discovery Mode (v2.1 Architecture)
**Project**: MemoScan "Discovery Mode" Feature & Feedback System  
**Date**: August 8, 2025  
**Version**: 2.1.0 (Incorporating comprehensive strategic refinements)

## 1. Executive Summary & Strategic Context

MemoScan is evolving from a single-purpose diagnostic tool into a dual-mode strategic research assistant. Discovery Mode will provide strategists with a descriptive, factual audit of a brand's positioning, surfacing four keys:

* **Positioning Themes** - Core strategic pillars
* **Key Messages** - Primary value propositions
* **Tone of Voice** - Communication personality
* **Brand Elements** - Visual identity coherence

Each key includes AI-generated evidence, confidence scores, and collapsible evidence UI.

## 1.A. Strategic Intent & Success Metrics

### Market Position
Discovery Mode creates a defensible moat by focusing on **qualitative strategic insights** rather than quantitative mentions (unlike Brandwatch/Semrush). We provide actionable brand strategy analysis, not just data aggregation.

### Target Users
- **Primary**: Brand Strategists at creative agencies
- **Secondary**: In-house Marketing Directors
- **Tertiary**: Competitive Intelligence Analysts

### Success Metrics
- **Adoption**: 20% of active users trying Discovery Mode within 6 months
- **Quality**: >80% "helpful" feedback ratings
- **Business Impact**: Feature mentioned in >30% of new sales conversations
- **Performance**: p95 scan time ≤ 90s
- **Cost Efficiency**: Token usage within 20% of projections

### Pricing Strategy
- **Launch**: Core feature included in all tiers (drive adoption)
- **6 Months**: Evaluate premium tier based on usage patterns
- **Long-term**: Possible "Agency Tier" with bulk scans and white-label exports

## 2. User Personas & Workflows

### Discovery Mode Use Cases
- **Brand Audits**: "What is this brand actually saying and projecting?"
- **Competitive Analysis**: "How do competitors position themselves?"
- **Client Onboarding**: "Quick understanding of a new account's current state"
- **Descriptive, foundational research**

### Diagnosis Mode Use Cases  
- **Message Testing**: "Is our core message memorable?"
- **Campaign Evaluation**: "Does this resonate with audiences?"
- **Evaluative, performance-focused analysis**

### Mode Selection Journey
Users encounter an upfront choice on the main scan interface:

```
"What would you like to do?"
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ 🔍 Discover Brand Strategy  │  │ 📊 Diagnose Memorability    │
│                             │  │                             │
│ Audit what a brand is       │  │ Test how memorable your     │
│ currently communicating     │  │ messaging is                │
└─────────────────────────────┘  └─────────────────────────────┘
```

## 3. Core Objectives

- Extend scanner.py pipeline with minimal changes
- Implement only prompt dictionary and schema differences
- Ensure "mode": "discovery" persists throughout scan lifecycle
- Build production-grade feedback loop for continuous improvement
- Support graceful degradation when visual analysis unavailable

## 4. Architectural & Technical Requirements

### 4.1 Architectural Principles
- **Single Pipeline**: Reuse existing scanner.py infrastructure
- **Mode Agnostic Core**: Crawling, filtering, and streaming remain unchanged
- **Prompt Switching**: Mode determines which prompt dictionary to use
- **Schema Enforcement**: Strict validation with graceful fallback

### 4.2 Backend (scanner.py)

#### Prompt Management
```python
PROMPT_REGISTRY = {
    "diagnosis": MEMORABILITY_KEYS_PROMPTS,
    "discovery": DECONSTRUCTION_KEYS_PROMPTS
}
# Model selection via environment variable
AI_MODEL = os.getenv("AI_MODEL", "gpt-4-turbo")
```

#### Auto-Repair and Validation Strategy
1. **Initial Parse**: Attempt Pydantic schema validation
2. **Limited Auto-Repair**: Safe type casting (e.g., "85" → 85)
3. **Selective Invalidation**: Discard invalid items, preserve valid ones
4. **Key-Level Fallback**: If entire structure malformed, discard key
5. **Comprehensive Logging**: Log raw output, repairs, and failures

#### Performance Budget
- **Per AI Key**: p95 ≤ 20s
- **Total Scan**: p95 ≤ 90s
- **Concurrency**: Run non-dependent keys in parallel
- **Token Monitoring**: Log usage per key for cost tracking

### 4.3 API Layer (app.py)

#### Scan Result Data Structure
```json
{
  "scan_id": "uuid-v4",
  "mode": "discovery",
  "url": "https://example.com",
  "timestamp": "2025-08-08T...",
  "results": {
    "positioning_themes": [...],
    "key_messages": [...],
    "tone_of_voice": {...},
    "brand_elements": {...},
    "visual_text_alignment": {...}
  },
  "metadata": {
    "model_id": "gpt-4-turbo",
    "token_usage": 4532,
    "scan_duration_ms": 67000,
    "screenshots_captured": 5
  }
}
```

#### Endpoints
- `POST /start_scan` - Accepts optional `mode` parameter (defaults to "diagnosis")
- `POST /feedback/discovery` - Structured feedback collection
- `GET /export/{scan_id}` - JSON/PDF export (post-completion only)
- `GET /analytics/discovery` - Admin dashboard for feedback patterns

#### Feedback Schema
```json
{
  "scan_id": "uuid",
  "key_name": "positioning_themes",
  "helpful": false,
  "category": "incorrect_evidence|missing_context|wrong_confidence|other",
  "comment": "The positioning themes missed our core value proposition",
  "timestamp": "2025-08-08T..."
}
```

### 4.4 Frontend Requirements

#### Mode Selection & Persistence
- Upfront mode selector on main scan interface
- Mode persists in localStorage for cross-session continuity
- URL parameter `?mode=discovery` for shareable links
- Visual badge indicating active mode throughout UI

#### Discovery Mode UI Components
- **Progress Indicator**: Shows keys being analyzed in real-time
- **Evidence Cards**: `<details>` elements with confidence scores
- **"Show All Evidence"** toggle for bulk expansion
- **Screenshot Gallery**: Thumbnails with modal zoom
- **Visual Alignment Alert**: Prominent warning if misalignment detected
- **Export Button**: Available post-completion

#### Accessibility Requirements
- ARIA labels on all interactive elements
- Keyboard navigation for mode selector
- Screen reader announcements for scan progress
- Focus management in modals

## 5. AI Output Schemas & Advanced Model-Optimized Prompts

### Global Prompt Rules
- **Role Context**: "You are a senior brand strategist..."
- **Step-by-Step**: Internal reasoning before JSON output
- **Evidence Only**: Verbatim quotes, no invented content
- **Confidence**: Integer 0-100 based on evidence quality
- **Strict JSON**: Output only valid JSON, nothing else

### Discovery Keys Schema Table

| Key | JSON Structure | Execution Order | Dependencies |
|-----|---------------|-----------------|--------------|
| **Positioning Themes** | `{"themes": [{"theme": "...", "confidence": 85, "evidence": "..."}]}` | 1 | None |
| **Key Messages** | `{"messages": [{"message": "...", "confidence": 90, "evidence": "..."}]}` | 2 | None |
| **Tone of Voice** | `{"tone_descriptors": [{"adjective": "...", "justification": "...", "confidence": 80, "evidence": "..."}]}` | 3 | None |
| **Brand Elements** | See Appendix A | 4 | Screenshots |
| **Visual-Text Alignment** | `{"alignment": "Yes/No", "justification": "..."}` | 5 (Last) | Positioning Themes + Brand Elements |

## 6. Phased Rollout Plan

### Phase 1: Core Functionality (Weeks 1-4)
- Implement mode selection UI
- Add Discovery prompt dictionary
- Build 3 text-based keys (Positioning, Messages, Tone)
- Deploy feedback collection system
- Screenshot capture (no analysis yet)

### Phase 2: Visual Analysis (Weeks 5-8)
- Implement Brand Elements visual analysis
- Add Visual-Text Cross-Check
- Handle partial screenshot scenarios
- Enhanced confidence scoring

### Phase 3: Export & Analytics (Weeks 9-12)
- JSON/PDF export functionality
- Feedback analytics dashboard
- Weekly tuning scripts
- Performance optimization

## 7. Critical Constraints & Operational Requirements

### Security & Rate Limiting
- **Scan Rate Limit**: 5 scans per hour per user/IP
- **Feedback Rate Limit**: 20 submissions per hour per user
- **Authentication**: Optional API key for higher limits
- **CSRF Protection**: All POST endpoints

### Data Retention
- **Scan Results**: 90 days
- **Feedback Logs**: 18 months max
- **Screenshots**: 7 days
- **PII Removal**: Automated monthly script

### Logging & Observability
```json
{
  "scan_id": "uuid",
  "mode": "discovery",
  "key_name": "positioning_themes",
  "model_id": "gpt-4-turbo",
  "prompt_hash": "sha256...",
  "latency_ms": 3421,
  "token_usage": {"prompt": 1200, "completion": 450},
  "validation_status": "repaired",
  "repairs_applied": ["confidence_type_cast"],
  "raw_output_truncated": "..."
}
```

## 8. UI/UX Error Handling

### Failure Scenarios

#### Complete Failure
- All 4 keys fail: Show "Scan Analysis Failed" with scan_id for support
- Offer retry with different model or reduced scope

#### Partial Failures
- Some keys fail: Display successful keys, mark failed as "unavailable"
- Visual analysis fails: Text-only results with clear indication
- Screenshots partial (2/5): Continue with warning in Brand Elements

#### Visual-Text Misalignment
- If alignment = "No": Display prominent warning icon
- Include strategic recommendation: "Review brand consistency"

#### Rate Limiting
- Clear countdown timer showing when next scan available
- Suggest upgrading for higher limits

## 9. Testing & Quality Gates

### Test Coverage Requirements
- **Unit Tests**: Schema validation, prompt construction, auto-repair logic
- **Integration Tests**: End-to-end Discovery scan flow
- **Performance Tests**: 10 concurrent scans, memory profiling
- **Visual Regression**: Screenshot gallery, evidence modals

### Discovery-Specific Test Cases
1. **Zero Results**: Brand with no clear positioning
2. **Contradictory Evidence**: Conflicting messages on same site
3. **Visual Unavailable**: Text-only fallback flow
4. **Confidence Distribution**: Ensure reasonable spread (not all 100 or 0)
5. **Token Overflow**: Handling when content exceeds context window

## 9.1 Export Formats

### JSON Export
- Clean, human-readable format
- Includes only validated results
- Available post-completion via API
- Includes metadata (scan date, URL, mode)

### PDF Export  
- Professional report template
- Executive summary page
- Per-key sections with evidence
- Screenshot appendix
- Branded with logo/colors

## 10. Documentation Requirements

### README Updates
```markdown
## Discovery Mode

### Activation
Set mode parameter when starting scan:
- API: POST /start_scan {"url": "...", "mode": "discovery"}
- UI: Select "Discover Brand Strategy" on homepage

### Environment Variables
- `AI_MODEL`: Model for analysis (default: gpt-4-turbo)
- `DISCOVERY_ENABLED`: Feature flag (default: true)
- `MAX_DISCOVERY_TOKENS`: Token limit per scan (default: 10000)

### Output Format
Discovery mode returns structured brand analysis...
```

### Onboarding & Tooltips
- First-time user tour explaining mode differences
- Contextual help icons on each Discovery key
- Example reports for reference

## 11. Roadmap & Future Enhancements

### Near-term (3-6 months)
- **Configurable Keys**: Select which analyses to run
- **Fast Scan Mode**: Reduced page set for quick audits
- **Bulk Operations**: Analyze multiple URLs in batch

### Medium-term (6-12 months)
- **Historical Tracking**: Show brand evolution over time
- **Competitive Matrix**: Side-by-side brand comparisons
- **Quick Edit**: Strategist corrections with revision history
- **Confidence Voting**: Crowd-sourced accuracy scores

### Long-term (12+ months)
- **Custom Prompts**: User-defined analysis frameworks
- **White-label Reports**: Agency branding options
- **API-first Architecture**: Headless mode for integrations

## Appendix A: Brand Elements Full Schema

```json
{
  "overall_impression": {
    "summary": "Brief visual identity summary",
    "keywords": ["Modern", "Minimalist", "Tech-forward"]
  },
  "coherence_score": 4,
  "detailed_analysis": {
    "color_palette": {
      "consistency": "High/Medium/Low",
      "notes": "Primary blues with accent oranges..."
    },
    "typography": {
      "consistency": "High/Medium/Low", 
      "notes": "Sans-serif headers with serif body..."
    },
    "imagery": {
      "consistency": "High/Medium/Low",
      "notes": "Lifestyle photography with illustrations..."
    },
    "brand_architecture": {
      "consistency": "High/Medium/Low",
      "notes": "Clear hierarchy with sub-brands..."
    }
  },
  "strategic_alignment": "Visual identity strongly supports positioning...",
  "confidence": 85,
  "evidence": "Homepage hero uses described color palette..."
}
```

## Version History
- v2.0.0: Initial Discovery Mode specification
- v2.1.0: Strategic refinements, phased rollout, detailed error handling