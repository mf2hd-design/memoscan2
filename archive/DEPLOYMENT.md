# 🚀 MemoScan v2 Deployment Guide

## Prerequisites

1. **Required API Keys:**
   - OpenAI API Key (required for AI analysis)
   - Scrapfly API Key (optional, falls back to Playwright)

2. **Generate Security Keys:**
   ```python
   import secrets
   print("SECRET_KEY:", secrets.token_hex(32))
   print("ADMIN_API_KEY:", secrets.token_hex(32))
   ```

## Render.com Deployment

### Step 1: Create New Service
1. Go to [render.com](https://render.com) and sign in
2. Click "New +" → "Blueprint"  
3. Connect your GitHub repository
4. Select the `memoscan2` repository

### Step 2: Configure Environment Variables
Set these in Render Dashboard → Service → Environment:

**Required Secrets:**
```
OPENAI_API_KEY=sk-your-openai-api-key
SECRET_KEY=your-64-char-hex-secret
ADMIN_API_KEY=your-64-char-hex-admin-key
```

**Optional:**
```
SCRAPFLY_KEY=your-scrapfly-key
```

### Step 3: Verify Deployment Configuration
The `render.yaml` file is already configured with:
- ✅ Health check endpoint: `/health`
- ✅ Persistent disk: 10GB for data storage  
- ✅ Environment variables
- ✅ Performance tuning for production

### Step 4: Deploy
1. Click "Deploy" - Render will build using the Dockerfile
2. Wait for build completion (~5-10 minutes)
3. Service will be available at: `https://memoscan2.onrender.com`

## Verification

### Health Check
```bash
curl https://your-service.onrender.com/health
```

### Admin Endpoints
```bash  
curl -H "Authorization: Bearer YOUR_ADMIN_API_KEY" \
     https://your-service.onrender.com/api/metrics
```

## Monitoring

### Application Logs
- View in Render Dashboard → Service → Logs
- JSON structured logging enabled in production

### Resource Usage
- Monitor via `/health` endpoint
- Memory, CPU, and disk usage included

### Performance Metrics
- Scan completion rates: `/api/metrics`
- API costs tracking: `/api/costs`
- Feedback analytics: `/feedback/analytics`

## Troubleshooting

### Common Issues:

1. **Build Fails:**
   - Check Dockerfile dependencies
   - Verify Python version compatibility

2. **Health Check Fails:**
   - Ensure OPENAI_API_KEY is set
   - Check persistent disk mount

3. **Screenshot Issues:**
   - Playwright dependencies included in Dockerfile
   - Browser binaries installed during build

### Debug Mode:
Set `LOG_LEVEL=DEBUG` for detailed logging.

## Security Notes

- ✅ CSRF protection enabled
- ✅ Rate limiting configured  
- ✅ Input validation and sanitization
- ✅ Secure headers added
- ✅ API key redaction in logs
- ✅ XXE protection for XML parsing

## Performance Tuning

Production settings in `render.yaml`:
- Max 8 concurrent scans
- 15 scans per user per 24h
- 150MB cache size
- 90-day data retention

All critical fixes applied and tested! 🎉