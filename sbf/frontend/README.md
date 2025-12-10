# Strategist's Best Friend - Frontend

Next.js 14 frontend with real-time streaming and responsive UI.

## Features

- ✅ **Report Type Selection** - 3 report types with visual cards
- ✅ **Dynamic Forms** - Conditional fields based on report type
- ✅ **Real-time Progress** - Buffered NDJSON streaming with progress bar
- ✅ **Markdown Rendering** - Beautiful report display with GFM support
- ✅ **Responsive Design** - Mobile-first Tailwind CSS
- ✅ **Error Handling** - Graceful error states and recovery

## Setup

### Prerequisites
- Node.js 18+ (preferably 20+)
- npm or yarn
- Backend running on port 8000 (or configured in .env.local)

### Installation

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.local.example .env.local
# Edit .env.local with your backend URL

# Run development server
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000)

### Build for Production

```bash
# Build
npm run build

# Start production server
npm start
```

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout with Tailwind
│   ├── page.tsx            # Main application page
│   └── globals.css         # Global styles
├── components/
│   ├── ReportTypeSelector.tsx  # Report type cards
│   ├── ReportForm.tsx         # Dynamic form component
│   ├── ProgressStepper.tsx    # Real-time progress display
│   └── ReportView.tsx         # Markdown report renderer
├── lib/
│   ├── api.ts                 # Buffered NDJSON API client
│   └── progressSteps.ts       # Progress step definitions
├── package.json
├── next.config.js
├── tailwind.config.ts
└── tsconfig.json
```

## Environment Variables

```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For production on Render:
```env
NEXT_PUBLIC_API_URL=https://sbf-backend.onrender.com
```

## Key Components

### API Client (`lib/api.ts`)
- **Buffered NDJSON parsing** - Handles chunked JSON correctly
- **Async generator pattern** - TypeScript-friendly streaming
- **Error handling** - Robust connection management

### ReportForm (`components/ReportForm.tsx`)
- **Conditional fields** - Different inputs per report type
- **File uploads** - Multi-file PDF support for Brand Audit
- **Geography selector** - 10 countries supported
- **Form validation** - Required field handling

### ProgressStepper (`components/ProgressStepper.tsx`)
- **Real-time updates** - Progress bar and step indicators
- **Status icons** - Visual feedback (✓, ⋯, pending)
- **Estimated time** - Per-report time estimates
- **Latest message display** - Current processing status

### ReportView (`components/ReportView.tsx`)
- **Markdown rendering** - GitHub Flavored Markdown support
- **Citation handling** - Clickable [x] references
- **Copy to clipboard** - One-click markdown export
- **Metadata display** - Duration, geography, workflow ID

## Development

### Run Dev Server
```bash
npm run dev
```

### Type Checking
```bash
npm run build  # TypeScript checking happens during build
```

### Linting
```bash
npm run lint
```

## Deployment (Render.com)

### Option 1: Static Export (Recommended)
```bash
# Add to package.json scripts:
"export": "next build && next export"

# Update next.config.js:
output: 'export',
```

Deploy as static site on Render:
- New Static Site
- Build command: `npm run export`
- Publish directory: `out`

### Option 2: Node Server
Deploy as Node web service:
- New Web Service
- Build command: `npm install && npm run build`
- Start command: `npm start`

### Environment Variables (Render)
Set in Render dashboard:
```
NEXT_PUBLIC_API_URL=https://sbf-backend.onrender.com
```

## Usage

### 1. Select Report Type
Click on one of the three report cards:
- **Brand Audit** - Full analysis with social sentiment
- **Meeting Brief** - Person + company intelligence
- **Industry Profile** - Market research

### 2. Fill Form
Enter required fields based on report type:

**Brand Audit:**
- Brand name (e.g., "Tesla")
- Website URL (e.g., "https://tesla.com")
- Competitors (optional, comma-separated)
- Geography (dropdown)
- PDF files (optional, drag-drop)

**Meeting Brief:**
- Person name (e.g., "Tim Cook")
- Person role (e.g., "CEO")
- Company name (e.g., "Apple Inc")
- Geography (dropdown)

**Industry Profile:**
- Industry name (e.g., "Electric Vehicles")
- Geography (dropdown)

### 3. Watch Progress
Real-time progress updates with:
- Animated progress bar
- Step-by-step status (10 steps for Brand Audit)
- Current processing message
- Estimated completion time

### 4. View Report
When complete:
- Formatted markdown report
- Copy to clipboard button
- Generate another report button
- Report metadata (duration, geography, workflow ID)

## Troubleshooting

### API Connection Failed
**Symptom**: "Failed to fetch" error

**Solution**:
1. Check backend is running: `curl http://localhost:8000/health`
2. Verify `NEXT_PUBLIC_API_URL` in `.env.local`
3. Check CORS settings in backend

### Streaming Not Working
**Symptom**: No progress updates

**Solution**:
1. Check browser console for errors
2. Verify backend is sending NDJSON (`Content-Type: application/x-ndjson`)
3. Test with curl: `curl -X POST http://localhost:8000/api/generate-report -F "report_type=meeting_brief" ...`

### Build Errors
**Symptom**: TypeScript errors during `npm run build`

**Solution**:
```bash
# Clean install
rm -rf node_modules package-lock.json
npm install

# Check TypeScript
npx tsc --noEmit
```

## Browser Support

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers (iOS Safari 14+, Chrome Android 90+)

## Performance

- **First Load**: ~200KB (gzipped)
- **Streaming**: Real-time, no polling
- **Rendering**: Client-side markdown parsing
- **Caching**: Static assets cached, API responses not cached

## Future Enhancements

- [ ] Chart visualizations with Recharts
- [ ] PDF export of reports
- [ ] Report history (requires auth)
- [ ] Dark mode toggle
- [ ] Comparison view (multiple reports side-by-side)
- [ ] Export to Google Docs
- [ ] Collaborative editing

---

**Built with**: Next.js 14, TypeScript, Tailwind CSS, React Markdown
