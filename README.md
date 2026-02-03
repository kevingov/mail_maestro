# Mail Maestro - Email Tracking & AI Response System

Complete email tracking and AI-powered response system with PostgreSQL database and Salesforce integration.

## Features

- **Email Tracking** - Track email sends and opens with 1x1 transparent tracking pixels
- **AI-Powered Responses** - Generate personalized email responses using OpenAI
- **A/B Testing** - Test different prompt versions and track performance
- **Salesforce Integration** - Sync with Salesforce accounts and contacts
- **Google Sheets Export** - Automatic data dumps to Google Sheets
- **PostgreSQL Database** - Persistent data storage on Railway
- **Workato Integration** - API endpoints for workflow automation

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL database (Railway)
- OpenAI API key
- Gmail API credentials (for email sending)
- Google Sheets API credentials (for data export)

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd mail_maestro

# Install dependencies
pip install -r requirements.txt

# Set environment variables (see SETUP.md)
export DATABASE_URL="postgresql://..."
export OPENAI_API_KEY="sk-..."
export EMAIL_USERNAME="your@email.com"
export EMAIL_PASSWORD="your-password"
```

### Running Locally

```bash
python main.py
```

The app will run on `http://localhost:5000`

### Deployment

This app is designed for Railway deployment:

1. Push to GitHub
2. Connect to Railway
3. Add PostgreSQL database
4. Set environment variables
5. Deploy automatically

See **SETUP.md** for detailed deployment instructions.

## API Endpoints

### Email Tracking
- `GET /track/<tracking_id>` - Tracking pixel endpoint
- `POST /api/track-send` - Register email sent
- `GET /api/stats` - Get tracking statistics

### Email Operations
- `POST /api/workato/send-new-email` - Send new personalized email
- `POST /api/workato/send-new-email-version-{a,b,c}` - Send with specific prompt version
- `POST /api/workato/reply-to-emails` - Generate and send AI replies
- `POST /api/workato/reply-to-emails-non-campaign` - Reply to non-campaign emails

### Data Export
- `GET /api/workato/dump-email-tracking` - Export data to Google Sheets

### Prompt Management
- `GET /prompts` - Prompt management UI
- `POST /prompts/save` - Save prompt version
- `POST /prompts/activate` - Activate prompt version

## Database Schema

### `email_tracking`
Stores email send records with tracking information.

### `email_opens`
Logs email open events with metadata (IP, user agent, etc).

### `prompt_versions`
Stores different prompt versions for A/B testing.

### `test_merchants`
Test merchant data for development.

## Architecture

- **Backend**: Flask web application
- **Database**: PostgreSQL (Railway)
- **Email**: Gmail API
- **AI**: OpenAI GPT models
- **Storage**: Google Sheets for data export

## Project Structure

```
mail_maestro/
├── config.py                        # Configuration module
├── main.py                          # Entry point
├── railway_app.py                   # Main Flask application
├── models/                          # Database layer
│   ├── __init__.py
│   └── database.py                  # PostgreSQL operations
├── services/                        # Business logic layer
│   ├── __init__.py
│   └── REFACTORING_GUIDE.md         # Service extraction guide
├── routes/                          # API endpoints layer
│   ├── __init__.py
│   └── REFACTORING_GUIDE.md         # Route extraction guide
├── utils/                           # Helper functions
│   ├── __init__.py
│   └── email_utils.py               # Email utilities
├── email_tracker.py                 # Email tracking utilities
├── dump_email_tracking.py           # Data export script
├── query_database.py                # Database query utility
├── requirements.txt                 # Python dependencies
├── Procfile                         # Railway configuration
├── templates/                       # HTML templates
├── README.md                        # This file
├── SETUP.md                         # Detailed setup instructions
├── MAINTENANCE.md                   # Maintenance and troubleshooting
├── REFACTORING.md                   # Refactoring roadmap
└── STRUCTURE.md                     # Project structure details
```

**Note:** The codebase is being refactored into a modular structure. See **REFACTORING.md** for details.

## Configuration

Key environment variables:

- `DATABASE_URL` - PostgreSQL connection string
- `OPENAI_API_KEY` - OpenAI API key
- `OPENAI_MODEL` - Model to use (default: gpt-5.2)
- `EMAIL_USERNAME` - Gmail address for sending
- `EMAIL_PASSWORD` - Gmail app password
- `GOOGLE_SHEETS_CREDENTIALS_JSON` - Google Sheets service account credentials
- `GOOGLE_SHEETS_ID` - Target spreadsheet ID

See **SETUP.md** for complete configuration details.

## Support

For issues or questions:
1. Check **MAINTENANCE.md** for troubleshooting
2. Review Railway logs
3. Check database connection and credentials

## License

Internal Affirm project
