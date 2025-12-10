# Strategist's Best Friend (SBF) - Backend

AI-powered brand research tool for strategists. Generate comprehensive reports using GPT-5.1 and web scraping.

## Features

- **7 Report Types**: Brand Audit, Meeting Brief, Industry Profile, Brand House, Four C's, Competitive Landscape, Audience Profile
- **GPT-5.1 Integration**: Uses OpenAI's Responses API with circuit breaker protection
- **Web Scraping**: Scrapfly-powered scraping with anti-bot protection
- **PDF Analysis**: Upload brand guidelines for RAG-enhanced reports
- **Streaming Responses**: Real-time progress updates via NDJSON
- **Caching**: 24-hour cache to reduce API costs

## Quick Start

```bash
# Clone and setup
cd sbf/backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
uvicorn app.main:app --reload
```

## API Usage

### Generate Report

```bash
curl -X POST http://localhost:8000/api/v1/generate-report \
  -F "report_type=brand_audit" \
  -F "brand_name=Nike" \
  -F "brand_url=https://nike.com" \
  -F "geography=US"
```

### Report Types & Required Fields

| Report Type | Required Fields |
|-------------|-----------------|
| `brand_audit` | brand_name, brand_url |
| `meeting_brief` | person_name, person_role, company_name |
| `industry_profile` | industry_name |
| `brand_house` | brand_name, brand_url |
| `four_cs` | brand_name, brand_url |
| `competitive_landscape` | brand_name, brand_url |
| `audience_profile` | audience_name |

### Response Format (NDJSON)

```json
{"type": "progress", "message": "Initializing...", "progress_percent": 5}
{"type": "progress", "message": "Scraping brand...", "progress_percent": 25}
{"type": "result", "markdown": "# Brand Audit...", "chart": null, "metadata": {...}}
```

## Architecture

```
app/
├── main.py                 # FastAPI application
├── api/endpoints.py        # Streaming endpoint
├── core/
│   ├── config.py          # Settings & environment
│   └── llm_client.py      # GPT-5.1 client + circuit breaker
├── models/schemas.py       # Pydantic models
├── graph/
│   ├── prompts.py         # LLM prompts
│   ├── nodes/             # Workflow step implementations
│   └── workflows/         # LangGraph workflow definitions
└── services/
    ├── cache.py           # File-based caching
    ├── cleaner.py         # HTML processing
    ├── rag_service.py     # PDF ingestion + ChromaDB
    └── scraping/          # Scrapfly client & strategies
```

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `SCRAPFLY_KEY` | Scrapfly API key | Required |
| `GPT5_MODEL` | Model identifier | gpt-5.1-2025-11-13 |
| `RATE_LIMIT_PER_HOUR` | Requests per IP | 3 |
| `CACHE_TTL_HOURS` | Cache duration | 24 |
| `CIRCUIT_BREAKER_THRESHOLD` | Failures before open | 3 |

## Workflows

Each report type uses a LangGraph workflow with these common patterns:

1. **Initialize** → Create workflow ID, set progress
2. **Cache Check** → Return cached report if available
3. **Research** → Scrape websites, collect data (varies by type)
4. **Analyze** → GPT-5.1 generates report from context
5. **Format** → Store in cache, return final report

### Brand Audit Workflow (10 steps)
```
initialize → cache_check → ingest_pdf → scrape_brand → social_sentiment 
→ identify_competitors → scrape_competitors → news_mentions → analyze → format
```

### Meeting Brief Workflow (8 steps)
```
initialize → cache_check → research_person → research_company 
→ recent_news → industry_context → analyze → format
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Docker

```bash
# Build
docker build -t sbf-backend .

# Run
docker run -p 8000:8000 --env-file .env sbf-backend
```

## Rate Limiting

- Default: 3 requests/hour per IP
- Configure via `RATE_LIMIT_PER_HOUR`
- Returns 429 when exceeded

## Error Handling

- **Circuit Breaker**: Opens after 3 consecutive GPT-5.1 failures, cooldown 10 minutes
- **Graceful Degradation**: Scraping failures don't stop workflow
- **Structured Errors**: All errors return typed ErrorResponse

## License

Proprietary - Saffron Brand Consultants
