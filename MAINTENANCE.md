# Maintenance Guide

Guide for maintaining, monitoring, and troubleshooting Mail Maestro.

## Table of Contents

1. [Database Operations](#database-operations)
2. [Data Export & Backups](#data-export--backups)
3. [Automated Scheduling](#automated-scheduling)
4. [Monitoring](#monitoring)
5. [Troubleshooting](#troubleshooting)

---

## Database Operations

### Query Database

Use the `query_database.py` utility to run SQL queries:

```bash
python query_database.py "SELECT * FROM email_tracking LIMIT 10;"
```

#### Example Queries

**Count total emails:**
```bash
python query_database.py "SELECT COUNT(*) FROM email_tracking;"
```

**Find opened emails:**
```bash
python query_database.py "SELECT * FROM email_tracking WHERE status = 'Email Open' LIMIT 10;"
```

**Recent emails:**
```bash
python query_database.py "SELECT tracking_id, recipient_email, status FROM email_tracking ORDER BY sent_at DESC LIMIT 20;"
```

**Get open rate by campaign:**
```bash
python query_database.py "SELECT campaign_name, COUNT(*) as sent, SUM(CASE WHEN open_count > 0 THEN 1 ELSE 0 END) as opened FROM email_tracking GROUP BY campaign_name;"
```

### Direct Database Access

Set the `DATABASE_URL` environment variable and connect:

```bash
export DATABASE_URL="postgresql://..."
psql $DATABASE_URL
```

---

## Data Export & Backups

### Export to Google Sheets

Automatically export tracking data to Google Sheets.

#### API Endpoint

```bash
curl https://your-app.up.railway.app/api/workato/dump-email-tracking
```

#### With Parameters

**Last 7 days only:**
```bash
curl "https://your-app.up.railway.app/api/workato/dump-email-tracking?since_days=7"
```

**Limit to 1000 records:**
```bash
curl "https://your-app.up.railway.app/api/workato/dump-email-tracking?limit=1000"
```

**Both parameters:**
```bash
curl "https://your-app.up.railway.app/api/workato/dump-email-tracking?since_days=7&limit=1000"
```

### Export to CSV/JSON

Use the `dump_email_tracking.py` script:

```bash
# Export to both CSV and JSON
python dump_email_tracking.py

# CSV only
python dump_email_tracking.py --format csv

# JSON only
python dump_email_tracking.py --format json

# Last 7 days
python dump_email_tracking.py --since-days 7

# From specific date
python dump_email_tracking.py --date 2025-11-01

# Limit records
python dump_email_tracking.py --limit 1000

# Combine options
python dump_email_tracking.py --format csv --since-days 30 --limit 5000
```

#### Output Location

Files are saved to `email_dumps/` directory:
- `email_tracking_YYYY-MM-DD.csv`
- `email_tracking_YYYY-MM-DD.json`

#### Options

- `--format`: Export format - `csv`, `json`, or `both` (default: both)
- `--limit`: Maximum records to export
- `--date`: Export from date onwards (YYYY-MM-DD)
- `--since-days`: Export last N days

---

## Automated Scheduling

Set up automatic daily data dumps.

### Option 1: cron-job.org (Recommended)

**Why cron-job.org?**
- Free and easy (2 minute setup)
- Reliable with email notifications
- No code changes needed

#### Setup Steps

1. Go to [cron-job.org](https://cron-job.org)
2. Sign up (free account)
3. Click **"Create cronjob"**
4. Configure:
   - **Title**: `Daily Email Tracking Dump`
   - **URL**: `https://your-app.up.railway.app/api/workato/dump-email-tracking`
   - **Schedule**: Daily at 2:00 AM (or preferred time)
   - **Method**: GET or POST
   - **Notification**: (Optional) Your email for failure alerts
5. Click **"Create cronjob"**
6. Test with **"Execute now"**

#### Customize Schedule

- **Daily at 2 AM**: `0 2 * * *`
- **Daily at 9 AM**: `0 9 * * *`
- **Every 6 hours**: `0 */6 * * *`
- **Twice daily**: `0 2,14 * * *`

### Option 2: GitHub Actions

Create `.github/workflows/daily-dump.yml`:

```yaml
name: Daily Email Dump

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:      # Allow manual trigger

jobs:
  dump:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Daily Dump
        run: |
          curl -X GET https://your-app.up.railway.app/api/workato/dump-email-tracking
```

Commit and push to enable.

### Option 3: Local Cron (Linux/Mac)

```bash
# Make script executable
chmod +x dump_email_tracking.py

# Edit crontab
crontab -e

# Add daily job (2 AM)
0 2 * * * cd /path/to/mail_maestro && DATABASE_URL="your_db_url" /usr/bin/python3 dump_email_tracking.py >> email_dump.log 2>&1
```

### Option 4: Windows Task Scheduler

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2:00 AM
4. Action: Start a program
   - Program: `python` or full path to python.exe
   - Arguments: `dump_email_tracking.py`
   - Start in: `C:\path\to\mail_maestro`
5. Add environment variable in task properties

---

## Monitoring

### Check Application Health

```bash
curl https://your-app.up.railway.app/api/health
```

Response includes database status and connection info.

### View Statistics

```bash
curl https://your-app.up.railway.app/api/stats
```

Returns:
- Total emails sent
- Total opens
- Open rate
- Recent opens

### Railway Logs

View application logs in Railway dashboard:
1. Go to project
2. Click on service
3. View **Logs** tab
4. Filter by error level if needed

### Database Connection Test

```bash
python query_database.py "SELECT 1;"
```

Should return `1` if connection works.

---

## Troubleshooting

### Database Issues

#### Connection Failed

**Symptoms:** `DATABASE_URL not found` or connection timeout

**Solutions:**
1. Verify `DATABASE_URL` is set in Railway variables
2. Check PostgreSQL service is running in Railway
3. Restart Railway service
4. Check Railway logs for specific errors

#### Tables Not Found

**Symptoms:** `relation "email_tracking" does not exist`

**Solutions:**
1. Database tables are auto-created on first run
2. Trigger initialization by restarting the app
3. Or manually run table creation queries from `railway_app.py:160-258`

#### Slow Queries

**Solutions:**
1. Add indexes on frequently queried columns
2. Use `LIMIT` in queries
3. Consider adding database caching
4. Archive old data periodically

### Google Sheets Issues

#### Sheet Not Updating

**Symptoms:** Data dump runs but sheet not updated

**Solutions:**
1. Check Railway logs for Google Sheets errors
2. Verify `GOOGLE_SHEETS_CREDENTIALS_JSON` is set correctly
3. Confirm sheet is shared with service account email
4. Check both Sheets API and Drive API are enabled in Google Cloud
5. Verify service account has Editor permissions on sheet

#### Authentication Errors

**Symptoms:** `Could not access Google Sheet` or auth errors

**Solutions:**
1. Re-download service account JSON key
2. Verify JSON is valid (use JSON validator)
3. Ensure no extra whitespace in environment variable
4. Check service account email format is correct

#### Permission Denied

**Solutions:**
1. Share the specific sheet with service account email
2. Give Editor (not Viewer) permissions
3. Don't share entire Google Drive, just the sheet

### Email Sending Issues

#### Emails Not Sending

**Symptoms:** Email send errors in logs

**Solutions:**
1. Use Gmail App Password (not regular password)
2. Enable 2-factor authentication on Gmail
3. Generate new app-specific password
4. Verify `EMAIL_USERNAME` is correct Gmail address
5. Check `EMAIL_PASSWORD` environment variable
6. Ensure Gmail API is enabled in Google Cloud
7. Check `token.pickle` file for Gmail authentication

#### Tracking Pixel Not Working

**Symptoms:** Emails sent but no opens recorded

**Solutions:**
1. Verify tracking pixel is in email HTML: `<img src="https://your-app.up.railway.app/track/{tracking_id}"...>`
2. Check email client is displaying images
3. Test tracking URL directly in browser
4. Review `/track/<id>` endpoint logs
5. Ensure database connection is working

### Workato Integration Issues

#### Wrong Data Returned

**Symptom:** Workato shows empty or incorrect data

**Solutions:**
1. Use `#{output.response.*}` not `#{output.body.*}`
2. Import `workato_reply_schema.json` for proper schema
3. Test endpoint manually with curl to verify response format
4. Check Workato logs for request/response details

#### 500 Server Errors

**Solutions:**
1. Check Railway logs for error details
2. Verify all required fields in request body
3. Test with minimal request payload first
4. Check database connection
5. Verify OpenAI API key is valid

### Performance Issues

#### Slow Response Times

**Solutions:**
1. Check Railway service resources
2. Monitor database query performance
3. Add database indexes
4. Enable connection pooling
5. Consider caching frequently accessed data

#### Memory Issues

**Solutions:**
1. Check Railway logs for memory errors
2. Reduce batch sizes in data operations
3. Paginate large queries
4. Clear old data periodically

### Data Issues

#### Duplicate Tracking IDs

**Solutions:**
1. Tracking IDs should be unique (UUID)
2. Check database constraints
3. Review email sending logic for duplicates

#### Missing Opens Data

**Solutions:**
1. Verify email client displays images
2. Check tracking pixel URL is correct
3. Test `/track/<id>` endpoint directly
4. Review email HTML structure

---

## Maintenance Tasks

### Weekly

- Review Railway logs for errors
- Check Google Sheets export is working
- Verify open rate statistics are reasonable

### Monthly

- Review database size and performance
- Check for failed scheduled jobs
- Update dependencies if needed
- Archive old data if database is large

### As Needed

- Rotate API keys if compromised
- Update prompt versions for A/B testing
- Clean up test data
- Optimize slow queries

---

## Useful Commands

**Check disk usage (Railway ephemeral):**
```bash
du -sh email_dumps/
```

**Count records by status:**
```bash
python query_database.py "SELECT status, COUNT(*) FROM email_tracking GROUP BY status;"
```

**Find emails never opened:**
```bash
python query_database.py "SELECT * FROM email_tracking WHERE open_count = 0 AND sent_at < NOW() - INTERVAL '7 days' LIMIT 50;"
```

**View recent errors (from logs):**
Check Railway dashboard → Logs → Filter by "ERROR"

---

## Support Contacts

For Railway issues: [railway.app/help](https://railway.app/help)
For Google Cloud issues: [cloud.google.com/support](https://cloud.google.com/support)

**Internal Support:** Review code comments and Railway logs for detailed debugging information.
