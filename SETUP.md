# Mail Maestro Setup Guide

Complete setup instructions for deploying Mail Maestro email tracking system on Railway with PostgreSQL, Google Sheets, and Workato integration.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Railway Deployment](#railway-deployment)
3. [PostgreSQL Database Setup](#postgresql-database-setup)
4. [Google Sheets Integration](#google-sheets-integration)
5. [Workato Integration](#workato-integration)
6. [Environment Variables](#environment-variables)
7. [Verification](#verification)

---

## Prerequisites

Before starting, ensure you have:

- GitHub account (for Railway deployment)
- Google Cloud account (for Sheets API)
- Railway account (free tier available)
- Access to Workato workspace (if using Workato integration)

---

## Railway Deployment

Railway provides hosting for the Flask application and PostgreSQL database.

### Initial Setup

1. **Create Railway Account**
   - Go to [Railway](https://railway.app/)
   - Sign up using GitHub
   - Connect your GitHub account

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose the `mail_maestro` repository
   - Railway will auto-detect the Python application

3. **Configure Deployment**
   - Railway automatically detects `Procfile` and `requirements.txt`
   - The app will be deployed using the configuration in these files
   - Default command: `web: python main.py` (from Procfile)

4. **Get Deployment URL**
   - After deployment, Railway provides a URL like:
     ```
     https://your-app-name.up.railway.app
     ```
   - Save this URL for later configuration

---

## PostgreSQL Database Setup

### Add PostgreSQL to Railway

1. **Add Database Service**
   - In Railway dashboard, click "New" → "Database" → "Add PostgreSQL"
   - Railway automatically provisions a PostgreSQL instance
   - Database is automatically linked to your application

2. **Database Connection**
   - Railway automatically sets the `DATABASE_URL` environment variable
   - Format: `postgresql://user:password@host:port/database`
   - Your application reads this automatically on startup

3. **Database Initialization**
   - Tables are created automatically on first deployment
   - The app runs `init_database()` from `models/database.py`
   - Creates the following tables:
     - `email_tracking` - Email send records and open counts
     - `email_opens` - Individual email open events
     - `prompt_versions` - AI prompt version management
     - `test_merchants` - Test merchant data

### Database Schema

**email_tracking table:**
```sql
CREATE TABLE email_tracking (
    id SERIAL PRIMARY KEY,
    tracking_id VARCHAR(255) UNIQUE NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    sender_email VARCHAR(255),
    subject TEXT,
    campaign_name VARCHAR(255),
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    open_count INTEGER DEFAULT 0,
    last_opened_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sfdc_task_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'AI Outbound Email',
    version_endpoint VARCHAR(255)
);
```

**email_opens table:**
```sql
CREATE TABLE email_opens (
    id SERIAL PRIMARY KEY,
    tracking_id VARCHAR(255) NOT NULL,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_agent TEXT,
    ip_address VARCHAR(45),
    referer TEXT,
    FOREIGN KEY (tracking_id) REFERENCES email_tracking (tracking_id)
);
```

**prompt_versions table:**
```sql
CREATE TABLE prompt_versions (
    id SERIAL PRIMARY KEY,
    version_name VARCHAR(255) NOT NULL,
    prompt_type VARCHAR(50) NOT NULL,
    prompt_content TEXT NOT NULL,
    version_letter VARCHAR(10) NOT NULL,
    endpoint_path VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(prompt_type, version_letter)
);
```

**test_merchants table:**
```sql
CREATE TABLE test_merchants (
    id SERIAL PRIMARY KEY,
    merchant_name VARCHAR(255) NOT NULL,
    contact_email VARCHAR(255),
    contact_title VARCHAR(255),
    merchant_industry VARCHAR(255),
    merchant_website VARCHAR(255),
    account_description TEXT,
    account_revenue DECIMAL(15, 2),
    account_employees INTEGER,
    account_location VARCHAR(255),
    account_gmv DECIMAL(15, 2),
    last_activity VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Google Sheets Integration

Google Sheets integration allows exporting email tracking data to Google Sheets for analysis and reporting.

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click project dropdown at the top
3. Click "New Project"
4. Enter project name: "Mail Maestro Sheets" (or any name)
5. Click "Create"

### Step 2: Enable Required APIs

1. In Google Cloud project, go to **APIs & Services** → **Library**
2. Search for "Google Sheets API" and click **Enable**
3. Search for "Google Drive API" and click **Enable** (required for sheet access)

### Step 3: Create Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Fill in details:
   - **Service account name**: `mail-maestro-sheets`
   - **Service account ID**: (auto-generated)
   - **Description**: "Service account for Mail Maestro email tracking"
4. Click **Create and Continue**
5. Skip optional steps (click **Continue** then **Done**)

### Step 4: Create and Download JSON Key

1. In **Credentials** page, find your service account
2. Click on the service account email
3. Go to **Keys** tab
4. Click **Add Key** → **Create new key**
5. Select **JSON** format
6. Click **Create**
7. A JSON file will download automatically

**IMPORTANT**: Save this file securely. Never commit it to version control.

### Step 5: Share Google Sheet with Service Account

1. Open your target Google Sheet
2. Click **Share** button (top right)
3. Copy the **Service Account Email** from the downloaded JSON file
   - Format: `mail-maestro-sheets@your-project.iam.gserviceaccount.com`
4. Paste the email in the share dialog
5. Give it **Editor** permissions
6. Click **Send** (uncheck "Notify people" if desired)

### Step 6: Add Credentials to Railway

1. Open the downloaded JSON file in a text editor
2. Copy the **entire contents** of the JSON file
3. Go to Railway project dashboard
4. Go to **Variables** tab
5. Add the following environment variables:

   **Required:**
   - **Name**: `GOOGLE_SHEETS_CREDENTIALS_JSON`
   - **Value**: Paste the entire JSON content

   **Optional (with defaults):**
   - **Name**: `GOOGLE_SHEETS_ID`
   - **Value**: Your Google Sheet ID (from the URL)
   - **Name**: `GOOGLE_SHEETS_NAME`
   - **Value**: Sheet tab name (default: "Send_Logs")

### Step 7: Test Google Sheets Integration

Test the integration by calling the dump endpoint:

```bash
curl https://your-app.up.railway.app/api/workato/dump-email-tracking
```

Check your Google Sheet - it should now contain email tracking data.

### Google Sheets Troubleshooting

**Error: "Could not access Google Sheet"**
- Verify you shared the sheet with the correct service account email
- Check that the service account has Editor permissions
- Confirm the sheet ID is correct in environment variables

**Error: "GOOGLE_SHEETS_CREDENTIALS_JSON not set"**
- Verify the environment variable exists in Railway
- Ensure the JSON is valid (complete file contents)
- Redeploy the application after adding variables

**Error: "gspread library not available"**
- Verify `gspread` is in `requirements.txt`
- Redeploy the Railway application
- Check deployment logs for installation errors

### Security Best Practices

- Never commit the JSON credentials file to git
- The JSON file grants full access to shared sheets - keep it secure
- Only share specific sheets with the service account, not entire Google Drive
- Regularly rotate service account keys
- Use different service accounts for development and production

---

## Workato Integration

Workato integration enables automated workflows and schema-based data validation.

### Workato Schema Setup

The application provides schema endpoints for Workato recipe configuration:

**Available Schema Endpoints:**

1. **Email Tracking Schema**
   ```
   GET /api/workato/schema/email-tracking
   ```
   Returns the schema for email tracking data structure.

2. **Email Opens Schema**
   ```
   GET /api/workato/schema/email-opens
   ```
   Returns the schema for email open events.

### Using Schemas in Workato

1. **Create New Recipe in Workato**
   - Go to Workato dashboard
   - Create new recipe
   - Add HTTP connector

2. **Configure HTTP Request**
   - Set URL to your Railway endpoint:
     ```
     https://your-app.up.railway.app/api/workato/schema/email-tracking
     ```
   - Method: GET
   - Test the connection

3. **Use Schema for Data Mapping**
   - Workato will parse the JSON schema
   - Use the schema fields in recipe actions
   - Map data between different systems

### Workato API Endpoints

**Send Email (with Tracking)**
```
POST /api/workato/send-email
```

Request body:
```json
{
  "recipient": "user@example.com",
  "subject": "Email Subject",
  "message": "Email message body",
  "campaign_name": "Campaign Name",
  "merchant_name": "Merchant Name",
  "contact_email": "contact@merchant.com",
  "account_description": "Account details",
  "sfdc_task_id": "00T1234567890"
}
```

**Dump Email Tracking Data**
```
POST/GET /api/workato/dump-email-tracking
```

Query parameters (optional):
- `format`: Export format (csv, json, or both) - default: both
- `since_days`: Only export last N days
- `limit`: Maximum number of records
- `date`: Export from specific date (YYYY-MM-DD)

---

## Environment Variables

Complete list of environment variables for Railway deployment.

### Required Variables

```bash
# Database (automatically set by Railway)
DATABASE_URL=postgresql://user:password@host:port/database

# OpenAI API
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.2

# Email Configuration
EMAIL_USERNAME=your-email@domain.com
EMAIL_PASSWORD=your-app-password
```

### Optional Variables

```bash
# Flask
SECRET_KEY=your-secret-key-here

# Email Settings
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587

# Gmail OAuth (if using Gmail API)
GMAIL_CLIENT_ID=your-client-id
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
GMAIL_CREDENTIALS_JSON={"credentials": "json"}

# Google Sheets Integration
GOOGLE_SHEETS_CREDENTIALS_JSON={"type": "service_account", ...}
GOOGLE_SHEETS_ID=14fg3zEBhzyEILrT85imjNtOkasybpOM2FspbE-Wx9Rc
GOOGLE_SHEETS_NAME=Send_Logs

# Custom AI Prompts
NEW_EMAIL_PROMPT_TEMPLATE=Your custom prompt...
REPLY_EMAIL_PROMPT_TEMPLATE=Your custom reply prompt...
```

### Setting Environment Variables in Railway

1. Go to Railway project dashboard
2. Select your service
3. Click on **Variables** tab
4. Click **Add Variable**
5. Enter variable name and value
6. Click **Add**
7. Railway automatically redeploys with new variables

---

## Verification

### Health Check

Verify the application is running:

```bash
curl https://your-app.up.railway.app/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-02-03T12:00:00"
}
```

### Test Email Tracking

1. **Create Test Tracking Pixel**
   ```bash
   curl https://your-app.up.railway.app/track/test-tracking-id
   ```
   Should return a 1x1 transparent pixel image.

2. **Check Stats**
   ```bash
   curl https://your-app.up.railway.app/api/stats
   ```
   Should return tracking statistics.

### Test Google Sheets Export

```bash
curl -X POST https://your-app.up.railway.app/api/workato/dump-email-tracking
```

Check your Google Sheet for exported data.

### Test Workato Schema

```bash
curl https://your-app.up.railway.app/api/workato/schema/email-tracking
```

Should return JSON schema definition.

---

## Common Issues

### Database Connection Fails

**Symptoms**: Application logs show "DATABASE_URL not found"

**Solutions**:
- Verify PostgreSQL service is added in Railway
- Check that DATABASE_URL variable exists
- Restart the application service
- Check Railway service logs for errors

### Google Sheets Access Denied

**Symptoms**: "Could not access Google Sheet" error

**Solutions**:
- Verify service account email is shared on the sheet
- Check service account has Editor permissions
- Confirm GOOGLE_SHEETS_CREDENTIALS_JSON is valid JSON
- Verify Google Sheets API and Drive API are enabled

### Tracking Pixel Not Loading

**Symptoms**: Tracking pixel returns 404 or error

**Solutions**:
- Verify tracking_id exists in database
- Check application logs for errors
- Test with `/api/health` to verify app is running
- Ensure Railway deployment completed successfully

### OpenAI API Errors

**Symptoms**: Email generation fails

**Solutions**:
- Verify OPENAI_API_KEY is set correctly
- Check API key has sufficient credits
- Verify OPENAI_MODEL is a valid model name
- Check OpenAI service status

---

## Next Steps

After completing setup:

1. Read [MAINTENANCE.md](MAINTENANCE.md) for ongoing maintenance procedures
2. Review [REFACTORING.md](REFACTORING.md) for codebase architecture
3. Set up automated daily dumps (see MAINTENANCE.md)
4. Configure monitoring and alerting
5. Set up backup procedures for database

---

## Support

For issues or questions:
- Check Railway deployment logs
- Review application logs via Railway dashboard
- Verify all environment variables are set correctly
- Test individual components using verification endpoints
