# Routes Refactoring Guide

This directory should contain Flask blueprints extracted from railway_app.py.

## Recommended Route Blueprints

### ui_routes.py
Flask routes for UI pages:
- `GET /` - Home page (lines ~2646-2800)
- `GET /prompts` - Prompt management UI (lines ~2800-4339)

### tracking_routes.py
Email tracking API endpoints:
- `POST /api/track-send` (lines ~5644-5700)
- `GET /track/<tracking_id>` (lines ~5700-5800)
- `GET /api/health` (lines ~5800-5850)
- `GET /api/stats` (lines ~5850-5950)
- `POST/GET /api/workato/get-all-emails` (lines ~5950-6100)
- `POST/GET /api/workato/get-all-email-opens` (lines ~6100-6200)
- `POST /api/workato/check-email-sent` (lines ~6200-6276)

### email_routes.py
Email operation endpoints:
- `POST /api/workato/reply-to-emails` (lines ~6396-6800)
- `POST /api/workato/reply-to-emails/status` (lines ~6800-6900)
- `POST /api/workato/send-new-email` (lines ~6900-7200)
- `POST /api/workato/check-non-campaign-emails` (lines ~7200-7442)

### prompt_routes.py
Prompt management API:
- `GET /api/prompts/get` (lines ~4340-4400)
- `POST /api/prompts/update` (lines ~4400-4500)
- `POST /api/prompts/reset` (lines ~4500-4600)
- `GET /api/prompts/get-versions` (lines ~4600-4700)
- `GET /api/prompts/get-stats` (lines ~4700-4800)
- `POST /api/prompts/create-version` (lines ~4800-4900)
- `POST /api/prompts/update-version` (lines ~4900-5000)
- `POST /api/prompts/delete-version` (lines ~5000-5047)

### integration_routes.py
Salesforce/Sheets integration:
- `POST /api/workato/update-sfdc-task-id` (lines ~7946-8000)
- `POST/GET /api/workato/dump-email-tracking` (lines ~8000-8091)

### test_routes.py
Test merchant endpoints:
- `POST/GET /api/test-merchants/save` (lines ~5295-5400)
- `GET /api/test-merchants/get` (lines ~5400-5500)
- `POST /api/test-merchants/generate-sample` (lines ~5500-5643)

### debug_routes.py
Debug endpoints:
- `GET /api/debug/env` (lines ~6347-6370)
- `GET /api/debug/openai` (lines ~6370-6395)

## Blueprint Structure Example

```python
from flask import Blueprint, request, jsonify

tracking_bp = Blueprint('tracking', __name__)

@tracking_bp.route('/api/track-send', methods=['POST'])
def track_send():
    # Implementation
    pass
```

## Registering Blueprints

In railway_app.py:
```python
from routes.tracking_routes import tracking_bp
from routes.email_routes import email_bp

app.register_blueprint(tracking_bp)
app.register_blueprint(email_bp)
```

## Migration Steps

1. Create blueprint file (e.g., tracking_routes.py)
2. Move related routes from railway_app.py
3. Update imports to use services and models
4. Register blueprint in railway_app.py
5. Test endpoints
6. Remove original routes from railway_app.py
