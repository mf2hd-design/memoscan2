# Quick Deploy Commands ⚡

## 🚀 Immediate Deployment Steps

### 1. Generate Security Keys (Run These First!)
```bash
# Generate SECRET_KEY
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"

# Generate ADMIN_API_KEY  
python3 -c "import secrets; print('ADMIN_API_KEY=' + secrets.token_hex(32))"
```
**💾 SAVE THESE KEYS SECURELY!**

### 2. Deploy to Render.com
```bash
# Ensure all changes are committed
git add .
git commit -m "Production deployment ready"
git push origin main

# Then go to render.com and:
# 1. New Web Service → Connect GitHub → Select memoscan2
# 2. Add the keys from step 1 as secrets
# 3. Deploy!
```

### 3. Post-Deploy Verification
```bash
# Replace YOUR_SERVICE_NAME with actual Render service name
export SERVICE_URL="https://YOUR_SERVICE_NAME.onrender.com"

# Check health
curl $SERVICE_URL/health

# Test basic functionality  
curl -X POST $SERVICE_URL/csrf-token

# Verify admin access (use your ADMIN_API_KEY)
curl -H "Authorization: Bearer YOUR_ADMIN_API_KEY" $SERVICE_URL/api/costs
```

## 🔧 Essential Environment Variables for Render

**Set as Secrets in Render Dashboard:**
```env
OPENAI_API_KEY=your_openai_api_key_here
SECRET_KEY=generated_from_step_1
ADMIN_API_KEY=generated_from_step_1
SCRAPFLY_KEY=optional_scrapfly_key
```

**Auto-configured via render.yaml:**
- PERSISTENT_DATA_DIR=/data
- ALLOWED_ORIGINS=https://memoscan2.onrender.com
- MAX_CONCURRENT_SCANS=8
- MAX_SCANS_PER_USER=15
- FLASK_ENV=production

## 📊 Post-Deploy Monitoring

```bash
# Monitor these endpoints regularly:
curl $SERVICE_URL/health                    # System health
curl $SERVICE_URL/status                    # Server status

# Admin monitoring (replace YOUR_ADMIN_KEY):
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" $SERVICE_URL/api/costs?hours=24
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" $SERVICE_URL/api/metrics?hours=24
curl -H "Authorization: Bearer YOUR_ADMIN_KEY" $SERVICE_URL/health/dependencies
```

## 🎯 Success Criteria

✅ **Health Check**: `/health` returns `{"status": "healthy"}`  
✅ **Basic Scan**: Can scan a website successfully  
✅ **Admin Access**: Cost/metrics endpoints accessible  
✅ **Security**: CSRF protection working  
✅ **Storage**: Persistent data directory mounted  

## 🆘 Quick Troubleshooting

**Build Fails?**
```bash
# Check these files are present and correct:
ls Dockerfile requirements.txt render.yaml
```

**Service Won't Start?**
- Check Render logs for errors
- Verify all environment secrets are set
- Test health endpoint

**Admin API Not Working?**
- Verify ADMIN_API_KEY is set as secret
- Check Authorization header format: `Bearer YOUR_KEY`

**High Costs?**
- Check `/api/costs` endpoint
- Review OpenAI usage dashboard
- Consider lowering MAX_SCANS_PER_USER

## 📱 Share with Your Team

Once deployed, share this with your 20 colleagues:

**🌐 MemoScan v2 is Live!**
- **URL**: https://YOUR_SERVICE_NAME.onrender.com
- **Limit**: 15 scans per 24 hours per person
- **Features**: Real-time scanning, feedback system, mobile-friendly
- **Support**: Contact you for issues

**That's it! Your MemoScan v2 is ready for production use! 🎉**