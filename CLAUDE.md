# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Application Overview

MemoScan v2 is a strategic brand analysis tool that evaluates websites for brand memorability using Saffron Brand Consultants' methodology. The application analyzes six key memorability factors: Emotion, Attention, Story, Involvement, Repetition, and Consistency.

## Development Commands

### Running the Application
- **Local development**: `python app.py` (Flask development server)
- **Production deployment**: Uses Gunicorn with gevent WebSocket workers via Docker
- **Docker build**: `docker build -t memoscan2 .`
- **Docker run**: `docker run -p 5000:5000 memoscan2`

### Python Environment
- **Install dependencies**: `pip install -r requirements.txt`
- **Playwright setup**: `playwright install --with-deps` (required for web scraping)
- **Python version**: 3.11+

### Environment Variables
- `OPENAI_API_KEY`: Required for AI analysis
- `SCRAPFLY_KEY`: Optional - for enhanced web scraping (fallback to Playwright)
- `PORT`: Server port (default handled by Gunicorn in production)

## Architecture

### Main Components

1. **app.py** - Flask application with SocketIO for real-time communication
   - Handles WebSocket connections for streaming scan results
   - Serves the web interface and feedback endpoints
   - Uses gevent for async operations with monkey patching

2. **scanner.py** - Core scanning engine
   - Implements the brand analysis pipeline
   - Handles web scraping with Scrapfly API + Playwright fallback
   - Manages OpenAI GPT-4o integration for memorability analysis
   - Includes scoring algorithms for link prioritization

3. **templates/index.html** - Single-page web application
   - Real-time UI updates via Socket.IO
   - Feedback system for AI analysis improvement
   - Screenshot gallery for visual evidence

### Key Technical Patterns

- **Streaming Architecture**: Uses Python generators to stream scan progress in real-time
- **Fallback Strategy**: Scrapfly API primary, Playwright secondary for web scraping
- **Circuit Breaker**: Prevents cascade failures during parallel page fetching
- **Shared Cache**: In-memory storage for screenshots and analysis data
- **Concurrent Processing**: ThreadPoolExecutor for parallel page analysis

### Data Flow
1. User submits URL → WebSocket connection established
2. Scanner discovers pages via HTML parsing + sitemap analysis
3. Link scoring algorithm prioritizes high-value pages
4. Parallel content extraction from top-ranked pages
5. AI analysis of six memorability keys with OpenAI GPT-4o
6. Real-time results streaming to frontend
7. Screenshot capture and caching for visual evidence

## Deployment

The application is configured for Render.com deployment:
- **Dockerfile**: Production container with Playwright dependencies
- **render.yaml**: Service configuration
- **Gunicorn**: Production WSGI server with WebSocket support

## Important Notes

- The scanner includes sophisticated link discovery from both HTML and XML sitemaps
- Supports multi-domain analysis (can pivot to better corporate portals)
- Includes social media text extraction for comprehensive brand analysis
- All AI responses are validated for required JSON structure
- Feedback system logs user corrections to improve future analysis

## File Structure

- `app.py` - Main Flask application
- `scanner.py` - Brand analysis engine  
- `templates/index.html` - Web interface
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container configuration
- `render.yaml` - Deployment configuration
- `*_backup*.py` - Development iterations/backups