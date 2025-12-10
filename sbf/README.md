# Strategist's Best Friend (SBF)

Strategic report generation platform powered by GPT-5.1 and comprehensive web research.

## Features

### 3 Report Types (MVP)
1. **Brand Audit** - Comprehensive health check with social sentiment and competitive analysis
2. **Meeting Brief** - Executive dossier with person background and company intelligence
3. **Industry Profile** - Market analysis with trends, challenges, and key players

### Key Capabilities
- ✅ **GPT-5.1 Analysis** - Advanced reasoning with circuit breaker fallback to GPT-4o
- ✅ **Multi-Platform Social Sentiment** - Twitter, Reddit, Instagram, Facebook scraping
- ✅ **Geo-Targeted Research** - 10 countries supported (US, UK, DE, FR, ES, IT, CA, AU, JP, IN)
- ✅ **PDF Document Processing** - RAG with in-memory ChromaDB (Brand Audit only)
- ✅ **Competitor Intelligence** - Auto-detection or manual specification
- ✅ **Persistent Workflows** - PostgreSQL-backed checkpointing (survives restarts)
- ✅ **Smart Caching** - 24-hour TTL to reduce API costs
- ✅ **Rate Limiting** - 3 reports/hour per IP
- ✅ **Streaming Progress** - Real-time NDJSON updates

## Architecture

### Backend (FastAPI + LangGraph)
```
backend/
├── app/
│   ├── core/              # Configuration, LLM client
│   ├── models/            # Pydantic schemas
│   ├── services/          # Scraping, RAG, caching, cleaning
│   ├── graph/             # LangGraph workflows and nodes
│   └── api/               # FastAPI endpoints
├── requirements.txt
├── Dockerfile
└── .env.example
```

### Tech Stack
- **FastAPI** - Async API framework
- **LangGraph** - Workflow orchestration with PostgreSQL checkpointing
- **GPT-5.1** - Primary LLM (Responses API) with GPT-4o fallback
- **Scrapfly SDK** - Web + social scraping with ASP
- **ChromaDB** - In-memory vector storage for PDFs
- **Structlog** - Structured logging
- **PostgreSQL** - Workflow state persistence

## Setup

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ (for production) or SQLite (for local dev)
- OpenAI API key (with GPT-5.1 access)
- Scrapfly API key

### Local Development

1. **Clone and setup**:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install --with-deps
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Run locally**:
```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --port 8000

# Or using Python directly
python -m app.main
```

4. **Test the API**:
```bash
curl http://localhost:8000/health
```

### Production Deployment (Render.com)

1. **Push to GitHub**:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin YOUR_REPO_URL
git push -u origin main
```

2. **Deploy to Render**:
   - Connect repository in Render dashboard
   - Select "Deploy from render.yaml"
   - Set secret environment variables:
     - `OPENAI_API_KEY`
     - `SCRAPFLY_KEY`
   - Deploy!

3. **Monitor**:
   - Health check: `https://sbf-backend.onrender.com/health`
   - Logs: Render dashboard → Logs tab
   - Metrics: Check `/api/cache/stats` endpoint

## API Usage

### Generate Report

**Endpoint**: `POST /api/generate-report`

**Brand Audit Example**:
```bash
curl -X POST https://sbf-backend.onrender.com/api/generate-report \
  -F "report_type=brand_audit" \
  -F "brand_name=Apple" \
  -F "brand_url=https://apple.com" \
  -F "geography=US" \
  -F "competitors=Samsung,Google" \
  -F "files=@annual_report.pdf"
```

**Meeting Brief Example**:
```bash
curl -X POST https://sbf-backend.onrender.com/api/generate-report \
  -F "report_type=meeting_brief" \
  -F "person_name=Tim Cook" \
  -F "person_role=CEO" \
  -F "company_name=Apple Inc" \
  -F "geography=US"
```

**Industry Profile Example**:
```bash
curl -X POST https://sbf-backend.onrender.com/api/generate-report \
  -F "report_type=industry_profile" \
  -F "industry_name=Electric Vehicles" \
  -F "geography=US"
```

### Streaming Response Format

The API returns NDJSON (newline-delimited JSON):

```json
{"type":"progress","message":"Initializing workflow...","progress_percent":5}
{"type":"progress","message":"Scraping brand website...","progress_percent":25}
{"type":"progress","message":"Collecting social sentiment...","progress_percent":45}
{"type":"result","markdown":"# Brand Audit: Apple\n\n...","chart":null,"metadata":{...}}
```

## Workflow Details

