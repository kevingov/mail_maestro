# Mail Maestro Refactoring Roadmap

This document outlines the refactoring strategy for transitioning the Mail Maestro codebase from a monolithic `railway_app.py` file to a modular, maintainable architecture.

## Table of Contents

1. [Current Architecture](#current-architecture)
2. [Target Architecture](#target-architecture)
3. [Modular Structure](#modular-structure)
4. [Migration Strategy](#migration-strategy)
5. [Implementation Phases](#implementation-phases)
6. [Testing Strategy](#testing-strategy)
7. [Rollback Plan](#rollback-plan)

---

## Current Architecture

### Monolithic Structure

The current application is primarily contained in a single file:

```
mail_maestro/
├── railway_app.py          # 390KB+ - All routes, logic, and utilities
├── main.py                 # Entry point (imports railway_app)
├── dump_email_tracking.py  # Standalone dump script
├── email_tracker.py        # Legacy tracking implementation
├── 2025_hackathon.py       # Original hackathon code
└── requirements.txt        # Dependencies
```

### Current Issues

**Maintainability:**
- Single 390KB file is difficult to navigate
- Hard to locate specific functionality
- Merge conflicts in team development
- Difficult to test individual components

**Scalability:**
- Cannot independently scale components
- Difficult to add new features
- Tight coupling between modules
- Code duplication across files

**Code Quality:**
- Mixed concerns (routing, business logic, utilities)
- Duplicated configurations
- Inconsistent error handling
- No clear separation of responsibilities

---

## Target Architecture

### Modular Design

Transform the monolithic structure into a clean, modular architecture:

```
mail_maestro/
├── main.py                      # Application entry point
├── config.py                    # ✅ Centralized configuration
├── requirements.txt             # Dependencies
├── Procfile                     # Railway deployment config
├── runtime.txt                  # Python version
│
├── models/                      # ✅ Data models and database
│   ├── __init__.py             # ✅ Package initialization
│   └── database.py             # ✅ Database connection and schema
│
├── routes/                      # API routes (to be created)
│   ├── __init__.py             # Routes package initialization
│   ├── tracking.py             # Tracking pixel routes
│   ├── workato.py              # Workato integration routes
│   ├── email.py                # Email send routes
│   └── admin.py                # Admin and stats routes
│
├── services/                    # Business logic (to be created)
│   ├── __init__.py             # Services package initialization
│   ├── email_service.py        # Email sending logic
│   ├── tracking_service.py     # Tracking logic
│   ├── openai_service.py       # OpenAI integration
│   ├── sheets_service.py       # Google Sheets integration
│   └── prompt_service.py       # Prompt version management
│
├── utils/                       # ✅ Utility functions
│   ├── __init__.py             # ✅ Package initialization
│   ├── email_utils.py          # ✅ Email formatting and parsing
│   ├── validation.py           # Input validation (to be created)
│   └── helpers.py              # General helpers (to be created)
│
└── tests/                       # Unit and integration tests
    ├── __init__.py
    ├── test_routes.py
    ├── test_services.py
    └── test_utils.py
```

### Benefits of Modular Architecture

**Maintainability:**
- Clear file organization
- Easy to locate and modify code
- Better code documentation
- Simplified onboarding for new developers

**Scalability:**
- Independent module updates
- Easy to add new features
- Better performance optimization opportunities
- Microservices-ready architecture

**Testing:**
- Unit test individual modules
- Mock dependencies easily
- Better test coverage
- Faster test execution

**Code Quality:**
- Single Responsibility Principle
- Separation of Concerns
- DRY (Don't Repeat Yourself)
- Consistent patterns and conventions

---

## Modular Structure

### Already Completed

#### ✅ config.py
Centralized configuration management:

```python
# config.py
class Config:
    """Application configuration"""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")
    # ... all configuration variables
```

**Usage:**
```python
from config import Config
api_key = Config.OPENAI_API_KEY
```

#### ✅ models/database.py
Database connection and schema management:

```python
# models/database.py
def get_db_connection():
    """Get PostgreSQL connection"""
    pass

def init_database():
    """Initialize database tables"""
    pass
```

**Features:**
- PostgreSQL connection handling
- Table schema initialization
- Error handling and logging
- Global DB availability flag

#### ✅ utils/email_utils.py
Email utility functions:

```python
# utils/email_utils.py
def format_pardot_email(first_name, email_content, recipient_email, sender_name):
    """Format email using Pardot template"""
    pass

def normalize_email(email):
    """Normalize email addresses"""
    pass

def strip_html_tags(html_text):
    """Remove HTML tags"""
    pass

def remove_quoted_text(text):
    """Remove quoted reply text"""
    pass
```

### To Be Created

#### routes/ - API Routes

**routes/tracking.py:**
```python
"""
Tracking pixel routes
Handles email open tracking
"""
from flask import Blueprint, Response

tracking_bp = Blueprint('tracking', __name__)

@tracking_bp.route('/track/<tracking_id>')
def track_pixel(tracking_id):
    """Serve tracking pixel and record open event"""
    pass
```

**routes/workato.py:**
```python
"""
Workato integration routes
API endpoints for Workato recipes
"""
from flask import Blueprint, request, jsonify

workato_bp = Blueprint('workato', __name__, url_prefix='/api/workato')

@workato_bp.route('/send-email', methods=['POST'])
def send_email():
    """Send email via Workato"""
    pass

@workato_bp.route('/dump-email-tracking', methods=['GET', 'POST'])
def dump_email_tracking():
    """Export email tracking data"""
    pass

@workato_bp.route('/schema/email-tracking')
def email_tracking_schema():
    """Return email tracking schema"""
    pass
```

**routes/email.py:**
```python
"""
Email sending routes
Handle direct email sending and replies
"""
from flask import Blueprint, request, jsonify

email_bp = Blueprint('email', __name__, url_prefix='/api/email')

@email_bp.route('/send', methods=['POST'])
def send_email():
    """Send email"""
    pass

@email_bp.route('/reply', methods=['POST'])
def send_reply():
    """Send reply to email"""
    pass
```

**routes/admin.py:**
```python
"""
Admin and statistics routes
Health checks, stats, and admin functions
"""
from flask import Blueprint, jsonify

admin_bp = Blueprint('admin', __name__, url_prefix='/api')

@admin_bp.route('/health')
def health_check():
    """Application health check"""
    pass

@admin_bp.route('/stats')
def get_stats():
    """Get tracking statistics"""
    pass
```

#### services/ - Business Logic

**services/email_service.py:**
```python
"""
Email sending service
Handles email composition and delivery
"""
from models.database import get_db_connection
from utils.email_utils import format_pardot_email
import smtplib

class EmailService:
    def __init__(self):
        self.smtp_host = Config.EMAIL_HOST
        self.smtp_port = Config.EMAIL_PORT

    def send_email(self, recipient, subject, body, tracking_id=None):
        """Send email with optional tracking"""
        pass

    def send_reply(self, thread_id, body, tracking_id=None):
        """Send reply in existing thread"""
        pass

    def create_tracking_pixel(self, tracking_id, base_url):
        """Generate tracking pixel HTML"""
        pass
```

**services/tracking_service.py:**
```python
"""
Tracking service
Manages email tracking and analytics
"""
from models.database import get_db_connection
import uuid

class TrackingService:
    def create_tracking_id(self):
        """Generate unique tracking ID"""
        return str(uuid.uuid4())

    def record_email_sent(self, tracking_id, recipient, subject, campaign=None):
        """Record email send event"""
        pass

    def record_email_open(self, tracking_id, user_agent=None, ip_address=None):
        """Record email open event"""
        pass

    def get_tracking_stats(self, tracking_id):
        """Get stats for specific tracking ID"""
        pass

    def get_campaign_stats(self, campaign_name):
        """Get stats for campaign"""
        pass
```

**services/openai_service.py:**
```python
"""
OpenAI service
Handles AI-powered email generation
"""
from openai import OpenAI
from config import Config, AFFIRM_VOICE_GUIDELINES

class OpenAIService:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.OPENAI_MODEL

    def generate_email(self, merchant_data, prompt_template=None):
        """Generate personalized email"""
        pass

    def generate_reply(self, context, reply_to, prompt_template=None):
        """Generate email reply"""
        pass

    def test_prompt_version(self, version_letter, merchant_data):
        """Test specific prompt version"""
        pass
```

**services/sheets_service.py:**
```python
"""
Google Sheets service
Handles data export to Google Sheets
"""
import gspread
from google.oauth2.service_account import Credentials
from config import Config

class SheetsService:
    def __init__(self):
        self.credentials = self._load_credentials()
        self.client = gspread.authorize(self.credentials)

    def _load_credentials(self):
        """Load service account credentials"""
        pass

    def export_tracking_data(self, data, sheet_id=None, sheet_name=None):
        """Export data to Google Sheet"""
        pass

    def append_rows(self, sheet_id, sheet_name, rows):
        """Append rows to sheet"""
        pass

    def clear_sheet(self, sheet_id, sheet_name):
        """Clear sheet contents"""
        pass
```

**services/prompt_service.py:**
```python
"""
Prompt version management service
Handles A/B testing of AI prompts
"""
from models.database import get_db_connection

class PromptService:
    def create_prompt_version(self, version_name, prompt_type, content, version_letter):
        """Create new prompt version"""
        pass

    def get_prompt_version(self, version_letter, prompt_type):
        """Get specific prompt version"""
        pass

    def activate_prompt_version(self, version_letter, prompt_type):
        """Set prompt version as active"""
        pass

    def list_prompt_versions(self, prompt_type=None):
        """List all prompt versions"""
        pass

    def get_version_stats(self, version_letter):
        """Get performance stats for prompt version"""
        pass
```

#### utils/ - Additional Utilities

**utils/validation.py:**
```python
"""
Input validation utilities
"""
import re

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_tracking_id(tracking_id):
    """Validate tracking ID format"""
    return len(tracking_id) > 0 and len(tracking_id) <= 255

def sanitize_input(text):
    """Sanitize user input"""
    pass
```

**utils/helpers.py:**
```python
"""
General helper functions
"""
from datetime import datetime

def format_timestamp(dt):
    """Format datetime for display"""
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def parse_date(date_string):
    """Parse date string"""
    return datetime.strptime(date_string, '%Y-%m-%d')

def generate_response(success, data=None, error=None):
    """Generate standardized API response"""
    return {
        'success': success,
        'data': data,
        'error': error,
        'timestamp': datetime.now().isoformat()
    }
```

---

## Migration Strategy

### Approach: Incremental Refactoring

**Strategy:** Gradually extract functionality from `railway_app.py` while maintaining backwards compatibility.

### Phase-by-Phase Migration

**Benefits:**
- No service disruption
- Can test each module independently
- Easy to rollback if issues arise
- Team can learn new structure incrementally

**Principles:**
- Extract one module at a time
- Test thoroughly before moving to next module
- Maintain backwards compatibility
- Update documentation as you go

---

## Implementation Phases

### Phase 1: Foundation (COMPLETED)

**Status:** ✅ Complete

**Completed work:**
- ✅ Created `config.py` for centralized configuration
- ✅ Created `models/database.py` for database operations
- ✅ Created `utils/email_utils.py` for email utilities
- ✅ Updated imports in existing code
- ✅ Verified Railway deployment still works

### Phase 2: Services Layer (IN PROGRESS)

**Goal:** Extract business logic from `railway_app.py` into service modules

**Tasks:**

1. **Create TrackingService** (High Priority)
   ```bash
   # Create file
   touch services/tracking_service.py
   ```
   - Extract tracking pixel logic
   - Extract open event recording
   - Extract tracking stats queries
   - Update routes to use TrackingService

2. **Create EmailService** (High Priority)
   ```bash
   touch services/email_service.py
   ```
   - Extract email sending logic
   - Extract Gmail API integration
   - Extract SMTP handling
   - Update routes to use EmailService

3. **Create OpenAIService** (Medium Priority)
   ```bash
   touch services/openai_service.py
   ```
   - Extract OpenAI API calls
   - Extract prompt management
   - Extract email generation logic
   - Update routes to use OpenAIService

4. **Create SheetsService** (Medium Priority)
   ```bash
   touch services/sheets_service.py
   ```
   - Extract Google Sheets integration
   - Extract data export logic
   - Update dump endpoint to use SheetsService

5. **Create PromptService** (Low Priority)
   ```bash
   touch services/prompt_service.py
   ```
   - Extract prompt version management
   - Extract A/B testing logic
   - Update endpoints to use PromptService

**Testing for Phase 2:**
- Unit test each service independently
- Mock database connections
- Test error handling
- Verify backwards compatibility

**Rollout:**
- Deploy one service at a time
- Monitor logs for errors
- Verify functionality after each deployment
- Keep old code commented out initially

### Phase 3: Routes Layer

**Goal:** Split `railway_app.py` routes into separate blueprint modules

**Tasks:**

1. **Create tracking routes** (High Priority)
   ```bash
   touch routes/tracking.py
   ```
   - Extract `/track/<tracking_id>` route
   - Use TrackingService
   - Register blueprint in main app

2. **Create Workato routes** (High Priority)
   ```bash
   touch routes/workato.py
   ```
   - Extract `/api/workato/*` routes
   - Use appropriate services
   - Register blueprint in main app

3. **Create email routes** (Medium Priority)
   ```bash
   touch routes/email.py
   ```
   - Extract email sending routes
   - Use EmailService
   - Register blueprint in main app

4. **Create admin routes** (Low Priority)
   ```bash
   touch routes/admin.py
   ```
   - Extract `/api/health` and `/api/stats`
   - Use TrackingService for stats
   - Register blueprint in main app

**Testing for Phase 3:**
- Integration test each route
- Test route parameters and validation
- Verify response formats
- Test error responses

**Blueprint Registration:**
```python
# main.py or railway_app.py
from routes.tracking import tracking_bp
from routes.workato import workato_bp
from routes.email import email_bp
from routes.admin import admin_bp

app.register_blueprint(tracking_bp)
app.register_blueprint(workato_bp)
app.register_blueprint(email_bp)
app.register_blueprint(admin_bp)
```

### Phase 4: Additional Utilities

**Goal:** Create remaining utility modules

**Tasks:**

1. **Create validation utilities**
   ```bash
   touch utils/validation.py
   ```
   - Email validation
   - Input sanitization
   - Parameter validation

2. **Create helper utilities**
   ```bash
   touch utils/helpers.py
   ```
   - Date formatting
   - Response generation
   - Common utility functions

**Testing for Phase 4:**
- Unit test validation functions
- Test edge cases
- Test error handling

### Phase 5: Cleanup

**Goal:** Remove legacy code and finalize refactoring

**Tasks:**

1. **Remove old code from railway_app.py**
   - Verify all functionality is migrated
   - Remove unused imports
   - Keep only Flask app initialization

2. **Update documentation**
   - Update code comments
   - Update API documentation
   - Update deployment guides

3. **Archive legacy files**
   ```bash
   mkdir legacy
   mv 2025_hackathon.py legacy/
   mv email_tracker.py legacy/
   ```

4. **Final verification**
   - Full integration test suite
   - Load testing
   - Security audit
   - Performance benchmarking

### Phase 6: Testing and Documentation

**Goal:** Comprehensive testing and documentation

**Tasks:**

1. **Create test suite**
   ```bash
   mkdir tests
   touch tests/test_routes.py
   touch tests/test_services.py
   touch tests/test_utils.py
   ```

2. **Write unit tests**
   - Test each module independently
   - Mock external dependencies
   - Aim for >80% code coverage

3. **Write integration tests**
   - Test API endpoints end-to-end
   - Test database operations
   - Test external service integrations

4. **Update documentation**
   - Update README.md
   - Update SETUP.md
   - Update MAINTENANCE.md
   - Add code documentation (docstrings)

---

## Testing Strategy

### Unit Testing

**Framework:** pytest

**Setup:**
```bash
pip install pytest pytest-cov pytest-mock
```

**Example test structure:**
```python
# tests/test_services/test_tracking_service.py
import pytest
from services.tracking_service import TrackingService

def test_create_tracking_id():
    service = TrackingService()
    tracking_id = service.create_tracking_id()
    assert len(tracking_id) > 0
    assert tracking_id is not None

def test_record_email_sent(mock_db):
    service = TrackingService()
    result = service.record_email_sent(
        tracking_id='test-id',
        recipient='test@example.com',
        subject='Test'
    )
    assert result is True
```

### Integration Testing

**Test API endpoints:**
```python
# tests/test_routes/test_tracking_routes.py
import pytest
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_tracking_pixel(client):
    response = client.get('/track/test-tracking-id')
    assert response.status_code == 200
    assert response.mimetype == 'image/gif'
```

### Test Coverage

**Run tests with coverage:**
```bash
pytest --cov=. --cov-report=html
```

**Coverage goals:**
- Utils: >90% coverage
- Services: >85% coverage
- Routes: >80% coverage
- Overall: >80% coverage

### Continuous Integration

**GitHub Actions example:**
```yaml
# .github/workflows/tests.yml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: pytest --cov=. --cov-report=term
```

---

## Rollback Plan

### Before Each Phase

**Preparation:**
1. Create git branch for the phase
   ```bash
   git checkout -b refactor/phase-2-services
   ```

2. Tag current production version
   ```bash
   git tag -a v1.0-pre-phase-2 -m "Before Phase 2 refactoring"
   git push origin v1.0-pre-phase-2
   ```

3. Document current functionality
   - List all working endpoints
   - Document expected behavior
   - Save test results

### During Migration

**Safety measures:**
1. Keep old code commented out initially
2. Deploy to staging environment first
3. Monitor logs closely
4. Have team member review changes

### If Issues Arise

**Immediate rollback:**

1. **Revert to previous deployment:**
   ```bash
   git revert <commit-hash>
   git push origin main
   ```
   Railway will auto-deploy the reverted version.

2. **Rollback to tagged version:**
   ```bash
   git checkout v1.0-pre-phase-2
   git push origin main --force
   ```

3. **Railway manual rollback:**
   - Go to Railway dashboard
   - Click "Deployments"
   - Find previous successful deployment
   - Click "Redeploy"

### Post-Rollback

**Investigation:**
1. Review error logs
2. Identify root cause
3. Fix issues in branch
4. Re-test thoroughly
5. Attempt deployment again

**Communication:**
- Notify team of rollback
- Document what went wrong
- Update rollback procedures if needed

---

## Best Practices

### Code Organization

**File naming:**
- Use snake_case for Python files
- Use descriptive names
- Group related functionality

**Module structure:**
```python
"""
Module docstring
Brief description of module purpose
"""

# Standard library imports
import os
import sys

# Third-party imports
from flask import Flask
import psycopg2

# Local imports
from config import Config
from models.database import get_db_connection

# Constants
MAX_RETRY = 3

# Classes and functions
class MyService:
    pass

def helper_function():
    pass
```

### Documentation

**Docstring format:**
```python
def send_email(recipient, subject, body):
    """
    Send email to recipient.

    Args:
        recipient (str): Email address of recipient
        subject (str): Email subject line
        body (str): Email body content

    Returns:
        bool: True if email sent successfully

    Raises:
        ValueError: If recipient email is invalid
        SMTPException: If email sending fails
    """
    pass
```

### Error Handling

**Consistent error handling:**
```python
try:
    result = some_operation()
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    return {'success': False, 'error': str(e)}
```

### Logging

**Structured logging:**
```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Email sent to {recipient}")
logger.warning(f"Retry attempt {attempt} of {max_retries}")
logger.error(f"Failed to send email: {error}")
```

---

## Progress Tracking

### Current Status

**Phase 1: Foundation** ✅ COMPLETE
- [x] config.py created
- [x] models/database.py created
- [x] utils/email_utils.py created
- [x] Verified deployment

**Phase 2: Services Layer** 🚧 IN PROGRESS
- [ ] Create TrackingService
- [ ] Create EmailService
- [ ] Create OpenAIService
- [ ] Create SheetsService
- [ ] Create PromptService

**Phase 3: Routes Layer** ⏸️ NOT STARTED
- [ ] Create tracking routes
- [ ] Create workato routes
- [ ] Create email routes
- [ ] Create admin routes

**Phase 4: Additional Utilities** ⏸️ NOT STARTED
- [ ] Create validation utilities
- [ ] Create helper utilities

**Phase 5: Cleanup** ⏸️ NOT STARTED
- [ ] Remove legacy code
- [ ] Update documentation
- [ ] Archive old files

**Phase 6: Testing** ⏸️ NOT STARTED
- [ ] Create test suite
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Achieve >80% coverage

---

## Next Steps

### Immediate Actions

1. **Complete Phase 2: Services Layer**
   - Start with TrackingService (highest priority)
   - Test thoroughly before moving to next service
   - Update documentation as you go

2. **Set up testing framework**
   - Install pytest
   - Create tests/ directory structure
   - Write initial test cases

3. **Create development branch**
   ```bash
   git checkout -b refactor/services-layer
   ```

### Future Considerations

**Microservices architecture:**
- Consider splitting services into separate deployments
- Use message queues for service communication
- Implement API gateway

**Advanced features:**
- Redis caching layer
- Celery for background tasks
- GraphQL API
- Real-time tracking with WebSockets

**DevOps improvements:**
- Docker containerization
- CI/CD pipeline
- Automated testing
- Performance monitoring

---

## Conclusion

This refactoring roadmap provides a clear path from the current monolithic architecture to a clean, modular, maintainable codebase. By following the phased approach and best practices outlined here, the Mail Maestro application will be easier to maintain, test, and scale.

**Key principles:**
- Incremental migration
- Thorough testing at each phase
- Maintain backwards compatibility
- Clear documentation
- Easy rollback capability

**Success metrics:**
- Improved code organization
- Better test coverage (>80%)
- Faster feature development
- Reduced bug count
- Easier onboarding for new developers

For questions or clarifications about the refactoring process, refer to this document and the SETUP.md and MAINTENANCE.md guides.
