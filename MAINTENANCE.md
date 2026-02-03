# Mail Maestro Maintenance Guide

Comprehensive guide for maintaining, monitoring, and troubleshooting the Mail Maestro email tracking system.

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Database Maintenance](#database-maintenance)
3. [Data Export and Backup](#data-export-and-backup)
4. [Scheduled Tasks](#scheduled-tasks)
5. [Monitoring and Logging](#monitoring-and-logging)
6. [Troubleshooting](#troubleshooting)
7. [Performance Optimization](#performance-optimization)
8. [Security Maintenance](#security-maintenance)

---

## Daily Operations

### Health Check Routine

Perform daily health checks to ensure system stability:

```bash
# Check application health
curl https://your-app.up.railway.app/api/health

# Check tracking statistics
curl https://your-app.up.railway.app/api/stats

# Verify database connection
curl https://your-app.up.railway.app/api/health | grep "database"
```

### Expected Health Check Response

```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-02-03T12:00:00Z",
  "total_emails": 1234,
  "total_opens": 567
}
```

### Monitoring Checklist

Daily checklist for system monitoring:

- [ ] Application is responding to health checks
- [ ] Database connection is stable
- [ ] No error spikes in Railway logs
- [ ] Email tracking pixels are loading correctly
- [ ] Google Sheets sync is working (if enabled)
- [ ] Disk space is adequate
- [ ] Response times are acceptable

---

## Database Maintenance

### Viewing Database Data

**Connect to Railway PostgreSQL:**

1. Go to Railway dashboard
2. Select PostgreSQL service
3. Click "Connect"
4. Use provided credentials to connect via:
   - Railway CLI: `railway connect postgres`
   - psql: `psql $DATABASE_URL`
   - GUI tools: TablePlus, pgAdmin, DBeaver

**Common Queries:**

```sql
-- Count total emails tracked
SELECT COUNT(*) FROM email_tracking;

-- Count total opens
SELECT COUNT(*) FROM email_opens;

-- Recent email sends (last 24 hours)
SELECT recipient_email, subject, sent_at, open_count
FROM email_tracking
WHERE sent_at > NOW() - INTERVAL '24 hours'
ORDER BY sent_at DESC;

-- Top opened emails
SELECT recipient_email, subject, open_count, campaign_name
FROM email_tracking
WHERE open_count > 0
ORDER BY open_count DESC
LIMIT 10;

-- Email open rate by campaign
SELECT
    campaign_name,
    COUNT(*) as total_sent,
    SUM(CASE WHEN open_count > 0 THEN 1 ELSE 0 END) as total_opened,
    ROUND(100.0 * SUM(CASE WHEN open_count > 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as open_rate
FROM email_tracking
WHERE campaign_name IS NOT NULL
GROUP BY campaign_name
ORDER BY open_rate DESC;

-- Recent opens with metadata
SELECT
    et.recipient_email,
    et.subject,
    eo.opened_at,
    eo.ip_address,
    eo.user_agent
FROM email_opens eo
JOIN email_tracking et ON eo.tracking_id = et.tracking_id
ORDER BY eo.opened_at DESC
LIMIT 20;
```

### Database Cleanup

**Remove old tracking data:**

```sql
-- Delete emails older than 90 days (backup first!)
DELETE FROM email_opens
WHERE tracking_id IN (
    SELECT tracking_id FROM email_tracking
    WHERE sent_at < NOW() - INTERVAL '90 days'
);

DELETE FROM email_tracking
WHERE sent_at < NOW() - INTERVAL '90 days';

-- Vacuum database to reclaim space
VACUUM ANALYZE;
```

**Archive old data before deletion:**

```bash
# Export old data before cleanup
python dump_email_tracking.py --date 2024-01-01 --format both
```

### Database Performance

**Check table sizes:**

```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Create indexes for performance:**

```sql
-- Index on tracking_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_email_tracking_tracking_id
ON email_tracking(tracking_id);

-- Index on recipient_email for search
CREATE INDEX IF NOT EXISTS idx_email_tracking_recipient
ON email_tracking(recipient_email);

-- Index on sent_at for date range queries
CREATE INDEX IF NOT EXISTS idx_email_tracking_sent_at
ON email_tracking(sent_at);

-- Index on campaign_name for analytics
CREATE INDEX IF NOT EXISTS idx_email_tracking_campaign
ON email_tracking(campaign_name);

-- Index on opened_at for email_opens
CREATE INDEX IF NOT EXISTS idx_email_opens_opened_at
ON email_opens(opened_at);
```

### Database Backup

**Manual backup via Railway:**

```bash
# Export database to SQL file
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Restore from backup
psql $DATABASE_URL < backup_20250203.sql
```

**Automated backup strategy:**

1. Use Railway's automatic backups (if available in your plan)
2. Schedule periodic exports to cloud storage
3. Keep at least 7 days of rolling backups
4. Monthly archives for long-term storage

---

## Data Export and Backup

### Email Tracking Dump Script

The `dump_email_tracking.py` script exports email tracking data to CSV and JSON formats.

### Basic Usage

**Export all data (CSV and JSON):**
```bash
python dump_email_tracking.py
```

**Export only CSV:**
```bash
python dump_email_tracking.py --format csv
```

**Export only JSON:**
```bash
python dump_email_tracking.py --format json
```

### Date Range Exports

**Last 7 days:**
```bash
python dump_email_tracking.py --since-days 7
```

**From specific date:**
```bash
python dump_email_tracking.py --date 2025-01-01
```

**Last 30 days, CSV only:**
```bash
python dump_email_tracking.py --format csv --since-days 30
```

### Limited Exports

**First 1000 records:**
```bash
python dump_email_tracking.py --limit 1000
```

**Combine filters:**
```bash
python dump_email_tracking.py --format csv --since-days 30 --limit 5000
```

### Export Output

Files are saved to the `email_dumps/` directory:
- `email_tracking_YYYY-MM-DD.csv`
- `email_tracking_YYYY-MM-DD.json`

Logs are written to `email_dump.log`

### API Endpoint Export

**Export via API (triggers dump and uploads to Google Sheets):**

```bash
# Export all data
curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking

# Export with parameters
curl "https://your-app.up.railway.app/api/workato/dump-email-tracking?format=csv&since_days=7"

# POST with JSON body
curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking \
  -H "Content-Type: application/json" \
  -d '{
    "format": "csv",
    "since_days": 7,
    "limit": 1000
  }'
```

### Google Sheets Export

When Google Sheets integration is configured, the dump endpoint automatically:

1. Exports data from PostgreSQL
2. Formats data for Sheets
3. Uploads to configured Google Sheet
4. Updates existing data or appends new rows

**Manual Google Sheets upload:**

The `/api/workato/dump-email-tracking` endpoint handles this automatically when `GOOGLE_SHEETS_CREDENTIALS_JSON` is configured.

---

## Scheduled Tasks

### Automated Daily Dumps

Since Railway doesn't support cron jobs natively, use external scheduling services.

### Option 1: External Cron Service (Recommended)

**Using cron-job.org (Free):**

1. Go to https://cron-job.org
2. Sign up for free account
3. Create new cron job:
   - **Title**: "Daily Email Tracking Dump"
   - **URL**: `https://your-app.up.railway.app/api/workato/dump-email-tracking`
   - **Schedule**: Daily at 2:00 AM (or preferred time)
   - **Method**: GET or POST
   - **Timezone**: Set your timezone

**Using EasyCron:**

1. Go to https://www.easycron.com
2. Create account (free tier available)
3. Add cron job:
   - **URL**: `https://your-app.up.railway.app/api/workato/dump-email-tracking`
   - **Cron Expression**: `0 2 * * *` (daily at 2 AM)
   - **Timezone**: Set your timezone

### Option 2: GitHub Actions

Create `.github/workflows/daily-dump.yml` in your repository:

```yaml
name: Daily Email Tracking Dump

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  dump:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Email Dump
        run: |
          curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking

      - name: Check Response
        run: |
          response=$(curl -s -o /dev/null -w "%{http_code}" \
            https://your-app.up.railway.app/api/workato/dump-email-tracking)
          if [ $response -ne 200 ]; then
            echo "Dump failed with status code: $response"
            exit 1
          fi
```

**Manual trigger via GitHub Actions:**
1. Go to repository → Actions tab
2. Select "Daily Email Tracking Dump"
3. Click "Run workflow"

### Option 3: Local Cron Job

**On Linux/Mac:**

1. Make script executable:
   ```bash
   chmod +x dump_email_tracking.py
   ```

2. Edit crontab:
   ```bash
   crontab -e
   ```

3. Add daily job (runs at 2 AM):
   ```bash
   0 2 * * * cd /path/to/mail_maestro && /usr/bin/python3 dump_email_tracking.py >> email_dump.log 2>&1
   ```

   With environment variable:
   ```bash
   0 2 * * * cd /path/to/mail_maestro && DATABASE_URL="your_db_url" /usr/bin/python3 dump_email_tracking.py >> email_dump.log 2>&1
   ```

**On Windows (Task Scheduler):**

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2:00 AM
4. Action: Start a program
   - **Program**: `python` (or full path)
   - **Arguments**: `dump_email_tracking.py`
   - **Start in**: `C:\path\to\mail_maestro`
5. Add environment variable in Task Properties

### Verifying Scheduled Tasks

**Check last run:**
```bash
# Check Google Sheet timestamp
# Check logs on cron service dashboard
# Check Railway logs for API calls
```

**Test scheduled endpoint:**
```bash
curl -v https://your-app.up.railway.app/api/workato/dump-email-tracking
```

---

## Monitoring and Logging

### Railway Logs

**View application logs:**

1. Go to Railway dashboard
2. Select your service
3. Click "Deployments"
4. View real-time logs

**Common log patterns to watch:**

```
✅ PostgreSQL database initialized
✅ Email sent successfully
❌ Database connection error
❌ OpenAI API error
⚠️  GOOGLE_SHEETS_CREDENTIALS_JSON not set
```

### Application Metrics

**Track key metrics:**

- Total emails sent per day
- Email open rate
- Average response time
- API error rate
- Database query performance

**Get metrics via API:**

```bash
curl https://your-app.up.railway.app/api/stats
```

### Log Analysis

**Filter logs for errors:**
```bash
railway logs --filter "error"
railway logs --filter "failed"
```

**Export logs:**
```bash
railway logs > logs_$(date +%Y%m%d).txt
```

### Setting Up Alerts

**Using Railway (if available):**
- Configure notification webhooks
- Set up alert rules for errors
- Monitor resource usage

**External monitoring services:**
- UptimeRobot - Free uptime monitoring
- Pingdom - Uptime and performance monitoring
- Better Uptime - Status page and alerts

**Simple uptime check:**
```bash
# Add to your cron service
*/5 * * * * curl -f https://your-app.up.railway.app/api/health || echo "App is down!"
```

---

## Troubleshooting

### Common Issues and Solutions

#### Application Won't Start

**Symptoms:**
- Railway shows "Build failed" or "Crashed"
- Cannot access any endpoints

**Solutions:**
1. Check Railway deployment logs for errors
2. Verify `Procfile` exists and is correct:
   ```
   web: python main.py
   ```
3. Check `requirements.txt` for missing or incompatible packages
4. Verify Python version in `runtime.txt` (should be `python-3.12`)
5. Check environment variables are set correctly

#### Database Connection Issues

**Symptoms:**
- "DATABASE_URL not found" error
- "Database connection error" in logs
- Application runs but data isn't persisted

**Solutions:**
1. Verify PostgreSQL service is added in Railway
2. Check DATABASE_URL exists in Variables tab
3. Test database connection:
   ```bash
   railway connect postgres
   ```
4. Check database service is running (not crashed)
5. Restart both database and application services

#### Tracking Pixel Not Working

**Symptoms:**
- 404 error when accessing pixel URL
- Image doesn't load in emails
- No open events recorded

**Solutions:**
1. Verify tracking_id exists in database:
   ```sql
   SELECT * FROM email_tracking WHERE tracking_id = 'your-tracking-id';
   ```
2. Test pixel URL directly in browser
3. Check email client isn't blocking images
4. Verify Railway deployment is live
5. Check application logs for route errors

#### Google Sheets Export Failing

**Symptoms:**
- "Could not access Google Sheet" error
- "GOOGLE_SHEETS_CREDENTIALS_JSON not set" error
- Data not appearing in sheet

**Solutions:**
1. Verify service account has access to sheet:
   - Open Google Sheet
   - Check if service account email is in share list
   - Ensure it has "Editor" permissions
2. Verify credentials JSON is valid:
   ```bash
   echo $GOOGLE_SHEETS_CREDENTIALS_JSON | python -m json.tool
   ```
3. Check Google Sheets API is enabled in Google Cloud Console
4. Verify sheet ID is correct
5. Test with curl:
   ```bash
   curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking
   ```

#### OpenAI API Errors

**Symptoms:**
- Email generation fails
- "OpenAI API error" in logs
- 500 error on send-email endpoint

**Solutions:**
1. Verify API key is set:
   ```bash
   railway variables | grep OPENAI_API_KEY
   ```
2. Check API key is valid and has credits
3. Verify model name is correct (gpt-5.2, gpt-4, etc.)
4. Check OpenAI service status
5. Review rate limits and quota

#### High Memory Usage

**Symptoms:**
- Application becomes slow
- Railway shows high memory usage
- Random crashes or restarts

**Solutions:**
1. Check for memory leaks in logs
2. Review database query efficiency
3. Implement query result pagination
4. Add database connection pooling
5. Optimize image processing (tracking pixel)
6. Consider upgrading Railway plan

#### Slow API Response Times

**Symptoms:**
- Requests timeout
- Slow page loads
- Users report delays

**Solutions:**
1. Add database indexes (see Database Performance section)
2. Implement caching for frequent queries
3. Optimize database queries
4. Check Railway resource limits
5. Review OpenAI API response times
6. Consider Redis for session/cache storage

---

## Performance Optimization

### Database Optimization

**Add indexes for common queries:**

```sql
-- Tracking ID lookups
CREATE INDEX IF NOT EXISTS idx_email_tracking_tracking_id
ON email_tracking(tracking_id);

-- Date range queries
CREATE INDEX IF NOT EXISTS idx_email_tracking_sent_at
ON email_tracking(sent_at);

-- Campaign analytics
CREATE INDEX IF NOT EXISTS idx_email_tracking_campaign
ON email_tracking(campaign_name);

-- Email search
CREATE INDEX IF NOT EXISTS idx_email_tracking_recipient
ON email_tracking(recipient_email);
```

**Query optimization:**

```sql
-- Use EXPLAIN to analyze queries
EXPLAIN ANALYZE
SELECT * FROM email_tracking
WHERE sent_at > NOW() - INTERVAL '7 days';

-- Vacuum regularly
VACUUM ANALYZE email_tracking;
VACUUM ANALYZE email_opens;
```

### Application Performance

**Enable caching:**
- Cache tracking pixel responses
- Cache frequently accessed data
- Use Redis for session storage (if needed)

**Optimize imports:**
- Remove unused imports
- Lazy load heavy libraries
- Use lightweight alternatives where possible

**Reduce OpenAI API calls:**
- Cache generated content when appropriate
- Implement rate limiting
- Use batch processing for multiple requests

### Railway Resource Management

**Monitor resource usage:**
1. Check Railway dashboard metrics
2. Review memory and CPU usage patterns
3. Identify peak usage times

**Optimize resource allocation:**
- Choose appropriate Railway plan
- Scale resources based on usage
- Consider multiple service instances for high traffic

---

## Security Maintenance

### Regular Security Tasks

**Monthly security checklist:**

- [ ] Review access logs for suspicious activity
- [ ] Update dependencies in `requirements.txt`
- [ ] Rotate API keys and credentials
- [ ] Review Railway access permissions
- [ ] Check for exposed secrets in logs
- [ ] Update Google Cloud service account keys
- [ ] Review database user permissions

### Credential Rotation

**Rotate OpenAI API key:**
1. Generate new key in OpenAI dashboard
2. Update `OPENAI_API_KEY` in Railway
3. Test application functionality
4. Delete old key in OpenAI dashboard

**Rotate Google Sheets credentials:**
1. Create new service account key
2. Update `GOOGLE_SHEETS_CREDENTIALS_JSON`
3. Test Google Sheets integration
4. Delete old key in Google Cloud Console

**Rotate database password:**
1. Railway handles this automatically
2. Manual rotation: use Railway dashboard
3. Application automatically picks up new DATABASE_URL

### Security Monitoring

**Watch for:**
- Unusual API access patterns
- Failed authentication attempts
- Unexpected data exports
- Suspicious email sends
- High error rates

**Log security events:**
```python
# Example: Log suspicious activity
logger.warning(f"Suspicious activity detected: {event_details}")
```

---

## Maintenance Schedule

### Daily Tasks
- Health check monitoring
- Review error logs
- Check email send success rate

### Weekly Tasks
- Review performance metrics
- Check disk space usage
- Verify backup completion
- Review API usage and costs

### Monthly Tasks
- Database cleanup (old data)
- Security updates
- Dependency updates
- Performance optimization review
- Credential rotation (as needed)

### Quarterly Tasks
- Full system audit
- Review and update documentation
- Load testing
- Disaster recovery testing
- Review access permissions

---

## Support Resources

**Railway Documentation:**
- https://docs.railway.app/

**PostgreSQL Documentation:**
- https://www.postgresql.org/docs/

**Google Cloud Documentation:**
- https://cloud.google.com/docs

**OpenAI API Documentation:**
- https://platform.openai.com/docs

**Application Logs:**
- Railway Dashboard → Your Service → Deployments → Logs

**Getting Help:**
- Check Railway logs first
- Review this maintenance guide
- Consult setup documentation
- Check Railway community forums
