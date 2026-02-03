# Mail Maestro - Project Structure

Complete overview of the project organization after refactoring.

## Directory Layout

```
mail_maestro/
│
├── config.py                          # Application configuration
├── main.py                            # Entry point for Railway
├── railway_app.py                     # Main Flask application
├── requirements.txt                   # Python dependencies
├── Procfile                           # Railway deployment config
├── runtime.txt                        # Python version spec
│
├── models/                            # Database layer
│   ├── __init__.py
│   └── database.py                    # PostgreSQL connection and schema
│
├── services/                          # Business logic layer
│   ├── __init__.py
│   ├── gmail_service.py               # Gmail API operations
│   ├── openai_service.py              # OpenAI integration
│   ├── salesforce_service.py          # Salesforce data parsing
│   ├── sheets_service.py              # Google Sheets export
│   ├── prompt_service.py              # Prompt version management
│   └── REFACTORING_GUIDE.md
│
├── routes/                            # API endpoints layer
│   ├── __init__.py
│   ├── ui_routes.py                   # Web UI pages
│   ├── tracking_routes.py             # Email tracking API
│   ├── email_routes.py                # Email operations API
│   ├── prompt_routes.py               # Prompt management API
│   ├── integration_routes.py          # External integrations
│   ├── test_routes.py                 # Test merchant API
│   ├── debug_routes.py                # Debug endpoints
│   └── REFACTORING_GUIDE.md
│
├── utils/                             # Helper functions
│   ├── __init__.py
│   └── email_utils.py                 # Email formatting and parsing
│
├── templates/                         # HTML templates
│   └── ...
│
├── README.md                          # Project overview
├── SETUP.md                           # Setup instructions
├── MAINTENANCE.md                     # Maintenance guide
├── REFACTORING.md                     # Refactoring roadmap
└── STRUCTURE.md                       # This file
```

## Module Responsibilities

### config.py
- Environment variable loading
- Application configuration class
- Constants (Affirm voice guidelines, email templates)
- No business logic

### models/database.py
- PostgreSQL connection management
- Database initialization and schema
- Table creation and migrations
- Database availability flag
- No business logic

### services/
Contains business logic and external service integrations.

#### gmail_service.py
- Gmail API authentication
- Email sending (plain and threaded)
- Email retrieval and parsing
- Reply detection logic
- Thread management

#### openai_service.py
- OpenAI API client
- AI response generation
- Message summarization
- Prompt template handling

#### salesforce_service.py
- Salesforce data parsing
- Activity normalization
- Case notification detection
- Duplicate email checking

#### sheets_service.py
- Google Sheets authentication
- Data export to sheets
- Automation log tracking
- Batch data writing

#### prompt_service.py
- Prompt version management
- Dynamic endpoint creation
- Prompt loading from database
- A/B testing support

### routes/
Flask blueprints for API endpoints.

#### ui_routes.py
- `GET /` - Home page
- `GET /prompts` - Prompt management UI

#### tracking_routes.py
- `POST /api/track-send` - Track email sent
- `GET /track/<id>` - Tracking pixel
- `GET /api/health` - Health check
- `GET /api/stats` - Statistics
- Email tracking queries

#### email_routes.py
- `POST /api/workato/send-new-email` - Send outreach email
- `POST /api/workato/reply-to-emails` - Generate and send replies
- `POST /api/workato/check-non-campaign-emails` - Check for replies needed

#### prompt_routes.py
- `GET /api/prompts/get` - Get prompts
- `POST /api/prompts/update` - Update prompt
- `POST /api/prompts/create-version` - Create version
- Version management endpoints

#### integration_routes.py
- `POST /api/workato/update-sfdc-task-id` - Update Salesforce ID
- `GET /api/workato/dump-email-tracking` - Export to Sheets

#### test_routes.py
- `POST /api/test-merchants/save` - Save test data
- `GET /api/test-merchants/get` - Retrieve test data
- `POST /api/test-merchants/generate-sample` - Test AI generation

#### debug_routes.py
- `GET /api/debug/env` - Environment check
- `GET /api/debug/openai` - OpenAI connection test

### utils/email_utils.py
- Email formatting (HTML templates)
- Email parsing (body extraction, quote removal)
- Email normalization (Gmail alias handling)
- Signature removal
- HTML to text conversion

## Data Flow

