# MemoScan v2 Production Deployment Guide

## Prerequisites

1. **Render.com Account**: Sign up at https://render.com
2. **GitHub Repository**: Code must be in a GitHub repository
3. **API Keys**: Have your OpenAI API key ready
4. **Domain** (Optional): Custom domain if desired

## Step-by-Step Deployment

### 1. Prepare Environment Variables

Generate secure keys for production:

```bash
# Generate SECRET_KEY (run in terminal)
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

# Generate ADMIN_API_KEY (run in terminal)  
python3 -c "import secrets; print('ADMIN_API_KEY=' + secrets.token_hex(32))"
```

**Save these keys securely** - you'll need them in step 3.

### 2. Push Code to GitHub

Ensure all changes are committed and pushed:

```bash
git add .
git commit -m "Production deployment ready with security fixes"
git push origin main
```

### 3. Deploy on Render.com

#### A. Create New Service
1. Go to https://render.com/dashboard
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Select the `memoscan2` repository

#### B. Configure Service
- **Name**: `memoscan2`
- **Environment**: `Docker`
- **Plan**: `Starter` ($7/month) or higher
- **Branch**: `main`
- **Health Check Path**: `/health`

#### C. Add Environment Variables
Go to "Environment" tab and add these secrets:

**Required Secrets** (click "Add from .env"):
```env
OPENAI_API_KEY=your_openai_api_key_here
SECRET_KEY=<generated_secret_key_from_step_1>
ADMIN_API_KEY=<generated_admin_key_from_step_1>
```

**Optional Secrets** (recommended):
```env
SCRAPFLY_KEY=your_scrapfly_key_here
```

**Public Environment Variables** (auto-configured via render.yaml):
- `PERSISTENT_DATA_DIR=/data`
- `ALLOWED_ORIGINS=https://memoscan2.onrender.com`
- `MAX_CONCURRENT_SCANS=8`
- `MAX_SCANS_PER_USER=15`
- And others...

#### D. Configure Persistent Storage
The render.yaml automatically configures a 10GB disk at `/data`.

### 4. Deploy and Monitor

#### A. Initial Deployment
1. Click "Create Web Service"
2. Monitor build logs for any issues
3. Wait for successful deployment (5-10 minutes)

#### B. Health Check
Once deployed, verify health:

```bash
# Basic health check
curl https://your-service-name.onrender.com/health

# Should return status: "healthy" with system metrics
```

#### C. Admin Access
Get your generated admin key (if you didn't set ADMIN_API_KEY):

```bash
# Check the generated admin key in logs
# Or check the secure file on the server
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" https://your-service.onrender.com/api/costs
```

### 5. Production Validation

#### A. Test Core Functionality
1. **Basic Scan**: Try scanning a simple website
2. **Feedback System**: Submit feedback on results
3. **User Limits**: Test rate limiting with multiple scans
4. **WebSocket**: Verify real-time updates work

#### B. Admin Endpoints
Test admin functionality:

```bash
# Cost monitoring
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" \
     https://your-service.onrender.com/api/costs?hours=24

# Scan metrics  
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" \
     https://your-service.onrender.com/api/metrics?hours=24

# Dependency health
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" \
     https://your-service.onrender.com/health/dependencies
```

#### C. System Monitoring
Monitor these endpoints regularly:
- `/health` - System health and resource usage
- `/status` - Server status and active scans

### 6. Post-Deployment Setup

#### A. Configure Monitoring
Set up external monitoring:
- **Uptime**: Use UptimeRobot or Pingdom on `/health`
- **Logs**: Monitor Render logs for errors
- **Costs**: Set budget alerts in OpenAI/Scrapfly dashboards

#### B. Share with Colleagues
Your service will be available at:
```
https://memoscan2.onrender.com
```

Provide colleagues with:
1. **URL**: The main application URL
2. **Usage Guidelines**: 15 scans per 24 hours per user
3. **Support**: How to report issues

#### C. Admin Access
For monitoring and maintenance, you'll have access to:
- **Analytics**: `/feedback/analytics?api_key=YOUR_ADMIN_KEY`
- **Cost Tracking**: `/api/costs?api_key=YOUR_ADMIN_KEY`
- **Metrics**: `/api/metrics?api_key=YOUR_ADMIN_KEY`

## Production Configuration Summary

### Security Features ✅
- CSRF protection enabled
- Admin API key authentication
- Input sanitization with bleach
- Security headers implemented
- No secrets in logs

### Monitoring Features ✅  
- System resource monitoring (CPU, memory, disk)
- Scan success rate tracking
- Cost monitoring for API usage
- Health checks with dependency validation
- Comprehensive error handling

### Scalability Features ✅
- Rate limiting per user (15/24h)
- Cache with LRU eviction (150MB limit)
- Concurrent scan limits (8 simultaneous)
- Data retention (90 days)
- Session management

### Operational Features ✅
- Persistent storage on disk
- Automatic cleanup routines  
- Graceful shutdown handling
- WebSocket reconnection
- JSON logging for production

## Troubleshooting

### Common Issues

**1. Build Fails**
- Check Dockerfile dependencies
- Verify requirements.txt includes all packages
- Check Docker build logs

**2. Service Won't Start**
- Verify environment variables are set
- Check `/health` endpoint
- Review application logs

**3. Storage Issues**
- Ensure disk is properly mounted at `/data`
- Check disk space in health endpoint
- Verify PERSISTENT_DATA_DIR environment variable

**4. API Costs High**
- Monitor `/api/costs` endpoint
- Check OpenAI usage dashboard
- Review scan frequency and user limits

### Support

- **Health Check**: https://your-service.onrender.com/health
- **System Status**: https://your-service.onrender.com/status  
- **Render Logs**: Available in Render dashboard
- **GitHub Issues**: Report issues in repository

## Maintenance

### Regular Tasks
- **Weekly**: Check `/api/costs` and `/api/metrics`
- **Monthly**: Review feedback analytics
- **Quarterly**: Update dependencies and security patches

### Scaling Up
If you need more capacity:
1. Upgrade Render plan to Professional ($25/month)
2. Increase concurrent scan limits
3. Add Redis for session storage (multi-instance)
4. Consider CDN for static assets

**Your MemoScan v2 is now production-ready with enterprise-grade security and monitoring!** 🚀