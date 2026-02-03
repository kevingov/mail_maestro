# Refactoring Guide

This document explains the modular structure created for Mail Maestro and provides a roadmap for migrating code from the monolithic `railway_app.py`.

## Overview

The original `railway_app.py` contains 8,278 lines with all functionality mixed together. The new modular structure separates concerns into:

- **config.py** - Configuration and constants
- **models/** - Database operations
- **services/** - Business logic (Gmail, OpenAI, Salesforce, Sheets)
- **routes/** - Flask route blueprints
- **utils/** - Helper functions

## Current Status

### Completed
- ✅ Created directory structure
- ✅ Extracted configuration to `config.py`
- ✅ Extracted database operations to `models/database.py`
- ✅ Created stub files with documentation
- ✅ Created refactoring guides for services and routes

### Remaining Work
- ⏳ Extract service modules (gmail, openai, salesforce, sheets, prompts)
- ⏳ Extract utility functions to utils/
- ⏳ Create Flask blueprints for routes
- ⏳ Update railway_app.py to use new modules
- ⏳ Add unit tests for each module

## New Project Structure

```
mail_maestro/
├── config.py                          # ✅ Configuration module
├── models/
│   ├── __init__.py                    # ✅ Package initialization
│   └── database.py                    # ✅ Database connection and schema
├── services/
│   ├── __init__.py                    # ✅ Package initialization
│   ├── REFACTORING_GUIDE.md          # ✅ Service extraction guide
│   ├── gmail_service.py               # ⏳ Gmail API operations
│   ├── openai_service.py              # ⏳ OpenAI operations
│   ├── salesforce_service.py          # ⏳ Salesforce integration
│   ├── sheets_service.py              # ⏳ Google Sheets operations
│   └── prompt_service.py              # ⏳ Prompt version management
├── routes/
│   ├── __init__.py                    # ✅ Package initialization
│   ├── REFACTORING_GUIDE.md          # ✅ Route extraction guide
│   ├── ui_routes.py                   # ⏳ UI pages
│   ├── tracking_routes.py             # ⏳ Email tracking API
│   ├── email_routes.py                # ⏳ Email operations API
│   ├── prompt_routes.py               # ⏳ Prompt management API
│   ├── integration_routes.py          # ⏳ Salesforce/Sheets API
│   ├── test_routes.py                 # ⏳ Test merchant API
│   └── debug_routes.py                # ⏳ Debug endpoints
├── utils/
│   ├── __init__.py                    # ✅ Package initialization
│   └── email_utils.py                 # ⏳ Email helper functions
├── railway_app.py                     # Main Flask app (to be refactored)
├── main.py                            # Entry point
└── email_tracker.py                   # Existing tracker module
```

## Migration Strategy

### Phase 1: Use New Config and Database Modules (Current)

Update `railway_app.py` to import from new modules:

```python
# Instead of defining config inline:
# OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

# Import from config:
from config import Config, AFFIRM_VOICE_GUIDELINES, PARDOT_EMAIL_TEMPLATE

# Instead of defining database functions:
# def get_db_connection(): ...

# Import from models:
from models.database import get_db_connection, init_database, DB_AVAILABLE
```

### Phase 2: Extract Services (Next)

Move business logic to service modules. Example for `openai_service.py`:

```python
# services/openai_service.py
from openai import OpenAI
from config import Config, AFFIRM_VOICE_GUIDELINES

client = OpenAI(api_key=Config.OPENAI_API_KEY)

def generate_ai_response(original_message, conversation_history, ...):
    """Generate AI reply to emails"""
    # Move implementation from railway_app.py ~665-1000
    pass
```

Then update railway_app.py:

```python
# Instead of defining function inline
# Change from:
# def generate_ai_response(...): ...

# To:
from services.openai_service import generate_ai_response
```

### Phase 3: Create Route Blueprints

Move Flask routes to blueprint files. Example for `tracking_routes.py`:

```python
# routes/tracking_routes.py
from flask import Blueprint, request, jsonify, Response
from models.database import get_db_connection
from services.email_service import track_email_send

tracking_bp = Blueprint('tracking', __name__)

@tracking_bp.route('/api/track-send', methods=['POST'])
def track_send():
    """Register email send event"""
    # Move implementation from railway_app.py
    pass

@tracking_bp.route('/track/<tracking_id>', methods=['GET'])
def track_open(tracking_id):
    """Tracking pixel endpoint"""
    # Move implementation from railway_app.py
    pass
```

Register blueprints in railway_app.py:

```python
from routes.tracking_routes import tracking_bp
from routes.email_routes import email_bp

app.register_blueprint(tracking_bp)
app.register_blueprint(email_bp)
```

### Phase 4: Extract Utilities

Move helper functions to utils modules:

```python
# utils/email_utils.py already has stubs
# Implement full functions from railway_app.py
```

## Detailed Migration Steps

### For Each Service Module:

1. **Create service file** (e.g., `services/gmail_service.py`)
2. **Copy functions** from railway_app.py (use line numbers in REFACTORING_GUIDE.md)
3. **Update imports** to use config, models, utils
4. **Add docstrings** and type hints
5. **Test independently** with mocked dependencies
6. **Update railway_app.py** to import from service
7. **Remove old code** from railway_app.py
8. **Test endpoints** to ensure functionality preserved

### For Each Route Blueprint:

1. **Create blueprint file** (e.g., `routes/tracking_routes.py`)
2. **Move related routes** from railway_app.py
3. **Update imports** to use services and models
4. **Register blueprint** in railway_app.py
5. **Test all endpoints** in blueprint
6. **Remove old routes** from railway_app.py

## Testing Strategy

After each module extraction:

1. **Unit tests** - Test module functions independently
2. **Integration tests** - Test module interactions
3. **API tests** - Test endpoints still work
4. **Manual testing** - Test full workflows (send email, track opens, etc.)

## Benefits of Refactoring

1. **Maintainability** - Easier to find and update code
2. **Testability** - Can test modules independently
3. **Reusability** - Services can be reused across routes
4. **Clarity** - Clear separation of concerns
5. **Scalability** - Easier to add new features
6. **Collaboration** - Multiple developers can work on different modules

## Key Considerations

### Preserve Critical Logic

The following complex logic must be preserved exactly:

1. **27-hour reply window** - Email threading logic
2. **CC recipient preservation** - Email parsing
3. **merchanthelp detection** - Conversation analysis
4. **Thread deduplication** - Prevents duplicate replies
5. **Prompt versioning** - Dynamic endpoint creation
6. **Email normalization** - Gmail alias handling

### Database Availability

Maintain the `DB_AVAILABLE` global flag pattern:
- Set by `get_db_connection()`
- Checked before database operations
- Allows graceful degradation

### Global State

Some functions rely on global state:
- Flask `app` instance
- Database availability flags
- Loaded prompt versions

Ensure these are properly managed during refactoring.

## Resources

- **services/REFACTORING_GUIDE.md** - Detailed service extraction map
- **routes/REFACTORING_GUIDE.md** - Detailed route extraction map
- **config.py** - Configuration reference
- **models/database.py** - Database operations reference

## Next Steps

1. **Start with services** - Extract one service at a time (recommend starting with simpler ones like `salesforce_service.py`)
2. **Test thoroughly** - Ensure each extraction doesn't break functionality
3. **Update imports** - Keep railway_app.py working throughout
4. **Create blueprints** - Move routes once services are stable
5. **Add tests** - Write unit tests for new modules
6. **Document** - Add docstrings and update this guide

## Questions?

See the REFACTORING_GUIDE.md files in `services/` and `routes/` directories for detailed line-by-line extraction maps.
