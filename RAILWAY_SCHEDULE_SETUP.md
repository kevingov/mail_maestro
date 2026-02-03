# Setting Up Automatic Daily Dumps on Railway

Railway doesn't support cron jobs directly in the Procfile. Here are the best ways to run the dump script automatically:

## Option 1: API Endpoint + External Cron Service (Recommended)

I've added an API endpoint that you can call from an external cron service.

### Step 1: The endpoint is already set up
The endpoint is available at:
```
POST/GET https://your-app.up.railway.app/api/workato/dump-email-tracking
```

### Step 2: Use a free cron service

**Option A: cron-job.org (Free)**
1. Go to https://cron-job.org
2. Sign up for free account
3. Create new cron job:
   - URL: `https://your-app.up.railway.app/api/workato/dump-email-tracking`
   - Schedule: Daily at 2:00 AM (or your preferred time)
   - Method: GET or POST

**Option B: EasyCron (Free tier available)**
1. Go to https://www.easycron.com
2. Create account
3. Add cron job:
   - URL: `https://your-app.up.railway.app/api/workato/dump-email-tracking`
   - Cron expression: `0 2 * * *` (daily at 2 AM)

**Option C: GitHub Actions (Free)**
Create `.github/workflows/daily-dump.yml`:
```yaml
name: Daily Email Dump

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  dump:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Dump
        run: |
          curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking
```

### Step 3: Optional Parameters

You can pass parameters to customize the dump:

**Via GET:**
```
https://your-app.up.railway.app/api/workato/dump-email-tracking?format=csv&since_days=7
```

**Via POST:**
```json
{
  "format": "csv",
  "since_days": 7,
  "limit": 1000
}
```

## Option 2: Railway Scheduled Tasks (If Available)

Railway may support scheduled tasks in the future. Check Railway dashboard for:
- Scheduled Tasks section
- Cron Jobs feature
- Automation settings

## Option 3: Manual Trigger

You can also trigger it manually:
```bash
curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking
```

Or visit in browser:
```
https://your-app.up.railway.app/api/workato/dump-email-tracking
```

## Option 4: Use Railway's Cron Service (If Available)

Some Railway plans support cron. Check:
1. Railway Dashboard → Your Project
2. Look for "Cron" or "Scheduled Tasks"
3. Add new cron job:
   - Command: `python dump_email_tracking.py`
   - Schedule: `0 2 * * *` (daily at 2 AM)

## Where are the files saved?

**Note:** Railway's filesystem is ephemeral - files are lost when the container restarts.

**Solutions:**
1. **Upload to cloud storage** (recommended):
   - Modify `dump_email_tracking.py` to upload to S3, Google Drive, or Dropbox
   - Or send via email attachment

2. **Store in database**:
   - Create a table to store dump data
   - Query when needed

3. **Send via webhook**:
   - POST the dump data to another service
   - Store in Workato, Zapier, or your own storage

## Recommended: Upload to Cloud Storage

I can modify the dump script to automatically upload to:
- Google Drive
- AWS S3
- Dropbox
- Email attachment

Would you like me to add cloud storage upload functionality?

