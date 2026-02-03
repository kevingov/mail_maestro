# Setup Instructions

Complete setup guide for deploying Mail Maestro on Railway with all integrations.

## Table of Contents

1. [Railway Deployment](#railway-deployment)
2. [PostgreSQL Database](#postgresql-database)
3. [Google Sheets Integration](#google-sheets-integration)
4. [Workato Integration](#workato-integration)
5. [Environment Variables](#environment-variables)

---

## Railway Deployment

### Initial Setup

1. **Create Railway Account**
   - Go to [railway.app](https://railway.app)
   - Sign up with GitHub

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your `mail_maestro` repository

3. **Add PostgreSQL Database**
   - In project dashboard, click "New"
   - Select "Database" → "Add PostgreSQL"
   - Railway automatically provides `DATABASE_URL` environment variable

4. **Configure Deployment**
   - Railway auto-detects Python and uses `Procfile`
   - Deployment happens automatically on git push

5. **Set Environment Variables** (see section below)

### Files for Railway

The following files configure Railway deployment:

- **Procfile**: `web: python main.py`
- **runtime.txt**: `python-3.12`
- **requirements.txt**: Python dependencies

---

## PostgreSQL Database

### Automatic Setup

The database schema is created automatically on first run via `init_database()` in `railway_app.py`.

### Tables Created

1. **email_tracking** - Email send records
2. **email_opens** - Open event logs
3. **prompt_versions** - A/B testing prompts
4. **test_merchants** - Test data

### Manual Database Access

Use the `query_database.py` utility:

```bash
python query_database.py "SELECT * FROM email_tracking LIMIT 10;"
```

See **MAINTENANCE.md** for more database operations.

---

## Google Sheets Integration

Set up Google Sheets API to automatically export tracking data.

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click "New Project"
3. Name it "Mail Maestro Sheets"
4. Click "Create"

### Step 2: Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search and enable:
   - **Google Sheets API**
   - **Google Drive API**

### Step 3: Create Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Fill in:
   - Name: `mail-maestro-sheets`
   - Description: "Service account for Mail Maestro email tracking"
4. Click **Create and Continue**
5. Skip optional steps, click **Done**

### Step 4: Create JSON Key

1. In **Credentials** page, click on your service account
2. Go to **Keys** tab
3. Click **Add Key** → **Create new key**
4. Select **JSON** format
5. Click **Create**
6. **Save the downloaded JSON file securely**

### Step 5: Share Google Sheet

1. Open your target Google Sheet
2. Click **Share** (top right)
3. Copy the service account email from JSON file:
   - Format: `mail-maestro-sheets@your-project.iam.gserviceaccount.com`
4. Paste email in share dialog
5. Give **Editor** permissions
6. Click **Send** (uncheck "Notify people")

### Step 6: Add to Railway

1. Copy entire contents of JSON credentials file
2. In Railway dashboard → **Variables**
3. Add variables:
   - `GOOGLE_SHEETS_CREDENTIALS_JSON` = (paste JSON content)
   - `GOOGLE_SHEETS_ID` = Your spreadsheet ID
   - `GOOGLE_SHEETS_NAME` = Sheet name (default: "Send_Logs")

### Test the Integration

```bash
curl https://your-app.up.railway.app/api/workato/dump-email-tracking
```

Check your Google Sheet for updated data.

### Security Notes

- Never commit JSON credentials to git
- Only share specific sheets with service account
- Keep credentials secure

---

## Workato Integration

Configure Workato to use Mail Maestro API endpoints.

### Available Endpoints

#### Send New Email
```
POST https://your-app.up.railway.app/api/workato/send-new-email
```

Request body:
```json
{
  "contact_name": "John Doe",
  "contact_email": "john@example.com",
  "contact_title": "CEO",
  "account_name": "Example Corp",
  "account_industry": "Technology",
  "account_website": "example.com",
  "account_description": "Company description",
  "activities": [...]
}
```

#### Reply to Emails
```
POST https://your-app.up.railway.app/api/workato/reply-to-emails
```

Request body:
```json
{
  "email": "contact@example.com"
}
```

### Using JSON Schema in Workato

The file `workato_reply_schema.json` defines the response structure.

#### Important: Use `response` field, not `body`

Workato wraps API responses:
```json
{
  "status_code": 200,
  "body": "...",        // JSON string (don't use)
  "response": {         // Parsed JSON object (use this!)
    "status": "success",
    "emails": [...]
  }
}
```

#### Correct Pill Syntax

✅ **Correct:**
```
#{output.response.status}
#{output.response.emails[0].reply_tracking_id}
#{output.response.emails[0].thread_id}
```

❌ **Wrong:**
```
#{output.body.emails[0].reply_tracking_id}
```

#### Response Structure

```
{
  status: string ("success" or "error")
  message: string
  timestamp: string (ISO 8601)
  accounts_processed: integer
  emails_processed: integer
  replies_sent: integer
  emails: array of {
    thread_id: string
    sender: string
    contact_name: string
    subject: string
    ai_response: string
    reply_tracking_id: string
    reply_tracking_url: string
    account_id: string
    salesforce_id: string
  }
}
```

### Version Tracking (A/B Testing)

The system now tracks which prompt version was used for each email.

- **Default endpoint**: `/api/workato/send-new-email`
  - Automatically tracked in database
- **Versioned endpoints**: `/api/workato/send-new-email-version-{a,b,c}`
  - Use for A/B testing different prompts

#### No Workato Changes Required

The default endpoint works as before. To use versioned endpoints:

1. Create new version in Prompts UI (`/prompts`)
2. Use endpoint: `/api/workato/send-new-email-version-a`

View statistics in the Prompts UI to compare performance.

---

## Environment Variables

Complete list of required environment variables for Railway:

### Required

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/db

# OpenAI
OPENAI_API_KEY=sk-...

# Email (Gmail)
EMAIL_USERNAME=your@gmail.com
EMAIL_PASSWORD=your-app-password
```

### Optional

```bash
# OpenAI Model (default: gpt-5.2)
OPENAI_MODEL=gpt-5.2

# Email Configuration
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587

# Google Sheets
GOOGLE_SHEETS_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_SHEETS_ID=your-spreadsheet-id
GOOGLE_SHEETS_NAME=Send_Logs

# Flask
SECRET_KEY=your-secret-key-here
```

### Setting Variables in Railway

1. Go to project dashboard
2. Click **Variables** tab
3. Add each variable with name and value
4. Railway redeploys automatically

---

## Troubleshooting

### Database Connection Issues
- Verify `DATABASE_URL` is set in Railway
- Check PostgreSQL service is running
- Review Railway logs for connection errors

### Google Sheets Errors
- Confirm service account email is shared with sheet
- Verify `GOOGLE_SHEETS_CREDENTIALS_JSON` is valid JSON
- Check that both Sheets API and Drive API are enabled

### Email Sending Fails
- Use Gmail app password, not regular password
- Enable "Less secure app access" if needed
- Verify `EMAIL_USERNAME` and `EMAIL_PASSWORD` are correct

### Workato Integration Issues
- Use `output.response.*` not `output.body.*`
- Import `workato_reply_schema.json` for response structure
- Test endpoint manually with curl first

See **MAINTENANCE.md** for more troubleshooting tips.
