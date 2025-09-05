# 🚂 Email Tracking Pixel - Railway PostgreSQL Deployment

Email tracking pixel service with PostgreSQL database for persistent data storage.

## Features

- 📧 **Email Tracking Pixel** - 1x1 transparent image for tracking email opens
- 🗄️ **PostgreSQL Database** - Persistent data storage on Railway
- 📊 **Tracking Statistics** - Open rates, IP addresses, user agents
- 🌐 **Global Access** - Works from any device, anywhere
- 🔒 **Secure** - No sensitive data stored

## Files Included

- `main.py` - Entry point for Railway deployment
- `railway_app_postgres.py` - Flask app with PostgreSQL integration
- `requirements.txt` - Python dependencies including psycopg2-binary
- `Procfile` - Railway deployment configuration
- `runtime.txt` - Python 3.12 specification

## Endpoints

- `GET /` - Service info
- `GET /track/<tracking_id>` - Tracking pixel (main endpoint)
- `GET /api/health` - Health check with database status
- `GET /api/stats` - Tracking statistics and recent opens

## Railway Setup

1. **Add PostgreSQL Service:**
   - Go to Railway dashboard
   - Click "New" → "Database" → "Add PostgreSQL"
   - Connect it to your app

2. **Environment Variables:**
   - Railway automatically provides `DATABASE_URL`
   - No additional setup needed

3. **Deploy:**
   - Push to GitHub
   - Railway auto-deploys from main branch

## Usage

The tracking pixel URL format:
```
https://your-app.up.railway.app/track/{tracking_id}
```

Embed in emails as:
```html
<img src="https://your-app.up.railway.app/track/unique-id" width="1" height="1" style="display:none;" />
```

## Database Schema

- `email_tracking` - Email send records
- `email_opens` - Email open events with metadata

Data persists across deployments and container restarts.