### Sending New Email
```
Workato Request
    ↓
email_routes.py (/api/workato/send-new-email)
    ↓
openai_service.generate_message() ← Generates email content
    ↓
gmail_service.send_email() ← Sends via Gmail API
    ↓
models/database.py ← Records in email_tracking table
    ↓
Response to Workato
```

### Tracking Email Opens
```
Email Client Loads Tracking Pixel
    ↓
tracking_routes.py (/track/<tracking_id>)
    ↓
models/database.py ← Records in email_opens table
    ↓
models/database.py ← Updates email_tracking.open_count
    ↓
Returns 1x1 transparent PNG
```

### Replying to Emails
```
Workato Request
    ↓
email_routes.py (/api/workato/reply-to-emails)
    ↓
gmail_service.get_emails_needing_replies() ← Fetches inbox
    ↓
salesforce_service.check_if_email_already_sent() ← Prevents duplicates
    ↓
openai_service.generate_ai_response() ← Generates reply
    ↓
gmail_service.send_threaded_email_reply() ← Sends reply
    ↓
models/database.py ← Records reply
    ↓
Response to Workato
```

### Exporting to Google Sheets
```
Scheduled Cron Job
    ↓
integration_routes.py (/api/workato/dump-email-tracking)
    ↓
models/database.py ← Queries email_tracking
    ↓
sheets_service.write_to_google_sheets() ← Writes to Sheet
    ↓
sheets_service.log_dump_to_automation_logs() ← Logs action
    ↓
Success Response
```

## Import Patterns

### From railway_app.py
```python
from flask import Flask
from config import Config, AFFIRM_VOICE_GUIDELINES
from models.database import get_db_connection, init_database
from services.gmail_service import authenticate_gmail, send_email
from services.openai_service import generate_ai_response
from routes.tracking_routes import tracking_bp
from routes.email_routes import email_bp
from utils.email_utils import format_pardot_email

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
init_database()

# Register blueprints
app.register_blueprint(tracking_bp)
app.register_blueprint(email_bp)
```

### From a route blueprint
```python
from flask import Blueprint, request, jsonify
from models.database import get_db_connection
from services.openai_service import generate_ai_response
from services.gmail_service import send_email
from utils.email_utils import format_pardot_email

email_bp = Blueprint('email', __name__)

@email_bp.route('/api/workato/send-new-email', methods=['POST'])
def send_new_email():
    # Implementation
    pass
```

### From a service module
```python
from openai import OpenAI
from config import Config, AFFIRM_VOICE_GUIDELINES
from models.database import get_db_connection
from utils.email_utils import strip_html_tags

def generate_ai_response(...):
    # Implementation
    pass
```

## Testing Structure

```
tests/
├── test_config.py                     # Config loading tests
├── test_database.py                   # Database tests
├── test_gmail_service.py              # Gmail service tests
├── test_openai_service.py             # OpenAI service tests
├── test_routes.py                     # Route tests
└── test_email_utils.py                # Utility tests
```

## Configuration Files

### Procfile (Railway)
```
web: python main.py
```

### runtime.txt
```
python-3.12
```

### requirements.txt
Key dependencies:
- flask
- psycopg2-binary (PostgreSQL)
- openai (OpenAI API)
- google-api-python-client (Gmail API)
- gspread (Google Sheets)

## Environment Variables

See SETUP.md for complete list. Key variables:
- `DATABASE_URL` - PostgreSQL connection
- `OPENAI_API_KEY` - OpenAI authentication
- `EMAIL_USERNAME` / `EMAIL_PASSWORD` - Gmail credentials
- `GOOGLE_SHEETS_CREDENTIALS_JSON` - Sheets service account
- `GMAIL_CREDENTIALS_JSON` - Gmail OAuth credentials

## Development Workflow

1. **Local Development**: Run `python main.py`
2. **Database**: Automatically initialized on startup
3. **Testing**: Run tests with pytest
4. **Deployment**: Push to GitHub, Railway auto-deploys
5. **Monitoring**: Check Railway logs and /api/health endpoint

## Migration Status

See REFACTORING.md for current refactoring status and next steps.

## Additional Resources

- **README.md** - Project overview and quickstart
- **SETUP.md** - Detailed setup instructions
- **MAINTENANCE.md** - Operations and troubleshooting
- **REFACTORING.md** - Refactoring roadmap
- **services/REFACTORING_GUIDE.md** - Service extraction details
- **routes/REFACTORING_GUIDE.md** - Route extraction details
