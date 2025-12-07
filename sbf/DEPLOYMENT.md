# Deployment Guide - Strategist's Best Friend

This guide will help you deploy the SBF application to the web using Render.com (recommended) or other platforms.

## Prerequisites

- GitHub account with your repository pushed
- Render.com account (free tier available)
- OpenAI API key with GPT-5.1 access
- Scrapfly API key (optional, for web scraping)

## Option 1: Deploy to Render.com (Recommended)

Render.com provides a simple, managed deployment with automatic builds from GitHub.

### Step 1: Prepare Your Repository

Your repository is already configured with `render.yaml`. Ensure all changes are committed and pushed:

```bash
git add .
git commit -m "Deploy configuration"
git push
```

### Step 2: Connect to Render

1. Go to [render.com](https://render.com) and sign up/login
2. Click **"New +"** → **"Blueprint"**
3. Connect your GitHub account and select your repository
4. Render will automatically detect the `render.yaml` file

### Step 3: Configure Environment Variables

In the Render dashboard, add these **Secret** environment variables:

**Required:**
- `OPENAI_API_KEY` - Your OpenAI API key (get from platform.openai.com)

**Optional but Recommended:**
- `SCRAPFLY_KEY` - Your Scrapfly API key (get from scrapfly.io)

### Step 4: Deploy

1. Click **"Apply"** to create the services
2. Render will:
   - Create a PostgreSQL database
   - Build and deploy the backend (Docker)
   - Build and deploy the frontend (Next.js)
   - Set up automatic deployments on git push

### Step 5: Access Your Application

After deployment (5-10 minutes):
- **Frontend**: `https://sbf-frontend.onrender.com`
- **Backend API**: `https://sbf-backend.onrender.com`

The frontend will automatically connect to the backend.

### Costs (Render.com)

- **Free Tier**: Both services can run on free tier (with limitations)
- **Starter Plan** (Recommended): ~$7/month per service ($14/month total)
- **Standard Plan** (Production): ~$25/month per service ($50/month total)
- **PostgreSQL**: $7/month for starter, free tier available

## Option 2: Deploy to Vercel (Frontend) + Render (Backend)

### Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) and connect your GitHub
2. Import your repository
3. Set **Root Directory** to `frontend`
4. Add environment variable:
   - `NEXT_PUBLIC_API_URL` - Your backend URL (e.g., `https://sbf-backend.onrender.com`)
5. Deploy

### Backend on Render

Follow steps 1-4 from Option 1, but only deploy the backend service.

## Option 3: Deploy with Docker Compose (Self-Hosted)

For deployment on your own VPS (DigitalOcean, AWS, etc.):

### Prerequisites

- Ubuntu/Debian server with Docker and Docker Compose installed
- Domain name pointed to your server (optional)

### Step 1: Clone Repository

```bash
git clone <your-repo-url>
cd sbf
```

### Step 2: Create Environment File

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

Add your API keys:
```
OPENAI_API_KEY=sk-...
SCRAPFLY_KEY=scp-...
DATABASE_URL=postgresql://user:pass@localhost:5432/sbf
```

### Step 3: Create Frontend Environment

```bash
cp frontend/.env.local.example frontend/.env.local
nano frontend/.env.local
```

Add:
```
NEXT_PUBLIC_API_URL=http://your-server-ip:8000
```

### Step 4: Deploy with Docker Compose

```bash
docker-compose up -d
```

Services will be available at:
- Frontend: `http://your-server-ip:3000`
- Backend: `http://your-server-ip:8000`

### Step 5: Set Up Nginx (Production)

For production with SSL:

```bash
sudo apt install nginx certbot python3-certbot-nginx
```

Create Nginx config (`/etc/nginx/sites-available/sbf`):

```nginx
server {
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Enable and get SSL:
```bash
sudo ln -s /etc/nginx/sites-available/sbf /etc/nginx/sites-enabled/
sudo certbot --nginx -d your-domain.com
sudo systemctl restart nginx
```

## Monitoring & Maintenance

### Health Checks

- Backend health: `https://your-backend-url/health`
- Check logs in Render dashboard or Docker logs

### Automatic Deployments

With Render, every push to `main` branch triggers automatic deployment.

### Scaling

On Render:
1. Go to service settings
2. Change plan (Starter → Standard → Pro)
3. Adjust worker count if needed

### Database Backups

Render automatically backs up PostgreSQL databases. For self-hosted:

```bash
docker exec sbf-postgres pg_dump -U postgres sbf > backup.sql
```

## Troubleshooting

### Build Fails

**Backend:**
- Check OpenAI API key is set correctly
- Verify Dockerfile syntax
- Check logs in Render dashboard

**Frontend:**
- Ensure `NEXT_PUBLIC_API_URL` is set
- Check package.json dependencies
- Verify build command in render.yaml

### Runtime Errors

**"OpenAI API key not found"**
- Add `OPENAI_API_KEY` in Render dashboard → Environment

**"Database connection failed"**
- Check `DATABASE_URL` is correctly injected
- Verify PostgreSQL service is running

**"Scrapfly errors"**
- Add `SCRAPFLY_KEY` or remove Scrapfly dependency (use Playwright only)

### Performance Issues

**Slow report generation:**
- Upgrade to Standard plan (more CPU/memory)
- Check GPT-5.1 API quotas
- Monitor database performance

**Timeouts:**
- Increase `GPT5_TIMEOUT` (default 180s)
- Increase `WORKFLOW_TIMEOUT` (default 900s)

## Support

For issues:
1. Check logs in Render dashboard
2. Review GitHub issues
3. Contact support

## Security Notes

- **Never commit** `.env` files
- Use Render's **Secret** variables for API keys
- Enable rate limiting (configured by default)
- Keep dependencies updated
- Monitor API usage and costs

## Cost Estimates

### Render.com (Recommended Setup)
- Backend (Standard): $25/month
- Frontend (Starter): $7/month
- PostgreSQL (Starter): $7/month
- **Total: ~$39/month**

### Self-Hosted (DigitalOcean Droplet)
- 2 vCPU, 4GB RAM: $24/month
- Domain: $10-15/year
- **Total: ~$25/month** (excluding domain)

Plus API costs:
- OpenAI GPT-5.1: Variable, ~$0.10-0.50 per report
- Scrapfly: Free tier or ~$19/month

---

Last updated: 2025-12-07
