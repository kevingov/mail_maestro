# Email Tracking Data Dump Script

This script dumps all email_tracking data from PostgreSQL to CSV/JSON files.

## Setup

1. **Install dependencies** (if not already installed):
   ```bash
   pip install psycopg2-binary
   ```

2. **Set environment variable**:
   ```bash
   export DATABASE_URL="postgresql://user:password@host:port/database"
   ```
   
   Or create a `.env` file:
   ```
   DATABASE_URL=postgresql://user:password@host:port/database
   ```

## Usage

### Basic Usage (dumps everything to CSV and JSON):
```bash
python dump_email_tracking.py
```

### Export only CSV:
```bash
python dump_email_tracking.py --format csv
```

### Export only JSON:
```bash
python dump_email_tracking.py --format json
```

### Export last 7 days:
```bash
python dump_email_tracking.py --since-days 7
```

### Export from specific date:
```bash
python dump_email_tracking.py --date 2025-11-01
```

### Limit number of records:
```bash
python dump_email_tracking.py --limit 1000
```

### Combine options:
```bash
python dump_email_tracking.py --format csv --since-days 30 --limit 5000
```

## Output

Files are saved to the `email_dumps/` directory:
- `email_tracking_YYYY-MM-DD.csv`
- `email_tracking_YYYY-MM-DD.json`

Logs are written to `email_dump.log`

## Schedule Daily Dump (Cron Job)

### On Linux/Mac:

1. **Make script executable**:
   ```bash
   chmod +x dump_email_tracking.py
   ```

2. **Edit crontab**:
   ```bash
   crontab -e
   ```

3. **Add daily job** (runs at 2 AM every day):
   ```
   0 2 * * * cd /path/to/mail_maestro && /usr/bin/python3 dump_email_tracking.py >> email_dump.log 2>&1
   ```

   Or with environment variable:
   ```
   0 2 * * * cd /path/to/mail_maestro && DATABASE_URL="your_db_url" /usr/bin/python3 dump_email_tracking.py >> email_dump.log 2>&1
   ```

### On Windows (Task Scheduler):

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Daily at 2:00 AM
4. Action: Start a program
   - Program: `python` (or full path to python.exe)
   - Arguments: `dump_email_tracking.py`
   - Start in: `C:\path\to\mail_maestro`
5. Add environment variable:
   - In Task Scheduler → Task → Properties → Environment Variables
   - Add `DATABASE_URL` with your database URL

## Options

- `--format`: Export format - `csv`, `json`, or `both` (default: both)
- `--limit`: Maximum number of records to export (default: all)
- `--date`: Only export records from this date onwards (YYYY-MM-DD)
- `--since-days`: Only export records from the last N days

## Example Output

**CSV file:**
```csv
id,tracking_id,recipient_email,sender_email,subject,campaign_name,sent_at,open_count,last_opened_at,created_at
366,cc8a06ef-71a9-4be4-8489-d77cbba99411,kevin.gov@affirm.com,jake.morgan@affirm.com,Ready to amplify...,Workato Personalized Outreach,2025-11-20T17:44:02.111539,0,,2025-11-20T17:44:02.111539
```

**JSON file:**
```json
[
  {
    "id": 366,
    "tracking_id": "cc8a06ef-71a9-4be4-8489-d77cbba99411",
    "recipient_email": "kevin.gov@affirm.com",
    "sender_email": "jake.morgan@affirm.com",
    "subject": "Ready to amplify...",
    "campaign_name": "Workato Personalized Outreach",
    "sent_at": "2025-11-20T17:44:02.111539",
    "open_count": 0,
    "last_opened_at": null,
    "created_at": "2025-11-20T17:44:02.111539"
  }
]
```

