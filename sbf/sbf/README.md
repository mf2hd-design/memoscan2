# Strategist's Best Friend (SBF)

AI-powered brand research tool for strategists. Generate comprehensive reports using GPT-5.1 and intelligent web scraping.

![SBF Demo](docs/demo.png)

## Features

### Report Types
| Type | Description |
|------|-------------|
| **Brand Audit** | Comprehensive brand health analysis with social sentiment, competitor benchmarking, and strategic recommendations |
| **Meeting Brief** | Person & company intelligence for meetings - background, news, talking points |
| **Industry Profile** | Market research with trends, key players, and opportunities |
| **Brand House** | Strategic brand positioning framework - essence, values, personality |
| **Four C's Analysis** | Company, Category, Consumer, Culture framework |
| **Competitive Landscape** | Market positioning map and competitor analysis |
| **Audience Profile** | Demographics, psychographics, and behavioral patterns |

### Technology
- **GPT-5.1** via OpenAI Responses API
- **Scrapfly** for anti-bot web scraping
- **LangGraph** for workflow orchestration
- **ChromaDB** for RAG (PDF analysis)
- **FastAPI** streaming responses
- **React** frontend with Tailwind CSS

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/your-org/sbf.git
cd sbf

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start services
docker-compose up -d

# Access frontend at http://localhost
```

### Option 2: Manual Setup

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add API keys to .env
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

## Configuration

Create a `.env` file in the root directory:

```bash
# Required
OPENAI_API_KEY=sk-...
SCRAPFLY_KEY=scp-...

# Optional
ENVIRONMENT=production
RATE_LIMIT_PER_HOUR=10
CACHE_TTL_HOURS=24
```

## API Documentation

Once running, access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Generate Report Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/generate-report \
  -F "report_type=brand_audit" \
  -F "brand_name=Nike" \
  -F "brand_url=https://nike.com" \
  -F "geography=US"
```

Response (NDJSON stream):
```json
{"type": "progress", "message": "Analyzing...", "progress_percent": 50}
{"type": "result", "markdown": "# Brand Audit...", "chart": null}
```

## Project Structure

```
sbf/
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── api/            # Endpoints
│   │   ├── core/           # Config, LLM client
│   │   ├── graph/          # LangGraph workflows
│   │   │   ├── nodes/      # Workflow steps
│   │   │   └── workflows/  # Workflow definitions
│   │   ├── models/         # Pydantic schemas
│   │   └── services/       # Cache, scraping, RAG
│   ├── tests/              # Unit & integration tests
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/               # React frontend
│   ├── src/
│   │   └── App.jsx        # Main component
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml      # Full stack deployment
└── README.md
```

## Development

### Running Tests

```bash
cd backend
make test          # Unit tests
make coverage      # With coverage report
```

### Code Quality

```bash
cd backend
make lint          # Lint with ruff
make lint-fix      # Auto-fix issues
```

### Test Client

```bash
cd backend
python test_client.py brand_audit --brand Nike --brand-url https://nike.com
```

## Deployment

### Render.com

```bash
cd backend
# Push to GitHub, then connect repo to Render
# Uses render.yaml for configuration
```

### Custom Docker

```bash
docker-compose up -d
```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   React Frontend │────▶│  FastAPI Backend │
└─────────────────┘     └────────┬────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   GPT-5.1     │      │   Scrapfly    │      │   ChromaDB    │
│  (Responses)  │      │   (Scraping)  │      │    (RAG)      │
└───────────────┘      └───────────────┘      └───────────────┘
```

## License

Proprietary - Saffron Brand Consultants
