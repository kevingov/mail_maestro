# Google Sheets API Credentials Setup

Follow these steps to get Google Sheets API credentials for the Railway endpoint.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top
3. Click "New Project"
4. Enter project name: "Mail Maestro Sheets" (or any name)
5. Click "Create"

## Step 2: Enable Google Sheets API

1. In your Google Cloud project, go to **APIs & Services** → **Library**
2. Search for "Google Sheets API"
3. Click on it and click **Enable**
4. Also search for "Google Drive API" and enable it (needed to access sheets)

## Step 3: Create Service Account

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **Service Account**
3. Fill in:
   - **Service account name**: `mail-maestro-sheets`
   - **Service account ID**: (auto-generated)
   - **Description**: "Service account for Mail Maestro email tracking"
4. Click **Create and Continue**
5. Skip the optional steps (click **Continue** then **Done**)

## Step 4: Create and Download JSON Key

1. In **Credentials** page, find your service account
2. Click on the service account email
3. Go to **Keys** tab
4. Click **Add Key** → **Create new key**
5. Select **JSON** format
6. Click **Create**
7. A JSON file will download - **SAVE THIS FILE SECURELY**

## Step 5: Share Google Sheet with Service Account

1. Open your Google Sheet: `14fg3zEBhzyEILrT85imjNtOkasybpOM2FspbE-Wx9Rc`
2. Click **Share** button (top right)
3. Copy the **Service Account Email** from the JSON file you downloaded
   - It looks like: `mail-maestro-sheets@your-project.iam.gserviceaccount.com`
4. Paste the email in the share dialog
5. Give it **Editor** permissions
6. Click **Send** (you can uncheck "Notify people")

## Step 6: Add Credentials to Railway

1. Open the JSON file you downloaded
2. Copy the **entire contents** of the JSON file
3. Go to your Railway project dashboard
4. Go to **Variables** tab
5. Add a new variable:
   - **Name**: `GOOGLE_SHEETS_CREDENTIALS_JSON`
   - **Value**: Paste the entire JSON content (as a single line or multi-line string)
6. Add another variable (optional - defaults are already set):
   - **Name**: `GOOGLE_SHEETS_ID`
   - **Value**: `14fg3zEBhzyEILrT85imjNtOkasybpOM2FspbE-Wx9Rc`
7. Add another variable (optional):
   - **Name**: `GOOGLE_SHEETS_NAME`
   - **Value**: `Send_Logs`

## Step 7: Test the Integration

1. Call the endpoint:
   ```bash
   curl https://your-app.up.railway.app/api/workato/dump-email-tracking
   ```

2. Check your Google Sheet - it should have the email tracking data!

## Troubleshooting

### Error: "Could not access Google Sheet"
- Make sure you shared the sheet with the service account email
- Check that the service account email is correct

### Error: "GOOGLE_SHEETS_CREDENTIALS_JSON not set"
- Verify the environment variable is set in Railway
- Make sure the JSON is valid (copy entire file contents)

### Error: "gspread library not available"
- The library should be in requirements.txt
- Redeploy your Railway app

## Security Notes

- **Never commit the JSON credentials file to git**
- The JSON file gives full access to your Google Sheets - keep it secure
- Only share specific sheets with the service account, not your entire Google Drive

## Quick Reference

**Service Account Email Format:**
```
your-service-account-name@your-project-id.iam.gserviceaccount.com
```

**Required Environment Variables:**
- `GOOGLE_SHEETS_CREDENTIALS_JSON` - Full JSON credentials (required)
- `GOOGLE_SHEETS_ID` - Spreadsheet ID (optional, defaults to your sheet)
- `GOOGLE_SHEETS_NAME` - Sheet name (optional, defaults to "Send_Logs")

