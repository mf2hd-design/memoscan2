# SBF Frontend

React frontend for Strategist's Best Friend.

## Features

- **Report Type Selection**: Choose from 7 different report types
- **Dynamic Forms**: Fields change based on selected report type
- **Real-time Progress**: Streaming progress updates as report generates
- **Markdown Rendering**: Beautiful display of generated reports
- **Export Options**: Copy to clipboard or download as Markdown

## Quick Start

```bash
# Install dependencies
npm install

# Start development server (with backend at localhost:8000)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Environment Variables

Create a `.env` file based on `.env.example`:

```bash
# API URL (defaults to localhost:8000 in development)
VITE_API_URL=http://localhost:8000
```

## Development

The development server runs on port 3000 and proxies `/api` requests to the backend at port 8000.

```bash
# Terminal 1: Start backend
cd ../backend
uvicorn app.main:app --reload

# Terminal 2: Start frontend
npm run dev
```

## Production Build

```bash
# Build with custom API URL
VITE_API_URL=https://api.sbf.example.com npm run build
```

## Docker

```bash
# Build image
docker build -t sbf-frontend .

# Run container
docker run -p 80:80 sbf-frontend
```

## Project Structure

```
src/
├── App.jsx         # Main application component
├── main.jsx        # React entry point
└── index.css       # Tailwind CSS styles
```

## Tech Stack

- **React 18** - UI framework
- **Vite** - Build tool
- **Tailwind CSS** - Styling
- **Lucide React** - Icons