### Brand Audit Pipeline (8-12 min)
1. Initialize → Cache Check
2. Ingest PDFs (if uploaded)
3. Scrape brand website
4. Scrape social sentiment (Twitter, Reddit, Instagram, Facebook)
5. Identify competitors (auto or manual)
6. Scrape top 3 competitors
7. Scrape recent news mentions
8. GPT-5.1 analysis
9. Format and cache report

### Meeting Brief Pipeline (4-6 min)
1. Initialize → Cache Check
2. Research person profile
3. Scrape company website
4. Scrape recent news
5. Identify competitors
6. GPT-5.1 analysis
7. Format and cache report

### Industry Profile Pipeline (5-7 min)
1. Initialize → Cache Check
2. Research market reports
3. Identify top brands
4. Find emerging players
5. Scrape recent news
6. GPT-5.1 analysis
7. Format and cache report

## Cost Estimates

### Per Report
- **Brand Audit**: ~$1.50-1.60 (15-20 Scrapfly requests + 80K GPT-5.1 tokens)
- **Meeting Brief**: ~$0.70-0.76 (5-8 Scrapfly requests + 40K GPT-5.1 tokens)
- **Industry Profile**: ~$1.10-1.20 (10-15 Scrapfly requests + 60K GPT-5.1 tokens)

### Infrastructure (Monthly)
- Render Standard Plan: $25/month
- PostgreSQL Starter: $7/month
- **Total**: $32/month fixed + variable API costs

## Configuration

### Environment Variables

See `.env.example` for full list. Key variables:

```env
# Required
OPENAI_API_KEY=sk-...
SCRAPFLY_KEY=scp-...
DATABASE_URL=postgresql+asyncpg://...

# Optional
RATE_LIMIT_PER_HOUR=3
CACHE_TTL_HOURS=24
GPT5_TIMEOUT=90
MAX_PDF_SIZE_MB=10
```

### Rate Limiting

Default: 3 reports/hour per IP address.

Modify in `.env`:
```env
RATE_LIMIT_PER_HOUR=5
```

### Caching

Reports are cached for 24 hours by default.

Modify in `.env`:
```env
CACHE_TTL_HOURS=48  # Cache for 2 days
```

Clear expired cache:
```bash
curl -X POST https://sbf-backend.onrender.com/api/cache/clear-expired
```

## Monitoring

### Health Check
```bash
curl https://sbf-backend.onrender.com/health
```

### Cache Statistics
```bash
curl https://sbf-backend.onrender.com/api/cache/stats
```

### Logs

Structured JSON logs in production:
```json
{
  "event": "workflow_complete",
  "report_type": "brand_audit",
  "duration": 342.5,
  "timestamp": "2025-01-15T10:30:00Z"
}
```

View in Render dashboard or stream to your logging service.

## Troubleshooting

### Workflow Timeout
**Symptom**: Report generation times out after 15 minutes

**Solution**: Increase timeout in `.env`:
```env
WORKFLOW_TIMEOUT=1200  # 20 minutes
```

### PDF Upload Fails
**Symptom**: "PDF too large" error

**Solution**: Increase limit or split PDFs:
```env
MAX_PDF_SIZE_MB=20
```

### Cache Miss Rate High
**Symptom**: Every query hits external APIs

**Solution**: Check cache directory permissions:
```bash
# In Dockerfile
RUN mkdir -p /tmp/sbf_cache && chmod 777 /tmp/sbf_cache
```

### GPT-5.1 Circuit Breaker Open
**Symptom**: All requests falling back to GPT-4o

**Solution**: Check OpenAI API status. Reset circuit breaker:
```env
CIRCUIT_BREAKER_COOLDOWN=300  # Reduce cooldown to 5 min
```

## Development

### Run Tests
```bash
pytest backend/app/tests -v
```

### Code Style
```bash
black backend/app
ruff check backend/app
```

### Type Checking
```bash
mypy backend/app
```

## Roadmap

### Phase 2 (Planned)
- [ ] Add remaining 4 report types (Brand House, Four C's, Competitive Landscape, Audience Profile)
- [ ] Frontend (Next.js)
- [ ] User authentication
- [ ] Report history and management
- [ ] PDF/DOCX export
- [ ] Webhook notifications

### Phase 3 (Future)
- [ ] Multi-language support
- [ ] Custom report templates
- [ ] API access for programmatic generation
- [ ] Team collaboration features
- [ ] Cost dashboard and budgeting

## License

Proprietary - Saffron Brand Consultants

## Support

For issues or questions:
- GitHub Issues: [YOUR_REPO]/issues
- Email: support@saffron.com

---

Built with ❤️ by Saffron Brand Consultants

**Powered by**: GPT-5.1, FastAPI, LangGraph, Scrapfly
